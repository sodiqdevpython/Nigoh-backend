from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('commands', '0004_rename_commands_pe_compute_idx_commands_pe_compute_77b00a_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='pendingcommand',
            name='attempts',
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text='Buyruq yuborilgan marotaba soni. 5 ga yetganda bekor qilinadi.',
            ),
        ),
    ]
