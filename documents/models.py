# documents/models.py
from django.db import models
from django.conf import settings
from django.core.files.base import ContentFile
from docxtpl import DocxTemplate
import io

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
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self): 
        return self.title
        
    class Meta:
        verbose_name = "База знаний"
        verbose_name_plural = "База знаний"
        ordering = ['category', 'order']


class DocumentTemplate(models.Model):
    title = models.CharField("Название шаблона", max_length=255)
    description = models.TextField("Описание для менеджера", blank=True)
    file = models.FileField("Файл шаблона (DOCX)", upload_to='templates/')
    
    # Конфигурация полей, которые мобильное приложение должно запросить у менеджера.
    # Пример: 
    # [
    #   {"key": "fio", "label": "ФИО Клиента", "type": "text"},
    #   {"key": "amount", "label": "Сумма контракта", "type": "numeric"}
    # ]
    fields_config = models.JSONField(
        "Настройки полей (JSON)", 
        default=list, 
        blank=True, 
        help_text='Пример: [{"key": "fio", "label": "ФИО Клиента", "type": "text"}]'
    )
    
    is_active = models.BooleanField("Активен", default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Шаблон документа"
        verbose_name_plural = "Шаблоны документов"


class GeneratedDocument(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Создан / Ожидает'),
        ('generated', 'Сгенерирован'),
        ('error', 'Ошибка генерации'),
    )

    template = models.ForeignKey(DocumentTemplate, on_delete=models.CASCADE, related_name='documents', verbose_name="Шаблон")
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='my_documents', verbose_name="Менеджер")
    
    title = models.CharField("Название документа (для удобства)", max_length=255, blank=True)
    
    # В этом поле хранятся все данные, которые менеджер ввел в приложении
    context_data = models.JSONField("Введенные данные (Переменные)", default=dict, blank=True)
    
    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES, default='draft')
    generated_file = models.FileField("Готовый документ", upload_to='generated_docs/', null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title or f"Документ #{self.id} ({self.template.title})"

    class Meta:
        verbose_name = "Сгенерированный документ"
        verbose_name_plural = "Сгенерированные документы"
        ordering = ['-created_at']

    def generate_document(self):
        """Динамически генерирует DOCX файл на основе context_data и шаблона"""
        if not self.template.file:
            raise ValueError("В выбранном шаблоне отсутствует файл DOCX.")
            
        try:
            doc = DocxTemplate(self.template.file.path)
            
            # Контекст берется ровно из того, что прислал фронтенд
            context = self.context_data or {}
            
            doc.render(context)
            buffer = io.BytesIO()
            doc.save(buffer)
            buffer.seek(0)
            
            # Формируем красивое название
            safe_title = "".join([c for c in (self.title or self.template.title) if c.isalpha() or c.isdigit() or c in ' -_']).rstrip()
            filename = f"{safe_title}_{self.id}.docx".replace(" ", "_")
            
            self.generated_file.save(filename, ContentFile(buffer.read()), save=False)
            self.status = 'generated'
            self.save()
        except Exception as e:
            self.status = 'error'
            self.save()
            raise e