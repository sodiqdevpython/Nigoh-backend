import json
from django.urls import reverse
from django.contrib import admin, messages
from django.shortcuts import render
from django.http import HttpResponseRedirect
from django.utils.html import format_html, mark_safe
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import Group, Computer, WhitelistedComputer
from .consumers import LIVE_METRICS
from commands.services import trigger_uninstall, trigger_update

# --- SOCKET ORQALI BUYRUQ YUBORISH FUNKSIYASI ---
def send_socket_command(room_name, action_name, extra_data=None):
    """Barcha joyda ishlatish uchun universal yuborgich"""
    channel_layer = get_channel_layer()
    payload = {'action': action_name}
    if extra_data:
        payload.update(extra_data)
        
    async_to_sync(channel_layer.group_send)(
        room_name,
        {
            'type': 'execute_command', # Consumer dagi funksiya nomi
            'data': payload
        }
    )

from django.contrib import admin
from .models import Group


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "building_display",
        "floor_display",
        "room_number",
        "created_at",
    )

    list_filter = (
        "building",
        "floor",
        "created_at",
    )

    search_fields = (
        "name",
        "room_number",
    )

    ordering = ("-created_at",)

    readonly_fields = ("created_at", "updated_at")

    # 🔥 Custom display methods
    def building_display(self, obj):
        return obj.get_building_display()
    building_display.short_description = "Bino"

    def floor_display(self, obj):
        return obj.get_floor_display()
    floor_display.short_description = "Qavat"


