from rest_framework import serializers
from .models import (
    AppUsageStatistic, ActivityLog,
    BlockedAttemptLog, ProcessAlertLog, ScreenShareSession
)
from endpoints.models import Computer


# ---------------------------------------------------------------
# AGENT YUBORADIGAN PAYLOADLARDA IDENTIFIKATOR
#
# Yangi agentlar `device_id` yuboradi, eski agentlar `bios_uuid`.
# Ikkalasini ham qabul qilamiz — `agent_id` property hech qaysi
# bo'sh bo'lmagan qiymatni qaytaradi.
# ---------------------------------------------------------------

class _AgentIdMixin:
    """Serializer ichida ishlatish — har ikkala field optional, biri majburiy."""

    def _ensure_one_id(self, data):
        if not data.get('device_id') and not data.get('bios_uuid'):
            raise serializers.ValidationError(
                "device_id yoki bios_uuid maydonidan birini yuboring."
            )

    @staticmethod
    def get_agent_id(validated):
        return validated.get('device_id') or validated.get('bios_uuid')


class ReportBlockedSerializer(_AgentIdMixin, serializers.Serializer):
    device_id = serializers.CharField(max_length=100, required=False, allow_blank=True)
    bios_uuid = serializers.CharField(max_length=100, required=False, allow_blank=True)
    # url_id endi ixtiyoriy — url_address ham fallback sifatida qabul qilinadi
    url_id = serializers.UUIDField(required=False, allow_null=True)
    url_address = serializers.CharField(required=False, allow_blank=True, max_length=255)
    attempts_count = serializers.IntegerField(min_value=1)

    def validate(self, attrs):
        self._ensure_one_id(attrs)
        if not attrs.get('url_id') and not attrs.get('url_address'):
            raise serializers.ValidationError(
                "url_id yoki url_address maydonidan birini yuboring."
            )
        return attrs


class ActivityLogItemSerializer(serializers.Serializer):
    """Bitta oyna/dastur uchun ma'lumot"""
    title = serializers.CharField(max_length=500, allow_blank=True, required=False)
    app_name = serializers.CharField(max_length=255)
    url = serializers.CharField(allow_blank=True, required=False)
    duration_seconds = serializers.IntegerField(min_value=0)


class BulkActivityLogSerializer(_AgentIdMixin, serializers.Serializer):
    """Agent yuboradigan umumiy paket"""
    device_id = serializers.CharField(max_length=100, required=False, allow_blank=True)
    bios_uuid = serializers.CharField(max_length=100, required=False, allow_blank=True)
    logs = ActivityLogItemSerializer(many=True)

    def validate(self, attrs):
        self._ensure_one_id(attrs)
        return attrs


class ProcessAlertSerializer(_AgentIdMixin, serializers.Serializer):
    device_id = serializers.CharField(max_length=100, required=False, allow_blank=True)
    bios_uuid = serializers.CharField(max_length=100, required=False, allow_blank=True)
    rule_id = serializers.UUIDField()
    app_name = serializers.CharField(max_length=255)
    full_path = serializers.CharField()
    attempts_count = serializers.IntegerField(min_value=1)

    def validate(self, attrs):
        self._ensure_one_id(attrs)
        return attrs


class AppUsageItemSerializer(serializers.Serializer):
    """Bitta dastur statistikasi uchun qolip"""
    app_name = serializers.CharField(max_length=255)
    full_path = serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)
    total_open_seconds = serializers.IntegerField(min_value=0)
    active_seconds = serializers.IntegerField(min_value=0)
    mouse_active_seconds = serializers.IntegerField(min_value=0)
    keyboard_active_seconds = serializers.IntegerField(min_value=0)


class BulkAppUsageSerializer(_AgentIdMixin, serializers.Serializer):
    """Agent yuboradigan umumiy paket"""
    device_id = serializers.CharField(max_length=100, required=False, allow_blank=True)
    bios_uuid = serializers.CharField(max_length=100, required=False, allow_blank=True)
    usages = AppUsageItemSerializer(many=True)

    def validate(self, attrs):
        self._ensure_one_id(attrs)
        return attrs


class AgentScreenShareResponseSerializer(_AgentIdMixin, serializers.Serializer):
    """Agent o'zining tayyor URL manzilini yuboradigan qolip"""
    device_id = serializers.CharField(max_length=100, required=False, allow_blank=True)
    bios_uuid = serializers.CharField(max_length=100, required=False, allow_blank=True)
    session_id = serializers.UUIDField()
    stream_url = serializers.URLField(max_length=1024)

    def validate(self, attrs):
        self._ensure_one_id(attrs)
        return attrs


# ---------------------------------------------------------------
# DETAIL VIEW UCHUN (admin paneldan)
# ---------------------------------------------------------------

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


class ComputerDetailSerializer(serializers.ModelSerializer):
    app_usages = AppUsageSerializer(many=True, read_only=True)

    class Meta:
        model = Computer
        fields = [
            'id', 'hostname', 'device_id', 'bios_uuid', 'mac_address', 'cpu_info',
            'ram_gb', 'storage_info', 'is_online', 'last_seen', 'app_usages'
        ]
