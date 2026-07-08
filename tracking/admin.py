from django.contrib import admin
from .models import (
    BlockedURL, BlockedAttemptLog, ActivityLog, BlockedProcess, ProcessAlertLog,
    AppUsageStatistic, ScreenShareSession, RemoteControlSession,
    ScreenshotRequest, BroadcastSession, AppIcon, LogRequest
)
from django.utils.html import format_html
import hashlib
from datetime import datetime
from django.http import HttpResponseRedirect
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import BroadcastComputer
from django.shortcuts import render


# ============================================================
# SCREENSHOT AUDIT — kim, qachon, qaysi PC'dan
# ============================================================
@admin.register(ScreenshotRequest)
class ScreenshotRequestAdmin(admin.ModelAdmin):
    list_display = ('computer', 'requested_by', 'status', 'preview', 'created_at', 'completed_at')
    list_filter = ('status', 'created_at')
    search_fields = ('computer__hostname', 'computer__device_id', 'requested_by__username')
    readonly_fields = ('computer', 'requested_by', 'status', 'image', 'delivered_at',
                       'completed_at', 'error_message', 'preview_large',
                       'created_at', 'updated_at')
    fields = ('computer', 'requested_by', 'status', 'preview_large',
              'delivered_at', 'completed_at', 'error_message',
              'created_at', 'updated_at')

    def has_add_permission(self, request):
        return False  # Faqat agent tomonidan yaratiladi

    def preview(self, obj):
        if obj.image:
            return format_html(
                '<a href="{0}" target="_blank"><img src="{0}" style="max-height:60px;max-width:120px;border:1px solid #444"/></a>',
                obj.image.url
            )
        return '—'
    preview.short_description = "Ko'rinishi"

    def preview_large(self, obj):
        if obj.image:
            return format_html(
                '<a href="{0}" target="_blank"><img src="{0}" style="max-width:800px;border:1px solid #444"/></a>',
                obj.image.url
            )
        return 'Rasm hali yuklanmagan'
    preview_large.short_description = "To'liq rasm"


@admin.register(LogRequest)
class LogRequestAdmin(admin.ModelAdmin):
    list_display = ('computer', 'requested_by', 'status', 'size_display', 'download_link',
                    'created_at', 'completed_at')
    list_filter = ('status', 'created_at')
    search_fields = ('computer__hostname', 'computer__device_id', 'requested_by__username')
    readonly_fields = ('computer', 'requested_by', 'status', 'log_file', 'log_size_bytes',
                       'delivered_at', 'completed_at', 'error_message', 'download_link',
                       'created_at', 'updated_at')
    fields = ('computer', 'requested_by', 'status', 'download_link', 'log_size_bytes',
              'delivered_at', 'completed_at', 'error_message', 'created_at', 'updated_at')

    def has_add_permission(self, request):
        return False  # faqat frontend "Log so'rash" tugmasidan yaratiladi

    def size_display(self, obj):
        if obj.log_size_bytes:
            return f"{obj.log_size_bytes / 1024:.1f} KB"
        return '—'
    size_display.short_description = "Hajmi"

    def download_link(self, obj):
        if obj.log_file:
            return format_html(
                '<a href="{0}" download style="color:#4ade80;font-weight:bold">⬇ Yuklab olish</a>',
                obj.log_file.url
            )
        return '—'
    download_link.short_description = "Log fayl"


