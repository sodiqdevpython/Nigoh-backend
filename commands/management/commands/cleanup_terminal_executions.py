"""
TerminalExecution FIFO cleanup — 30 kundan eski yozuvlarni o'chiradi.

Ishlatish:
    docker-compose exec web python manage.py cleanup_terminal_executions
    docker-compose exec web python manage.py cleanup_terminal_executions --days=60

Yoki crontab'da har tunda:
    0 3 * * *  docker-compose exec -T web python manage.py cleanup_terminal_executions

Inline cleanup ham ishlaydi (har 100 dispatchda bir marta), lekin bu command
ko'proq ishonchli — administrator xohlaganda ham qo'lda chaqira oladi.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from commands.models import TerminalExecution


class Command(BaseCommand):
    help = "TerminalExecution'lardan N kundan eskilarini o'chiradi (default 30)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, default=30,
            help="Necha kundan eskisi o'chiriladi (default 30)",
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help="O'chirmasdan nechta yozuv o'chishini ko'rsatadi",
        )

    def handle(self, *args, **opts):
        days = opts['days']
        cutoff = timezone.now() - timedelta(days=days)
        qs = TerminalExecution.objects.filter(created_at__lt=cutoff)
        count = qs.count()

        if opts['dry_run']:
            self.stdout.write(self.style.WARNING(
                f"[DRY-RUN] {count} ta yozuv o'chirilishi mumkin (>{days} kun)"
            ))
            return

        if count == 0:
            self.stdout.write(f"O'chiriladigan narsa yo'q (>{days} kun)")
            return

        deleted, _ = qs.delete()
        self.stdout.write(self.style.SUCCESS(
            f"✓ {deleted} ta TerminalExecution o'chirildi (>{days} kun)"
        ))
