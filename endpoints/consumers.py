import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Computer

class ComputerConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.bios_uuid = self.scope['url_route']['kwargs']['bios_uuid']
        
        # 1. Shaxsiy xona (Aynan bitta PC uchun)
        self.pc_room_name = f'pc_{self.bios_uuid}'
        await self.channel_layer.group_add(self.pc_room_name, self.channel_name)

        # 2. Guruh xonasi (PC qaysi guruhda bo'lsa, o'sha guruh xonasiga kiradi)
        self.group_id = await self.get_computer_group_id()
        if self.group_id:
            self.group_room_name = f'group_{self.group_id}'
            await self.channel_layer.group_add(self.group_room_name, self.channel_name)
        else:
            self.group_room_name = None

        # 3. Barcha PC lar xonasi (Ommaviy buyruqlar uchun)
        self.all_pcs_room = 'all_pcs'
        await self.channel_layer.group_add(self.all_pcs_room, self.channel_name)

        # Holatni Onlayn qilish
        await self.set_online_status(is_online=True)
        await self.accept()
        print(f"[+] Ulandi: {self.bios_uuid} | Guruh: {self.group_id}")

    async def disconnect(self, close_code):
        # Uzilganda barcha xonalardan chiqaramiz
        await self.channel_layer.group_discard(self.pc_room_name, self.channel_name)
        await self.channel_layer.group_discard(self.all_pcs_room, self.channel_name)
        if self.group_room_name:
            await self.channel_layer.group_discard(self.group_room_name, self.channel_name)
        
        await self.set_online_status(is_online=False)
        print(f"[-] Uzildi: {self.bios_uuid}")

    async def receive(self, text_data):
        data = json.loads(text_data)
        print(f"[{self.bios_uuid}] dan javob/statistika: {data}")
        await self.update_last_seen()

    # --- ADMIN YUBORETGAN BUYRUQLARNI QABUL QILISH UCHUN EVENT HANDLER ---
    async def execute_command(self, event):
        """
        Admin paneldan kiritilgan barcha dinamik ma'lumotlarni agentga uzatamiz
        """
        data = event['data']
        
        # C# agentga siz kiritgan ma'lumotlarni aniq formatda yuboramiz
        await self.send(text_data=json.dumps({
            'type': data.get('type', 'command'),
            'action': data.get('action', ''),
            'message': data.get('message', ''),
            'payload': data.get('payload', {})
        }))

    # --- BAZA BILAN ISHLAYDIGAN FUNKSIYALAR ---
    @database_sync_to_async
    def get_computer_group_id(self):
        try:
            comp = Computer.objects.get(bios_uuid=self.bios_uuid)
            return comp.group_id if comp.group else None
        except Computer.DoesNotExist:
            return None

    @database_sync_to_async
    def set_online_status(self, is_online):
        try:
            comp = Computer.objects.get(bios_uuid=self.bios_uuid)
            comp.is_online = is_online
            comp.save()
        except Computer.DoesNotExist:
            pass

    @database_sync_to_async
    def update_last_seen(self):
        try:
            Computer.objects.filter(bios_uuid=self.bios_uuid).update()
            comp = Computer.objects.get(bios_uuid=self.bios_uuid)
            comp.save(update_fields=['last_seen'])
        except Computer.DoesNotExist:
            pass

