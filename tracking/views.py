import os
from rest_framework import generics, status
from rest_framework.response import Response
from django.db.models import F
from .models import BlockedURL, BlockedAttemptLog, ActivityLog, ProcessAlertLog
from endpoints.models import Computer
from .serializers import ReportBlockedSerializer, BulkActivityLogSerializer, ProcessAlertSerializer
from django.conf import settings
from rest_framework.views import APIView
from datetime import datetime

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
    """
    Agent taqiqlangan dasturni yopib, shu endpointga alert yuboradi.
    """
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
            
            # 1. Tarixga yozamiz
            ProcessAlertLog.objects.create(
                computer=computer,
                process_rule=process_rule,
                app_name=app_name,
                full_path=full_path,
                attempts_count=attempts_count
            )

            # 2. Qoidaning umumiy hisoblagichini oshirib qo'yamiz (tezkor usul)
            BlockedProcess.objects.filter(id=rule_id).update(blocked_count=F('blocked_count') + attempts_count)

            return Response({
                "status": "success", 
                "message": f"Alert saqlandi: {app_name} ({attempts_count} marta)"
            }, status=status.HTTP_201_CREATED)
            
        except Computer.DoesNotExist:
            return Response({"error": "Computer topilmadi"}, status=status.HTTP_404_NOT_FOUND)
        except BlockedProcess.DoesNotExist:
            return Response({"error": "Bu qoida qora ro'yxatda yo'q (yoki rule_id xato)"}, status=status.HTTP_404_NOT_FOUND)

