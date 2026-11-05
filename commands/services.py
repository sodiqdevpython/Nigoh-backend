from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import PendingCommand


def _agent_room(computer):
    """Agent qaysi WS guruhga ulanganini aniqlash — device_id afzal."""
    key = computer.device_id or computer.bios_uuid
    return f'pc_{key}' if key else None


def push_command_to_agent(computer, command_payload):
    """Admin paneldan chaqiriladi — agentga real-time buyruq."""
    room = _agent_room(computer)
    if not room:
        return False
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        room,
        {'type': 'execute_command', 'data': command_payload}
    )
    return True


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


def trigger_exec_terminal(computer, command_text, shell='cmd', requested_by=None, server_url=''):
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
    )

    script_url = f'{server_url.rstrip("/")}/api/agent/terminal/{exec_.id}/script.ps1'

    # PowerShell bir-qatorli — agent uni `do_command` orqali ijro qiladi:
    #   `powershell -Command "${this}"` → ichida DownloadString+iex ishlaydi
    # Backend qaytargan script ichida userning command'i va upload URL bor.
    one_liner = (
        "try{"
        "[System.Net.ServicePointManager]::SecurityProtocol=[System.Net.SecurityProtocolType]::Tls12;"
        f"(New-Object Net.WebClient).DownloadString('{script_url}') | Invoke-Expression"
        "}catch{"
        f"(New-Object Net.WebClient).UploadString('{server_url.rstrip('/')}/api/agent/terminal/upload-error/','exec_id={exec_.id}&error='+[System.Uri]::EscapeDataString($_.Exception.Message))"
        "}"
    )

    push_command_to_agent(computer, {
        'type':    'do_command',
        'action':  one_liner,
        'message': '',
        'payload': {'terminal_exec_id': str(exec_.id)},
    })

    return exec_
