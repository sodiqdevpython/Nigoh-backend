from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import PendingCommand


def _agent_room(computer):
    """Agent qaysi WS guruhga ulanganini aniqlash — device_id afzal."""
    key = computer.device_id or computer.bios_uuid
    return f'pc_{key}' if key else None


def _watchdog_room(computer):
    """Watchdog qaysi WS guruhga ulanganini aniqlash (admin buyruqlar uchun)."""
    key = computer.device_id or computer.bios_uuid
    return f'wd_{key}' if key else None


def push_command_to_agent(computer, command_payload):
    """Admin paneldan chaqiriladi — agentga (user session) real-time buyruq."""
    room = _agent_room(computer)
    if not room:
        return False
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        room,
        {'type': 'execute_command', 'data': command_payload}
    )
    return True


def push_command_to_watchdog(computer, command_payload):
    """Watchdog'ga (SYSTEM huquqida) real-time buyruq.
    Admin huquqi kerak bo'lgan hollar — printer sozlash, service boshqarish, h.k.
    """
    room = _watchdog_room(computer)
    if not room:
        return False
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        room,
        {'type': 'execute_command', 'data': command_payload}
    )
    return True


def push_terminal_command(computer, command_payload, run_as_admin=False):
    """`run_as_admin` ga qarab agent yoki Watchdog'ga yo'naltiradi."""
    if run_as_admin:
        return push_command_to_watchdog(computer, command_payload)
    return push_command_to_agent(computer, command_payload)


def trigger_update(computer, release=None, force=True):
    """Yangilash buyrug'ini yaratadi va WS orqali push qiladi.

    release berilmasa — hozirgi ACTIVE Nigoh release ishlatiladi.
    force default True: rollout foizini e'tiborga olmaymiz (barcha agentlar yangilanadi).
    """
    from .models import Release
    if release is None:
        release = (
            Release.objects
            .filter(target='nigoh', is_active=True)
            .order_by('-created_at')
            .first()
        )
        if release is None:
            raise ValueError("Aktiv Nigoh release yo'q — avval Release yarating va tick qiling")

    cmd = PendingCommand.objects.create(
        computer=computer,
        action=PendingCommand.ACTION_UPDATE,
        release=release,
        force=force,
    )
    push_command_to_agent(computer, {
        'type':         'force_update',
        'target':       release.target,
        'version':      release.version,
        'manifest_url': f'/api/agent/manifest/{release.target}/{release.version}/',
        'force':        force,
        'command_id':   str(cmd.id),
    })
    return cmd


def trigger_uninstall(computer):
    cmd = PendingCommand.objects.create(
        computer=computer,
        action=PendingCommand.ACTION_UNINSTALL,
    )
    push_command_to_agent(computer, {
        'type':       'force_uninstall',
        'confirm':    True,
        'command_id': str(cmd.id),
    })
    return cmd


def trigger_restart(computer):
    cmd = PendingCommand.objects.create(
        computer=computer,
        action=PendingCommand.ACTION_RESTART,
    )
    push_command_to_agent(computer, {
        'type':       'restart',
        'command_id': str(cmd.id),
    })
    return cmd


def _build_terminal_one_liner(exec_id, server_url):
    """`do_command` orqali agentga yuboriladigan PowerShell bir-liner.

    Agent bu bir-linerni mavjud `SystemCommandManager.ExecuteHiddenCommand` orqali
    bajaradi — u esa backend'dan to'liq script yuklab olib ishlatadi.
    """
    base = server_url.rstrip('/')
    script_url = f'{base}/api/agent/terminal/{exec_id}/script.ps1'
    error_url = f'{base}/api/agent/terminal/upload-error/'
    return (
        "try{"
        "[System.Net.ServicePointManager]::SecurityProtocol=[System.Net.SecurityProtocolType]::Tls12;"
        f"(New-Object Net.WebClient).DownloadString('{script_url}') | Invoke-Expression"
        "}catch{"
        f"(New-Object Net.WebClient).UploadString('{error_url}','exec_id={exec_id}&error='+[System.Uri]::EscapeDataString($_.Exception.Message))"
        "}"
    )


