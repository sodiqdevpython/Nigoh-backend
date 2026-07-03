from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('endpoints', '0005_alter_computer_auth_token'),
    ]

    operations = [
        migrations.AddField(
            model_name='computer',
            name='last_screenshot',
            field=models.ImageField(
                blank=True, null=True,
                upload_to='device_screenshots/',
                help_text="Device detail ochilganda avtomatik olingan eng oxirgi rasm",
            ),
        ),
        migrations.AddField(
            model_name='computer',
            name='last_screenshot_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
