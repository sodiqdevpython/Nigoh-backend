import os
import hashlib
from rest_framework import generics, status
from rest_framework.response import Response
from django.db.models import F
from .models import BlockedURL, BlockedAttemptLog, ActivityLog, ProcessAlertLog, BlockedProcess, AppUsageStatistic, ScreenShareSession, RemoteControlSession
from endpoints.models import Computer
from .serializers import ReportBlockedSerializer, BulkActivityLogSerializer, ProcessAlertSerializer, BulkAppUsageSerializer, AgentScreenShareResponseSerializer
from django.conf import settings
from rest_framework.views import APIView
from datetime import datetime
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework.permissions import IsAuthenticated

def get_secure_token():
    secret_word = "sodiq2005.py"
    today = datetime.now().strftime("%Y-%m-%d")
    raw_string = f"{secret_word}-{today}"
    return hashlib.sha256(raw_string.encode()).hexdigest()

class ReportBlockedURLView(generics.CreateAPIView):
    serializer_class = ReportBlockedSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        bios_uuid = serializer.validated_data['bios_uuid']
        url_id = serializer.validated_data['url_id'] # Endi ID ni olamiz
        attempts_count = serializer.validated_data['attempts_count']

        try:
            computer = Computer.objects.get(bios_uuid=bios_uuid)
            # URL ni ham to'g'ridan-to'g'ri Primary Key (id) orqali juda tez topib olamiz
            blocked_url = BlockedURL.objects.get(id=url_id)

            BlockedAttemptLog.objects.create(
                computer=computer, 
                url=blocked_url,
                attempts_count=attempts_count
            )

            BlockedURL.objects.filter(id=url_id).update(visit_count=F('visit_count') + attempts_count)

            return Response({
                "status": "success", 
                "message": f"Urinish tarixga saqlandi ({attempts_count} marta)"
            }, status=status.HTTP_201_CREATED)
            
        except Computer.DoesNotExist:
            return Response({"error": "Computer topilmadi"}, status=status.HTTP_404_NOT_FOUND)
        except BlockedURL.DoesNotExist:
            return Response({"error": "Bu URL qora ro'yxatda yo'q (yoki ID xato)"}, status=status.HTTP_404_NOT_FOUND)
    


class BlacklistVersionView(APIView):
    """
    Agent CSV fayl yangilangan yoki yo'qligini tekshirishi uchun
    """
    def get(self, request, *args, **kwargs):
        file_path = os.path.join(settings.MEDIA_ROOT, 'blacklist.csv')
        
        if os.path.exists(file_path):
            # OS darajasida faylning oxirgi o'zgartirilgan vaqtini (timestamp) olamiz
            timestamp = os.path.getmtime(file_path)
            return Response({
                "has_file": True,
                # C# da solishtirish oson bo'lishi uchun Unix Timestamp (son) qaytaramiz
                "last_modified_timestamp": timestamp,
                # Odam o'qishi (log) uchun matnli variant
                "last_modified_str": datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
            })
            
        return Response({
            "has_file": False, 
            "last_modified_timestamp": 0
        })


