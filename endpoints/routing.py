from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # PC bios_uuid bilan ulanadigan manzil
    re_path(r'ws/pc/(?P<bios_uuid>[\w\-]+)/$', consumers.ComputerConsumer.as_asgi()),
]