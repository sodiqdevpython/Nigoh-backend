import secrets
from django.db import migrations, models


def _populate_auth_tokens(apps, schema_editor):
    Computer = apps.get_model('endpoints', 'Computer')
    for c in Computer.objects.filter(auth_token__isnull=True):
        c.auth_token = secrets.token_hex(32)
        c.save(update_fields=['auth_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('endpoints', '0003_remove_group_description_group_building_group_floor_and_more'),
    ]

    operations = [
        # 1. bios_uuid endi UNIQUE emas (ghost UUID lar bo'lishi mumkin)
        migrations.AlterField(
            model_name='computer',
            name='bios_uuid',
            field=models.CharField(
                blank=True, db_index=True, max_length=100, null=True,
                help_text="Raw BIOS UUID — debug uchun (ghost bo'lishi mumkin)",
            ),
        ),

        # 2. device_id — yangi asosiy ID (32 hex), agent o'zi yaratadi
        migrations.AddField(
            model_name='computer',
            name='device_id',
            field=models.CharField(
                blank=True, db_index=True, max_length=32, null=True, unique=True,
                help_text="Agent tomonidan yaratilgan GUID hex (32 belgi)",
            ),
        ),

        # 3. auth_token — avval null=True bilan qo'shamiz
        migrations.AddField(
            model_name='computer',
            name='auth_token',
            field=models.CharField(max_length=64, null=True, unique=True),
        ),
        # Mavjud yozuvlarga unique token beriladi
        migrations.RunPython(_populate_auth_tokens, reverse_code=migrations.RunPython.noop),
        # Shundan keyin null=False va default qo'yamiz
        migrations.AlterField(
            model_name='computer',
            name='auth_token',
            field=models.CharField(
                default='', max_length=64, unique=True,
                help_text="Agent uchun xavfsizlik tokeni",
            ),
            preserve_default=False,
        ),

        # 4. Versiya maydonlari
        migrations.AddField(
            model_name='computer',
            name='agent_version',
            field=models.CharField(
                blank=True, max_length=20, null=True,
                help_text="Nigoh.exe versiyasi (agent xabar bergan)",
            ),
        ),
        migrations.AddField(
            model_name='computer',
            name='watchdog_version',
            field=models.CharField(
                blank=True, max_length=20, null=True,
                help_text="WatchdogService.exe versiyasi",
            ),
        ),
        migrations.AddField(
            model_name='computer',
            name='last_version_report',
            field=models.DateTimeField(
                blank=True, null=True,
                help_text="Oxirgi marta versiya xabar bergan vaqt",
            ),
        ),
    ]
