import hashlib
import os
import zipfile
from io import BytesIO

from django.core.files.base import ContentFile
from django.db import models
from utils.models import BaseModel


def _release_zip_path(instance, filename):
    return f"updates/{instance.target}/{instance.version}/{filename}"


class Release(BaseModel):
    """Chiqarilgan versiyalar. Administrator ZIP yuklaydi — backend o'zi ochadi."""

    TARGET_NIGOH = 'nigoh'
    TARGET_WATCHDOG = 'watchdog'
    TARGET_CHOICES = [
        (TARGET_NIGOH, 'Nigoh.exe (asosiy agent)'),
        (TARGET_WATCHDOG, 'WatchdogService.exe'),
    ]

    target = models.CharField(max_length=20, choices=TARGET_CHOICES, default=TARGET_NIGOH)
    version = models.CharField(max_length=20, help_text="Masalan: 1.2.0")
    notes = models.TextField(blank=True, help_text="Changelog")

    # Admin bitta ZIP tashlaydi — backend o'zi ochib ishlaydi
    zip_file = models.FileField(
        upload_to=_release_zip_path, blank=True, null=True,
        help_text="ZIP fayl yuklang — backend ichidagi fayllarni avtomatik ochadi"
    )

    # Rollout — hozircha ishlatilmaydi, har doim 100% (barcha agentlarga)
    rollout_percentage = models.IntegerField(
        default=100,
        help_text="Endi ishlatilmaydi — har doim 100%",
    )
    is_active = models.BooleanField(
        default=False,
        help_text="Faqat BITTA release active bo'la oladi har target uchun. Bu belgilangani yangi o'rnatishlar va yangilanishlar uchun ishlatiladi."
    )

    # Manifest — deleted_files va h.k. (avtomatik to'ldiriladi)
    manifest = models.JSONField(
        default=dict, blank=True,
        help_text="Avtomatik: {'deleted_files': [...], 'total_files': N, 'total_size': N}"
    )

    class Meta:
        unique_together = [('target', 'version')]
        ordering = ['-created_at']

    def __str__(self):
        state = 'active' if self.is_active else 'idle'
        return f"{self.target} v{self.version} ({state})"

    def save(self, *args, **kwargs):
        # WATCHDOG: faqat BITTA record bo'la oladi.
        # Watchdog hech qachon field'da yangilanmaydi, shuning uchun
        # bir marta yaratiladi va zarurat bo'lsa admin edit qilib qayta yuklaydi.
        if self.target == self.TARGET_WATCHDOG and self._state.adding:
            existing = Release.objects.filter(target=self.TARGET_WATCHDOG).exclude(pk=self.pk).first()
            if existing:
                # Yangi record yaratish o'rniga mavjudini yangilaymiz —
                # admin uchun oddiy: har safar qayta yaratsa ham eskisi o'chib yangisi qoladi.
                Release.objects.filter(target=self.TARGET_WATCHDOG).exclude(pk=self.pk).delete()

        super().save(*args, **kwargs)

        # is_active=True bo'lsa — shu target ning boshqa release'larini deactive qilamiz
        if self.is_active:
            Release.objects.filter(target=self.target, is_active=True).exclude(pk=self.pk).update(is_active=False)

    def extract_zip_and_create_files(self):
        """
        ZIP ni ochib, har bir faylni UpdateFile sifatida saqlaydi.
        Oldingi versiya bilan solishtirib deleted_files ni aniqlaydi.
        """
        if not self.zip_file:
            return

        # Eski UpdateFile larni tozalaymiz (qayta yuklash holati uchun)
        self.files.all().delete()

        new_paths = set()
        total_size = 0

        with zipfile.ZipFile(self.zip_file, 'r') as zf:
            for info in zf.infolist():
                # Papkalarni o'tkazib yuboramiz
                if info.is_dir():
                    continue

                file_data = zf.read(info.filename)

                # SHA256 hisoblash
                sha = hashlib.sha256(file_data).hexdigest()

                # Nisbiy yo'l — ZIP ichidagi yo'l (backslash bilan normalize)
                rel_path = info.filename.replace('/', '\\')

                # Faylni media ga saqlaymiz — `upload_to=_upload_path` o'zi
                # `updates/<target>/<version>/` prefixini qo'shadi, shuning uchun
                # bu yerda faqat fayl yo'lini berish kerak (ikki marta qo'shilmasin).
                uf = UpdateFile(
                    release=self,
                    rel_path=rel_path,
                    sha256=sha,
                    size=len(file_data),
                )
                uf.file.save(info.filename, ContentFile(file_data), save=False)
                uf.save()

                new_paths.add(rel_path)
                total_size += len(file_data)

        # Oldingi versiya bilan solishtirish — deleted_files topish
        deleted_files = []
        prev_release = (
            Release.objects
            .filter(target=self.target)
            .exclude(id=self.id)
            .order_by('-created_at')
            .first()
        )
        if prev_release:
            old_paths = set(
                prev_release.files.values_list('rel_path', flat=True)
            )
            deleted_files = sorted(old_paths - new_paths)

        self.manifest = {
            'deleted_files': deleted_files,
            'total_files': len(new_paths),
            'total_size': total_size,
        }
        self.save(update_fields=['manifest'])


