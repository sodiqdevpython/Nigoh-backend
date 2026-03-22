import csv
import os
from django.db import models
from django.conf import settings
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from utils.models import BaseModel
from endpoints.models import Computer

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
    """
    Taqiqlangan dasturlar ro'yxati (Keyword yoki Directory).
    Agent shu qoidalarga qarab jarayonlarni yopadi.
    """
    MATCH_CHOICES = (
        ('KEYWORD', 'Nom bo\'yicha (Keyword)'),
        ('DIRECTORY', 'Papkasi bo\'yicha (Directory)'),
    )
    
    name = models.CharField(max_length=150, help_text="Qoida nomi, masalan: 'CS:GO O'yini' yoki 'Telegram'")
    match_type = models.CharField(max_length=10, choices=MATCH_CHOICES, default='KEYWORD')
    rule_value = models.CharField(max_length=500, unique=True)
    default_reason = models.CharField(max_length=255, blank=True, null=True)
    
    # Bu dastur guruh bo'ylab umumiy necha marta bloklanganini sanaymiz
    blocked_count = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.name} ({self.get_match_type_display()}: {self.rule_value})"


class ProcessAlertLog(BaseModel):
    """
    Agent taqiqlangan dasturni yopganda yuboradigan Alert (xabar).
    """
    computer = models.ForeignKey(Computer, on_delete=models.CASCADE, related_name='process_alerts')
    process_rule = models.ForeignKey(BlockedProcess, on_delete=models.CASCADE, related_name='alerts')
    
    app_name = models.CharField(max_length=255) # Aynan qaysi dastur yopildi
    full_path = models.TextField()              # Qayerdan ushlandi
    attempts_count = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.computer.hostname} -> {self.app_name} ({self.attempts_count} marta)"



# --- CSV FAYLNI AVTOMATIK YANGILASH MANTIQI (Process uchun) ---

def generate_process_blacklist_csv():
    """Bazada bor barcha taqiqlangan jarayonlarni CSV qilib yozadi"""
    media_path = settings.MEDIA_ROOT
    os.makedirs(media_path, exist_ok=True)
    file_path = os.path.join(media_path, 'process_blacklist.csv')
    
    processes = BlockedProcess.objects.all().values_list(
        'id', 'name', 'match_type', 'rule_value', 'default_reason'
    )
    
    with open(file_path, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['id', 'name', 'match_type', 'rule_value', 'default_reason'])
        for proc in processes:
            writer.writerow([str(proc[0]), proc[1], proc[2], proc[3], proc[4]])

@receiver(post_save, sender=BlockedProcess)
def update_process_csv_on_save(sender, instance, **kwargs):
    generate_process_blacklist_csv()

@receiver(post_delete, sender=BlockedProcess)
def update_process_csv_on_delete(sender, instance, **kwargs):
    generate_process_blacklist_csv()