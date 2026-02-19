from django.db import models
from django.conf import settings

class Client(models.Model):
    STATUS_CHOICES = (
        ('new', 'Новый'),
        ('consultation', 'Консультация'),
        ('documents', 'Сбор документов'),
        ('visa', 'Виза'),
        ('success', 'Завершен (Успех)'),
        ('rejected', 'Отказ'),
        ('archive', 'Архив (Авто)'),
    )

    # Основная информация
    full_name = models.CharField("ФИО Клиента", max_length=255)
    dob = models.DateField("Дата рождения", null=True, blank=True)
    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES, default='new')
    is_priority = models.BooleanField("Приоритетный клиент", default=False, help_text="Если нет, клиент может уйти в архив автоматически")
    
    # Контакты
    phone = models.CharField("Номер телефона", max_length=50)
    email = models.EmailField("Email", blank=True, null=True)
    city = models.CharField("Город", max_length=100)
    
    # Документы
    passport_local_num = models.CharField("Серия внутреннего паспорта", max_length=50, blank=True)
    passport_inter_num = models.CharField("Серия загранпаспорта", max_length=50, blank=True)
    
    # Менеджмент
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='my_clients', verbose_name="Основной менеджер")
    shared_with = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='shared_clients', verbose_name="Доступ открыт также для")
    
    # Задачи и комменты
    current_tasks = models.TextField("Текущие задачи", blank=True)
    comments = models.TextField("Комментарии", blank=True)
    
    # Партнерская секция
    is_partner_client = models.BooleanField("От партнера?", default=False)
    partner_name = models.CharField("Название партнера", max_length=255, blank=True)
    has_discount = models.BooleanField("Есть скидка?", default=False)
    discount_amount = models.DecimalField("Сумма/Процент скидки", max_digits=10, decimal_places=2, default=0.00, help_text="Скидка на услуги (USD)")

    # --- Личные данные (Расширенные) ---
    citizenship = models.CharField("Гражданство", max_length=100, default="Туркменистан")
    
    # --- Паспортные данные ---
    passport_local_num = models.CharField("Серия/Номер внутреннего паспорта", max_length=50, blank=True)
    passport_inter_num = models.CharField("Номер загранпаспорта", max_length=50, blank=True)
    
    # НОВЫЕ ПОЛЯ ДЛЯ ДОГОВОРА
    passport_issued_by = models.CharField("Кем выдан паспорт", max_length=255, blank=True, help_text="Например: МВД Туркменистана")
    passport_issued_date = models.DateField("Дата выдачи паспорта", null=True, blank=True)
    address_registration = models.TextField("Адрес регистрации (Прописка)", blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.full_name} [{self.get_status_display()}]"

    class Meta:
        verbose_name = "Клиент"
        verbose_name_plural = "Клиенты"


class ClientRelative(models.Model):
    """Ближайший родственник клиента"""
    client = models.OneToOneField(Client, on_delete=models.CASCADE, related_name='relative')
    full_name = models.CharField("ФИО", max_length=255)
    relation_type = models.CharField("Кем приходится", max_length=100, help_text="Отец, Мать, Брат...")
    phone = models.CharField("Телефон", max_length=50)
    work_place = models.CharField("Место работы", max_length=255, blank=True)

    def __str__(self):
        return f"Родственник: {self.full_name} для {self.client.full_name}"