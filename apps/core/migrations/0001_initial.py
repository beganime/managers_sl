from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='SystemSetting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата создания')),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='Дата обновления')),
                ('key', models.CharField(db_index=True, max_length=120, unique=True, verbose_name='Ключ')),
                ('value', models.TextField(blank=True, verbose_name='Значение')),
                ('description', models.CharField(blank=True, max_length=255, verbose_name='Описание')),
            ],
            options={
                'verbose_name': 'Системная настройка',
                'verbose_name_plural': 'Системные настройки',
                'ordering': ['key'],
            },
        ),
    ]
