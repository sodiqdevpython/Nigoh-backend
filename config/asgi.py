import os
import django # <--- Qo'shildi
from django.core.asgi import get_asgi_application

# Sozlamalarni o'rnatamiz
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Djangoni to'liq ishga tushiramiz (Importlardan oldin bo'lishi shart!)
django.setup() 

# Endi qolgan narsalarni import qilsak bo'ladi
from channels.routing import ProtocolTypeRouter, URLRouter
import endpoints.routing

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": URLRouter(
        endpoints.routing.websocket_urlpatterns
    ),
})