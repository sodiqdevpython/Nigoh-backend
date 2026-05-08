from django.shortcuts import redirect
from django.conf import settings
import re

# Faqat shu URLlar login tekshiruvidan o'tadi (HTML render qiladigan viewlar)
PROTECTED_URLS = [
    r'^/$',                      # home
    r'^/groups/$',               # guruhlar ro'yxati
    r'^/groups/[^/]+/$',         # guruh detail dashboard (uuid/)
    r'^/devices/$',              # qurilmalar ro'yxati
    r'^/device/[^/]+/$',         # qurilma detail
    r'^/blocked-urls/$',         # bloklangan URLlar
    r'^/blocked-processes/$',    # bloklangan jarayonlar
]

PROTECTED_PATTERNS = [re.compile(p) for p in PROTECTED_URLS]


class LoginRequiredMiddleware:
    """
    Faqat HTML sahifalarini render qiladigan viewlarni himoyalaydi.
    JSON endpointlar, WebSocket, admin — o'z autentifikatsiyasini ishlatadi.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info

        is_protected = any(p.match(path) for p in PROTECTED_PATTERNS)

        if is_protected and not request.user.is_authenticated:
            return redirect(settings.LOGIN_URL)

        return self.get_response(request)
