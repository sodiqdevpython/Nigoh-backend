import os
import hashlib
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from .models import (
    BlockedURL, BlockedAttemptLog, ActivityLog, ProcessAlertLog,
    BlockedProcess, AppUsageStatistic, ScreenShareSession, RemoteControlSession,
    ScreenshotRequest, BroadcastSession, LogRequest
)
from endpoints.models import Computer
from .serializers import (
    ReportBlockedSerializer, BulkActivityLogSerializer, ProcessAlertSerializer,
    BulkAppUsageSerializer, AgentScreenShareResponseSerializer
)
from django.conf import settings
from rest_framework.views import APIView
from datetime import datetime, timedelta
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework.permissions import IsAuthenticated


# -----------------------------------------------------------------
# YORDAMCHI — agentdan kelgan device_id YOKI bios_uuid bo'yicha PC topish
# -----------------------------------------------------------------

def _find_computer(identifier):
    """device_id (yangi agent) yoki bios_uuid (eski agent) bo'yicha topadi."""
    if not identifier:
        return None
    return Computer.objects.filter(
        Q(device_id=identifier) | Q(bios_uuid=identifier)
    ).first()


# ============================================================
# KUNLIK BUCKETING — bir dastur/URL uchun kuniga BITTA yozuv
#
# Muammo: agent har 30 sek yozadi → Chrome kun bo'yi ochiq bo'lsa
#         2880+ ta yangi qator DB ga tushadi.
# Yechim: bugungi (created_at::date == today) yozuvlar bo'lsa unga
#         qo'shib boramiz. Yo'q bo'lsa yangi qator. Ertaga yana yangi
#         qator (tarix saqlanadi).
#
# Yordamchi metod BARCHA report view'lari uchun bir xil ishlaydi.
# ============================================================

def _today_range():
    """Bugungi (server local time) boshi va ertangi kunning boshi."""
    now = timezone.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end   = start + timedelta(days=1)
    return start, end


def _normalize_url(url):
    """Agent bilan bir xil normalizatsiya: protocol, www, oxirgi slash olib tashlanadi."""
    if not url:
        return ""
    s = url.strip().strip('"').lower()
    if s.startswith('https://'):
        s = s[8:]
    elif s.startswith('http://'):
        s = s[7:]
    if s.startswith('www.'):
        s = s[4:]
    return s.rstrip('/')


def _find_blocked_url(url_id, url_address):
    """
    Avval url_id bo'yicha qidiradi. Topilmasa — url_address bo'yicha fallback
    (agent'da eski CSV bo'lishi mumkin, url_id o'chirilgan bo'lishi mumkin, va h.k.).
    """
    # 1) Aniq id bo'yicha
    if url_id:
        try:
            return BlockedURL.objects.get(id=url_id)
        except BlockedURL.DoesNotExist:
            pass

    # 2) url_address bo'yicha fallback — bir nechta variantni sinaymiz
    if url_address:
        addr = url_address.strip()
        # Aynan tenglik (case-insensitive)
        found = BlockedURL.objects.filter(url_address__iexact=addr).first()
        if found:
            return found

        # Normalizatsiya qilingan variantda
        normalized = _normalize_url(addr)
        if normalized and normalized != addr.lower():
            found = BlockedURL.objects.filter(url_address__iexact=normalized).first()
            if found:
                return found

        # Backendda ba'zi yozuvlar 'https://...' bilan saqlanishi mumkin — teskari urinamiz
        candidates = BlockedURL.objects.all().values('id', 'url_address')
        for cand in candidates:
            if _normalize_url(cand['url_address']) == normalized:
                return BlockedURL.objects.get(id=cand['id'])

    return None


def _agent_id_from_validated(serializer):
    """Serializer validated_data dan device_id yoki bios_uuid ni qaytaradi."""
    v = serializer.validated_data
    return v.get('device_id') or v.get('bios_uuid')


def _computer_ws_key(computer):
    """WebSocket group nomi uchun kalit (consumer ham shu kalitga ulanadi)."""
    return computer.device_id or computer.bios_uuid


