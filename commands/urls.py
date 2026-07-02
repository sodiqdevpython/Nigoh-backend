from django.urls import path

from .views import (
    AgentCommandView,
    AgentReportView,
    ManifestView,
    InstallScriptView,
    LatestWatchdogView,
    LatestAgentZipView,
    LatestWatchdogVersionView,
)

urlpatterns = [
    path('command/', AgentCommandView.as_view(), name='agent-command'),
    path('manifest/<str:target>/<str:version>/', ManifestView.as_view(), name='agent-manifest'),
    path('report/', AgentReportView.as_view(), name='agent-report'),

    # Installer endpointlari — yangi mijozda agentni o'rnatish uchun
    path('install/', InstallScriptView.as_view(), name='install-script'),
    path('install/watchdog.exe', LatestWatchdogView.as_view(), name='install-watchdog'),
    path('install/nigoh.zip', LatestAgentZipView.as_view(), name='install-agent-zip'),
    path('install/watchdog_version.json', LatestWatchdogVersionView.as_view(), name='install-watchdog-version'),
]