def trigger_exec_terminal(computer, command_text, shell='cmd', requested_by=None,
                          server_url='', run_as_admin=False):
    """
    Admin terminalda yuborgan buyruqni agentga uzatadi.

    AGENTNI YANGILASHGA HOJAT YO'Q — mavjud `do_command` kanalidan foydalaniladi.

    Oqim:
      1) TerminalExecution yaratiladi (buyruq matni DB'ga saqlanadi)
      2) Backend'ga `/api/agent/terminal/<id>/script.ps1` endpointidan to'liq
         PowerShell script olinadigan BIR QATOR buyruq WS orqali agentga yuboriladi
      3) Agent mavjud `do_command` handler orqali PowerShell'ni ishga tushiradi
      4) Script backend'dan yuklanib bajariladi — natijani multipart orqali
         `/api/agent/terminal/upload/` ga yuboradi
      5) TerminalExecution.status=done bo'ladi, admin uni ko'radi

    Multi-line va uzun buyruqlar to'liq ishlaydi — script ichida base64 decode qilinadi,
    quoting muammolari yo'q.
    """
    from .models import TerminalExecution

    if shell not in (TerminalExecution.SHELL_CMD, TerminalExecution.SHELL_PWSH):
        shell = TerminalExecution.SHELL_CMD

    exec_ = TerminalExecution.objects.create(
        computer=computer,
        requested_by=requested_by,
        shell=shell,
        command_text=command_text or '',
        status=TerminalExecution.STATUS_PENDING,
        run_as_admin=run_as_admin,
    )

    one_liner = _build_terminal_one_liner(exec_.id, server_url)

    push_terminal_command(computer, {
        'type':    'do_command',
        'action':  one_liner,
        'message': '',
        'payload': {
            'terminal_exec_id': str(exec_.id),
            'run_as_admin':     run_as_admin,
        },
    }, run_as_admin=run_as_admin)

    return exec_


# ═══════════════════════════════════════════════════════════════════
# SCHEDULED SCRIPTS — har kuni online bo'lganda bir marta ishga tushadi
# ═══════════════════════════════════════════════════════════════════

def _get_server_url_from_env():
    """Settings'dan server URL ni oladi. SERVER_URL env variable yoki fallback."""
    import os
    return (os.environ.get('SERVER_URL')
            or os.environ.get('SITE_URL')
            or 'http://localhost:8000').rstrip('/')


def dispatch_scheduled_scripts_for(computer, is_newly_created=False, server_url=None):
    """
    PC online bo'lgan paytda chaqiriladi.

    Har bir aktiv ScheduledScript uchun:
      - Shu PC uchun applicable ekanligi tekshiriladi
      - Bugun shu PC'da shu script allaqachon ishga tushganmi?
        Yo'q bo'lsa — TerminalExecution yaratiladi va `do_command` yuboriladi
      - Bir kunga bir marta kafolati UniqueConstraint bilan ta'minlanadi

    Return: ishga tushirilgan scriptlar soni.
    """
    from datetime import date, timedelta
    from django.db import IntegrityError
    from .models import ScheduledScript, TerminalExecution

    if not computer:
        return 0

    today = date.today()
    server_url = server_url or _get_server_url_from_env()
    dispatched = 0

    try:
        active_scripts = ScheduledScript.objects.filter(is_active=True)
    except Exception as e:
        print(f"[dispatch_scheduled xato] {e}")
        return 0

    for script in active_scripts:
        try:
            if not script.is_applicable_to(computer, is_newly_created=is_newly_created):
                continue

            # Bugun ishga tushganmi? — DB darajasidagi uniqueness
            already = TerminalExecution.objects.filter(
                scheduled_script=script,
                computer=computer,
                executed_date=today,
            ).exists()
            if already:
                continue

            # Yangi execution yaratamiz — UniqueConstraint tufayli race-condition'siz
            try:
                exec_ = TerminalExecution.objects.create(
                    computer=computer,
                    scheduled_script=script,
                    executed_date=today,
                    shell=script.shell,
                    command_text=script.command_text,
                    run_as_admin=script.run_as_admin,
                    status=TerminalExecution.STATUS_PENDING,
                )
            except IntegrityError:
                # Boshqa consumer bir zumda yaratib bo'lgan — ok, o'tkazamiz
                continue

            # do_command yuboramiz
            one_liner = _build_terminal_one_liner(exec_.id, server_url)
            ok = push_terminal_command(computer, {
                'type':    'do_command',
                'action':  one_liner,
                'message': '',
                'payload': {
                    'terminal_exec_id':  str(exec_.id),
                    'scheduled_script':  str(script.id),
                    'run_as_admin':      script.run_as_admin,
                },
            }, run_as_admin=script.run_as_admin)
            if ok:
                dispatched += 1
            else:
                # WS mavjud emas — execution'ni pending holida qoldiramiz,
                # keyingi connectda yana urinib ko'riladi? Yo'q — executed_date bilan
                # bugunga bir marta cheklovi bor. Shuning uchun offline deb belgilaylik.
                exec_.status = TerminalExecution.STATUS_FAILED
                target = 'Watchdog' if script.run_as_admin else 'Agent'
                exec_.stderr = f"{target} WS channel topilmadi (ulangani yo'q)"
                exec_.save(update_fields=['status', 'stderr'])
        except Exception as e:
            print(f"[dispatch_scheduled.script={script.id} xato] {e}")
            continue

    # FIFO cleanup — 30 kundan eski yozuvlarni o'chirish (sekin, inline tashkil etilmagan).
    # Har 100 ta dispatch'da bir marta tozalaymiz (DB'ni bo'g'maslik uchun).
    if dispatched > 0:
        try:
            _maybe_cleanup_old_executions()
        except Exception as e:
            print(f"[cleanup xato] {e}")

    return dispatched


