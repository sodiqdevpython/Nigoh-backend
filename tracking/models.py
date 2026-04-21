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

