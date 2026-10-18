from django.db import migrations, models


def populate_abbreviations(apps, schema_editor):
    import re

    University = apps.get_model('education', 'University')
    ignored = {'имени', 'им', 'имя', 'государственный', 'государственная'}
    for university in University.objects.filter(abbreviation='').iterator():
        explicit = re.match(r'^([A-ZА-ЯЁ0-9][A-ZА-ЯЁ0-9.\-]{1,14})\s*\(', university.name or '')
        if explicit:
            abbreviation = explicit.group(1).replace('.', '')
        else:
            words = re.findall(r'[A-Za-zА-Яа-яЁё0-9]+', university.name or '')
            abbreviation = ''.join(word[0].upper() for word in words if word.casefold() not in ignored)[:16]
        university.abbreviation = abbreviation
        university.save(update_fields=['abbreviation'])


class Migration(migrations.Migration):
    dependencies = [('education', '0004_alter_currency_code')]

    operations = [
        migrations.AddField(
            model_name='university',
            name='abbreviation',
            field=models.CharField(blank=True, db_index=True, max_length=24, verbose_name='Аббревиатура'),
        ),
        migrations.RunPython(populate_abbreviations, migrations.RunPython.noop),
    ]
