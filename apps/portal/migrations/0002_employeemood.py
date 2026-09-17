from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('portal', '0001_initial'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(
        name='EmployeeMood',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('date', models.DateField()), ('slot', models.PositiveSmallIntegerField()),
            ('score', models.PositiveSmallIntegerField(choices=[(1, 'Тяжело'), (2, 'Не очень'), (3, 'Спокойно'), (4, 'Хорошо'), (5, 'Отлично')])),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='daily_moods', to=settings.AUTH_USER_MODEL)),
        ],
        options={'ordering': ['date', 'slot'], 'constraints': [
            models.UniqueConstraint(fields=('user', 'date', 'slot'), name='unique_employee_mood_slot'),
            models.CheckConstraint(condition=models.Q(slot__gte=1, slot__lte=3), name='employee_mood_three_slots'),
            models.CheckConstraint(condition=models.Q(score__gte=1, score__lte=5), name='employee_mood_score_range'),
        ]},
    )]
