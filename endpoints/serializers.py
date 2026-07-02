from rest_framework import serializers
from .models import Computer, Group


class ComputerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Computer
        fields = [
            'id', 'device_id', 'bios_uuid', 'auth_token',
            'hostname', 'mac_address', 'group',
            'cpu_info', 'ram_gb', 'storage_info',
            'agent_version', 'watchdog_version',
        ]
        read_only_fields = ['id', 'auth_token']

    def create(self, validated_data):
        # device_id bo'yicha aniqlanadi — agent har doim shu bilan keladi
        device_id = validated_data.get('device_id')
        if device_id:
            computer, _ = Computer.objects.update_or_create(
                device_id=device_id,
                defaults=validated_data
            )
            return computer

        # Eski agentlar device_id yubormasa — bios_uuid bo'yicha fallback (legacy)
        bios_uuid = validated_data.get('bios_uuid')
        if bios_uuid:
            computer, _ = Computer.objects.update_or_create(
                bios_uuid=bios_uuid,
                defaults=validated_data
            )
            return computer

        return super().create(validated_data)
