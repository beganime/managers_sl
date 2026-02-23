# documents/models.py
from django.db import models
from django.conf import settings
from django.core.files.base import ContentFile
from docxtpl import DocxTemplate
import io
import locale

try:
    locale.setlocale(locale.LC_ALL, 'ru_RU.UTF-8')
except:
    pass

from clients.models import Client
from catalog.models import Program

class InfoSnippet(models.Model):
    CATEGORY_CHOICES = (
        ('script', 'Скрипты продаж'),
        ('faq', 'Ответы на частые вопросы'),
        ('requisites', 'Реквизиты и Счета'),
        ('links', 'Полезные ссылки'),
    )
    category = models.CharField("Категория", max_length=50, choices=CATEGORY_CHOICES)
    title = models.CharField("Название", max_length=255)
    content = models.TextField("Содержание (Текст для копирования)")
    order = models.PositiveIntegerField("Порядок", default=0)

    def __str__(self): return self.title
    class Meta:
        verbose_name = "База знаний"
        verbose_name_plural = "База знаний"
        ordering = ['category', 'order']


class ContractTemplate(models.Model):
    # ОБНОВЛЕНИЕ: Разделили обучение на Бюджет и Контракт
    TYPE_CHOICES = (
        ('education_budget', 'Обучение (Бюджет)'),
        ('education_contract', 'Обучение (Контракт)'),
        ('work', 'Рабочая виза'),
        ('consent', 'Согласие на обработку'),
    )
    title = models.CharField("Название шаблона", max_length=255)
    type = models.CharField("Тип документа", max_length=30, choices=TYPE_CHOICES, default='education_contract')
    file = models.FileField("Файл шаблона (.docx)", upload_to="templates/contracts/")
    
    def __str__(self): return f"{self.title} ({self.get_type_display()})"
    class Meta:
        verbose_name = "Шаблон документа"
        verbose_name_plural = "Шаблоны документов"


class Contract(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Черновик (На проверке)'),
        ('approved', 'Одобрено (Готов к скачиванию)'),
        ('rejected', 'Отклонено'),
    )

    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="Менеджер")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, verbose_name="Студент/Клиент")
    template = models.ForeignKey(ContractTemplate, on_delete=models.PROTECT, verbose_name="Выберите шаблон")
    
    program = models.ForeignKey(Program, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Программа (для цены)")
    custom_price = models.DecimalField("Стоимость (если отличается от программы)", max_digits=10, decimal_places=2, null=True, blank=True)
    payment_deadline = models.DateField("Срок оплаты (до какого числа)", null=True, blank=True)
    
    customer_fio = models.CharField("ФИО Заказчика (Плательщика)", max_length=255, blank=True, help_text="Если пусто, подставится ФИО студента")
    customer_passport = models.CharField("Паспорт Заказчика", max_length=100, blank=True)
    customer_issued_at = models.DateField("Дата выдачи паспорта Заказчика", null=True, blank=True)
    customer_address = models.TextField("Адрес регистрации Заказчика", blank=True)

    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES, default='draft')
    generated_file = models.FileField("Готовый файл", upload_to="generated_contracts/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def generate_document(self):
        if not self.template.file:
            return
            
        doc = DocxTemplate(self.template.file.path)
        
        # Исправлено: берем service_fee из Program (т.к. price там нет)
        price = self.custom_price if self.custom_price else (self.program.service_fee if self.program else 0)
        
        cust_fio = self.customer_fio if self.customer_fio else self.client.full_name
        cust_pass = self.customer_passport if self.customer_passport else self.client.passport_inter_num
        cust_date = self.customer_issued_at.strftime("%d.%m.%Y") if self.customer_issued_at else (self.client.passport_issued_date.strftime("%d.%m.%Y") if self.client.passport_issued_date else "___")
        cust_addr = self.customer_address if self.customer_address else self.client.address_registration

        context = {
            'id': self.id,
            'date_today': self.created_at.strftime("%d.%m.%Y"),
            'year': self.created_at.strftime("%Y"),
            'manager_fio': f"{self.manager.first_name} {self.manager.last_name}",
            
            'student_fio': self.client.full_name,
            'citizenship': self.client.citizenship,
            'dob': self.client.dob.strftime("%d.%m.%Y") if self.client.dob else "",
            'passport_num': self.client.passport_inter_num,
            'passport_local': self.client.passport_local_num,
            'issued_by': self.client.passport_issued_by,
            'issued_date': self.client.passport_issued_date.strftime("%d.%m.%Y") if self.client.passport_issued_date else "",
            'address': self.client.address_registration,
            'city': self.client.city,

            'customer_fio': cust_fio,
            'customer_passport': cust_pass,
            'customer_issued_date': cust_date,
            'customer_address': cust_addr,
            
            'amount': f"{price:,.2f}",
            'payment_deadline': self.payment_deadline.strftime("%d.%m.%Y") if self.payment_deadline else "__________",
            'program_name': self.program.name if self.program else "Услуги компании", # Исправлено: title -> name
        }

        doc.render(context)
        
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        
        filename = f"{self.template.get_type_display()}_{self.client.full_name}.docx"
        self.generated_file.save(filename, ContentFile(buffer.read()), save=False)
        self.status = 'approved'
        self.save()

    class Meta:
        verbose_name = "Договор / Документ"
        verbose_name_plural = "Документооборот"