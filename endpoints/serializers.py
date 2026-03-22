from rest_framework import serializers
from .models import Computer, Group

class ComputerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Computer
        fields = [
            'id', 'bios_uuid', 'hostname', 'mac_address', 'ip_address', 'group',
            'cpu_info', 'ram_gb', 'storage_info', 'last_boot_time'  # Yangi maydonlar qo'shildi
        ]
        read_only_fields = ['id']

    # Agar bu bios_uuid bazada bo'lsa, xato bermasdan borini qaytarishi yoki yangilashi uchun
    def create(self, validated_data):
        bios_uuid = validated_data.get('bios_uuid')
        computer, created = Computer.objects.update_or_create(
            bios_uuid=bios_uuid,
            defaults=validated_data
        )
        return computer