import json
import os
import asyncpg
from channels.generic.websocket import AsyncWebsocketConsumer

# DB ga saqlanmaydi — faqat xotirada yashaydi
LIVE_METRICS = {}

# Har bir device_id uchun hozirgi faol channel_name saqlanadi.
# Stale disconnect() yangi ulanishni offline qilib qo'ymasligi uchun.
ACTIVE_CHANNELS = {}

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
        kwargs = self.scope['url_route']['kwargs']
        # Yangi agentlar device_id bilan ulanadi; eski agentlar — bios_uuid
        self.device_id = kwargs.get('device_id')
        self.bios_uuid = kwargs.get('bios_uuid')
        # Identifikatsiya kaliti — group nomi va xotira indeksi uchun
        self.key = self.device_id or self.bios_uuid
        self.group_room_name = None

        self.pc_room_name = f'pc_{self.key}'
        await self.channel_layer.group_add(self.pc_room_name, self.channel_name)

        # Agent yangi qurilma bo'lsa — avtomatik yaratiladi (404 emas)
        await self.ensure_computer_exists()

        self.group_id = await self.get_computer_group_id()
        if self.group_id:
            self.group_room_name = f'group_{self.group_id}'
            await self.channel_layer.group_add(self.group_room_name, self.channel_name)

        self.all_pcs_room = 'all_pcs'
        await self.channel_layer.group_add(self.all_pcs_room, self.channel_name)

        ACTIVE_CHANNELS[self.key] = self.channel_name

        await self.set_online_status(True)
        await self.accept()
        print(f"[+] Ulandi: {self.key} | Guruh: {self.group_id}")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.pc_room_name, self.channel_name)
        await self.channel_layer.group_discard(self.all_pcs_room, self.channel_name)
        if self.group_room_name:
            await self.channel_layer.group_discard(self.group_room_name, self.channel_name)

        if ACTIVE_CHANNELS.get(self.key) == self.channel_name:
            ACTIVE_CHANNELS.pop(self.key, None)
            await self.set_online_status(False)
            LIVE_METRICS.pop(self.key, None)

        print(f"[-] Uzildi: {self.key} | channel: {self.channel_name[:12]}...")

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return
        msg_type = data.get('type')

        if msg_type == 'metrics':
            payload = data.get('payload', {})
            LIVE_METRICS[self.key] = {
                'cpu':         payload.get('cpu', 0),
                'ram_used_mb': payload.get('ram_used_mb', 0),
                'drives':      payload.get('drives', []),
                'network':     payload.get('network', 0),
            }
            await self.touch_last_seen()
            print(f"[{self.key}] metrikalar: {LIVE_METRICS[self.key]}")
            return

        if msg_type == 'agent_info':
            await self.update_agent_info(
                agent_version=data.get('version'),
                watchdog_version=data.get('watchdog_version'),
                hostname=data.get('hostname'),
                bios_uuid=data.get('bios_uuid'),
            )
            print(f"[{self.key}] agent_info: v={data.get('version')} watchdog={data.get('watchdog_version')}")
            await self.push_pending_command_if_any()
            return

        if msg_type == 'update_progress':
            print(f"[{self.key}] update: {data.get('status')} — {data.get('message')}")
            return

    async def execute_command(self, event):
        """Admin panel yaratgan buyruqni agentga real-time uzatadi.

        MUHIM: data ichidagi BARCHA maydonlarni oldinga uzatamiz — force_update
        uchun target, version, manifest_url, command_id kabi maydonlar zarur.
        delivered_at yangilanadi, attempts oshadi. attempts >= 5 bo'lsa yubormaymiz.
        """
        data = event['data']
        cmd_id = data.get('command_id')

        # attempts >= 5 bo'lsa yubormaymiz (retry limitni backend ushlab turadi)
        if cmd_id:
            try:
                pool = await get_pool()
                row = await pool.fetchrow(
                    "SELECT attempts, acknowledged_at FROM commands_pendingcommand WHERE id = $1",
                    cmd_id
                )
                if row and (row['acknowledged_at'] is not None or (row['attempts'] or 0) >= 5):
                    print(f"[{self.key}] cmd={cmd_id} yuborilmadi (attempts={row['attempts']}, ack={row['acknowledged_at']})")
                    return
            except Exception as e:
                print(f"[execute_command tekshirish xato] {e}")

        await self.send(text_data=json.dumps(data))

        if cmd_id:
            try:
                pool = await get_pool()
                await pool.execute(
                    """UPDATE commands_pendingcommand
                          SET delivered_at = NOW(),
                              attempts     = attempts + 1
                        WHERE id = $1""",
                    cmd_id
                )
            except Exception as e:
                print(f"[execute_command delivered_at xato] {e}")

    # --- Pure async DB (asyncpg) — thread SHART EMAS ---

    def _id_filter(self):
        """Qaysi maydon bo'yicha qidirilishini qaytaradi (device_id afzal)."""
        if self.device_id:
            return 'device_id', self.device_id
        return 'bios_uuid', self.bios_uuid

    async def ensure_computer_exists(self):
        """Yangi qurilma birinchi marta ulansa — avtomatik yozuv yaratamiz."""
        if not self.device_id:
            return  # eski agentlar — register/ orqali avval kelishi kerak
        try:
            pool = await get_pool()
            # Avval mavjudligini tekshiramiz (oddiy INSERT auth_token NOT NULL bilan xato bermasin)
            row = await pool.fetchrow(
                'SELECT id FROM endpoints_computer WHERE device_id = $1',
                self.device_id
            )
            if row:
                return  # mavjud — INSERT shart emas

            # Yangi yozuv yaratamiz. auth_token endi NULLABLE.
            await pool.execute(
                '''INSERT INTO endpoints_computer
                       (id, device_id, hostname, is_online, last_seen, created_at, updated_at)
                   VALUES (gen_random_uuid(), $1, $2, FALSE, NOW(), NOW(), NOW())
                   ON CONFLICT (device_id) DO NOTHING''',
                self.device_id, 'unknown'
            )
        except Exception as e:
            print(f"[ensure_computer_exists xato] {e}")

    async def get_computer_group_id(self):
        try:
            pool = await get_pool()
            field, value = self._id_filter()
            row = await pool.fetchrow(
                f'SELECT group_id FROM endpoints_computer WHERE {field} = $1',
                str(value)
            )
            return row['group_id'] if row else None
        except Exception as e:
            print(f"[get_group_id xato] {e}")
            return None

    async def set_online_status(self, is_online):
        try:
            pool = await get_pool()
            field, value = self._id_filter()
            await pool.execute(
                f'''UPDATE endpoints_computer
                       SET is_online = $1, last_seen = NOW()
                     WHERE {field} = $2''',
                is_online, str(value)
            )
        except Exception as e:
            print(f"[set_online xato] {e}")

    async def touch_last_seen(self):
        try:
            pool = await get_pool()
            field, value = self._id_filter()
            await pool.execute(
                f'UPDATE endpoints_computer SET last_seen = NOW() WHERE {field} = $1',
                str(value)
            )
        except Exception as e:
            print(f"[touch_last_seen xato] {e}")

    async def update_agent_info(self, agent_version=None, watchdog_version=None,
                                hostname=None, bios_uuid=None):
        """`agent_info` xabari kelganda versiya/hostname ni yangilaymiz."""
        try:
            pool = await get_pool()
            field, value = self._id_filter()
            sets, params = [], []
            if agent_version:
                params.append(agent_version); sets.append(f"agent_version = ${len(params)}")
            if watchdog_version:
                params.append(watchdog_version); sets.append(f"watchdog_version = ${len(params)}")
            if hostname:
                params.append(hostname); sets.append(f"hostname = ${len(params)}")
            if bios_uuid:
                params.append(bios_uuid); sets.append(f"bios_uuid = ${len(params)}")
            sets.append("last_version_report = NOW()")
            sets.append("last_seen = NOW()")
            if not sets:
                return
            params.append(str(value))
            await pool.execute(
                f"UPDATE endpoints_computer SET {', '.join(sets)} WHERE {field} = ${len(params)}",
                *params
            )
        except Exception as e:
            print(f"[update_agent_info xato] {e}")

    async def push_pending_command_if_any(self):
        """Agent ulanganda navbatdagi kutilayotgan buyruqni push qiladi.

        Retry logikasi:
          - acknowledged_at IS NULL — agent hali muvaffaqiyat/muvaffaqiyatsizligini bildirmagan
          - attempts < 5 — 5 marotaba urinishdan oshmagan
          - PC offline bo'lsa — bu qatorlar tegilmaydi, PC online bo'lganda bu metod chaqiriladi

        Har yuborishda attempts +1 oshadi. 5 ga yetganda AgentReportView majburan
        muvaffaqiyatsiz deb belgilaydi.
        """
        try:
            pool = await get_pool()
            field, value = self._id_filter()
            row = await pool.fetchrow(
                f'''SELECT pc.id, pc.action, pc.force, pc.release_id, pc.attempts,
                              r.target, r.version
                       FROM commands_pendingcommand pc
                  LEFT JOIN commands_release r ON pc.release_id = r.id
                       JOIN endpoints_computer c ON pc.computer_id = c.id
                      WHERE c.{field} = $1
                        AND pc.acknowledged_at IS NULL
                        AND pc.attempts < 5
                   ORDER BY pc.created_at
                      LIMIT 1''',
                str(value)
            )
            if not row:
                return

            cmd_id     = row['id']
            action     = row['action']
            attempts   = row['attempts'] or 0

            if action == 'update' and row['target'] and row['version']:
                payload = {
                    'type': 'force_update',
                    'target': row['target'],
                    'version': row['version'],
                    'manifest_url': f'/api/agent/manifest/{row["target"]}/{row["version"]}/',
                    'force': row['force'],
                    'command_id': str(cmd_id),
                }
            elif action == 'uninstall':
                payload = {'type': 'force_uninstall', 'confirm': True, 'command_id': str(cmd_id)}
            elif action == 'restart':
                payload = {'type': 'restart', 'command_id': str(cmd_id)}
            else:
                return

            await self.send(text_data=json.dumps(payload))

            # attempts oshiramiz + delivered_at ni yangilaymiz (oxirgi urinish vaqti)
            await pool.execute(
                """UPDATE commands_pendingcommand
                      SET delivered_at = NOW(),
                          attempts     = attempts + 1
                    WHERE id = $1""",
                cmd_id
            )
            print(f"[{self.key}] buyruq push ({attempts + 1}/5): {action} cmd={cmd_id}")
        except Exception as e:
            print(f"[push_pending_command xato] {e}")
