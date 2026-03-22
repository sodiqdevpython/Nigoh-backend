from rest_framework import serializers

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