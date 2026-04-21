from rest_framework import serializers
from .models import (
    AppUsageStatistic, ActivityLog, 
    BlockedAttemptLog, ProcessAlertLog, ScreenShareSession
)
from endpoints.models import Computer

class ReportBlockedSerializer(serializers.Serializer):
    bios_uuid = serializers.CharField(max_length=100)
    url_id = serializers.UUIDField()
    attempts_count = serializers.IntegerField(min_value=1)

class ActivityLogItemSerializer(serializers.Serializer):
    """Bitta oyna/dastur uchun ma'lumot"""
    title = serializers.CharField(max_length=500, allow_blank=True, required=False)
    app_name = serializers.CharField(max_length=255)
    url = serializers.CharField(allow_blank=True, required=False)
    duration_seconds = serializers.IntegerField(min_value=0)

class BulkActivityLogSerializer(serializers.Serializer):
    """Agent yuboradigan umumiy paket"""
    bios_uuid = serializers.CharField(max_length=100)
    # Agent o'nlab loglarni bitta 'logs' array ichida yuboradi
    logs = ActivityLogItemSerializer(many=True)


class ProcessAlertSerializer(serializers.Serializer):
    bios_uuid = serializers.CharField(max_length=100)
    rule_id = serializers.UUIDField() 
    app_name = serializers.CharField(max_length=255)
    full_path = serializers.CharField()
    attempts_count = serializers.IntegerField(min_value=1)


class AppUsageItemSerializer(serializers.Serializer):
    """Bitta dastur statistikasi uchun qolip"""
    app_name = serializers.CharField(max_length=255)
    total_open_seconds = serializers.IntegerField(min_value=0)
    active_seconds = serializers.IntegerField(min_value=0)
    mouse_active_seconds = serializers.IntegerField(min_value=0)
    keyboard_active_seconds = serializers.IntegerField(min_value=0)

class BulkAppUsageSerializer(serializers.Serializer):
    """Agent yuboradigan umumiy paket"""
    bios_uuid = serializers.CharField(max_length=100)
    usages = AppUsageItemSerializer(many=True)

class AgentScreenShareResponseSerializer(serializers.Serializer):
    """ Agent o'zining tayyor URL manzilini yuboradigan qolip """
    bios_uuid = serializers.CharField(max_length=100)
    session_id = serializers.UUIDField()
    stream_url = serializers.URLField(max_length=1024)


# detail uchun
class AppUsageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppUsageStatistic
        fields = '__all__'

class ActivityLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityLog
        fields = '__all__'

class BlockedAttemptSerializer(serializers.ModelSerializer):
    url_address = serializers.CharField(source='url.url_address', read_only=True)
    class Meta:
        model = BlockedAttemptLog
        fields = ['id', 'url_address', 'attempts_count', 'created_at']

# Kompyuterning barcha ma'lumotlarini bittada beruvchi Detail Serializer
class ComputerDetailSerializer(serializers.ModelSerializer):
    app_usages = AppUsageSerializer(many=True, read_only=True)
    # Ehtiyojga qarab boshqalarini ham qo'shishingiz mumkin
    
    class Meta:
        model = Computer
        fields = [
            'id', 'hostname', 'bios_uuid', 'mac_address', 'cpu_info', 
            'ram_gb', 'storage_info', 'is_online', 'last_seen', 'app_usages'
        ]

