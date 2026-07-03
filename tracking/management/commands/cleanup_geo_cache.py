"""
30 kundan eski URLGeoCache yozuvlarini o'chiradi.

Ishlatish:
    docker exec nigoh_web python manage.py cleanup_geo_cache
    docker exec nigoh_web python manage.py cleanup_geo_cache --days 7
"""
from django.core.management.base import BaseCommand

from tracking.geo import cleanup_old_cache, CACHE_RETENTION_DAYS
from tracking.models import URLGeoCache


class Command(BaseCommand):
    help = "Eski URLGeoCache yozuvlarini FIFO o'chiradi (default: 30 kun)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, default=CACHE_RETENTION_DAYS,
            help=f'Necha kundan keyin o\'chirilsin (default: {CACHE_RETENTION_DAYS})',
        )

    def handle(self, *args, **options):
        days = options['days']
        total_before = URLGeoCache.objects.count()
        deleted = cleanup_old_cache(days=days)
        total_after = URLGeoCache.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f"O'chirildi: {deleted}. Yozuvlar: {total_before} → {total_after}"
        ))
