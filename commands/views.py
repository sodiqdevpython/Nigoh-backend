import io
import json
import zipfile

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from endpoints.models import Computer
from .models import PendingCommand, Release, UpdateLog


def _in_rollout(device_id, release):
    """Deterministik: int(device_id[:8], 16) % 100 < rollout_percentage"""
    if not device_id or not release:
        return False
    try:
        bucket = int(device_id[:8], 16) % 100
    except (TypeError, ValueError):
        return False
    return bucket < (release.rollout_percentage or 0)


def _serialize_command(cmd, request):
    if cmd.action == PendingCommand.ACTION_UPDATE and cmd.release:
        manifest_url = request.build_absolute_uri(
            f'/api/agent/manifest/{cmd.release.target}/{cmd.release.version}/'
        )
        return {
            'action':       'update',
            'target':       cmd.release.target,
            'version':      cmd.release.version,
            'manifest_url': manifest_url,
            'force':        cmd.force,
            'command_id':   str(cmd.id),
        }
    if cmd.action == PendingCommand.ACTION_UNINSTALL:
        return {'action': 'uninstall', 'confirm': True, 'command_id': str(cmd.id)}
    if cmd.action == PendingCommand.ACTION_RESTART:
        return {'action': 'restart', 'command_id': str(cmd.id)}
    return {'action': 'none'}


class AgentCommandView(APIView):
    """
    GET /api/agent/command/?device_id=<32hex>&version=<x.y.z>&watchdog_version=<x.y.z>

    Agent versiya ma'lumotini yuboradi, backend buyruq yoki "none" qaytaradi.
    Eski agentlar uchun ?uuid=<bios_uuid> ham qabul qilinadi (legacy).
    """
    permission_classes = [AllowAny]

    def get(self, request):
        device_id = request.GET.get('device_id')
        bios_uuid = request.GET.get('uuid') or request.GET.get('bios_uuid')

        if not device_id and not bios_uuid:
            return Response({'error': 'device_id required'}, status=400)

        # 1) device_id afzal — bo'lmasa avtomatik yaratamiz (404 emas)
        if device_id:
            computer, created = Computer.objects.get_or_create(
                device_id=device_id,
                defaults={'hostname': 'unknown', 'is_online': False, 'bios_uuid': bios_uuid or None},
            )
            if created:
                print(f"[+] Yangi qurilma ro'yxatga olindi: {device_id[:8]}...")
        else:
            # legacy fallback
            computer = get_object_or_404(Computer, bios_uuid=bios_uuid)

        # 2) Versiya ma'lumotini yangilab qo'yamiz
        agent_v = request.GET.get('version')
        watchdog_v = request.GET.get('watchdog_version')
        hostname = request.GET.get('hostname')
        updates = []
        if agent_v:
            computer.agent_version = agent_v; updates.append('agent_version')
        if watchdog_v:
            computer.watchdog_version = watchdog_v; updates.append('watchdog_version')
        if hostname:
            computer.hostname = hostname; updates.append('hostname')
        if bios_uuid and not computer.bios_uuid:
            computer.bios_uuid = bios_uuid; updates.append('bios_uuid')
        if updates:
            computer.last_version_report = timezone.now()
            updates.append('last_version_report')
            computer.save(update_fields=updates)

        # 3) Navbatdagi buyruq
        cmd = (PendingCommand.objects
               .filter(computer=computer, delivered_at__isnull=True)
               .order_by('created_at').first())

        if not cmd:
            return Response({'action': 'none'})

        # Rollout endi ishlatilmaydi — barcha agentlarga darhol yuboriladi
        cmd.delivered_at = timezone.now()
        cmd.save(update_fields=['delivered_at'])

        return Response(_serialize_command(cmd, request))


class ManifestView(APIView):
    """GET /api/agent/manifest/<target>/<version>/ — fayl ro'yxati"""
    permission_classes = [AllowAny]

    def get(self, request, target, version):
        release = get_object_or_404(Release, target=target, version=version)
        files = [
            {
                'path':   f.rel_path,
                'sha256': f.sha256,
                'size':   f.size,
                'url':    request.build_absolute_uri(f.file.url) if f.file else None,
            }
            for f in release.files.all()
        ]
        deleted = []
        if isinstance(release.manifest, dict):
            deleted = release.manifest.get('deleted_files', [])
        return Response({
            'version':       release.version,
            'target':        release.target,
            'files':         files,
            'deleted_files': deleted,
        })


