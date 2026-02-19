from django.db import models
from django.conf import settings

class Currency(models.Model):
    """
    Таблица валют. 
    Базовая логика: 1 USD = rate * Local Currency.
    """
    code = models.CharField("Код валюты (ISO)", max_length=3, unique=True) # TMT, RUB, EUR
    name = models.CharField("Название", max_length=50)
    symbol = models.CharField("Символ", max_length=5, default='$')
    rate = models.DecimalField("Курс к 1 USD", max_digits=10, decimal_places=4, help_text="Сколько единиц этой валюты в 1 долларе?")
    
    def __str__(self):
        return f"{self.code} ({self.rate})"

    class Meta:
        verbose_name = "Валюта"
        verbose_name_plural = "Курсы валют"
        ordering = ['code']


class University(models.Model):
    name = models.CharField("Название ВУЗа", max_length=255)
    country = models.CharField("Страна", max_length=100)
    city = models.CharField("Город", max_length=100)
    logo = models.ImageField("Логотип", upload_to='uni_logos/', blank=True)
    
    # Валюта страны для отображения цен
    local_currency = models.ForeignKey(Currency, on_delete=models.SET_NULL, null=True, verbose_name="Валюта страны")
    
    description = models.TextField("Общее описание")
    expenses_info = models.TextField("Расходы (проживание и т.д.)", blank=True)
    invitation_info = models.TextField("Информация о приглашении", blank=True)
    
    intake_period = models.CharField("Период приема", max_length=100, help_text="Например: Сентябрь - Январь")
    age_limit = models.CharField("Возрастные ограничения", max_length=50, blank=True)
    required_docs = models.TextField("Нужные документы")
    contacts = models.TextField("Контакты университета")
    
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Кем добавлен")

    def __str__(self):
        return f"{self.name} ({self.country})"

    class Meta:
        verbose_name = "Университет"
        verbose_name_plural = "Университеты"
        ordering = ['name']


class Program(models.Model):
    university = models.ForeignKey(University, on_delete=models.CASCADE, related_name='programs', verbose_name="Университет")
    name = models.CharField("Название программы", max_length=255)
    degree = models.CharField("Степень", max_length=100, choices=[
        ('bachelor', 'Бакалавр'), 
        ('master', 'Магистр'),
        ('specialist', 'Специалитет'), 
        ('language', 'Языковые курсы')
    ])
    
    # Финансы
    tuition_fee = models.DecimalField("Стоимость обучения (Местная валюта)", max_digits=12, decimal_places=2)
    service_fee = models.DecimalField("Стоимость НАШИХ услуг (USD)", max_digits=10, decimal_places=2, default=500.00)
    
    duration = models.CharField("Длительность", max_length=50)
    
    is_active = models.BooleanField("Активна", default=True)
    # Вместо удаления используем "Мягкое удаление" (Soft Delete) чтобы не ломать историю
    is_deleted = models.BooleanField("Удалена (Архив)", default=False)

    def __str__(self):
        return f"{self.name} - {self.university.name}"

    class Meta:
        verbose_name = "Программа обучения"
        verbose_name_plural = "Программы обучения"
        ordering = ['university__name', 'name']