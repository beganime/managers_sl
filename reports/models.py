# reports/models.py
from django.conf import settings
from django.db import models
from django.utils import timezone


class DailyReport(models.Model):
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="Сотрудник"
    )
    date = models.DateField("Дата отчета", default=timezone.now)

    content = models.TextField("Что проделано за день")

    # Старые поля оставляем, чтобы ничего не сломать
    leads_processed = models.PositiveIntegerField("Обработано новых заявок", default=0)
    deals_closed = models.PositiveIntegerField("Закрыто сделок", default=0)

    # Новые поля под бизнес-процесс
    income = models.DecimalField("Доход за день (USD)", max_digits=12, decimal_places=2, default=0.00)
    expense = models.DecimalField("Расход за день (USD)", max_digits=12, decimal_places=2, default=0.00)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def net_result(self):
        return self.income - self.expense

    def __str__(self):
        employee_name = self.employee.first_name or self.employee.email
        return f"Отчет за {self.date} - {employee_name}"

    class Meta:
        verbose_name = "Ежедневный отчет"
        verbose_name_plural = "Ежедневные отчеты"
        ordering = ['-date', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['employee', 'date'],
                name='unique_daily_report_per_employee_per_day'
            )
        ]