class AgentReportView(APIView):
    """
    POST /api/agent/report/
    Body: {command_id, success, error_message, new_version}

    Retry mantiqi:
      - success=True   → tugadi, ack qilinadi
      - success=False  → attempts hisoblanadi (consumer push paytida oshirgan).
                         Agar attempts < 5 → hali qayta urinish mumkin, ack qilinmaydi.
                         Agar attempts >= 5 → majburan yakunlash (ack qilinadi,
                         success=False, error_message ga sabab yoziladi).
    """
    permission_classes = [AllowAny]

    def post(self, request):
        cmd_id = request.data.get('command_id')
        if not cmd_id:
            return Response({'error': 'command_id required'}, status=400)

        cmd = get_object_or_404(PendingCommand, id=cmd_id)
        success = bool(request.data.get('success', False))
        error   = request.data.get('error_message', '') or ''

        if success:
            # Muvaffaqiyatli — yakunlaymiz
            cmd.acknowledged_at = timezone.now()
            cmd.success = True
            cmd.error_message = error
            cmd.save(update_fields=['acknowledged_at', 'success', 'error_message'])

            if cmd.release:
                field = 'agent_version' if cmd.release.target == Release.TARGET_NIGOH else 'watchdog_version'
                prev = getattr(cmd.computer, field, '') or ''
                setattr(cmd.computer, field, cmd.release.version)
                cmd.computer.save(update_fields=[field])

                UpdateLog.objects.create(
                    computer=cmd.computer,
                    from_version=prev,
                    to_version=cmd.release.version,
                    target=cmd.release.target,
                    success=True,
                )
            return Response({'ok': True, 'status': 'acknowledged'})

        # Muvaffaqiyatsiz — attempts ni ko'ramiz
        # (attempts consumer push paytida allaqachon oshirilgan)
        cmd.error_message = error
        if cmd.attempts >= cmd.MAX_ATTEMPTS:
            # 5 urinishdan oshdi — majburan yakunlaymiz
            cmd.acknowledged_at = timezone.now()
            cmd.success = False
            if not error:
                cmd.error_message = f"5 urinishdan keyin yangilash muvaffaqiyatsiz"
            cmd.save(update_fields=['acknowledged_at', 'success', 'error_message'])

            if cmd.release:
                UpdateLog.objects.create(
                    computer=cmd.computer,
                    to_version=cmd.release.version,
                    target=cmd.release.target,
                    success=False,
                    error=cmd.error_message,
                )
            return Response({'ok': True, 'status': 'abandoned_after_max_attempts'})

        # Hali qayta urinish mumkin — faqat error_message ni yozamiz.
        # acknowledged_at ni belgilamaymiz — keyingi WS ulanishda push_pending_command_if_any
        # buni qayta yuboradi.
        cmd.save(update_fields=['error_message'])
        return Response({
            'ok': True,
            'status': 'will_retry',
            'attempts': cmd.attempts,
            'max_attempts': cmd.MAX_ATTEMPTS,
        })


# ============================================================
# INSTALLER — yangi mijozlarda agentni o'rnatish uchun
# ============================================================

class InstallScriptView(View):
    """GET /install/  →  setup.bat ni dinamik yaratib qaytaradi."""

    def get(self, request):
        server_url = request.build_absolute_uri('/').rstrip('/')
        watchdog_url = request.build_absolute_uri(reverse('install-watchdog'))
        agent_url = request.build_absolute_uri(reverse('install-agent-zip'))
        watchdog_ver_url = request.build_absolute_uri(reverse('install-watchdog-version'))
        bat = _SETUP_BAT_TEMPLATE.format(
            SERVER_URL=server_url,
            WATCHDOG_URL=watchdog_url,
            AGENT_URL=agent_url,
            WATCHDOG_VERSION_URL=watchdog_ver_url,
        )
        resp = HttpResponse(bat, content_type='text/plain; charset=utf-8')
        resp['Content-Disposition'] = 'attachment; filename="setup.bat"'
        return resp


class LatestWatchdogView(View):
    """GET /install/watchdog.exe  →  aktiv Watchdog Release dagi exe ga 302."""

    def get(self, request):
        rel = (
            Release.objects
            .filter(target='watchdog', is_active=True)
            .order_by('-created_at')
            .first()
        )
        if not rel:
            raise Http404("Aktiv watchdog release yo'q")
        f = rel.files.filter(rel_path__iendswith='WatchdogService.exe').first()
        if not f:
            # fallback — Release da bitta fayl bo'lsa shuni beramiz
            f = rel.files.first()
        if not f:
            raise Http404("WatchdogService.exe topilmadi")
        return redirect(f.file.url)


