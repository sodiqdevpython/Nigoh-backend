from django.urls import path
from .views import ReportBlockedURLView, BlacklistVersionView, ReportActivityLogView, ProcessBlacklistVersionView, ReportProcessAlertView

urlpatterns = [
    # Agent POST so'rov yuboradigan manzil
    path('report-blocked/', ReportBlockedURLView.as_view(), name='report-blocked'),
    path('blacklist-version/', BlacklistVersionView.as_view(), name='blacklist-version'),

    # Statistika (loglar) ni qabul qiluvchi yangi yo'nalish
    path('report-activity/', ReportActivityLogView.as_view(), name='report-activity'),

    path('process-blacklist-version/', ProcessBlacklistVersionView.as_view(), name='process-blacklist-version'),
    path('report-process-alert/', ReportProcessAlertView.as_view(), name='report-process-alert'),
]