_cleanup_tick = {'n': 0}


def _maybe_cleanup_old_executions():
    """30 kundan eski TerminalExecution'larni o'chiradi (har 100 chaqirishda 1 marta)."""
    from datetime import timedelta
    from django.utils import timezone
    from .models import TerminalExecution

    _cleanup_tick['n'] += 1
    if _cleanup_tick['n'] % 100 != 1:
        return

    cutoff = timezone.now() - timedelta(days=30)
    deleted, _ = TerminalExecution.objects.filter(created_at__lt=cutoff).delete()
    if deleted:
        print(f"[FIFO cleanup] {deleted} ta eski TerminalExecution o'chirildi (>30 kun)")


def dispatch_pending_admin_executions_for(computer, server_url=None):
    """
    Watchdog WS ulangan paytda chaqiriladi — bugungi `pending` qolgan admin
    execution'larni **qayta push qiladi**.

    Sabab: agent ulanishi va Watchdog ulanishi parallel. Agent oldin ulansa va
    dispatcher admin script uchun exec yaratsa, `wd_<id>` room'da hali hech kim
    yo'q bo'lsa — xabar yo'qolib ketadi va exec `pending` da qoladi. Watchdog
    ulanganda shu holatni to'g'irlash uchun shu funksiya chaqiriladi.

    Qaytaradi: qayta push qilingan execution'lar soni.
    """
    from datetime import date, timedelta
    from .models import TerminalExecution

    if not computer:
        return 0
    server_url = server_url or _get_server_url_from_env()

    # Oxirgi 24 soat'dagi pending admin execution'larni olish.
    # Juda eski (1 kundan oldin) pending'lar — abandon qilamiz.
    cutoff = date.today() - timedelta(days=1)
    pending = TerminalExecution.objects.filter(
        computer=computer,
        run_as_admin=True,
        status=TerminalExecution.STATUS_PENDING,
        created_at__gte=cutoff,
    )

    pushed = 0
    for exec_ in pending:
        try:
            one_liner = _build_terminal_one_liner(exec_.id, server_url)
            ok = push_command_to_watchdog(computer, {
                'type':    'do_command',
                'action':  one_liner,
                'message': '',
                'payload': {
                    'terminal_exec_id': str(exec_.id),
                    'run_as_admin':     True,
                    'retry':            True,
                },
            })
            if ok:
                pushed += 1
        except Exception as e:
            print(f"[dispatch_pending_admin_exec={exec_.id} xato] {e}")

    return pushed


def dispatch_scheduled_script_now(script, requested_by=None, server_url=None):
    """
    Admin "Hozir ishga tushir" bosganda chaqiriladi — bugungi guardni tekshirmasdan,
    applicable online PC'larga darhol yuboradi.

    Qaytaradi: yuborilgan PC'lar soni.
    """
    from datetime import date
    from .models import TerminalExecution

    if not script.is_active:
        return 0

    server_url = server_url or _get_server_url_from_env()
    today = date.today()
    sent = 0

    if script.target_mode == script.TARGET_ALL:
        from endpoints.models import Computer
        qs = Computer.objects.filter(is_online=True)
    else:
        qs = script.target_computers.filter(is_online=True)

    for computer in qs:
        # executed_date = None — chunki bu "force" (admin qo'lida), bir kuniga 1 marta
        # cheklovi tegilmaydi. Audit sifatida yoziladi.
        try:
            exec_ = TerminalExecution.objects.create(
                computer=computer,
                scheduled_script=script,
                executed_date=None,  # None = force run, unique constraint tegmaydi
                requested_by=requested_by,
                shell=script.shell,
                command_text=script.command_text,
                run_as_admin=script.run_as_admin,
                status=TerminalExecution.STATUS_PENDING,
            )
            one_liner = _build_terminal_one_liner(exec_.id, server_url)
            ok = push_terminal_command(computer, {
                'type':    'do_command',
                'action':  one_liner,
                'message': '',
                'payload': {
                    'terminal_exec_id': str(exec_.id),
                    'run_as_admin':     script.run_as_admin,
                },
            }, run_as_admin=script.run_as_admin)
            if ok:
                sent += 1
        except Exception as e:
            print(f"[dispatch_now.pc={computer.id} xato] {e}")

    return sent
