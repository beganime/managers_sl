# documents/models.py
import json
import io
import logging
from django.db import models
from django.conf import settings
from django.core.files.base import ContentFile
from docxtpl import DocxTemplate

logger = logging.getLogger(__name__)

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
    is_active = models.BooleanField("Активен", default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Шаблон документа"
        verbose_name_plural = "Шаблоны документов"


class TemplateField(models.Model):
    FIELD_TYPES = (
        ('text', 'Строка текста'),
        ('numeric', 'Число'),
        ('date', 'Дата'),
        ('textarea', 'Большой текст'),
    )

    template = models.ForeignKey(DocumentTemplate, on_delete=models.CASCADE, related_name='fields', verbose_name="Шаблон")
    key = models.CharField("Ключ (как в docx)", max_length=50, help_text="Например: client_fio")
    label = models.CharField("Название поля (для менеджера)", max_length=255, help_text="Например: ФИО Клиента")
    field_type = models.CharField("Тип поля", max_length=20, choices=FIELD_TYPES, default='text')
    is_required = models.BooleanField("Обязательное", default=True)
    order = models.PositiveIntegerField("Порядок вывода", default=0)

    class Meta:
        verbose_name = "Поле шаблона"
        verbose_name_plural = "Поля шаблона"
        ordering = ['order']

    def __str__(self):
        return f"{self.label} ({self.key})"


class GeneratedDocument(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Создан / Ожидает'),
        ('generated', 'Сгенерирован'),
        ('error', 'Ошибка генерации'),
    )

    template = models.ForeignKey(DocumentTemplate, on_delete=models.CASCADE, related_name='documents', verbose_name="Шаблон")
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='my_documents', verbose_name="Менеджер")
    title = models.CharField("Название документа (для удобства)", max_length=255, blank=True)
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
        """
        Безопасная генерация документа.
        Возвращает кортеж: (success: bool, message: str)
        Это предотвращает падение сервера (500 Error) и отдает ошибку прямо в UI.
        """
        if not self.template.file:
            return False, "В выбранном шаблоне отсутствует файл DOCX."
            
        try:
            # Считываем файл напрямую в байты, чтобы избежать конфликтов блокировки (file locks)
            template_bytes = self.template.file.read()
            template_stream = io.BytesIO(template_bytes)
            
            doc = DocxTemplate(template_stream)
            
            context = self.context_data or {}
            if isinstance(context, str):
                try:
                    context = json.loads(context)
                except json.JSONDecodeError:
                    context = {}
            
            # Рендер DOCX документа
            doc.render(context)
            
            # Сохранение в буфер
            buffer = io.BytesIO()
            doc.save(buffer)
            buffer.seek(0)
            
            # Очистка названия файла от спецсимволов
            safe_title = "".join([c for c in str(self.title or self.template.title) if c.isalpha() or c.isdigit() or c in ' -_']).rstrip()
            filename = f"{safe_title}_{self.id}.docx".replace(" ", "_")
            
            self.generated_file.save(filename, ContentFile(buffer.read()), save=False)
            self.status = 'generated'
            
            # Обновляем только нужные поля (оптимизация под Highload)
            self.save(update_fields=['generated_file', 'status', 'updated_at'])
            
            return True, "Документ успешно сгенерирован!"
            
        except Exception as e:
            error_msg = f"Ошибка генерации (DocxTemplate): {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.status = 'error'
            if self.pk:
                self.save(update_fields=['status', 'updated_at'])
            
            # Возвращаем False вместо 'raise e', устраняя 500 ошибку
            return False, error_msg