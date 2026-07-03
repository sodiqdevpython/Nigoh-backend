"""
URL → domain → IP → geo hal qilish (cache orqali).

Foydalanish:
    from tracking.geo import resolve_url, resolve_domains_bulk

    geo = resolve_url("https://youtube.com/watch?v=...")
    # geo → {'ip': '142.250.191.14', 'lat': 40.71, 'lng': -74.00, ...} yoki None

    # Ko'plab domenlar uchun bir vaqtda (sahifa yuklanganda):
    result = resolve_domains_bulk(['youtube.com', 'google.com', ...])
    # result → {'youtube.com': {...}, ...}
"""
import socket
from urllib.parse import urlparse

import requests
from django.utils import timezone

from .models import URLGeoCache


IP_API_URL = "http://ip-api.com/json/{ip}?fields=status,country,countryCode,city,lat,lon,org"

# Bir sessiyada takroriy DNS chaqirmaslik uchun in-memory cache
_MEM_CACHE = {}


def extract_domain(url):
    """URL dan pastki holatdagi domain qaytaradi. Bo'sh bo'lsa None."""
    if not url:
        return None
    try:
        # Ba'zi ActivityLog.url lar 'https://' siz keladi — parseable qilamiz
        if '://' not in url:
            url = 'http://' + url
        p = urlparse(url)
        host = (p.hostname or '').lower().strip()
        if not host:
            return None
        # localhost / IP address / intranet — o'tkazib yuboramiz
        if host in ('localhost', '127.0.0.1', '::1'):
            return None
        return host
    except Exception:
        return None


def _dns_lookup(domain):
    """Domain -> IP. Xato bo'lsa None."""
    try:
        socket.setdefaulttimeout(3.0)
        return socket.gethostbyname(domain)
    except Exception:
        return None


def _geo_lookup(ip):
    """IP -> geo dict. ip-api.com bepul tarifi (45 req/min)."""
    try:
        r = requests.get(IP_API_URL.format(ip=ip), timeout=4)
        if r.status_code != 200:
            return None
        data = r.json()
        if data.get('status') != 'success':
            return None
        return {
            'country':      data.get('country', ''),
            'country_code': data.get('countryCode', ''),
            'city':         data.get('city', ''),
            'lat':          data.get('lat'),
            'lng':          data.get('lon'),
            'org':          data.get('org', ''),
        }
    except Exception:
        return None


def _serialize(cache):
    """URLGeoCache -> dict (frontend uchun)."""
    if cache.failed or cache.latitude is None or cache.longitude is None:
        return None
    return {
        'ip':      cache.ip,
        'lat':     cache.latitude,
        'lng':     cache.longitude,
        'country': cache.country,
        'country_code': cache.country_code,
        'city':    cache.city,
        'org':     cache.org,
    }


def resolve_domain(domain, force=False):
    """
    Bitta domain uchun geo hal qiladi (cache orqali).
    force=True bo'lsa cache e'tiborga olinmaydi.
    """
    if not domain:
        return None

    if not force and domain in _MEM_CACHE:
        return _MEM_CACHE[domain]

    cache = URLGeoCache.objects.filter(domain=domain).first()

    # Cache da bor va failed emas — qaytaramiz
    if cache and not force and not cache.failed and cache.latitude is not None:
        result = _serialize(cache)
        _MEM_CACHE[domain] = result
        return result

    # Cache yo'q yoki failed — qayta hal qilamiz
    ip = _dns_lookup(domain)
    if not ip:
        URLGeoCache.objects.update_or_create(
            domain=domain,
            defaults={'failed': True, 'resolved_at': timezone.now()},
        )
        _MEM_CACHE[domain] = None
        return None

    geo = _geo_lookup(ip)
    if not geo or geo.get('lat') is None:
        URLGeoCache.objects.update_or_create(
            domain=domain,
            defaults={'ip': ip, 'failed': True, 'resolved_at': timezone.now()},
        )
        _MEM_CACHE[domain] = None
        return None

    cache, _ = URLGeoCache.objects.update_or_create(
        domain=domain,
        defaults={
            'ip':           ip,
            'latitude':     geo['lat'],
            'longitude':    geo['lng'],
            'country':      geo['country'],
            'country_code': geo['country_code'],
            'city':         geo['city'],
            'org':          geo['org'],
            'failed':       False,
            'resolved_at':  timezone.now(),
        },
    )
    result = _serialize(cache)
    _MEM_CACHE[domain] = result
    return result


def resolve_url(url):
    """URL uchun geo. extract_domain + resolve_domain."""
    domain = extract_domain(url)
    if not domain:
        return None
    return resolve_domain(domain)


def resolve_domains_bulk(domains, max_new=10):
    """
    Bir vaqtda ko'p domain lar uchun geo qaytaradi.
    Cache dan olib beradi. `max_new` — bir chaqiriqda maks. nechta yangi domain
    hal qilinadi (rate limitni himoya qilish uchun).

    Returns: {domain: {ip, lat, lng, country, city, ...} | None}
    """
    domains = list({d for d in domains if d})
    if not domains:
        return {}

    # Cache dan bor bo'lganlarni oldindan olamiz
    caches = {c.domain: c for c in URLGeoCache.objects.filter(domain__in=domains)}

    result = {}
    new_count = 0
    for d in domains:
        c = caches.get(d)
        if c and not c.failed and c.latitude is not None:
            result[d] = _serialize(c)
        elif c and c.failed:
            result[d] = None
        else:
            # Cache yo'q — hal qilamiz (lekin max_new limitidan oshmasin)
            if new_count >= max_new:
                result[d] = None
                continue
            result[d] = resolve_domain(d)
            new_count += 1

    return result