def get_secure_token():
    secret_word = "sodiq2005.py"
    today = datetime.now().strftime("%Y-%m-%d")
    raw_string = f"{secret_word}-{today}"
    return hashlib.sha256(raw_string.encode()).hexdigest()


# -----------------------------------------------------------------
# AGENT ENDPOINTLARI
# -----------------------------------------------------------------

class ReportBlockedURLView(generics.CreateAPIView):
    serializer_class = ReportBlockedSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        agent_id = _agent_id_from_validated(serializer)
        url_id = serializer.validated_data.get('url_id')
        url_address = serializer.validated_data.get('url_address', '')
        attempts_count = serializer.validated_data['attempts_count']

        computer = _find_computer(agent_id)
        if computer is None:
            return Response({"error": "Computer topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        # url_id yoki url_address bo'yicha qidiramiz. Agentda eski CSV bo'lishi
        # mumkin — shu sabab fallback kerak.
        blocked_url = _find_blocked_url(url_id, url_address)
        if blocked_url is None:
            # Muvaffaqiyatsiz yozuvni ushlab qolmaymiz — agent qayta-qayta urinmasin,
            # lokal DB'ga jamlanib ketmasin. Log ko'rinishida signal beramiz.
            print(f"[WARN] Bloklangan URL topilmadi (agent CSV eskirgan?): "
                  f"url_id={url_id}, url_address={url_address}")
            return Response({
                "status": "warning",
                "message": "URL bazada topilmadi (CSV eskirgan bo'lishi mumkin)",
                "url_id_received": str(url_id) if url_id else None,
                "url_address_received": url_address,
            }, status=status.HTTP_200_OK)

        # ============================================================
        # KUNLIK BUCKETING: (computer, url) bo'yicha bugungi qator bo'lsa
        # attempts_count ni qo'shamiz. Ertaga yangi qator (tarix saqlanadi).
        # ============================================================
        today_start, today_end = _today_range()
        existing = BlockedAttemptLog.objects.filter(
            computer=computer,
            url=blocked_url,
            created_at__gte=today_start,
            created_at__lt=today_end,
        ).first()

        if existing:
            BlockedAttemptLog.objects.filter(pk=existing.pk).update(
                attempts_count=F('attempts_count') + attempts_count,
            )
        else:
            BlockedAttemptLog.objects.create(
                computer=computer,
                url=blocked_url,
                attempts_count=attempts_count,
            )

        BlockedURL.objects.filter(id=blocked_url.id).update(
            visit_count=F('visit_count') + attempts_count
        )

        return Response({
            "status": "success",
            "message": f"Urinish tarixga saqlandi ({attempts_count} marta)"
        }, status=status.HTTP_200_OK)


class BlacklistVersionView(APIView):
    """Agent CSV fayl yangilangan yoki yo'qligini tekshirishi uchun"""

    def get(self, request, *args, **kwargs):
        file_path = os.path.join(settings.MEDIA_ROOT, 'blacklist.csv')
        if os.path.exists(file_path):
            timestamp = os.path.getmtime(file_path)
            return Response({
                "has_file": True,
                "last_modified_timestamp": timestamp,
                "last_modified_str": datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
            })
        return Response({"has_file": False, "last_modified_timestamp": 0})


class ReportActivityLogView(APIView):
    """Agent yig'ilgan statistikalarni bittada (paket qilib) yuboradi."""

    def post(self, request, *args, **kwargs):
        serializer = BulkActivityLogSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        agent_id = _agent_id_from_validated(serializer)
        logs_data = serializer.validated_data['logs']

        computer = _find_computer(agent_id)
        if computer is None:
            return Response({"error": "Computer topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        # ============================================================
        # KUNLIK BUCKETING: (app_name, title, url) bo'yicha bugungi qator
        # bo'lsa duration ni qo'shamiz. Ertaga yangi qator (tarix saqlanadi).
        # ============================================================
        today_start, today_end = _today_range()

        existing_today = ActivityLog.objects.filter(
            computer=computer,
            created_at__gte=today_start,
            created_at__lt=today_end,
        )
        # Kalit: (app_name, title, url) — bir xil hammasi bir xil bo'lsa qo'shiladi
        def _key(app_name, title, url):
            return (app_name or '', (title or '')[:500], url or '')

        existing_by_key = {_key(r.app_name, r.title, r.url): r for r in existing_today}

        to_update, to_create = [], []
        new_by_key = {}

        for log in logs_data:
            app_name = log['app_name']
            title    = log.get('title', '') or ''
            url      = log.get('url', '') or ''
            key      = _key(app_name, title, url)

            row = existing_by_key.get(key) or new_by_key.get(key)

            if row is not None:
                row.duration_seconds += log['duration_seconds']
                # DB dan kelgan yozuv bo'lsa update ro'yxatiga qo'shamiz
                # (new_by_key dagi hali yozilmagan yangi qatorga tegmaymiz)
                if key in existing_by_key and row not in to_update:
                    to_update.append(row)
            else:
                new_row = ActivityLog(
                    computer=computer,
                    title=title,
                    app_name=app_name,
                    url=url,
                    duration_seconds=log['duration_seconds'],
                )
                to_create.append(new_row)
                new_by_key[key] = new_row

        if to_update:
            ActivityLog.objects.bulk_update(to_update, ['duration_seconds'])
        if to_create:
            ActivityLog.objects.bulk_create(to_create)

        return Response({
            "status": "success",
            "updated": len(to_update),
            "created": len(to_create),
            "message": f"{len(to_update)} yangilandi, {len(to_create)} yaratildi.",
        }, status=status.HTTP_200_OK)


class ProcessBlacklistVersionView(APIView):
    """Agent process_blacklist.csv fayli yangilangan yoki yo'qligini tekshirishi uchun"""

    def get(self, request, *args, **kwargs):
        file_path = os.path.join(settings.MEDIA_ROOT, 'process_blacklist.csv')
        if os.path.exists(file_path):
            timestamp = os.path.getmtime(file_path)
            return Response({
                "has_file": True,
                "last_modified_timestamp": timestamp,
                "last_modified_str": datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
            })
        return Response({"has_file": False, "last_modified_timestamp": 0})


class ReportProcessAlertView(generics.CreateAPIView):
    """Agent yopilgan dastur (Alert) haqida xabar yuboradi"""
    serializer_class = ProcessAlertSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        agent_id = _agent_id_from_validated(serializer)
        rule_id = serializer.validated_data['rule_id']
        app_name = serializer.validated_data['app_name']
        full_path = serializer.validated_data['full_path']
        attempts_count = serializer.validated_data['attempts_count']

        computer = _find_computer(agent_id)
        if computer is None:
            return Response({"error": "Computer topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        try:
            process_rule = BlockedProcess.objects.get(id=rule_id)
        except BlockedProcess.DoesNotExist:
            return Response({"error": "Bu qoida qora ro'yxatda yo'q (yoki rule_id xato)"},
                            status=status.HTTP_404_NOT_FOUND)

        # ============================================================
        # KUNLIK BUCKETING: (computer, process_rule, app_name) bo'yicha
        # bugungi qator bo'lsa attempts_count qo'shamiz.
        # ============================================================
        today_start, today_end = _today_range()
        existing = ProcessAlertLog.objects.filter(
            computer=computer,
            process_rule=process_rule,
            app_name=app_name,
            created_at__gte=today_start,
            created_at__lt=today_end,
        ).first()

        if existing:
            ProcessAlertLog.objects.filter(pk=existing.pk).update(
                attempts_count=F('attempts_count') + attempts_count,
            )
        else:
            ProcessAlertLog.objects.create(
                computer=computer,
                process_rule=process_rule,
                app_name=app_name,
                full_path=full_path,
                attempts_count=attempts_count,
            )

        BlockedProcess.objects.filter(id=rule_id).update(
            blocked_count=F('blocked_count') + attempts_count
        )

        return Response({
            "status": "success",
            "message": f"Alert saqlandi: {app_name} ({attempts_count} marta)"
        }, status=status.HTTP_200_OK)


class ReportAppUsageView(APIView):
    """Agent barcha dasturlar statistikasini bittada (paket qilib) yuboradi."""

    def post(self, request, *args, **kwargs):
        serializer = BulkAppUsageSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        agent_id = _agent_id_from_validated(serializer)
        usages_data = serializer.validated_data['usages']

        computer = _find_computer(agent_id)
        if computer is None:
            return Response({"error": "Computer topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        # ============================================================
        # KUNLIK BUCKETING: bugungi yozuv bo'lsa unga qo'shamiz,
        # bo'lmasa yangi qator. Ertaga yangi kun uchun yangi qator.
        # ============================================================
        today_start, today_end = _today_range()

        existing_today = AppUsageStatistic.objects.filter(
            computer=computer,
            created_at__gte=today_start,
            created_at__lt=today_end,
        )
        existing_by_name = {row.app_name: row for row in existing_today}

        to_update, to_create = [], []
        new_by_name = {}

        for usage in usages_data:
            app_name = usage['app_name']
            row = existing_by_name.get(app_name) or new_by_name.get(app_name)

            if row is not None:
                # Bugungi yozuv topildi — vaqtlarni qo'shamiz
                row.total_open_seconds      += usage['total_open_seconds']
                row.active_seconds          += usage['active_seconds']
                row.mouse_active_seconds    += usage['mouse_active_seconds']
                row.keyboard_active_seconds += usage['keyboard_active_seconds']
                # full_path bo'sh bo'lsa, yangisidan tiklaymiz
                if not row.full_path and usage.get('full_path'):
                    row.full_path = usage.get('full_path')
                if row in existing_today and row not in to_update:
                    to_update.append(row)
            else:
                # Bugun uchun birinchi marta — yangi qator
                new_row = AppUsageStatistic(
                    computer=computer,
                    app_name=app_name,
                    full_path=usage.get('full_path') or None,
                    total_open_seconds=usage['total_open_seconds'],
                    active_seconds=usage['active_seconds'],
                    mouse_active_seconds=usage['mouse_active_seconds'],
                    keyboard_active_seconds=usage['keyboard_active_seconds'],
                )
                to_create.append(new_row)
                new_by_name[app_name] = new_row

        if to_update:
            AppUsageStatistic.objects.bulk_update(to_update, [
                'total_open_seconds', 'active_seconds',
                'mouse_active_seconds', 'keyboard_active_seconds', 'full_path',
            ])
        if to_create:
            AppUsageStatistic.objects.bulk_create(to_create)

        return Response({
            "status": "success",
            "updated": len(to_update),
            "created": len(to_create),
            "message": f"{len(to_update)} yangilandi, {len(to_create)} yaratildi.",
        }, status=status.HTTP_200_OK)


# -----------------------------------------------------------------
# SCREEN SHARE
# -----------------------------------------------------------------

class RequestScreenShareView(APIView):
    """O'qituvchi ma'lum bir kompyuter ekranini ko'rishni so'raydi."""

    def post(self, request, bios_uuid, *args, **kwargs):
        # URL parametri 'bios_uuid' deb nomlangan, lekin device_id ham bo'lishi mumkin.
        try:
            n_seconds = int(request.data.get('n', 300))
        except ValueError:
            n_seconds = 300

        computer = _find_computer(bios_uuid)
        if computer is None:
            return Response({"error": "Computer topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        session = ScreenShareSession.objects.create(
            computer=computer,
            requested_duration=n_seconds,
            status='PENDING'
        )

        channel_layer = get_channel_layer()
        group_name = f"pc_{_computer_ws_key(computer)}"

        command_payload = {
            "type": "screen_share",
            "action": n_seconds,
            "payload": {"session_id": str(session.id)}
        }

        async_to_sync(channel_layer.group_send)(
            group_name,
            {"type": "execute_command", "data": command_payload}
        )

        return Response({
            "status": "pending",
            "message": "Buyruq agentga yuborildi. Agent URL yuborishi kutilmoqda.",
            "session_id": session.id
        }, status=status.HTTP_201_CREATED)


class AgentScreenShareResponseView(APIView):
    """Agent ekranni yozishni boshlab, tayyor URL ni backendga (Sessiyaga) yuboradi."""

    def post(self, request, *args, **kwargs):
        serializer = AgentScreenShareResponseSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        agent_id = _agent_id_from_validated(serializer)
        session_id = serializer.validated_data['session_id']
        stream_url = serializer.validated_data['stream_url']

        computer = _find_computer(agent_id)
        if computer is None:
            return Response({"error": "Computer topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        try:
            session = ScreenShareSession.objects.get(id=session_id, computer=computer)
        except ScreenShareSession.DoesNotExist:
            return Response({"error": "Sessiya topilmadi yoki bu PC ga tegishli emas"},
                            status=status.HTTP_404_NOT_FOUND)

        session.status = 'ACTIVE'
        session.stream_url = stream_url
        session.save()

        return Response({
            "status": "success",
            "message": "Stream URL qabul qilindi. Sessiya faol."
        }, status=status.HTTP_200_OK)


class AgentScreenShareUpdateView(APIView):
    """Agent tayyor bo'lgach, sessiyani PATCH qilib ACTIVE holatiga o'tkazadi."""

    @swagger_auto_schema(
        operation_summary="Agent tayyor bo'lgach Stream URL ni saqlaydi",
        operation_description="Agent faqat URL dagi session_id orqali sessiyani topadi va stream_url ni joylashtiradi.",
        tags=["Screen Share"],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['stream_url'],
            properties={
                'stream_url': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format=openapi.FORMAT_URI,
                    description="Agent video oqim uzatayotgan aniq manzil",
                    example="http://192.168.1.55:5004/231ef59ef9caf99f649ed5c2"
                ),
            }
        ),
        responses={200: openapi.Response(description="Muvaffaqiyatli")},
    )
    def patch(self, request, session_id, *args, **kwargs):
        stream_url = request.data.get('stream_url')
        if not stream_url:
            return Response({"error": "stream_url majburiy"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            session = ScreenShareSession.objects.get(id=session_id)
        except ScreenShareSession.DoesNotExist:
            return Response({"error": "Sessiya topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        session.status = 'ACTIVE'
        session.stream_url = stream_url
        session.save(update_fields=['status', 'stream_url'])

        return Response({
            "status": "success",
            "message": "Sessiya faollashdi va URL muvaffaqiyatli saqlandi."
        }, status=status.HTTP_200_OK)


# -----------------------------------------------------------------
# REMOTE CONTROL
# -----------------------------------------------------------------

class RequestRemoteControlView(APIView):
    """O'qituvchi tanlangan PC ni masofadan boshqarishni so'raydi."""
    permission_classes = [IsAuthenticated]

    def post(self, request, bios_uuid, *args, **kwargs):
        # URL parametri 'bios_uuid' deb nomlangan, lekin device_id ham bo'lishi mumkin.
        duration = request.data.get('time', 300)

        computer = _find_computer(bios_uuid)
        if computer is None:
            return Response({"error": "Kompyuter topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        if not computer.is_online:
            return Response({"error": "Bu kompyuter hozir oflayn. So'rov yuborib bo'lmaydi."},
                            status=status.HTTP_400_BAD_REQUEST)

        session = RemoteControlSession.objects.create(
            author=request.user,
            computer=computer,
            duration=duration,
            is_active=False
        )

        channel_layer = get_channel_layer()
        group_name = f"pc_{_computer_ws_key(computer)}"

        command_payload = {
            "type": "remote_controll",
            "action": duration,
            "payload": {"session_id": str(session.id)}
        }

        async_to_sync(channel_layer.group_send)(
            group_name,
            {"type": "execute_command", "data": command_payload}
        )

        return Response({
            "status": "pending",
            "message": "Remote Control buyrug'i yuborildi. Agent kutilmoqda.",
            "session_id": session.id
        }, status=status.HTTP_201_CREATED)


# =============================================================
# SCREENSHOT
# =============================================================

class ScreenshotUploadView(APIView):
    """
    Agent bu endpoint'ga rasm POST qiladi (multipart/form-data).
    Fields:
        device_id (yoki bios_uuid)
        request_id  — ScreenshotRequest.id
        image       — jpeg/png fayl
    """
    permission_classes = []  # authentication yo'q, agent device_id bilan tekshirilinadi
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        agent_id = request.data.get('device_id') or request.data.get('bios_uuid')
        request_id = request.data.get('request_id')
        image = request.FILES.get('image')

        if not agent_id or not request_id or not image:
            return Response({'error': "device_id, request_id, image majburiy"},
                            status=status.HTTP_400_BAD_REQUEST)

        computer = _find_computer(agent_id)
        if computer is None:
            return Response({'error': 'Computer topilmadi'}, status=status.HTTP_404_NOT_FOUND)

        try:
            ssr = ScreenshotRequest.objects.get(id=request_id, computer=computer)
        except ScreenshotRequest.DoesNotExist:
            return Response({'error': 'So\'rov topilmadi (yoki bu kompyuterga tegishli emas)'},
                            status=status.HTTP_404_NOT_FOUND)

        ssr.image = image
        ssr.status = 'COMPLETED'
        ssr.completed_at = timezone.now()
        ssr.save(update_fields=['image', 'status', 'completed_at'])

        # Eng oxirgi rasmni Computer.last_screenshot ga ko'chiramiz —
        # eski rasm django-cleanup orqali avtomatik o'chadi.
        try:
            # ssr.image endi saqlangan, uni ochib Computer ga ko'chiramiz
            ssr.image.open('rb')
            from django.core.files.base import ContentFile
            content = ssr.image.read()
            ssr.image.close()
            fname = f"{computer.id}.jpg"
            # Eski faylni o'chirish uchun None qilib qo'yamiz, keyin yangisini beramiz
            if computer.last_screenshot:
                computer.last_screenshot.delete(save=False)
            computer.last_screenshot.save(fname, ContentFile(content), save=False)
            computer.last_screenshot_at = timezone.now()
            computer.save(update_fields=['last_screenshot', 'last_screenshot_at'])
        except Exception as e:
            print(f"[last_screenshot copy xato] {e}")

        return Response({'status': 'success', 'id': str(ssr.id)}, status=status.HTTP_200_OK)


class LogUploadView(APIView):
    """
    Agent shifrlangan result.log faylini shu endpoint'ga yuklaydi (multipart).
    Fields:
        device_id  (yoki bios_uuid)
        request_id  — LogRequest.id
        log         — natijaviy fayl
    """
    permission_classes = []
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        agent_id   = request.data.get('device_id') or request.data.get('bios_uuid')
        request_id = request.data.get('request_id')
        log_file   = request.FILES.get('log')

        if not agent_id or not request_id or not log_file:
            return Response({'error': "device_id, request_id, log majburiy"},
                            status=status.HTTP_400_BAD_REQUEST)

        computer = _find_computer(agent_id)
        if computer is None:
            return Response({'error': 'Computer topilmadi'}, status=status.HTTP_404_NOT_FOUND)

        try:
            lr = LogRequest.objects.get(id=request_id, computer=computer)
        except LogRequest.DoesNotExist:
            return Response({'error': "So'rov topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        lr.log_file = log_file
        lr.log_size_bytes = log_file.size
        lr.status = 'COMPLETED'
        lr.completed_at = timezone.now()
        lr.save(update_fields=['log_file', 'log_size_bytes', 'status', 'completed_at'])

        return Response({'status': 'success', 'id': str(lr.id)}, status=status.HTTP_200_OK)


class AgentRemoteControlUpdateView(APIView):
    """Agent tayyor bo'lgach, URL manzilni yuborib, sessiyani aktivlashtiradi."""

    def patch(self, request, session_id, *args, **kwargs):
        base_url = request.data.get('url')
        if not base_url:
            return Response({"error": "url majburiy"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            session = RemoteControlSession.objects.get(id=session_id)
        except RemoteControlSession.DoesNotExist:
            return Response({"error": "Sessiya topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        clean_url = base_url.rstrip('/')
        full_stream_url = clean_url

        session.is_active = True
        session.stream_url = full_stream_url
        session.save(update_fields=['is_active', 'stream_url'])

        return Response({
            "status": "success",
            "message": "Remote Control faollashdi.",
            "full_url": full_stream_url
        }, status=status.HTTP_200_OK)
