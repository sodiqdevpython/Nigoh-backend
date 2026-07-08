import csv
import os
from django.db import models
from django.conf import settings
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from utils.models import BaseModel
from endpoints.models import Computer
from django.contrib.auth import get_user_model

User = get_user_model()

class BroadcastComputer(Computer):
    class Meta:
        proxy = True # Baza yaratilmaydi, faqat admin panel uchun!
        verbose_name = "Ekranni Tarqatish (Broadcast)"
        verbose_name_plural = "Ekranni Tarqatish (Broadcast)"


class RemoteControlSession(BaseModel):
    """
    Masofaviy boshqaruv (Remote Control) jarayonini saqlovchi model
    """
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='remote_sessions')
    computer = models.ForeignKey('endpoints.Computer', on_delete=models.CASCADE, related_name='remote_sessions')
    
    # Qancha vaqt berilgani (sekundda)
    duration = models.PositiveIntegerField(default=300)
    
    # Agent tayyor bo'lgach yuboradigan URL
    stream_url = models.URLField(max_length=1024, blank=True, null=True)
    
    # Holati (Aktiv yoki yo'q)
    is_active = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.computer.hostname} ({self.author.username})"

class BlockedURL(BaseModel):
    # Agent bloklashi kerak bo'lgan URL manzil (masalan: "tiktok.com")
    url_address = models.CharField(max_length=255, unique=True, db_index=True)
    
    # Shu manzilga necha marta kirishga urinish bo'lganini sanaymiz
    visit_count = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.url_address

# --- CSV FAYLNI AVTOMATIK YANGILASH MANTIQI ---

def generate_blacklist_csv():
    """Bazada bor barcha URL'larni olib, media papkaga CSV qilib yozadi"""
    media_path = settings.MEDIA_ROOT
    os.makedirs(media_path, exist_ok=True)
    file_path = os.path.join(media_path, 'blacklist.csv')
    
    # Bazadan faqat kerakli ustunlarni olamiz (tez ishlashi uchun)
    urls = BlockedURL.objects.all().values_list('id', 'url_address', 'visit_count')
    
    # CSV faylni ustidan yozamiz
    with open(file_path, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        # Sarlavhalarni (header) yozamiz
        writer.writerow(['id', 'url_address', 'visit_count'])
        
        # Ma'lumotlarni qator-qator yozib chiqamiz
        for url in urls:
            writer.writerow([str(url[0]), url[1], url[2]])

# Signal: URL qo'shilganda yoki tahrirlanganda CSV ni yangilaymiz
@receiver(post_save, sender=BlockedURL)
def update_csv_on_save(sender, instance, **kwargs):
    generate_blacklist_csv()

# Signal: URL o'chirilganda ham CSV ni yangilaymiz
@receiver(post_delete, sender=BlockedURL)
def update_csv_on_delete(sender, instance, **kwargs):
    generate_blacklist_csv()


class BlockedAttemptLog(BaseModel):
    computer = models.ForeignKey(Computer, on_delete=models.CASCADE, related_name='blocked_attempts')
    url = models.ForeignKey(BlockedURL, on_delete=models.CASCADE, related_name='attempts')
    
    # Agent o'zi hisoblab yuborgan urinishlar soni
    attempts_count = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.computer.hostname} -> {self.url.url_address} ({self.attempts_count} marta)"



class ActivityLog(BaseModel):
    """
    Kompyuterda qaysi dastur/sayt qancha vaqt ochiq turgani haqida statistika
    """
    computer = models.ForeignKey('endpoints.Computer', on_delete=models.CASCADE, related_name='activities', db_index=True)
    
    # Oyna sarlavhasi (masalan: "Google Gemini", "Document1 - Word")
    title = models.CharField(max_length=500, blank=True, null=True)
    
    # Dastur yoki brauzer nomi (masalan: "Google Chrome", "csgo.exe")
    app_name = models.CharField(max_length=255, db_index=True)
    
    # Agar brauzer bo'lsa, URL manzil saqlanadi (uzun bo'lishi mumkinligi uchun TextField)
    url = models.TextField(blank=True, null=True)
    
    # Shu oynada necha soniya faol bo'lganligi
    duration_seconds = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.computer.hostname} | {self.app_name} ({self.duration_seconds}s)"



