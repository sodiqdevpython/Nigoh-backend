from django.urls import path
from .views import (
    ReportBlockedURLView, BlacklistVersionView, ReportActivityLogView,
    ProcessBlacklistVersionView, ReportProcessAlertView, ReportAppUsageView,
    RequestScreenShareView, AgentScreenShareResponseView, AgentScreenShareUpdateView,
    RequestRemoteControlView, AgentRemoteControlUpdateView, ScreenshotUploadView
)

urlpatterns = [
    # Agent POST so'rov yuboradigan manzil
    path('report-blocked/', ReportBlockedURLView.as_view(), name='report-blocked'),
    path('blacklist-version/', BlacklistVersionView.as_view(), name='blacklist-version'),

    # Statistika (loglar) ni qabul qiluvchi yangi yo'nalish
    path('report-activity/', ReportActivityLogView.as_view(), name='report-activity'),

    path('process-blacklist-version/', ProcessBlacklistVersionView.as_view(), name='process-blacklist-version'),
    path('report-process-alert/', ReportProcessAlertView.as_view(), name='report-process-alert'),

    path('report-app-usage/', ReportAppUsageView.as_view(), name='report-app-usage'),

    # Screenshot — agent rasmni multipart bilan yuklaydi
    path('screenshot-upload/', ScreenshotUploadView.as_view(), name='screenshot-upload'),

    # screen share uchun
    # O'qituvchi POST qiladi (n=soniya body'da ketishi ham mumkin, URL dan olinmaydi)
    path('request-screen-share/<str:bios_uuid>/', RequestScreenShareView.as_view(), name='request-screen-share'),
    
    # Agent POST qiladi (URL ni yuboradi)
    path('agent-screen-share-response/', AgentScreenShareResponseView.as_view(), name='agent-screen-share-response'),
    path('screen-share-sessions/<uuid:session_id>/', AgentScreenShareUpdateView.as_view(), name='agent-screen-share-update'),


    # Remote Control boshlash (POST: {"time": 300})
    path('request-remote-control/<str:bios_uuid>/', RequestRemoteControlView.as_view(), name='request-remote-control'),
    
    # Agent URL jo'natishi (PATCH: {"url": "http://192.168.1.55"})
    path('remote-control-sessions/<uuid:session_id>/', AgentRemoteControlUpdateView.as_view(), name='agent-remote-control-update'),
]