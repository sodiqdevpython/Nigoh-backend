from django.contrib import admin, messages
from django.utils.html import format_html

from endpoints.models import Computer
from .models import PendingCommand, Release, UpdateFile, UpdateLog
from .services import trigger_uninstall, trigger_update


class UpdateFileInline(admin.TabularInline):
    """ZIP ochilgandan keyin fayllar bu yerda ko'rinadi (faqat o'qish)."""
    model = UpdateFile
    extra = 0
    fields = ['rel_path', 'sha256_short', 'size_display', 'file']
    readonly_fields = ['rel_path', 'sha256_short', 'size_display', 'file']
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def sha256_short(self, obj):
        return obj.sha256[:16] + '...' if obj.sha256 else '—'
    sha256_short.short_description = 'SHA256'

    def size_display(self, obj):
        if obj.size > 1024 * 1024:
            return f"{obj.size / 1024 / 1024:.1f} MB"
        if obj.size > 1024:
            return f"{obj.size / 1024:.1f} KB"
        return f"{obj.size} B"
    size_display.short_description = 'Hajmi'


@admin.register(Release)
class ReleaseAdmin(admin.ModelAdmin):
    list_display = [
        'target', 'version', 'is_active',
        'file_count', 'total_size_display', 'created_at',
    ]
    list_filter = ['target', 'is_active']
    list_editable = ['is_active']
    search_fields = ['version', 'notes']
    inlines = [UpdateFileInline]
    actions = ['push_to_all_now']

    fieldsets = (
        (None, {
            'description': "Nigoh uchun xohlagancha Release yaratsa bo'ladi, lekin faqat BITTASI 'active' bo'la oladi. "
                           "Watchdog faqat 1 marta yaratiladi va u boshqa qayta yaratmaydi.",
            'fields': ('target', 'version', 'notes'),
        }),
        ('ZIP yuklash', {
            'description': "ZIP faylni yuklang — backend o'zi ochadi va fayllarni ajratadi.",
            'fields': ('zip_file',),
        }),
        ('Holat', {
            'description': "Aktiv qilingani yangi o'rnatishlar va yangilanishlar uchun ishlatiladi.",
            'fields': ('is_active',),
        }),
        ("Manifest (avtomatik to'ldiriladi)", {
            'classes': ('collapse',),
            'fields': ('manifest',),
        }),
    )

    def file_count(self, obj):
        count = obj.files.count()
        return count or '—'
    file_count.short_description = 'Fayllar'

    def total_size_display(self, obj):
        manifest = obj.manifest or {}
        size = manifest.get('total_size', 0)
        if size > 1024 * 1024:
            return f"{size / 1024 / 1024:.1f} MB"
        if size > 1024:
            return f"{size / 1024:.1f} KB"
        return '—'
    total_size_display.short_description = 'Hajmi'

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        # ZIP yuklangan bo'lsa — ochib, fayllarni yaratamiz
        if obj.zip_file and 'zip_file' in form.changed_data:
            try:
                obj.extract_zip_and_create_files()
                file_count = obj.files.count()
                deleted = (obj.manifest or {}).get('deleted_files', [])
                msg = f"ZIP muvaffaqiyatli ochildi: {file_count} ta fayl yaratildi."
                if deleted:
                    msg += f" {len(deleted)} ta fayl o'chirilgan (oldingi versiyaga nisbatan)."
                self.message_user(request, msg, level=messages.SUCCESS)
            except Exception as e:
                self.message_user(
                    request,
                    f"ZIP ochishda xatolik: {e}",
                    level=messages.ERROR,
                )

    @admin.action(description="Barcha online agentlarga zudlik bilan yuborish (force)")
    def push_to_all_now(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Faqat bitta Release tanlang", level=messages.ERROR)
            return
        release = queryset.first()
        if not release.files.exists():
            self.message_user(request, "Bu Release da fayllar yo'q!", level=messages.ERROR)
            return
        count = 0
        for computer in Computer.objects.filter(is_online=True):
            trigger_update(computer, release, force=True)
            count += 1
        self.message_user(request, f"{count} ta agentga yuborildi", level=messages.SUCCESS)


@admin.register(PendingCommand)
class PendingCommandAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'computer', 'action', 'release',
        'status_display', 'attempts_display',
        'delivered_at', 'acknowledged_at',
    ]
    list_filter = ['action', 'success']
    search_fields = ['computer__hostname', 'computer__device_id']
    readonly_fields = ['delivered_at', 'acknowledged_at', 'attempts']

    def status_display(self, obj):
        if obj.acknowledged_at and obj.success:
            return format_html('<span style="color:#28a745">✓ Tugadi</span>')
        if obj.acknowledged_at and obj.success is False:
            if obj.attempts >= obj.MAX_ATTEMPTS:
                return format_html('<span style="color:#dc3545">✗ Bekor (5 urinish)</span>')
            return format_html('<span style="color:#dc3545">✗ Xato</span>')
        if obj.attempts >= obj.MAX_ATTEMPTS:
            return format_html('<span style="color:#dc3545">✗ Bekor</span>')
        if obj.attempts > 0:
            return format_html('<span style="color:#ffc107">⟳ Qayta urinish</span>')
        return format_html('<span style="color:#6c757d">⏳ Kutmoqda</span>')
    status_display.short_description = 'Holat'

    def attempts_display(self, obj):
        return f"{obj.attempts}/{obj.MAX_ATTEMPTS}"
    attempts_display.short_description = 'Urinishlar'


@admin.register(UpdateLog)
class UpdateLogAdmin(admin.ModelAdmin):
    list_display = ['computer', 'target', 'from_version', 'to_version', 'success', 'created_at']
    list_filter = ['target', 'success']
    search_fields = ['computer__hostname', 'computer__device_id', 'to_version']
    readonly_fields = ['created_at', 'updated_at']
