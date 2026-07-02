import uuid
import django.db.models.deletion
from django.db import migrations, models

import commands.models  # noqa  — _upload_path callable uchun


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('endpoints', '0004_device_id_and_versioning'),
    ]

    operations = [
        migrations.CreateModel(
            name='Release',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('target', models.CharField(
                    choices=[('nigoh', 'Nigoh.exe (asosiy agent)'),
                             ('watchdog', 'WatchdogService.exe')],
                    default='nigoh', max_length=20,
                )),
                ('version', models.CharField(help_text='Masalan: 1.2.0', max_length=20)),
                ('notes', models.TextField(blank=True, help_text='Changelog')),
                ('rollout_percentage', models.IntegerField(
                    default=0,
                    help_text='0-100. Faqat shu % agent yangilanishi mumkin (deterministik device_id hash)',
                )),
                ('is_active', models.BooleanField(
                    default=False,
                    help_text="Faqat bitta Release active bo'la oladi har target uchun",
                )),
                ('manifest', models.JSONField(blank=True, default=dict, help_text="{'deleted_files': [...], ...}")),
            ],
            options={
                'ordering': ['-created_at'],
                'unique_together': {('target', 'version')},
            },
        ),
        migrations.CreateModel(
            name='UpdateFile',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('file', models.FileField(upload_to=commands.models._upload_path)),
                ('rel_path', models.CharField(
                    help_text="Agent papkasidagi nisbiy yo'l, masalan: 'Nigoh.exe' yoki 'lib\\\\ng_db_module.dll'",
                    max_length=255,
                )),
                ('sha256', models.CharField(blank=True, help_text='Saqlashda avtomatik hisoblanadi', max_length=64)),
                ('size', models.BigIntegerField(default=0)),
                ('release', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='files',
                    to='commands.release',
                )),
            ],
            options={'abstract': False},
        ),
        migrations.CreateModel(
            name='PendingCommand',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('action', models.CharField(
                    choices=[('update', 'Yangilash'),
                             ('uninstall', "O'chirish"),
                             ('restart', 'Qayta ishga tushirish')],
                    max_length=20,
                )),
                ('force', models.BooleanField(default=False, help_text="Rollout % e'tiborga olinmaydi")),
                ('delivered_at', models.DateTimeField(blank=True, null=True)),
                ('acknowledged_at', models.DateTimeField(blank=True, null=True)),
                ('success', models.BooleanField(null=True)),
                ('error_message', models.TextField(blank=True)),
                ('computer', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='pending_commands',
                    to='endpoints.computer',
                )),
                ('release', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    to='commands.release',
                    help_text="Faqat action=update bo'lganda",
                )),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='pendingcommand',
            index=models.Index(fields=['computer', 'delivered_at'], name='commands_pe_compute_idx'),
        ),
        migrations.CreateModel(
            name='UpdateLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('from_version', models.CharField(blank=True, max_length=20)),
                ('to_version', models.CharField(max_length=20)),
                ('target', models.CharField(max_length=20)),
                ('success', models.BooleanField()),
                ('error', models.TextField(blank=True)),
                ('computer', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='update_logs',
                    to='endpoints.computer',
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
