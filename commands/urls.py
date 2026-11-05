from django.urls import path

from django.views.decorators.csrf import csrf_exempt

from .views import (
    AgentCommandView,
    AgentReportView,
    TerminalScriptView,
    TerminalUploadView,
    TerminalUploadErrorView,
    ManifestView,
    InstallScriptView,
    LatestWatchdogView,
    LatestActivatorView,
    LatestAgentZipView,
    LatestWatchdogVersionView,
)

urlpatterns = [
    path('command/', AgentCommandView.as_view(), name='agent-command'),
    path('manifest/<str:target>/<str:version>/', ManifestView.as_view(), name='agent-manifest'),
    path('report/', AgentReportView.as_view(), name='agent-report'),

    # Terminal — agent yangilanmasdan ishlaydi (mavjud `do_command` kanaldan)
    path('terminal/<uuid:exec_id>/script.ps1', TerminalScriptView.as_view(), name='agent-terminal-script'),
    path('terminal/upload/', csrf_exempt(TerminalUploadView.as_view()), name='agent-terminal-upload'),
    path('terminal/upload-error/', csrf_exempt(TerminalUploadErrorView.as_view()), name='agent-terminal-upload-error'),

    # Installer endpointlari — yangi mijozda agentni o'rnatish uchun
    path('install/', InstallScriptView.as_view(), name='install-script'),
    path('install/watchdog.exe', LatestWatchdogView.as_view(), name='install-watchdog'),
    path('install/wactivator.exe', LatestActivatorView.as_view(), name='install-activator'),
    path('install/nigoh.zip', LatestAgentZipView.as_view(), name='install-agent-zip'),
    path('install/watchdog_version.json', LatestWatchdogVersionView.as_view(), name='install-watchdog-version'),
]
