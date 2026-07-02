from django.db import migrations, models
import commands.models


class Migration(migrations.Migration):

    dependencies = [
        ('commands', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='release',
            name='zip_file',
            field=models.FileField(
                blank=True, null=True,
                upload_to=commands.models._release_zip_path,
                help_text="ZIP fayl yuklang — backend ichidagi fayllarni avtomatik ochadi",
            ),
        ),
    ]
