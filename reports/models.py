# reports/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone

class DailyReport(models.Model):
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="Сотрудник")
    date = models.DateField("Дата отчета", default=timezone.now)
    
    content = models.TextField("Что проделано за день")
    leads_processed = models.PositiveIntegerField("Обработано новых заявок", default=0)
    deals_closed = models.PositiveIntegerField("Закрыто сделок", default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Отчет за {self.date} - {self.employee.first_name}"

    class Meta:
        verbose_name = "Ежедневный отчет"
        verbose_name_plural = "Ежедневные отчеты"
        ordering = ['-date']