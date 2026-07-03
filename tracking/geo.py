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
from datetime import timedelta
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    requests = None    # requirements.txt ga qo'shildi lekin agar hali o'rnatilmagan bo'lsa

from django.utils import timezone

from .models import URLGeoCache

# Cache retention — 30 kundan eski yozuvlar o'chiriladi (avtomatik)
CACHE_RETENTION_DAYS = 30

# 24 soatda 1 marta tozalash (avtomatik cleanup throttle)
_LAST_CLEANUP_AT = None


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
        # setdefaulttimeout globaldir — buni faqat lokal sockettimeout qilib emas,
        # gethostbyname'ning ichki timeout'ini yoqib qo'yamiz. 3s yetadi.
        socket.setdefaulttimeout(3.0)
        ip = socket.gethostbyname(domain)
        print(f"[dns] {domain} -> {ip}")
        return ip
    except Exception as e:
        print(f"[dns FAIL] {domain}: {e}")
        return None


def _geo_lookup(ip):
    """IP -> geo dict. ip-api.com bepul tarifi (45 req/min)."""
    if requests is None:
        print("[geo_lookup] requests paketi o'rnatilmagan — pip install requests")
        return None
    try:
        r = requests.get(IP_API_URL.format(ip=ip), timeout=5)
        if r.status_code != 200:
            print(f"[geo FAIL] {ip}: HTTP {r.status_code}")
            return None
        data = r.json()
        if data.get('status') != 'success':
            return None
        result = {
            'country':      data.get('country', ''),
            'country_code': data.get('countryCode', ''),
            'city':         data.get('city', ''),
            'lat':          data.get('lat'),
            'lng':          data.get('lon'),
            'org':          data.get('org', ''),
        }
        print(f"[geo] {ip} -> {result['country']}/{result['city']}")
        return result
    except Exception as e:
        print(f"[geo FAIL] {ip}: {e}")
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


def cleanup_old_cache(days=None):
    """
    30 kundan eski yozuvlarni o'chiradi (FIFO).
    Qaytishi: o'chirilgan yozuvlar soni.
    """
    if days is None:
        days = CACHE_RETENTION_DAYS
    cutoff = timezone.now() - timedelta(days=days)
    deleted, _ = URLGeoCache.objects.filter(updated_at__lt=cutoff).delete()
    if deleted:
        print(f"[cache cleanup] {deleted} ta eski yozuv o'chirildi (> {days} kun)")
    return deleted


def _maybe_run_cleanup():
    """Har 24 soatda bir marta avtomatik cleanup (in-memory throttle)."""
    global _LAST_CLEANUP_AT
    now = timezone.now()
    if _LAST_CLEANUP_AT and (now - _LAST_CLEANUP_AT).total_seconds() < 86400:
        return
    try:
        cleanup_old_cache()
    except Exception as e:
        print(f"[cache cleanup xato] {e}")
    _LAST_CLEANUP_AT = now


def resolve_domains_bulk(domains, max_new=40, retry_failed=True):
    """
    Bir vaqtda ko'p domain lar uchun geo qaytaradi.
    `max_new` — bir chaqiriqda maks. nechta YANGI/FAIL domain qayta hal qilinadi.
    `retry_failed=True` bo'lsa avval fail bo'lganlar qayta sinaladi.
    """
    domains = list({d for d in domains if d})
    if not domains:
        return {}

    # 24 soatda 1 marta eski yozuvlarni tozalash
    _maybe_run_cleanup()

    caches = {c.domain: c for c in URLGeoCache.objects.filter(domain__in=domains)}
    print(f"[bulk] {len(domains)} domain, {len(caches)} cache, retry_failed={retry_failed}")

    result = {}
    new_count = 0
    for d in domains:
        c = caches.get(d)
        if c and not c.failed and c.latitude is not None:
            result[d] = _serialize(c)
            continue

        # Cache yo'q yoki failed — qayta hal qilamiz
        if new_count >= max_new:
            result[d] = _serialize(c) if c else None
            continue

        # retry_failed=False va failed cache bor bo'lsa — o'tkazib yuboramiz
        if c and c.failed and not retry_failed:
            result[d] = None
            continue

        result[d] = resolve_domain(d, force=True)
        new_count += 1

    print(f"[bulk] hal qilingan yangi: {new_count}, jami muvaffaqiyatli: {sum(1 for v in result.values() if v)}")
    return result
