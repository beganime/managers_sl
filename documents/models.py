# documents/models.py
import json
import io
import logging
from django.db import models
from django.conf import settings
from django.core.files.base import ContentFile
from docxtpl import DocxTemplate

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# База знаний — сниппеты
# ─────────────────────────────────────────────────────────────────────────────

class InfoSnippet(models.Model):
    CATEGORY_CHOICES = (
        ('script',     'Скрипты продаж'),
        ('faq',        'Ответы на частые вопросы'),
        ('requisites', 'Реквизиты и Счета'),
        ('links',      'Полезные ссылки'),
    )
    category   = models.CharField("Категория", max_length=50, choices=CATEGORY_CHOICES)
    title      = models.CharField("Название",  max_length=255)
    content    = models.TextField("Содержание (Текст для копирования)")
    order      = models.PositiveIntegerField("Порядок", default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name          = "База знаний"
        verbose_name_plural   = "База знаний"
        ordering              = ['category', 'order']


# ─────────────────────────────────────────────────────────────────────────────
# Тесты
# ─────────────────────────────────────────────────────────────────────────────

class KnowledgeTest(models.Model):
    title       = models.CharField("Название теста", max_length=255)
    description = models.TextField("Описание", blank=True)
    is_active   = models.BooleanField("Активен", default=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name        = "Тест"
        verbose_name_plural = "Тесты (База знаний)"
        ordering            = ['-created_at']


class TestQuestion(models.Model):
    test    = models.ForeignKey(
        KnowledgeTest, on_delete=models.CASCADE,
        related_name='questions', verbose_name="Тест"
    )
    text    = models.TextField("Текст вопроса")
    options = models.JSONField(
        "Варианты ответов",
        default=list,
        help_text='Список строк: ["Вариант 1", "Вариант 2", ...]'
    )
    correct = models.PositiveSmallIntegerField(
        "Индекс правильного ответа (с 0)",
        default=0
    )
    order   = models.PositiveIntegerField("Порядок", default=0)

    def __str__(self):
        return self.text[:60]

    class Meta:
        verbose_name        = "Вопрос"
        verbose_name_plural = "Вопросы"
        ordering            = ['order']


# ─────────────────────────────────────────────────────────────────────────────
# Шаблоны документов
# ─────────────────────────────────────────────────────────────────────────────

class DocumentTemplate(models.Model):
    title       = models.CharField("Название шаблона", max_length=255)
    description = models.TextField("Описание для менеджера", blank=True)
    file        = models.FileField("Файл шаблона (DOCX)", upload_to='templates/')
    is_active   = models.BooleanField("Активен", default=True)
    updated_at  = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name        = "Шаблон документа"
        verbose_name_plural = "Шаблоны документов"


class TemplateField(models.Model):
    FIELD_TYPES = (
        ('text',     'Строка текста'),
        ('numeric',  'Число'),
        ('date',     'Дата'),
        ('textarea', 'Большой текст'),
    )
    template   = models.ForeignKey(
        DocumentTemplate, on_delete=models.CASCADE,
        related_name='fields', verbose_name="Шаблон"
    )
    key        = models.CharField(
        "Ключ (как в docx)", max_length=50,
        help_text="Например: client_fio"
    )
    label      = models.CharField(
        "Название поля (для менеджера)", max_length=255,
        help_text="Например: ФИО Клиента"
    )
    field_type = models.CharField(
        "Тип поля", max_length=20, choices=FIELD_TYPES, default='text'
    )
    is_required = models.BooleanField("Обязательное", default=True)
    order       = models.PositiveIntegerField("Порядок вывода", default=0)

    class Meta:
        verbose_name        = "Поле шаблона"
        verbose_name_plural = "Поля шаблона"
        ordering            = ['order']

    def __str__(self):
        return f"{self.label} ({self.key})"


# ─────────────────────────────────────────────────────────────────────────────
# Сгенерированные документы
# ─────────────────────────────────────────────────────────────────────────────

class GeneratedDocument(models.Model):
    STATUS_CHOICES = (
        ('draft',     'Создан / Ожидает'),
        ('generated', 'Сгенерирован'),
        ('approved',  'Одобрен администратором'),   # ← новый статус
        ('error',     'Ошибка генерации'),
    )

    template       = models.ForeignKey(
        DocumentTemplate, on_delete=models.CASCADE,
        related_name='documents', verbose_name="Шаблон"
    )
    manager        = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='my_documents', verbose_name="Менеджер"
    )
    title          = models.CharField(
        "Название документа", max_length=255, blank=True
    )
    context_data   = models.JSONField(
        "Введённые данные", default=dict, blank=True
    )
    status         = models.CharField(
        "Статус", max_length=20, choices=STATUS_CHOICES, default='draft'
    )
    generated_file = models.FileField(
        "Готовый документ", upload_to='generated_docs/', null=True, blank=True
    )
    # Администратор, одобривший документ
    approved_by    = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='approved_documents',
        verbose_name="Одобрено администратором"
    )
    approved_at    = models.DateTimeField(null=True, blank=True)

    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title or f"Документ #{self.id} ({self.template.title})"

    class Meta:
        verbose_name        = "Сгенерированный документ"
        verbose_name_plural = "Сгенерированные документы"
        ordering            = ['-created_at']

    # ── Свойство: можно ли скачивать ────────────────────────────────────────
    @property
    def can_download(self) -> bool:
        """Скачивание доступно только после одобрения администратором."""
        return self.status == 'approved' and bool(self.generated_file)

    # ── Генерация DOCX ───────────────────────────────────────────────────────
    def generate_document(self):
        if not self.template.file:
            return False, "В шаблоне отсутствует файл DOCX."
        try:
            template_bytes  = self.template.file.read()
            template_stream = io.BytesIO(template_bytes)
            doc             = DocxTemplate(template_stream)

            context = self.context_data or {}
            if isinstance(context, str):
                try:
                    context = json.loads(context)
                except json.JSONDecodeError:
                    context = {}

            doc.render(context)

            buffer = io.BytesIO()
            doc.save(buffer)
            buffer.seek(0)

            safe_title = "".join(
                c for c in str(self.title or self.template.title)
                if c.isalpha() or c.isdigit() or c in ' -_'
            ).rstrip()
            filename = f"{safe_title}_{self.id}.docx".replace(" ", "_")

            self.generated_file.save(filename, ContentFile(buffer.read()), save=False)
            self.status = 'generated'
            self.save(update_fields=['generated_file', 'status', 'updated_at'])

            return True, "Документ успешно сгенерирован!"

        except Exception as e:
            msg = f"Ошибка DocxTemplate: {e}"
            logger.error(msg, exc_info=True)
            self.status = 'error'
            if self.pk:
                self.save(update_fields=['status', 'updated_at'])
            return False, msg