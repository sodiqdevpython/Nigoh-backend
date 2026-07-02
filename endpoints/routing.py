from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Yangi — agent device_id (32 hex) bilan ulanadi
    re_path(r'ws/pc/(?P<device_id>[a-fA-F0-9]{32})/$', consumers.ComputerConsumer.as_asgi()),

    # Eski (legacy) — bios_uuid bilan ulanish (eski agentlar uchun saqlangan)
    re_path(r'ws/pc/(?P<bios_uuid>[\w\-]+)/$', consumers.ComputerConsumer.as_asgi()),
]
