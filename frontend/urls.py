from django.urls import path
from . import views as v

urlpatterns = [
    path('login/', v.login_view, name='login'),
    path('logout/', v.logout_view, name='logout'),
    path('', v.home, name='home'),

    path('groups/', v.group_management, name='group_management'),

    path('devices/', v.device_list_view, name='device_list'),
    path('device/<str:pk>/', v.device_detail_view, name='device_detail'),
    path('device/<str:pk>/command/', v.device_command_view, name='device_command'),
    path('remote-control/request/<str:bios_uuid>/', v.create_remote_session_view, name='remote_control_request'),
    
    path('remote-control/status/<str:session_id>/', v.check_session_status_view, name='remote_control_status'),

    path('groups/<uuid:pk>/', v.group_detail_view, name='group_detail'),
    path('groups/<uuid:pk>/metrics/', v.group_metrics_view, name='group_metrics'),
    path('groups/<uuid:pk>/command/', v.group_command_view, name='group_command'),
    path('groups/<uuid:pk>/stats/', v.group_stats_view, name='group_stats'),

    path('blocked-urls/', v.blocked_urls_view, name='blocked_urls'),
    path('blocked-processes/', v.blocked_processes_view, name='blocked_processes'),

    # Screenshot — bosilganda so'rov yaratadi va WS orqali agentga yuboradi
    path('device/<str:pk>/screenshot-request/', v.request_screenshot_view, name='request_screenshot'),
    path('device/<str:pk>/screenshot-poll/<uuid:req_id>/', v.poll_screenshot_view, name='poll_screenshot'),

    # Log — admin agent'ning shifrlangan result.log ni oladi
    path('device/<str:pk>/log-request/', v.request_log_view, name='request_log'),
    path('device/<str:pk>/log-poll/<uuid:req_id>/', v.poll_log_view, name='poll_log'),

    # App icons — dastur logotiplari JSON (DB dagi)
    path('app-icons.json', v.app_icons_json, name='app_icons_json'),

    # Tashqariga chiqishlar — 3D globus
    path('external-connections/', v.external_connections_view, name='external_connections'),
    path('external-connections/data.json', v.external_connections_data_json, name='external_connections_data'),

    # Broadcast (screen share)
    path('broadcast/start/', v.broadcast_start_view, name='broadcast_start'),
    path('broadcast/agent-url/<uuid:session_id>/', v.broadcast_agent_url_view, name='broadcast_agent_url'),
    path('broadcast/status/<uuid:session_id>/', v.broadcast_status_view, name='broadcast_status'),
]
