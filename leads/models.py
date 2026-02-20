from django.db import models

class Lead(models.Model):
    # Статусы для удобства обработки менеджерами в админке
    STATUS_CHOICES = (
        ('new', 'Новая заявка'),
        ('contacted', 'Взят в работу'),
        ('converted', 'Стал клиентом'),
        ('rejected', 'Отказ/Спам'),
    )

    full_name = models.CharField("Имя", max_length=255)
    email = models.EmailField("Email", blank=True, null=True)
    phone = models.CharField("Телефон", max_length=50)
    country = models.CharField("Страна", max_length=100, blank=True)
    education = models.CharField("Образование", max_length=255, blank=True)
    age = models.PositiveIntegerField("Возраст", null=True, blank=True)
    relation = models.CharField("Родство", max_length=100, blank=True, help_text="Например: Сам, Родитель, Брат")
    direction = models.CharField("Направление", max_length=255, blank=True, help_text="Желаемая программа/ВУЗ")
    
    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES, default='new')
    created_at = models.DateTimeField("Дата создания", auto_now_add=True)

    def __str__(self):
        return f"{self.full_name} ({self.phone})"

    class Meta:
        verbose_name = "Заявка с сайта"
        verbose_name_plural = "Заявки с сайта"
        ordering = ['-created_at']