class BlockedProcess(BaseModel):
    MATCH_CHOICES = (
        ('PROCESS', "O'zining nomi"),
        ('PARENT', "Ota jarayoni nomi"),
    )
    
    name = models.CharField(max_length=150, unique=True, help_text="Dastur nomi (.exe yozish shart emas), masalan: 'telegram'")
    match_type = models.CharField(max_length=10, choices=MATCH_CHOICES, default='PROCESS')
    
    description = models.TextField(blank=True, null=True, help_text="Nima sababdan taqiqlangani haqida izoh")
    
    blocked_count = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.name} ({self.get_match_type_display()})"


class ProcessAlertLog(BaseModel):
    computer = models.ForeignKey(Computer, on_delete=models.CASCADE, related_name='process_alerts')
    process_rule = models.ForeignKey(BlockedProcess, on_delete=models.CASCADE, related_name='alerts')
    
    app_name = models.CharField(max_length=255)
    full_path = models.TextField()
    attempts_count = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.computer.hostname} -> {self.app_name} ({self.attempts_count} marta)"

# --- CSV FAYLNI AVTOMATIK YANGILASH MANTIQI ---
def generate_process_blacklist_csv():
    media_path = settings.MEDIA_ROOT
    os.makedirs(media_path, exist_ok=True)
    file_path = os.path.join(media_path, 'process_blacklist.csv')
    
    # Faqat 4 ta ustun olinadi: 0=id, 1=name, 2=match_type, 3=description
    processes = BlockedProcess.objects.all().values_list(
        'id', 'name', 'match_type', 'description'
    )
    
    with open(file_path, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['id', 'name', 'match_type', 'description'])
        
        for proc in processes:
            # Xato chiqmasligi uchun faqat 4 ta indeks chaqiriladi (0, 1, 2, 3)
            writer.writerow([str(proc[0]), proc[1], proc[2], proc[3]])

@receiver(post_save, sender=BlockedProcess)
def update_process_csv_on_save(sender, instance, **kwargs):
    generate_process_blacklist_csv()

@receiver(post_delete, sender=BlockedProcess)
def update_process_csv_on_delete(sender, instance, **kwargs):
    generate_process_blacklist_csv()


class AppUsageStatistic(BaseModel):
    """
    Dasturlardan foydalanishning batafsil statistikasi (Mouse, Keyboard, Active vaqtlar)
    """
    computer = models.ForeignKey('endpoints.Computer', on_delete=models.CASCADE, related_name='app_usages')
    
    app_name = models.CharField(max_length=255, db_index=True)

    # Exe faylning to'liq yo'li — masalan "C:\Program Files\Google\Chrome\...\chrome.exe"
    # Agent ba'zi processlarga (SYSTEM, protected) ruxsati bo'lmasa bo'sh bo'lishi mumkin.
    full_path = models.CharField(
        max_length=500, blank=True, null=True,
        help_text="Exe faylning to'liq yo'li"
    )

    # Barcha vaqtlar soniyalarda (sekund) saqlanadi
    total_open_seconds = models.PositiveIntegerField(default=0, help_text="Umumiy ochiq turgan vaqt")
    active_seconds = models.PositiveIntegerField(default=0, help_text="Sof aktiv bo'lgan (fokusdagi) vaqt")
    mouse_active_seconds = models.PositiveIntegerField(default=0, help_text="Sichqoncha qimirlagan vaqt")
    keyboard_active_seconds = models.PositiveIntegerField(default=0, help_text="Klaviatura bosilgan vaqt")

    def __str__(self):
        return f"{self.computer.hostname} | {self.app_name} ({self.active_seconds}s aktiv)"


