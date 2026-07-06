from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0005_lead_api_source_lead_archive_reason_lead_archived_at_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='mobile_app_source',
            field=models.BooleanField(default=False, verbose_name='Mobile app client'),
        ),
        migrations.AddField(
            model_name='client',
            name='mobile_app_user_id',
            field=models.PositiveIntegerField(blank=True, db_index=True, null=True, verbose_name='Mobile app user ID'),
        ),
        migrations.AddField(
            model_name='clientfile',
            name='external_file_url',
            field=models.URLField(blank=True, max_length=1000, verbose_name='External file URL'),
        ),
        migrations.AddField(
            model_name='clientfile',
            name='external_mobile_document_id',
            field=models.PositiveIntegerField(blank=True, db_index=True, null=True, verbose_name='Mobile document ID'),
        ),
        migrations.AddField(
            model_name='clientfile',
            name='external_mobile_user_id',
            field=models.PositiveIntegerField(blank=True, db_index=True, null=True, verbose_name='Mobile user ID'),
        ),
        migrations.AddField(
            model_name='clientfile',
            name='has_translation',
            field=models.BooleanField(default=False, verbose_name='Has translation'),
        ),
        migrations.AddField(
            model_name='clientfile',
            name='review_comment',
            field=models.TextField(blank=True, verbose_name='Review comment'),
        ),
        migrations.AddField(
            model_name='clientfile',
            name='reviewed_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Reviewed at'),
        ),
        migrations.AddField(
            model_name='clientfile',
            name='reviewed_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reviewed_crm_files', to=settings.AUTH_USER_MODEL, verbose_name='Reviewed by'),
        ),
        migrations.AddField(
            model_name='clientfile',
            name='source',
            field=models.CharField(blank=True, max_length=80, verbose_name='Source'),
        ),
        migrations.AddField(
            model_name='clientfile',
            name='status',
            field=models.CharField(choices=[('pending', 'Pending review'), ('approved', 'Approved'), ('rejected', 'Rejected')], db_index=True, default='pending', max_length=20, verbose_name='Review status'),
        ),
    ]