def _upload_path(instance, filename):
    return f"updates/{instance.release.target}/{instance.release.version}/{filename}"


class UpdateFile(BaseModel):
    """Release ga tegishli har bir fayl alohida saqlanadi."""

    release = models.ForeignKey(
        Release, on_delete=models.CASCADE, related_name='files'
    )
    file = models.FileField(upload_to=_upload_path)
    rel_path = models.CharField(
        max_length=255,
        help_text="Agent papkasidagi nisbiy yo'l, masalan: 'Nigoh.exe'"
    )
    sha256 = models.CharField(
        max_length=64, blank=True,
        help_text="Avtomatik hisoblanadi"
    )
    size = models.BigIntegerField(default=0)

    def save(self, *args, **kwargs):
        if self.file and not self.sha256:
            h = hashlib.sha256()
            for chunk in self.file.chunks():
                h.update(chunk)
            self.sha256 = h.hexdigest()
            try:
                self.size = self.file.size
            except Exception:
                self.size = 0
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.rel_path} ({self.release})"


class PendingCommand(BaseModel):
    """
    Agent uchun navbatda turgan buyruq. HTTP polling yoki WS push orqali yetkaziladi.
    """

    ACTION_UPDATE = 'update'
    ACTION_UNINSTALL = 'uninstall'
    ACTION_RESTART = 'restart'
    ACTION_CHOICES = [
        (ACTION_UPDATE, 'Yangilash'),
        (ACTION_UNINSTALL, "O'chirish"),
        (ACTION_RESTART, 'Qayta ishga tushirish'),
    ]

    computer = models.ForeignKey(
        'endpoints.Computer', on_delete=models.CASCADE,
        related_name='pending_commands'
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    release = models.ForeignKey(
        Release, on_delete=models.CASCADE, null=True, blank=True,
        help_text="Faqat action=update bo'lganda"
    )
    force = models.BooleanField(
        default=False, help_text="Rollout % e'tiborga olinmaydi"
    )

    delivered_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    success = models.BooleanField(null=True)
    error_message = models.TextField(blank=True)

    # Retry mexanizmi: agent offline yoki yangilash muvaffaqiyatsiz bo'lsa
    # backend har WS ulanishida qayta yuboradi. 5 ta urinishdan keyin
    # bekor qilinadi va admin qo'lda tekshirishi kerak.
    attempts = models.PositiveSmallIntegerField(
        default=0,
        help_text="Buyruq yuborilgan marotaba soni. 5 ga yetganda bekor qilinadi."
    )
    MAX_ATTEMPTS = 5

    class Meta:
        indexes = [models.Index(fields=['computer', 'delivered_at'])]
        ordering = ['created_at']

    def __str__(self):
        return f"{self.action} → {self.computer_id} ({self.id})"

    @property
    def is_pending(self):
        """Hali ham urinib ko'rish mumkinmi?"""
        return self.acknowledged_at is None and self.attempts < self.MAX_ATTEMPTS

    @property
    def is_abandoned(self):
        """5 urinishdan oshib ketdi — endi urinilmaydi."""
        return self.acknowledged_at is None and self.attempts >= self.MAX_ATTEMPTS


class UpdateLog(BaseModel):
    """Har bir agentning yangilash tarixi."""

    computer = models.ForeignKey(
        'endpoints.Computer', on_delete=models.CASCADE,
        related_name='update_logs'
    )
    from_version = models.CharField(max_length=20, blank=True)
    to_version = models.CharField(max_length=20)
    target = models.CharField(max_length=20)
    success = models.BooleanField()
    error = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        status = 'OK' if self.success else 'FAIL'
        return f"{self.computer_id} {self.target} → {self.to_version} [{status}]"
