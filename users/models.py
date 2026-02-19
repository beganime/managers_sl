from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils import timezone
from datetime import timedelta

from students_life import settings

class Office(models.Model):
    city = models.CharField("Город", max_length=100)
    address = models.CharField("Адрес", max_length=255)
    phone = models.CharField("Телефон офиса", max_length=50)

    def __str__(self):
        return f"{self.city} ({self.address})"

    class Meta:
        verbose_name = "Офис"
        verbose_name_plural = "Офисы"


class UserManager(BaseUserManager):
    """Нужен для авторизации по Email вместо Username"""
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email обязателен')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Кастомная модель пользователя (Менеджера/Админа).
    Авторизация происходит по EMAIL.
    """
    STATUS_CHOICES = (
        ('working', 'Работаю'),
        ('vacation', 'В отпуске'),
        ('sick', 'На больничном'),
    )

    username = None  # Убираем поле username
    email = models.EmailField("Email (Логин)", unique=True)
    
    # Персональные данные
    middle_name = models.CharField("Отчество", max_length=100, blank=True)
    avatar = models.ImageField("Аватар", upload_to='avatars/', blank=True, null=True)
    dob = models.DateField("Дата рождения", null=True, blank=True)
    office = models.ForeignKey(Office, on_delete=models.SET_NULL, null=True, verbose_name="Офис")
    
    # Рабочие данные
    job_description = models.TextField("Описание должности", blank=True)
    work_status = models.CharField("Текущий статус", max_length=20, choices=STATUS_CHOICES, default='working')
    
    # Аналитика эффективности
    # Логика обновления этого поля будет в periodic tasks (Celery) или при входе
    is_effective = models.BooleanField("Эффективный сотрудник", default=True, help_text="Расчитывается автоматически на основе активности за 7 дней")
    last_activity = models.DateTimeField("Последняя активность", auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def check_efficiency(self):
        """Метод для проверки эффективности (вызывается из аналитики)"""
        seven_days_ago = timezone.now() - timedelta(days=7)
        # Если не было входа и нет действий (можно расширить логику)
        if self.last_login and self.last_login < seven_days_ago:
            self.is_effective = False
        else:
            self.is_effective = True
        self.save()

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"

    class Meta:
        verbose_name = "Сотрудник"
        verbose_name_plural = "Сотрудники"

# Пример того, что должно быть у менеджера для расчета ЗП
# (Можно добавить это в модель User или ManagerProfile)

class ManagerSalary(models.Model):
    manager = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    
    # Текущий баланс (Зарплата + Бонусы)
    current_balance = models.DecimalField("Баланс к выплате (USD)", max_digits=10, decimal_places=2, default=0.00)
    
    # KPI и План
    monthly_plan = models.DecimalField("План на месяц (USD)", max_digits=10, decimal_places=2, default=5000.00)
    current_month_revenue = models.DecimalField("Выручка в этом месяце", max_digits=12, decimal_places=2, default=0.00)
    commission_percent = models.DecimalField("Процент от сделок (%)", max_digits=5, decimal_places=2, default=10.00, help_text="Сколько получает менеджер с чистого дохода")
    def add_commission(self, amount):
        self.current_balance += amount
        self.save()
        
    def reset_balance(self):
        """Вызывается кнопкой 'Запросить зарплату'"""
        # Логика переноса в архив выплат
        self.current_balance = 0
        self.save()