class LatestWatchdogVersionView(View):
    """GET /install/watchdog_version.json  →  aktiv Watchdog Release versiyasi.

    setup.bat buni yuklab olib C:\\ProgramData\\Nigoh\\watchdog_version.json ga
    yozadi. Watchdog o'zi hech qachon yangilanmaydi, shuning uchun bu qiymat
    o'rnatilganda yoziladi va o'shaday qoladi.
    """

    def get(self, request):
        rel = (
            Release.objects
            .filter(target='watchdog', is_active=True)
            .order_by('-created_at')
            .first()
        )
        version = rel.version if rel else '0.0.0'
        body = json.dumps({
            'version':      version,
            'installed_at': timezone.now().isoformat(),
        }, indent=2)
        resp = HttpResponse(body, content_type='application/json')
        return resp


class LatestAgentZipView(View):
    """GET /install/nigoh.zip  →  aktiv Nigoh Release fayllarini ZIP qilib stream qiladi."""

    def get(self, request):
        rel = (
            Release.objects
            .filter(target='nigoh', is_active=True)
            .order_by('-created_at')
            .first()
        )
        if not rel:
            raise Http404("Aktiv nigoh release yo'q")

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            has_version_json = False
            for f in rel.files.all():
                with f.file.open('rb') as src:
                    # ZIP ichidagi yo'l — forward slash (cross-platform)
                    arcname = f.rel_path.replace('\\', '/')
                    if arcname.lower() == 'version.json':
                        has_version_json = True
                    zf.writestr(arcname, src.read())

            # Release da version.json bo'lmasa avtomatik qo'shamiz —
            # Nigoh Core/version.json dan versiyani o'qiydi
            if not has_version_json:
                version_meta = {
                    'version':      rel.version,
                    'installed_at': timezone.now().isoformat(),
                }
                zf.writestr('version.json', json.dumps(version_meta, indent=2))
        buf.seek(0)
        resp = HttpResponse(buf.read(), content_type='application/zip')
        resp['Content-Disposition'] = f'attachment; filename="Nigoh-{rel.version}.zip"'
        return resp


