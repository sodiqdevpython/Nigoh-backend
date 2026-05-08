import json
import os
import asyncpg
from channels.generic.websocket import AsyncWebsocketConsumer

# DB ga saqlanmaydi — faqat xotirada yashaydi
LIVE_METRICS = {}

# asyncpg connection pool (bir marta yaratiladi, thread kerak emas)
_pool = None


async def get_pool():
    """Lazy-init asyncpg pool — pure async, zero threads."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=os.environ.get('DB_HOST', 'db'),
            port=int(os.environ.get('DB_PORT', 5432)),
            database=os.environ.get('DB_NAME'),
            user=os.environ.get('DB_USER'),
            password=os.environ.get('DB_PASSWORD'),
            min_size=2,
            max_size=10,
        )
    return _pool


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

    # --- Pure async DB (asyncpg) — thread SHART EMAS ---

    async def get_computer_group_id(self):
        try:
            pool = await get_pool()
            row = await pool.fetchrow(
                'SELECT group_id FROM endpoints_computer WHERE bios_uuid = $1',
                str(self.bios_uuid)
            )
            return row['group_id'] if row else None
        except Exception as e:
            print(f"[get_group_id xato] {e}")
            return None

    async def set_online_status(self, is_online):
        try:
            pool = await get_pool()
            await pool.execute(
                '''UPDATE endpoints_computer
                      SET is_online = $1, last_seen = NOW()
                    WHERE bios_uuid = $2''',
                is_online, str(self.bios_uuid)
            )
        except Exception as e:
            print(f"[set_online xato] {e}")

    async def touch_last_seen(self):
        try:
            pool = await get_pool()
            await pool.execute(
                'UPDATE endpoints_computer SET last_seen = NOW() WHERE bios_uuid = $1',
                str(self.bios_uuid)
            )
        except Exception as e:
            print(f"[touch_last_seen xato] {e}")
