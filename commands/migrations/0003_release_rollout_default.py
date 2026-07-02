from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('commands', '0002_release_zip_file'),
    ]

    operations = [
        migrations.AlterField(
            model_name='release',
            name='rollout_percentage',
            field=models.IntegerField(
                default=100,
                help_text='Endi ishlatilmaydi — har doim 100%',
            ),
        ),
        migrations.AlterField(
            model_name='release',
            name='is_active',
            field=models.BooleanField(
                default=False,
                help_text="Faqat BITTA release active bo'la oladi har target uchun. Bu belgilangani yangi o'rnatishlar va yangilanishlar uchun ishlatiladi.",
            ),
        ),
    ]
