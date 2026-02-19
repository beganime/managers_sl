from django.db import models

class Service(models.Model):
    """
    Каталог дополнительных услуг (Виза, Трансфер, Билеты).
    Создает Администратор.
    """
    title = models.CharField("Название услуги", max_length=255)
    description = models.TextField("Описание", blank=True)
    
    # Цены
    price_client = models.DecimalField("Цена для клиента (USD)", max_digits=10, decimal_places=2, help_text="Эту цену видит менеджер")
    
    # СЕКРЕТНОЕ ПОЛЕ (Скрыть в admin.py от менеджеров через fieldsets)
    real_cost = models.DecimalField("Себестоимость (USD)", max_digits=10, decimal_places=2, default=0.00, help_text="Реальная цена услуги. НЕ ПОКАЗЫВАТЬ МЕНЕДЖЕРАМ.")
    
    is_active = models.BooleanField("Активна", default=True)

    def __str__(self):
        return f"{self.title} ({self.price_client}$)"

    class Meta:
        verbose_name = "Услуга (Каталог)"
        verbose_name_plural = "Услуги (Каталог)"