@admin.register(BroadcastSession)
class BroadcastSessionAdmin(admin.ModelAdmin):
    list_display = ('input_computer', 'output_count', 'author', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('input_computer__hostname', 'author__username')
    readonly_fields = ('stream_url', 'created_at', 'updated_at')
    filter_horizontal = ('output_computers',)

    def output_count(self, obj):
        return obj.output_computers.count()
    output_count.short_description = "Chiquvchi PClar soni"

@admin.register(BlockedURL)
class BlockedURLAdmin(admin.ModelAdmin):
    # Ro'yxatda nimalar ko'rinishi
    list_display = ('url_address', 'visit_count', 'created_at')
    
    # Qidiruv oynasi (URL bo'yicha)
    search_fields = ('url_address',)


@admin.register(BlockedAttemptLog)
class BlockedAttemptLogAdmin(admin.ModelAdmin):
    # Ro'yxatda nimalar ko'rinishi (PC nomi, URL va vaqti)
    list_display = ('computer', 'url', 'created_at')
    
    # O'ng tomonda PC va vaqt bo'yicha filterlar
    # list_filter = ('url', 'computer', 'created_at')
    
    # Qidiruv tizimi
    search_fields = ('computer__hostname', 'computer__bios_uuid', 'url__url_address')
    
    # Tarixni hech kim qo'lda o'zgartira olmasligi uchun
    readonly_fields = ('computer', 'url', 'id', 'created_at', 'updated_at')


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('computer', 'app_name', 'title', 'duration_seconds', 'created_at')
    
    # Qidiruv
    search_fields = ('computer__hostname', 'computer__bios_uuid', 'title', 'app_name', 'url')
    
    readonly_fields = ('computer', 'title', 'app_name', 'url', 'duration_seconds', 'id', 'created_at', 'updated_at')


@admin.register(BlockedProcess)
class BlockedProcessAdmin(admin.ModelAdmin):
    # default_reason o'rniga description qo'shildi
    list_display = ('name', 'match_type', 'blocked_count', 'description')
    # list_filter = ('match_type',)
    search_fields = ('name', 'description')
    readonly_fields = ('blocked_count', 'id', 'created_at', 'updated_at')

@admin.register(ProcessAlertLog)
class ProcessAlertLogAdmin(admin.ModelAdmin):
    list_display = ('computer', 'process_rule', 'app_name', 'attempts_count', 'created_at')
    # list_filter = ('app_name', 'process_rule', 'computer', 'created_at')
    search_fields = ('computer__hostname', 'computer__bios_uuid', 'app_name', 'full_path', 'process_rule__name')
    readonly_fields = ('computer', 'process_rule', 'app_name', 'full_path', 'attempts_count', 'id', 'created_at', 'updated_at')

@admin.register(AppUsageStatistic)
class AppUsageStatisticAdmin(admin.ModelAdmin):
    list_display = (
        'computer', 'app_name', 'total_open_seconds', 
        'active_seconds', 'mouse_active_seconds', 'keyboard_active_seconds', 'created_at'
    )
    # list_filter = ('app_name', 'computer', 'created_at')
    search_fields = ('computer__hostname', 'computer__bios_uuid', 'app_name')
    readonly_fields = (
        'computer', 'app_name', 'total_open_seconds', 
        'active_seconds', 'mouse_active_seconds', 'keyboard_active_seconds', 
        'id', 'created_at', 'updated_at'
    )

def get_secure_token():
    secret_word = "sodiq2005.py"
    today = datetime.now().strftime("%Y-%m-%d")
    raw_string = f"{secret_word}-{today}"
    return hashlib.sha256(raw_string.encode()).hexdigest()

@admin.register(ScreenShareSession)
class ScreenShareSessionAdmin(admin.ModelAdmin):
    list_display = ('computer', 'status', 'stream_link', 'requested_duration', 'created_at')
    # list_filter = ('status', 'created_at')
    search_fields = ('computer__hostname', 'computer__bios_uuid', 'stream_url')
    readonly_fields = (
        'computer', 'requested_duration', 'status', 
        'stream_url', 'id', 'created_at', 'updated_at'
    )

    def stream_link(self, obj):
        if obj.status == 'ACTIVE' and obj.stream_url:
            # 1. Agent yuborgan ma'lumotdan faqat toza IP ni ajratib olamiz
            # (Agar agent http:// yoki port qo'shib yuborgan bo'lsa ham tozalab tashlaydi)
            clean_ip = obj.stream_url.replace('http://', '').replace('https://', '').split(':')[0].split('/')[0]
            
            # 2. Xavfsiz tokenni chaqiramiz
            token = get_secure_token()
            
            # 3. Yakuniy, mutlaqo to'g'ri va xavfsiz manzilni yig'amiz
            final_url = f"http://{clean_ip}:5004/{token}"
            
            return format_html(
                '<a href="{}" target="_blank" style="color: blue; font-weight: bold; text-decoration: underline;"> Ekranni ko\'rish</a>', 
                final_url
            )
        return "Kutilmoqda..."
    
    stream_link.short_description = 'Stream URL (Havola)'



@admin.action(description="Tanlanganlarga ekranni tarqatish (Broadcast)")
def broadcast_screen_action(modeladmin, request, queryset):
    # Agar O'qituvchi formani to'ldirib jo'natgan bo'lsa
    if 'apply' in request.POST:
        stream_url = request.POST.get('stream_url')
        duration = request.POST.get('duration', '300')
        
        channel_layer = get_channel_layer()
        
        for computer in queryset:
            group_name = f"pc_{computer.bios_uuid}"
            
            # Agent kutayotgan aniq xabar formati
            command_payload = {
                "type": "do_command",
                "action": f"start chrome --app={stream_url}",
                "payload": {
                    "stream_url": stream_url # Agent ulanishi uchun URL ni shu yerga beramiz
                }
            }

            # Socketga xabar otish
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    "type": "execute_command", 
                    "data": command_payload
                }
            )
        
        # Muvaffaqiyatli jo'natilgach, Yashil rangli yozuv chiqaramiz
        modeladmin.message_user(request, f"Muvaqqafiyatli! {queryset.count()} ta kompyuterga ekran tarqatish buyrug'i yuborildi.")
        return HttpResponseRedirect(request.get_full_path())
    
    # Agar forma hali to'ldirilmagan bo'lsa (Endi bosgan payti), HTML ni ochamiz
    return render(request, 'admin/broadcast_screen_form.html', context={'computers': queryset})


