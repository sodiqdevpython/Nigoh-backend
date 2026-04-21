import json
from django.urls import reverse
from django.contrib import admin, messages
from django.shortcuts import render
from django.http import HttpResponseRedirect
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import Group, Computer

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
    list_display = ('hostname', 'bios_uuid', 'group', 'is_online', 'last_seen')
    list_filter = ('is_online', 'group')
    search_fields = ('hostname', 'bios_uuid')
    
    # Yangi dinamik harakatni ro'yxatga qo'shamiz
    actions = ['send_custom_command']

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
                    async_to_sync(channel_layer.group_send)(
                        f'pc_{pc.bios_uuid}',
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