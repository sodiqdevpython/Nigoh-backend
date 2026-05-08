import json
from django.utils import timezone
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Computer

# DB ga saqlanmaydi — faqat xotirada yashaydi
LIVE_METRICS = {}

class ComputerConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.bios_uuid = self.scope['url_route']['kwargs']['bios_uuid']

        self.pc_room_name = f'pc_{self.bios_uuid}'
        await self.channel_layer.group_add(self.pc_room_name, self.channel_name)

        self.group_id = await self.get_computer_group_id()
        if self.group_id:
            self.group_room_name = f'group_{self.group_id}'
            await self.channel_layer.group_add(self.group_room_name, self.channel_name)
        else:
            self.group_room_name = None

        self.all_pcs_room = 'all_pcs'
        await self.channel_layer.group_add(self.all_pcs_room, self.channel_name)

        await self.set_online_status(True)
        await self.accept()
        print(f"[+] Ulandi: {self.bios_uuid} | Guruh: {self.group_id}")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.pc_room_name, self.channel_name)
        await self.channel_layer.group_discard(self.all_pcs_room, self.channel_name)
        if self.group_room_name:
            await self.channel_layer.group_discard(self.group_room_name, self.channel_name)

        await self.set_online_status(False)
        LIVE_METRICS.pop(self.bios_uuid, None)
        print(f"[-] Uzildi: {self.bios_uuid}")

    async def receive(self, text_data):
        data = json.loads(text_data)

        if data.get('type') == 'metrics':
            payload = data.get('payload', {})
            LIVE_METRICS[self.bios_uuid] = {
                'cpu':         payload.get('cpu', 0),
                'ram_used_mb': payload.get('ram_used_mb', 0),
                'drives':      payload.get('drives', []),
                'network':     payload.get('network', 0),
            }
            # last_seen ni bitta query bilan yangilaymiz — thread tejash uchun
            await self.touch_last_seen()
            print(f"[{self.bios_uuid}] metrikalar: {LIVE_METRICS[self.bios_uuid]}")

    async def execute_command(self, event):
        data = event['data']
        await self.send(text_data=json.dumps({
            'type':    data.get('type', 'command'),
            'action':  data.get('action', ''),
            'message': data.get('message', ''),
            'payload': data.get('payload', {}),
        }))

    # --- DB FUNKSIYALAR (bitta query, minimum thread) ---

    @database_sync_to_async
    def get_computer_group_id(self):
        try:
            return Computer.objects.values_list('group_id', flat=True).get(bios_uuid=self.bios_uuid)
        except Computer.DoesNotExist:
            return None

    @database_sync_to_async
    def set_online_status(self, is_online):
        # Bitta UPDATE query — GET+SAVE yo'q
        Computer.objects.filter(bios_uuid=self.bios_uuid).update(
            is_online=is_online,
            last_seen=timezone.now(),
        )

    @database_sync_to_async
    def touch_last_seen(self):
        # Bitta UPDATE query — har 15s da chaqiriladi
        Computer.objects.filter(bios_uuid=self.bios_uuid).update(
            last_seen=timezone.now(),
        )
