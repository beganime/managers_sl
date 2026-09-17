"""Additive expansion only. Existing identifiers and text fields stay intact.

Do not fill all existing rows with one evaluated UUID default. Existing rows
remain NULL until the explicit reconciliation commands have been reviewed.
"""
import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('crm', '0014_alter_client_funding_type'),
        ('education', '0005_university_abbreviation'),
    ]
    operations = [
        migrations.AddField(model_name=name, name='public_id', field=models.UUIDField(null=True, unique=True, editable=False))
        for name in ('client', 'application')
    ] + [
        migrations.AlterField(model_name=name, name='public_id', field=models.UUIDField(default=uuid.uuid4, null=True, unique=True, editable=False))
        for name in ('client', 'application')
    ] + [
        migrations.AddField(
            model_name='application', name=name,
            field=models.ForeignKey(to=target, on_delete=django.db.models.deletion.PROTECT, null=True, blank=True, related_name='crm_applications'),
        ) for name, target in (
            ('university', 'education.university'),
            ('program', 'education.program'),
            ('country_reference', 'education.country'),
        )
    ] + [
        migrations.AddField(model_name='application', name='academic_year', field=models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)),
    ]