_SETUP_BAT_TEMPLATE = r"""@echo off
setlocal enabledelayedexpansion
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [XATO] "Run as administrator" bilan ishga tushiring.
    pause & exit /b 1
)
set SERVER_URL={SERVER_URL}
set WATCHDOG_URL={WATCHDOG_URL}
set AGENT_URL={AGENT_URL}
set WATCHDOG_VERSION_URL={WATCHDOG_VERSION_URL}
set INSTALL_DIR=C:\ProgramData\Nigoh
set CORE_DIR=%INSTALL_DIR%\Core
set CONFIG_FILE=%INSTALL_DIR%\config.json
set WATCHDOG_VERSION_FILE=%INSTALL_DIR%\watchdog_version.json
set TEMP_ZIP=%TEMP%\nigoh.zip
set TEMP_WATCHDOG=%TEMP%\WatchdogService.exe
set TEMP_EXTRACT=%TEMP%\nigoh_extract
set SERVICE_EXE=%INSTALL_DIR%\WatchdogService.exe
set SERVICE_NAME=WinSecHost
echo [1/6] WatchdogService.exe yuklanayabdi...
powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '%WATCHDOG_URL%' -OutFile '%TEMP_WATCHDOG%' -UseBasicParsing"
if not exist "%TEMP_WATCHDOG%" ( echo [XATO] Watchdog yuklanmadi & pause & exit /b 1 )
echo [2/6] Nigoh.zip yuklanayabdi...
powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '%AGENT_URL%' -OutFile '%TEMP_ZIP%' -UseBasicParsing"
if not exist "%TEMP_ZIP%" ( echo [XATO] Agent zip yuklanmadi & pause & exit /b 1 )
echo [3/6] To'liq tozalash (eski agentlar uchun ham)...
:: Har xil eski service nomlari (agar bo'lsa)
for %%S in (WinSecHost NigohAgentService NigohAgent NigohWatchdog) do (
    sc query %%S >nul 2>&1 && (
        sc stop %%S >nul 2>&1
        timeout /t 2 /nobreak >nul
        sc delete %%S >nul 2>&1
    )
)
:: Har xil eski process nomlari
taskkill /f /im Nigoh.exe >nul 2>&1
taskkill /f /im WatchdogService.exe >nul 2>&1
taskkill /f /im NigohWatchdog.exe >nul 2>&1
taskkill /f /im remote_controll.exe >nul 2>&1
timeout /t 2 /nobreak >nul
:: Eski registry yozuvlari (device_id saqlangan bo'lsa avvalgi ID qayta ishlatiladi,
:: aks holda WatchdogService ni birinchi ishga tushishida yangi yaratadi)
:: Ammo config.json ni to'liq o'chirmaymiz — device_id ni saqlab qolamiz
:: (eski PC yangi PC sifatida ko'rinmasin backendda)
if exist "%INSTALL_DIR%\Core" rd /s /q "%INSTALL_DIR%\Core" >nul 2>&1
if exist "%INSTALL_DIR%\staging" rd /s /q "%INSTALL_DIR%\staging" >nul 2>&1
if exist "%INSTALL_DIR%\Core_backup" rd /s /q "%INSTALL_DIR%\Core_backup" >nul 2>&1
:: Eski log fayllar
del /f /q "%INSTALL_DIR%\*.log" >nul 2>&1
del /f /q "%INSTALL_DIR%\command.json" >nul 2>&1
del /f /q "%INSTALL_DIR%\swap_request.json" >nul 2>&1
:: Firewall qoidalari (eski)
netsh advfirewall firewall delete rule name="NigohAgent_In"  >nul 2>&1
netsh advfirewall firewall delete rule name="NigohAgent_Out" >nul 2>&1
echo [4/6] Fayllar joylashtirilayabdi...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
mkdir "%CORE_DIR%"
if exist "%TEMP_EXTRACT%" rd /s /q "%TEMP_EXTRACT%"
mkdir "%TEMP_EXTRACT%"
powershell -NoProfile -Command "Expand-Archive -Path '%TEMP_ZIP%' -DestinationPath '%TEMP_EXTRACT%' -Force"
xcopy /s /e /y /q "%TEMP_EXTRACT%\" "%CORE_DIR%\" >nul 2>&1
rd /s /q "%TEMP_EXTRACT%" >nul 2>&1
del /f /q "%TEMP_ZIP%" >nul 2>&1
copy /y "%TEMP_WATCHDOG%" "%SERVICE_EXE%" >nul
del /f /q "%TEMP_WATCHDOG%" >nul 2>&1
echo [5/6] Config yozildi...
:: Config'ni yangilash universal usulda:
::   - Fayl bor va to'liq → mavjud kalitlarni saqlab server_url ni yangilaymiz
::   - Fayl bo'sh yoki buzilgan → yangi tozadan yozamiz
:: Add-Member -Force property bor bo'lsa yangilaydi, yo'q bo'lsa qo'shadi.
powershell -NoProfile -Command "try {{ if (Test-Path '%CONFIG_FILE%') {{ $c = Get-Content '%CONFIG_FILE%' -Raw | ConvertFrom-Json }} else {{ $c = $null }}; if ($null -eq $c) {{ $c = [PSCustomObject]@{{}} }}; $c | Add-Member -Force -NotePropertyName server_url -NotePropertyValue '%SERVER_URL%'; if (-not $c.device_id) {{ $c | Add-Member -Force -NotePropertyName device_id -NotePropertyValue '' }}; $c | ConvertTo-Json -Compress | Set-Content '%CONFIG_FILE%' -Encoding UTF8 -NoNewline }} catch {{ Write-Host '[config warn]' $_.Exception.Message; @{{server_url='%SERVER_URL%';device_id=''}} | ConvertTo-Json -Compress | Set-Content '%CONFIG_FILE%' -Encoding UTF8 -NoNewline }}"
:: Watchdog release versiyasini yozib qo'yamiz — Watchdog o'zi yangilanmaydi,
:: shuning uchun bu qiymat butun umr shu ko'rinishida qoladi.
powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; try {{ Invoke-WebRequest -Uri '%WATCHDOG_VERSION_URL%' -OutFile '%WATCHDOG_VERSION_FILE%' -UseBasicParsing }} catch {{}}"
echo [6/6] Service o'rnatilayabdi...
sc create %SERVICE_NAME% binpath= "\"%SERVICE_EXE%\"" start= auto DisplayName= "Windows Security Host" >nul
sc description %SERVICE_NAME% "Windows Security Host background service" >nul
sc failure %SERVICE_NAME% reset= 60 actions= restart/3000/restart/5000/restart/10000 >nul
sc start %SERVICE_NAME% >nul 2>&1
echo.
echo === O'rnatish tugadi. Service: %SERVICE_NAME% ===
pause
"""
