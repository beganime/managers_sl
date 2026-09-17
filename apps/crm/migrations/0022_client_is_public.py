from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('crm', '0021_emailrecord')]
    operations = [migrations.AddField(
        model_name='client', name='is_public',
        field=models.BooleanField(default=False, db_index=True, verbose_name='Доступен сотрудникам компании'),
    )]
