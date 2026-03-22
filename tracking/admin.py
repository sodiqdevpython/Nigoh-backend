from django.contrib import admin
from .models import BlockedURL, BlockedAttemptLog, ActivityLog, BlockedProcess, ProcessAlertLog

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
    list_filter = ('url', 'computer', 'created_at')
    
    # Qidiruv tizimi
    search_fields = ('computer__hostname', 'computer__bios_uuid', 'url__url_address')
    
    # Tarixni hech kim qo'lda o'zgartira olmasligi uchun
    readonly_fields = ('computer', 'url', 'id', 'created_at', 'updated_at')


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('computer', 'app_name', 'title', 'duration_seconds', 'created_at')
    
    # O'ng tomondan dastur nomi yoki kompyuter bo'yicha tezkor filtr
    list_filter = ('app_name', 'computer', 'created_at')
    
    # Qidiruv
    search_fields = ('computer__hostname', 'computer__bios_uuid', 'title', 'app_name', 'url')
    
    readonly_fields = ('computer', 'title', 'app_name', 'url', 'duration_seconds', 'id', 'created_at', 'updated_at')


@admin.register(BlockedProcess)
class BlockedProcessAdmin(admin.ModelAdmin):
    # 'blocked_count' ni ro'yxatga qo'shdik
    list_display = ('name', 'match_type', 'rule_value', 'blocked_count', 'default_reason')
    list_filter = ('match_type',)
    search_fields = ('name', 'rule_value', 'default_reason')
    # Hisoblagichni qo'lda o'zgartirib bo'lmaydigan qildik
    readonly_fields = ('blocked_count', 'id', 'created_at', 'updated_at')

@admin.register(ProcessAlertLog)
class ProcessAlertLogAdmin(admin.ModelAdmin):
    # 'reason' olib tashlandi, o'rniga 'process_rule' (qoida) va 'app_name' (dastur nomi) qo'shildi
    list_display = ('computer', 'process_rule', 'app_name', 'attempts_count', 'created_at')
    list_filter = ('app_name', 'process_rule', 'computer', 'created_at')
    # Qidiruv tizimini ham yangiladik (process_rule__name orqali qoida nomidan izlaydi)
    search_fields = ('computer__hostname', 'computer__bios_uuid', 'app_name', 'full_path', 'process_rule__name')
    readonly_fields = ('computer', 'process_rule', 'app_name', 'full_path', 'attempts_count', 'id', 'created_at', 'updated_at')