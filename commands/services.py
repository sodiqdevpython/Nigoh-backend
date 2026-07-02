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
