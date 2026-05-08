import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

# channels har dispatch da aclose_old_connections() → sync_to_async → thread ochadi.
# Thread yaratish bu muhitda ishlamaydi, shuning uchun noop bilan almashtiramiz.
# DB operatsiyalari endi asyncpg orqali (thread shart emas).
async def _noop():
    pass

import channels.consumer
import channels.db
channels.consumer.aclose_old_connections = _noop
channels.db.aclose_old_connections = _noop

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
import endpoints.routing

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": URLRouter(
        endpoints.routing.websocket_urlpatterns
    ),
})