@admin.register(Computer)
class ComputerAdmin(admin.ModelAdmin):
    list_display = (
        'hostname', 'device_id_short', 'whitelist_badge',
        'agent_version', 'watchdog_version',
        'group', 'is_online',
        'cpu_display', 'ram_display', 'disk_display', 'network_display',
        'last_seen',
    )

    def whitelist_badge(self, obj):
        if obj.is_whitelisted:
            return format_html('<span style="color:#ff5252;font-weight:bold;">🔒 Whitelist</span>')
        return format_html('<span style="color:#4caf50;">Ochiq</span>')
    whitelist_badge.short_description = "Ko'rinish"
    list_filter = ('is_online', 'is_whitelisted', 'group', 'agent_version', 'watchdog_version')
    search_fields = ('hostname', 'bios_uuid', 'device_id')
    # is_whitelisted — WhitelistedComputer orqali boshqariladi, bu yerda faqat ko'rinadi
    readonly_fields = ('auth_token', 'last_version_report', 'last_seen', 'is_whitelisted')

    def device_id_short(self, obj):
        if obj.device_id:
            return obj.device_id[:12] + '...'
        return obj.bios_uuid or '—'
    device_id_short.short_description = 'Device ID'

    def _m(self, obj):
        # LIVE_METRICS device_id afzal, eski agentlar uchun bios_uuid bilan ham tekshiriladi
        return LIVE_METRICS.get(obj.device_id) or LIVE_METRICS.get(obj.bios_uuid)

    def cpu_display(self, obj):
        m = self._m(obj)
        if not m:
            return '—'
        v = m['cpu']
        color = '#f44336' if v > 90 else '#FF9800' if v > 70 else '#2196F3'
        return format_html('<span style="color:{}">{} %</span>', color, v)
    cpu_display.short_description = 'CPU'

    def ram_display(self, obj):
        m = self._m(obj)
        if not m:
            return '—'
        mb = int(m.get('ram_used_mb', 0))
        return format_html('<span style="color:#9C27B0">{} MB</span>', mb)
    ram_display.short_description = 'RAM (ishl.)'

    def disk_display(self, obj):
        m = self._m(obj)
        if not m:
            return '—'
        drives = m.get('drives', [])
        parts  = []
        for d in drives:
            pct   = d.get('used_percent', 0)
            color = '#f44336' if pct > 90 else '#FF9800' if pct > 70 else '#4CAF50'
            parts.append(format_html(
                '<span style="color:{}">{}: {}/{} GB ({}%)</span>',
                color, d.get('letter', '?'),
                d.get('used_gb', 0), d.get('total_gb', 0), pct
            ))
        return mark_safe(' &nbsp;|&nbsp; '.join(str(p) for p in parts)) if parts else '—'
    disk_display.short_description = 'Disk'

    def network_display(self, obj):
        m = self._m(obj)
        if not m:
            return '—'
        return format_html('<span style="color:#009688">{} Kbps</span>', m['network'])
    network_display.short_description = 'Tarmoq'
    
    # Yangi dinamik harakatni ro'yxatga qo'shamiz.
    # Uninstall — faqat superuser uchun (asosiy frontendda ko'rinmaydi).
    actions = ['send_custom_command', 'trigger_active_update', 'force_uninstall_selected']

    def get_actions(self, request):
        actions = super().get_actions(request)
        # Uninstall — faqat superuser ko'radi. Bu action asosiy front web'ga
        # qo'shilmagan, faqat Django admin ichida.
        if not request.user.is_superuser and 'force_uninstall_selected' in actions:
            del actions['force_uninstall_selected']
        return actions

    @admin.action(description="Aktiv Nigoh release'ini yuborish (retry qo'shiladi)")
    def trigger_active_update(self, request, queryset):
        sent = 0
        errors = 0
        for computer in queryset:
            try:
                trigger_update(computer)  # aktiv release'ni avtomatik oladi
                sent += 1
            except ValueError as e:
                errors += 1
                self.message_user(request, str(e), level=messages.ERROR)
                break
            except Exception as e:
                errors += 1
                self.message_user(request, f"{computer.hostname}: {e}", level=messages.WARNING)
        if sent:
            self.message_user(
                request,
                f"{sent} ta agentga update navbatga qo'yildi (offline bo'lsa online bo'lganda yuboriladi)",
                level=messages.SUCCESS,
            )

    @admin.action(description="⚠️ TO'LIQ O'CHIRISH — agentni va Watchdog service ni o'chiradi")
    def force_uninstall_selected(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(
                request,
                "Bu amalni faqat superuser bajara oladi",
                level=messages.ERROR,
            )
            return
        sent = 0
        for computer in queryset:
            trigger_uninstall(computer)
            sent += 1
        self.message_user(
            request,
            f"{sent} ta agentga to'liq uninstall yuborildi (offline bo'lsa online bo'lganda bajariladi)",
            level=messages.SUCCESS,
        )

    @admin.action(description="Buyruq yuborish")
    def send_custom_command(self, request, queryset):
        if 'apply' in request.POST:
            cmd_type = request.POST.get('cmd_type')
            cmd_action = request.POST.get('cmd_action')
            cmd_message = request.POST.get('cmd_message', '')
            cmd_payload_str = request.POST.get('cmd_payload', '{}')

            try:
                cmd_payload = json.loads(cmd_payload_str) if cmd_payload_str else {}
            except json.JSONDecodeError:
                self.message_user(request, "Payload yaroqsiz JSON formatida! Xatoni to'g'irlang.", level=messages.ERROR)
                # 1-O'ZGARISH: Xato bo'lsa ro'yxatga qaytarish
                return HttpResponseRedirect(reverse('admin:endpoints_computer_changelist'))

            channel_layer = get_channel_layer()
            sent_count = 0
            
            for pc in queryset:
                if pc.is_online:
                    key = pc.device_id or pc.bios_uuid
                    if not key:
                        continue
                    async_to_sync(channel_layer.group_send)(
                        f'pc_{key}',
                        {
                            'type': 'execute_command',
                            'data': {
                                'type': cmd_type,
                                'action': cmd_action,
                                'message': cmd_message,
                                'payload': cmd_payload
                            }
                        }
                    )
                    sent_count += 1
            
            self.message_user(request, f"Maxsus buyruq {sent_count} ta Onlayn kompyuterga yetkazildi.", level=messages.SUCCESS)
            # 2-O'ZGARISH: Muvaffaqiyatli bo'lsa ro'yxatga qaytarish
            return HttpResponseRedirect(reverse('admin:endpoints_computer_changelist'))

        return render(request, 'admin/custom_command.html', context={'queryset': queryset})


# ============================================================
# WHITELIST — faqat superadmin ko'radi
# Ko'plab PC larni qo'shish uchun bu yerdan yozuv qo'shasiz.
# ComputerAdmin da search_fields = ('hostname', 'bios_uuid', 'device_id') bor —
# autocomplete_fields shu asosida select2 orqali qidiradi.
# ============================================================
@admin.register(WhitelistedComputer)
class WhitelistedComputerAdmin(admin.ModelAdmin):
    list_display = ('computer', 'note_short', 'added_by', 'created_at')
    search_fields = ('computer__hostname', 'computer__device_id', 'computer__bios_uuid', 'note')
    autocomplete_fields = ('computer',)
    readonly_fields = ('added_by', 'created_at', 'updated_at')
    fields = ('computer', 'note', 'added_by', 'created_at', 'updated_at')

    def note_short(self, obj):
        return (obj.note[:60] + '...') if obj.note and len(obj.note) > 60 else (obj.note or '—')
    note_short.short_description = 'Izoh'

    def save_model(self, request, obj, form, change):
        if not obj.added_by:
            obj.added_by = request.user
        super().save_model(request, obj, form, change)

    def has_module_permission(self, request):
        # Faqat superuser bu bo'limni ko'radi
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser