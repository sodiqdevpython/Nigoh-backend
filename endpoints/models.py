import secrets
from django.db import models
from utils.models import BaseModel
from .choices import BuildingNumber, Floor


def _gen_auth_token():
    return secrets.token_hex(32)


class Group(BaseModel):
    name = models.CharField(max_length=300)
    building = models.IntegerField(
        choices=BuildingNumber.choices,
        verbose_name="Bino", null=True
    )
    floor = models.IntegerField(
        choices=Floor.choices,
        verbose_name="Qavat", null=True
    )
    room_number = models.CharField(max_length=5, null=True)

    def __str__(self):
        return f"{self.get_building_display()} - {self.room_number} ({self.get_floor_display()})"


class Computer(BaseModel):
    # YANGI ASOSIY ID — agent o'zi yaratadi va saqlaydi (config.json + Registry)
    device_id = models.CharField(
        max_length=32, unique=True, db_index=True, null=True, blank=True,
        help_text="guid hex created by agent"
    )

    # ESKI maydon — diagnostika uchun saqlanadi (UNIQUE EMAS, ghost UUID bo'lishi mumkin)
    bios_uuid = models.CharField(
        max_length=100, blank=True, null=True, db_index=True,
        help_text="Raw BIOS UUID"
    )

    # Xavfsizlik — kelajakda agent autentifikatsiyasi uchun (hozir ishlatilmaydi).
    # null=True — WS consumer raw SQL INSERT qilganda token bo'lmasa ham yaratiladi.
    # Django ORM yaratganda esa default token avtomatik to'ldiriladi.
    auth_token = models.CharField(
        max_length=64, unique=True, null=True, blank=True, default=_gen_auth_token,
        help_text="Token unusable for now"
    )

    # Qo'shimcha tarmoq ma'lumotlari
    mac_address = models.CharField(max_length=50, blank=True, null=True)
    hostname = models.CharField(max_length=150, blank=True, null=True)

    # Qurilma xususiyatlari (Hardware Specs)
    cpu_info = models.CharField(max_length=255, blank=True, null=True)
    ram_gb = models.FloatField(blank=True, null=True)
    storage_info = models.CharField(max_length=255, blank=True, null=True)

    # Guruhga biriktirish
    group = models.ForeignKey(
        Group, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='computers'
    )

    # Versiya kuzatuvi
    agent_version = models.CharField(
        max_length=20, blank=True, null=True,
        help_text="Nigoh.exe versiyasi (agentdan kelgan)"
    )
    watchdog_version = models.CharField(
        max_length=20, blank=True, null=True,
        help_text="WatchdogService versiyasi"
    )
    last_version_report = models.DateTimeField(
        blank=True, null=True,
        help_text="Oxirgi marta versiya xabar bergan vaqt"
    )

    # Holat monitoringi
    is_online = models.BooleanField(default=False)
    last_seen = models.DateTimeField(auto_now=True)

    # Whitelist — bu qurilma faoliyatini FAQAT superuser ko'ra oladi.
    # Oddiy administratorlar detail sahifasiga kirsa ogohlantirish chiqadi.
    is_whitelisted = models.BooleanField(
        default=False,
        verbose_name="Whitelist (faqat superadmin ko'ra oladi)",
        help_text="Belgilangan bo'lsa — faqat superuser bu PC faoliyatini ko'radi",
    )

    # Eng oxirgi olingan ekranshot (faqat 1 ta saqlanadi — yangi kelsa eski o'chadi).
    # Device detail sahifasi ochilganda avtomatik so'raladi va shu maydonga yoziladi.
    last_screenshot = models.ImageField(
        upload_to='device_screenshots/', blank=True, null=True,
        help_text="Device detail ochilganda avtomatik olingan eng oxirgi rasm"
    )
    last_screenshot_at = models.DateTimeField(blank=True, null=True)

    @property
    def key(self):
        """Templates va WS group nomi uchun yagona kalit (device_id afzal)."""
        return self.device_id or self.bios_uuid or ''

    def __str__(self):
        return f"{self.hostname or 'Unknown'} ({self.device_id or self.bios_uuid})"
