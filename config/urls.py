from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

# ============================================================
# Admin panel branding
# ============================================================
admin.site.site_header = "Nigoh — Boshqaruv paneli"
admin.site.site_title  = "Nigoh Admin"
admin.site.index_title = "Boshqaruv paneliga xush kelibsiz"

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
   public=True,
   permission_classes=(permissions.AllowAny,),
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

# if settings.DEBUG:
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)