class ScreenShareSession(BaseModel):
    """
    Ekran ulashish jarayonini (sessiyasini) boshqaruvchi model
    """
    STATUS_CHOICES = (
        ('PENDING', 'Kutilmoqda (Agentga xabar ketdi)'),
        ('ACTIVE', 'Faol (Agent URL yubordi)'),
        ('CLOSED', 'Yopilgan / Yakunlangan'),
    )
    
    computer = models.ForeignKey('endpoints.Computer', on_delete=models.CASCADE, related_name='screen_sessions')
    
    # Qancha vaqt ruxsat berilgani (soniyada)
    requested_duration = models.PositiveIntegerField(default=300)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    # Agent o'zining ekranini uzatayotgan aniq manzil (URL)
    stream_url = models.URLField(max_length=500, blank=True, null=True)

    def __str__(self):
        return f"{self.computer.hostname} - {self.status}"


# ============================================================
# SCREENSHOT — admin qo'lda button bosganda agent bir marta rasm oladi
# ============================================================

def _screenshot_upload_path(instance, filename):
    """Yil/oy/computer.id/uuid.jpg strukturasi (media/screenshots/2026/06/...)"""
    from datetime import datetime
    now = datetime.now()
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'jpg'
    return f"screenshots/{now.year}/{now.month:02d}/{instance.computer_id}/{instance.id}.{ext}"


class ScreenshotRequest(BaseModel):
    """
    Har bir 'Screenshot ol' bosishi shu yerga yoziladi.
    Kim (admin), qachon, qaysi kompyuterda — audit trail.
    """
    STATUS_CHOICES = (
        ('PENDING',  'Kutilmoqda'),
        ('DELIVERED','Agent qabul qildi'),
        ('COMPLETED','Rasm keldi'),
        ('FAILED',   'Xato'),
    )

    computer = models.ForeignKey(
        'endpoints.Computer', on_delete=models.CASCADE,
        related_name='screenshot_requests'
    )
    requested_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='screenshot_requests',
        help_text="Qaysi admin so'ragan (audit uchun)"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    # Rasm — agent yuklab qo'yadi, DB'da FileField sifatida saqlanadi
    image = models.ImageField(
        upload_to=_screenshot_upload_path, blank=True, null=True,
        help_text="Agent tomonidan yuborilgan screenshot"
    )
    delivered_at = models.DateTimeField(null=True, blank=True, help_text="Agent qabul qilgan vaqt")
    completed_at = models.DateTimeField(null=True, blank=True, help_text="Rasm yuklangan vaqt")
    error_message = models.TextField(blank=True, default='')

    # Ixtiyoriy izoh (kelgusi kengaytmalar uchun)
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['computer', '-created_at']),
        ]

    def __str__(self):
        who = self.requested_by.username if self.requested_by else 'anonymous'
        return f"{self.computer.hostname} — {who} ({self.status})"


# ============================================================
# LOG REQUEST — admin agent'ning result.log faylini so'raydi
# ============================================================

def _log_upload_path(instance, filename):
    from datetime import datetime
    now = datetime.now()
    return f"agent_logs/{now.year}/{now.month:02d}/{instance.computer_id}/{instance.id}.log"


class LogRequest(BaseModel):
    """
    Har bir 'Log so'rash' bosishi shu yerga yoziladi.
    Agent shifrlangan result.log faylini yuklaydi — admin uni yuklab olib
    nigoh-log-decrypt.ps1 skripti bilan ochadi.
    """
    STATUS_CHOICES = (
        ('PENDING',   'Kutilmoqda'),
        ('DELIVERED', 'Agent qabul qildi'),
        ('COMPLETED', 'Log keldi'),
        ('FAILED',    'Xato'),
    )

    computer = models.ForeignKey(
        'endpoints.Computer', on_delete=models.CASCADE,
        related_name='log_requests'
    )
    requested_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='log_requests',
        help_text="Qaysi admin so'ragan (audit uchun)"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    log_file = models.FileField(
        upload_to=_log_upload_path, blank=True, null=True,
        help_text="Agent yuborgan shifrlangan result.log"
    )
    log_size_bytes = models.PositiveIntegerField(default=0, help_text="Fayl hajmi (bayt)")
    delivered_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['computer', '-created_at'])]
        verbose_name = "Log so'rovi"
        verbose_name_plural = "Log so'rovlari"

    def __str__(self):
        who = self.requested_by.username if self.requested_by else 'anonymous'
        return f"{self.computer.hostname} — {who} ({self.status})"


