# timetracking/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone

class WorkShift(models.Model):
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="Сотрудник")
    date = models.DateField("Дата смены", default=timezone.now)
    time_in = models.DateTimeField("Время прихода", default=timezone.now)
    time_out = models.DateTimeField("Время ухода", null=True, blank=True)
    is_active = models.BooleanField("Смена активна (В офисе)", default=True)
    
    hours_worked = models.DecimalField("Отработано часов", max_digits=5, decimal_places=2, default=0.00)
    
    # НОВОЕ ПОЛЕ: Маркер нарушения
    is_auto_closed = models.BooleanField("Закрыто автоматически (Забыл уйти)", default=False)

    def save(self, *args, **kwargs):
        # Автоматический подсчет часов при завершении смены
        if self.time_out and self.time_in:
            diff = self.time_out - self.time_in
            self.hours_worked = round(diff.total_seconds() / 3600, 2)
            self.is_active = False
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Смена: {self.employee} ({self.date})"

    class Meta:
        verbose_name = "Рабочая смена"
        verbose_name_plural = "Учет рабочего времени"
        ordering = ['-date', '-time_in']