class ReportActivityLogView(APIView):
    """
    Agent yig'ilgan statistikalarni bittada (paket qilib) yuboradi.
    Juda tez ishlashi uchun bulk_create ishlatiladi.
    """
    def post(self, request, *args, **kwargs):
        serializer = BulkActivityLogSerializer(data=request.data)
        if serializer.is_valid():
            bios_uuid = serializer.validated_data['bios_uuid']
            logs_data = serializer.validated_data['logs']

            try:
                computer = Computer.objects.get(bios_uuid=bios_uuid)
            except Computer.DoesNotExist:
                return Response({"error": "Computer topilmadi"}, status=status.HTTP_404_NOT_FOUND)

            # Bazaga yozish uchun obyektlar ro'yxatini tayyorlaymiz (hali bazaga yozilmaydi)
            activities_to_create = [
                ActivityLog(
                    computer=computer,
                    title=log.get('title', ''),
                    app_name=log['app_name'],
                    url=log.get('url', ''),
                    duration_seconds=log['duration_seconds']
                ) for log in logs_data
            ]

            # Barcha ma'lumotlarni atigi 1 ta SQL so'rov bilan yashin tezligida saqlaymiz!
            ActivityLog.objects.bulk_create(activities_to_create)

            return Response({
                "status": "success",
                "message": f"{len(activities_to_create)} ta jarayon statistikasi muvaffaqiyatli saqlandi."
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)




class ProcessBlacklistVersionView(APIView):
    """
    Agent process_blacklist.csv fayli yangilangan yoki yo'qligini tekshirishi uchun
    """
    def get(self, request, *args, **kwargs):
        file_path = os.path.join(settings.MEDIA_ROOT, 'process_blacklist.csv')
        
        if os.path.exists(file_path):
            timestamp = os.path.getmtime(file_path)
            return Response({
                "has_file": True,
                "last_modified_timestamp": timestamp,
                "last_modified_str": datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
            })
            
        return Response({
            "has_file": False, 
            "last_modified_timestamp": 0
        })


class ReportProcessAlertView(generics.CreateAPIView):
    """ Agent yopilgan dastur (Alert) haqida xabar yuboradi """
    serializer_class = ProcessAlertSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        bios_uuid = serializer.validated_data['bios_uuid']
        rule_id = serializer.validated_data['rule_id'] 
        app_name = serializer.validated_data['app_name']
        full_path = serializer.validated_data['full_path']
        attempts_count = serializer.validated_data['attempts_count']
        
        try:
            computer = Computer.objects.get(bios_uuid=bios_uuid)
            process_rule = BlockedProcess.objects.get(id=rule_id)
            
            ProcessAlertLog.objects.create(
                computer=computer,
                process_rule=process_rule,
                app_name=app_name,
                full_path=full_path,
                attempts_count=attempts_count
            )
            BlockedProcess.objects.filter(id=rule_id).update(blocked_count=F('blocked_count') + attempts_count)

            return Response({
                "status": "success", 
                "message": f"Alert saqlandi: {app_name} ({attempts_count} marta)"
            }, status=status.HTTP_201_CREATED)
            
        except Computer.DoesNotExist:
            return Response({"error": "Computer topilmadi"}, status=status.HTTP_404_NOT_FOUND)
        except BlockedProcess.DoesNotExist:
            return Response({"error": "Bu qoida qora ro'yxatda yo'q (yoki rule_id xato)"}, status=status.HTTP_404_NOT_FOUND)


class ReportAppUsageView(APIView):
    """
    Agent barcha dasturlar statistikasini bittada (paket qilib) yuboradi.
    """
    def post(self, request, *args, **kwargs):
        serializer = BulkAppUsageSerializer(data=request.data)
        if serializer.is_valid():
            bios_uuid = serializer.validated_data['bios_uuid']
            usages_data = serializer.validated_data['usages']

            try:
                computer = Computer.objects.get(bios_uuid=bios_uuid)
            except Computer.DoesNotExist:
                return Response({"error": "Computer topilmadi"}, status=status.HTTP_404_NOT_FOUND)

            # Bazaga yozish uchun obyektlar ro'yxatini xotirada tayyorlaymiz
            usages_to_create = [
                AppUsageStatistic(
                    computer=computer,
                    app_name=usage['app_name'],
                    total_open_seconds=usage['total_open_seconds'],
                    active_seconds=usage['active_seconds'],
                    mouse_active_seconds=usage['mouse_active_seconds'],
                    keyboard_active_seconds=usage['keyboard_active_seconds']
                ) for usage in usages_data
            ]

            # Barcha statistikani bitta SQL so'rov bilan saqlaymiz
            AppUsageStatistic.objects.bulk_create(usages_to_create)

            return Response({
                "status": "success",
                "message": f"{len(usages_to_create)} ta dastur statistikasi saqlandi."
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# screen sharing uchun

class RequestScreenShareView(APIView):
    """
    O'qituvchi ma'lum bir kompyuter ekranini ko'rishni so'raydi.
    """
    def post(self, request, bios_uuid, *args, **kwargs):
        # Vaqtni olamiz
        try:
            n_seconds = int(request.data.get('n', 300))
        except ValueError:
            n_seconds = 300 

        # Kompyuterni topamiz
        try:
            computer = Computer.objects.get(bios_uuid=bios_uuid)
        except Computer.DoesNotExist:
            return Response({"error": "Computer topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        # 1. Bazada yangi PENDING sessiya yaratamiz
        session = ScreenShareSession.objects.create(
            computer=computer,
            requested_duration=n_seconds,
            status='PENDING'
        )

        # 2. Agentga WebSocket orqali xabar yuboramiz (faqat Session ID ketadi)
        channel_layer = get_channel_layer()
        group_name = f"pc_{bios_uuid}" 
        
        command_payload = {
            "type": "screen_share",
            "action": n_seconds,       # Qancha soniya
            "payload": {
                "session_id": str(session.id) # Session ID ni payload ichiga soldik
            }
        }

        # Socketga xabar otish
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "execute_command",  # <--- Sizdagi funksiya nomi
                "data": command_payload     # <--- Sizdagi funksiya kutayotgan o'zgaruvchi
            }
        )

        # 3. O'qituvchiga sessiya ochilganini aytamiz
        return Response({
            "status": "pending",
            "message": "Buyruq agentga yuborildi. Agent URL yuborishi kutilmoqda.",
            "session_id": session.id
        }, status=status.HTTP_201_CREATED)


# --- 2. AGENT UCHUN (Tayyor bo'lgach URL ni tashlaydi) ---

class AgentScreenShareResponseView(APIView):
    """
    Agent ekranni yozishni boshlab, tayyor URL ni backendga (Sessiyaga) yuboradi.
    """
    def post(self, request, *args, **kwargs):
        serializer = AgentScreenShareResponseSerializer(data=request.data)
        if serializer.is_valid():
            bios_uuid = serializer.validated_data['bios_uuid']
            session_id = serializer.validated_data['session_id']
            stream_url = serializer.validated_data['stream_url']

            try:
                # O'qituvchi yaratgan sessiyani topamiz
                session = ScreenShareSession.objects.get(id=session_id, computer__bios_uuid=bios_uuid)
                
                # Holatni faol qilib, URL ni saqlab qo'yamiz
                session.status = 'ACTIVE'
                session.stream_url = stream_url
                session.save()

                return Response({
                    "status": "success",
                    "message": "Stream URL qabul qilindi. Sessiya faol."
                }, status=status.HTTP_200_OK)

            except ScreenShareSession.DoesNotExist:
                return Response({"error": "Sessiya topilmadi yoki bu PC ga tegishli emas"}, status=status.HTTP_404_NOT_FOUND)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AgentScreenShareUpdateView(APIView):
    """
    Agent tayyor bo'lgach, sessiyani PATCH qilib ACTIVE holatiga o'tkazadi
    va o'zining stream_url manzilini bazaga yozib qo'yadi.
    """
    
    @swagger_auto_schema(
        operation_summary="Agent tayyor bo'lgach Stream URL ni saqlaydi",
        operation_description="Agent faqat URL dagi session_id orqali sessiyani topadi va stream_url ni joylashtiradi.",
        tags=["Screen Share"],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['stream_url'], # bios_uuid olib tashlandi
            properties={
                'stream_url': openapi.Schema(
                    type=openapi.TYPE_STRING, 
                    format=openapi.FORMAT_URI, 
                    description="Agent video oqim uzatayotgan aniq manzil",
                    example="http://192.168.1.55:5004/231ef59ef9caf99f649ed5c2"
                ),
            }
        ),
        responses={
            200: openapi.Response(
                description="Muvaffaqiyatli",
                examples={"application/json": {"status": "success", "message": "Sessiya faollashdi va URL muvaffaqiyatli saqlandi."}}
            ),
            400: openapi.Response(
                description="Xatolik",
                examples={"application/json": {"error": "stream_url majburiy"}}
            ),
            404: openapi.Response(
                description="Sessiya topilmadi",
                examples={"application/json": {"error": "Sessiya topilmadi"}}
            ),
        }
    )
    def patch(self, request, session_id, *args, **kwargs):
        # Faqat stream_url ni olamiz
        stream_url = request.data.get('stream_url')

        if not stream_url:
            return Response(
                {"error": "stream_url majburiy"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Faqat session_id orqali qidiramiz
            session = ScreenShareSession.objects.get(id=session_id)
            
            session.status = 'ACTIVE'
            session.stream_url = stream_url
            session.save(update_fields=['status', 'stream_url'])

            return Response({
                "status": "success",
                "message": "Sessiya faollashdi va URL muvaffaqiyatli saqlandi."
            }, status=status.HTTP_200_OK)

        except ScreenShareSession.DoesNotExist:
            return Response(
                {"error": "Sessiya topilmadi"}, 
                status=status.HTTP_404_NOT_FOUND
            )


# --- 1. O'QITUVCHI SO'ROV YUBORISHI ---

class RequestRemoteControlView(APIView):
    """
    O'qituvchi (Author) tanlangan PC ni masofadan boshqarishni so'raydi.
    """
    # So'rov yuborgan odam avtorizatsiyadan o'tgan bo'lishi shart
    permission_classes = [IsAuthenticated] 

    def post(self, request, bios_uuid, *args, **kwargs):
        duration = request.data.get('time', 300) # Default 300 sekund

        try:
            computer = Computer.objects.get(bios_uuid=bios_uuid)
        except Computer.DoesNotExist:
            return Response({"error": "Kompyuter topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        # FAqat onlayn kompyuterlarga ruxsat berish
        if not computer.is_online:
            return Response({"error": "Bu kompyuter hozir oflayn. So'rov yuborib bo'lmaydi."}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Bazada sessiya yaratamiz
        session = RemoteControlSession.objects.create(
            author=request.user,
            computer=computer,
            duration=duration,
            is_active=False
        )

        # 2. Agentga Socket orqali xabar yuboramiz
        channel_layer = get_channel_layer()
        group_name = f"pc_{bios_uuid}" 
        
        command_payload = {
            "type": "remote_controll",
            "action": duration,
            "payload": {
                "session_id": str(session.id)
            }
        }

        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "execute_command", 
                "data": command_payload
            }
        )

        return Response({
            "status": "pending",
            "message": "Remote Control buyrug'i yuborildi. Agent kutilmoqda.",
            "session_id": session.id
        }, status=status.HTTP_201_CREATED)


# --- 2. AGENT URL YUBORISHI (PATCH) ---

class AgentRemoteControlUpdateView(APIView):
    """
    Agent tayyor bo'lgach, URL manzilni yuborib, sessiyani aktivlashtiradi.
    Token Backend'da hisoblanib, to'liq URL qilib saqlanadi.
    """
    def patch(self, request, session_id, *args, **kwargs):
        base_url = request.data.get('url') # Agentdan keladigan manzil (Masalan: http://192.168.1.179:5050)

        if not base_url:
            return Response({"error": "url majburiy"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            session = RemoteControlSession.objects.get(id=session_id)
            
            # ==========================================
            # 1. TO'LIQ URL YASASH MANTIQI
            # ==========================================
            # Agent yuborgan URL oxirida adashib slash (/) bo'lsa, olib tashlaymiz
            clean_url = base_url.rstrip('/') 
            
            # Tokenni ulab to'liq manzilni yig'amiz: http://...:5050/token/
            full_stream_url = f"{clean_url}"
            
            # ==========================================
            # 2. BAZAGA TO'LIQ URL BILAN SAQLASH
            # ==========================================
            session.is_active = True
            session.stream_url = full_stream_url # Tayyor URL saqlanadi
            session.save(update_fields=['is_active', 'stream_url'])

            return Response({
                "status": "success",
                "message": "Remote Control faollashdi.",
                "full_url": full_stream_url # Agentga ham ko'rsatib qo'yamiz (ixtiyoriy)
            }, status=status.HTTP_200_OK)

        except RemoteControlSession.DoesNotExist:
            return Response({"error": "Sessiya topilmadi"}, status=status.HTTP_404_NOT_FOUND)