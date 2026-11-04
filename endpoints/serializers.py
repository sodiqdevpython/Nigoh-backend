from rest_framework import serializers
from .models import Computer, Group


class ComputerSerializer(serializers.ModelSerializer):
    # Migratsiya uchun — agent eski (random) device_id dan yangi hardware ID ga
    # o'tganda eski ID shu yerda keladi. Modelda saqlanmaydi (write_only).
    previous_device_id = serializers.CharField(
        write_only=True, required=False, allow_blank=True, allow_null=True
    )

    class Meta:
        model = Computer
        fields = [
            'id', 'device_id', 'previous_device_id', 'bios_uuid', 'auth_token',
            'hostname', 'mac_address', 'group',
            'cpu_info', 'ram_gb', 'storage_info',
            'agent_version', 'watchdog_version',
        ]
        read_only_fields = ['id', 'auth_token']

    def create(self, validated_data):
        # previous_device_id modelga tegishli emas — ajratib olamiz
        previous_device_id = validated_data.pop('previous_device_id', None)

        # device_id bo'yicha aniqlanadi — agent har doim shu bilan keladi
        device_id = validated_data.get('device_id')
        if device_id:
            # ─── MIGRATSIYA ─────────────────────────────────────────────
            # Agent eski ID dan yangi hardware ID ga o'tgan bo'lsa, eski
            # yozuvni YANGI ID ga ko'chiramiz (device_id ni yangilaymiz).
            # Shu bitta qatorni o'zgartiramiz — barcha bog'liq ma'lumotlar
            # (loglar, buyruqlar, guruh, egasi, tarix) o'z joyida qoladi,
            # ya'ni eski PC YO'QOLMAYDI va dublikat yaratilmaydi.
            if previous_device_id and previous_device_id != device_id:
                # Yangi ID allaqachon mavjud bo'lsa — migratsiya shart emas
                if not Computer.objects.filter(device_id=device_id).exists():
                    old = Computer.objects.filter(device_id=previous_device_id).first()
                    if old:
                        old.device_id = device_id
                        old.save(update_fields=['device_id'])

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
