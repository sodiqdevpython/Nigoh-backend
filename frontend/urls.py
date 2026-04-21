from django.urls import path
from . import views as v

urlpatterns = [
    path('login/', v.login_view, name='login'),
    path('logout/', v.logout_view, name='logout'),
    path('', v.home, name='home'),

    path('groups/', v.group_management, name='group_management'),

    path('devices/', v.device_list_view, name='device_list'),
    path('device/<str:pk>/', v.device_detail_view, name='device_detail'),
    path('remote-control/request/<str:bios_uuid>/', v.create_remote_session_view, name='remote_control_request'),
    
    path('remote-control/status/<str:session_id>/', v.check_session_status_view, name='remote_control_status'),
]