# ============================================================
# BROADCAST — 1 input → N outputs ekran ulashish
# (input screen_share.exe ishga tushiradi, output'lar brauzerdan URL'ga o'tadi)
# ============================================================

class BroadcastSession(BaseModel):
    STATUS_CHOICES = (
        ('PENDING',  'Kutilmoqda (input URL yubormagan)'),
        ('ACTIVE',   'Faol (barcha output URL oldi)'),
        ('CLOSED',   'Yakunlangan'),
        ('FAILED',   'Xato'),
    )

    author = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='broadcast_sessions'
    )
    input_computer = models.ForeignKey(
        'endpoints.Computer', on_delete=models.CASCADE,
        related_name='broadcast_as_input',
        help_text="Ekranini uzatuvchi PC (screen_share.exe shu yerda ishga tushadi)"
    )
    output_computers = models.ManyToManyField(
        'endpoints.Computer', related_name='broadcast_as_output',
        blank=True,
        help_text="Ekranni ko'rsatuvchi PClar (brauzerdan URL'ga o'tishadi)"
    )
    duration = models.PositiveIntegerField(default=1800, help_text="Sessiya davomiyligi (sek)")
    stream_url = models.URLField(max_length=500, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Broadcast: {self.input_computer.hostname} → {self.output_computers.count()} outputs"


# ============================================================
# APP ICON — dastur nomiga logotip biriktirish
# Frontend Ilovalar statistikasi va Faollik tarixi jadvallarida
# hamda chartda ishlatiladi. Agar DB da mavjud bo'lmasa — JS
# ichidagi kod mashhur ilovalar uchun avtomatik chiqaradi.
# ============================================================

def _app_icon_upload_path(instance, filename):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'png'
    safe = ''.join(c for c in instance.name.lower() if c.isalnum() or c in '-_')[:40] or 'icon'
    return f"app_icons/{safe}.{ext}"


class AppIcon(BaseModel):
    """Admin panel orqali qo'lda qo'shiladigan dastur logotiplari."""
    name = models.CharField(
        max_length=100, unique=True, db_index=True,
        help_text="Dastur nomi (.exe qo'shish shart emas). Masalan: chrome, telegram, msedge"
    )
    icon = models.ImageField(
        upload_to=_app_icon_upload_path,
        help_text="PNG/JPG/SVG rasmni yuklang"
    )

    class Meta:
        ordering = ['name']
        verbose_name = "Dastur logotipi"
        verbose_name_plural = "Dastur logotiplari"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Nomni oddiy ko'rinishga keltiramiz — lowercase, .exe olib tashlanadi
        if self.name:
            self.name = self.name.strip().lower()
            if self.name.endswith('.exe'):
                self.name = self.name[:-4]
        super().save(*args, **kwargs)


# ============================================================
# URLGeoCache — domain -> IP -> geo cache
# ActivityLog dagi URL lar qayerga chiqishini xaritada ko'rsatish uchun.
# Har bir domain uchun bir marta hal qilinadi va cache lanadi.
# ============================================================
class URLGeoCache(BaseModel):
    domain = models.CharField(max_length=255, unique=True, db_index=True)
    ip = models.CharField(max_length=45, blank=True, default='')
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    country = models.CharField(max_length=100, blank=True, default='')
    country_code = models.CharField(max_length=8, blank=True, default='')
    city = models.CharField(max_length=100, blank=True, default='')
    org = models.CharField(max_length=200, blank=True, default='')
    resolved_at = models.DateTimeField(null=True, blank=True)
    failed = models.BooleanField(default=False, help_text="DNS/geo hal qilinmaganda True")

    class Meta:
        ordering = ['domain']
        verbose_name = "URL geo cache"
        verbose_name_plural = "URL geo cache"

    def __str__(self):
        loc = f"{self.city}, {self.country}" if self.city else self.country
        return f"{self.domain} → {self.ip or '—'} ({loc or '—'})"