# --- MAXSUS BO'LIMNI REGISTRATSIYA QILISH ---
@admin.register(BroadcastComputer)
class BroadcastComputerAdmin(admin.ModelAdmin):
    # ip_address olib tashlandi, o'rniga bios_uuid qo'yildi
    list_display = ('hostname', 'bios_uuid', 'is_online') 
    
    list_filter = ('is_online',) 
    
    # Qidiruv tizimidan ham ip_address olib tashlandi
    search_fields = ('hostname', 'bios_uuid')
    
    actions = [broadcast_screen_action]

    def has_add_permission(self, request):
        return False



@admin.register(RemoteControlSession)
class RemoteControlSessionAdmin(admin.ModelAdmin):
    list_display = ('computer', 'author', 'is_active', 'remote_link', 'duration', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('computer__hostname', 'author__username')
    readonly_fields = ('computer', 'author', 'duration', 'is_active', 'stream_url', 'created_at', 'updated_at')

    def remote_link(self, obj):
        # Faqat aktiv bo'lsa va url mavjud bo'lsa
        if obj.is_active and obj.stream_url:
            # IP ni tozalab olamiz
            clean_ip = obj.stream_url.replace('http://', '').replace('https://', '').split(':')[0].split('/')[0]
            
            # Tokenni yasaymiz
            token = get_secure_token()
            
            # PORT 5003 qilib yangi ulanish yig'amiz
            final_url = f"http://{clean_ip}:5003/{token}"
            
            return format_html(
                '<a href="{}" target="_blank" style="color: #d9534f; font-weight: bold; text-decoration: underline;">🎮 Boshqarish</a>', 
                final_url
            )
        return "Kutilmoqda..."
    
    remote_link.short_description = 'Boshqaruv Havolasi'


# ============================================================
# APP ICON — dastur logotiplarini qo'lda boshqarish
# ============================================================
@admin.register(AppIcon)
class AppIconAdmin(admin.ModelAdmin):
    list_display = ('name', 'preview', 'created_at')
    search_fields = ('name',)
    readonly_fields = ('preview_large', 'created_at', 'updated_at')
    fields = ('name', 'icon', 'preview_large', 'created_at', 'updated_at')

    def preview(self, obj):
        if obj.icon:
            return format_html(
                '<img src="{}" style="width:24px;height:24px;object-fit:contain;background:rgba(0,0,0,0.05);border-radius:4px;padding:2px;">',
                obj.icon.url,
            )
        return '—'
    preview.short_description = 'Logo'

    def preview_large(self, obj):
        if obj.icon:
            return format_html(
                '<img src="{}" style="width:96px;height:96px;object-fit:contain;background:rgba(0,0,0,0.05);border-radius:8px;padding:6px;">',
                obj.icon.url,
            )
        return '—'
    preview_large.short_description = 'Ko\'rinishi'

