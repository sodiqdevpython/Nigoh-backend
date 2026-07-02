from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Kunlik bucketing uchun indexlar — bir kun ichida takrorlanadigan yozuv
    bo'lsa uni tez topib update qilish uchun.

    Query pattern:
        AppUsageStatistic.objects.filter(
            computer=X, created_at__gte=today_start, created_at__lt=today_end
        )
    """

    dependencies = [
        ('tracking', '0008_screenshotrequest_broadcastsession_and_more'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='appusagestatistic',
            index=models.Index(
                fields=['computer', 'created_at'],
                name='appusage_comp_created_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='activitylog',
            index=models.Index(
                fields=['computer', 'created_at'],
                name='activity_comp_created_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='blockedattemptlog',
            index=models.Index(
                fields=['computer', 'url', 'created_at'],
                name='blocked_comp_url_created_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='processalertlog',
            index=models.Index(
                fields=['computer', 'process_rule', 'created_at'],
                name='alert_comp_rule_created_idx',
            ),
        ),
    ]
