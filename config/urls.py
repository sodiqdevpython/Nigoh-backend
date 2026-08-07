from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve as static_serve

# ============================================================
# Admin panel branding
# ============================================================
admin.site.site_header = "Nigoh — Admin"
admin.site.site_title  = "Nigoh Admin"

# Swagger uchun importlar
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

# Installer qisqa URL uchun
from commands.views import InstallScriptView

schema_view = get_schema_view(
   openapi.Info(
      title="Nigoh API",
      default_version='v1',
      description="Tarmoq va Resurslarni Optimallashtirish Tizimi API",
   ),
   public=False,
   permission_classes=(permissions.IsAdminUser,),
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('endpoints/', include('endpoints.urls')),
    path('tracking/', include('tracking.urls')),
    path('api/agent/', include('commands.urls')),

    # Qisqa installer URL: http://server/install/setup.bat
    # (InstallScriptView ichidagi reverse() haligacha /api/agent/install/... ga yo'naltiradi —
    #  bu foydalanuvchi yodlaydigan URL ning qisqa varianti)
    path('install/setup.bat', InstallScriptView.as_view()),

    path('', include('frontend.urls')),

    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
]

# static() DEBUG=False bo'lganda hech narsa qilmaydi (Django ichki mantiqi shunday).
# Shuning uchun django.views.static.serve ni to'g'ridan-to'g'ri chaqiramiz —
# bu DEBUG'dan qat'iy nazar ishlaydi. Prod'da ideal emas (nginx serve qilishi
# kerak), lekin muammoni darrov hal qiladi.
urlpatterns += [
    re_path(r'^static/(?P<path>.*)$', static_serve, {'document_root': settings.STATIC_ROOT}),
    re_path(r'^media/(?P<path>.*)$',  static_serve, {'document_root': settings.MEDIA_ROOT}),
]

# DEBUG bo'lsa Django o'zi ham serve qiladi (yuqoridagi bilan bir xil)
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)