# documents/models.py
import io
import json
import logging

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from docxtpl import DocxTemplate

from .review_guard import safe_get_document_review


logger = logging.getLogger(__name__)


class KnowledgeSection(models.Model):
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name='Родительский раздел',
    )
    title = models.CharField('Название', max_length=255)
    slug = models.SlugField(
        'Slug',
        max_length=255,
        blank=True,
        db_index=True,
        allow_unicode=True,
    )
    icon = models.CharField('Иконка', max_length=60, blank=True, default='folder')
    color = models.CharField('Цвет', max_length=30, blank=True)
    order = models.PositiveIntegerField('Порядок', default=0)
    is_active = models.BooleanField('Активен', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Раздел базы знаний'
        verbose_name_plural = 'Разделы базы знаний'
        ordering = ['parent__id', 'order', 'title']

    def __str__(self):
        return self.full_path

    @property
    def full_path(self):
        parts = [self.title]
        parent = self.parent
        guard = 0

        while parent and guard < 20:
            parts.append(parent.title)
            parent = parent.parent
            guard += 1

        return ' / '.join(reversed(parts))

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title, allow_unicode=True) or 'section'
        super().save(*args, **kwargs)


class InfoSnippet(models.Model):
    CATEGORY_CHOICES = (
        ('script', 'Скрипты продаж'),
        ('faq', 'Ответы на частые вопросы'),
        ('requisites', 'Реквизиты и Счета'),
        ('links', 'Полезные ссылки'),
    )

    section = models.ForeignKey(
        KnowledgeSection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='snippets',
        verbose_name='Раздел',
    )
    category = models.CharField(
        'Категория',
        max_length=50,
        choices=CATEGORY_CHOICES,
        default='faq',
    )
    title = models.CharField('Название', max_length=255)
    content = models.TextField('Содержание (Текст для копирования)')
    order = models.PositiveIntegerField('Порядок', default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = 'База знаний'
        verbose_name_plural = 'База знаний'
        ordering = ['section__order', 'category', 'order', 'title']


class KnowledgeTest(models.Model):
    section = models.ForeignKey(
        KnowledgeSection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tests',
        verbose_name='Раздел',
    )
    title = models.CharField('Название теста', max_length=255)
    description = models.TextField('Описание', blank=True)
    is_active = models.BooleanField('Активен', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = 'Тест'
        verbose_name_plural = 'Тесты (База знаний)'
        ordering = ['-created_at']


class TestQuestion(models.Model):
    test = models.ForeignKey(
        KnowledgeTest,
        on_delete=models.CASCADE,
        related_name='questions',
        verbose_name='Тест',
    )
    text = models.TextField('Текст вопроса')
    options = models.JSONField(
        'Варианты ответов',
        default=list,
        help_text='Список строк: ["Вариант 1", "Вариант 2", ...]',
    )
    correct = models.PositiveSmallIntegerField(
        'Индекс правильного ответа (с 0)',
        default=0,
    )
    order = models.PositiveIntegerField('Порядок', default=0)

    def __str__(self):
        return self.text[:60]

    class Meta:
        verbose_name = 'Вопрос'
        verbose_name_plural = 'Вопросы'
        ordering = ['order']


class KnowledgeTestAttempt(models.Model):
    test = models.ForeignKey(
        KnowledgeTest,
        on_delete=models.CASCADE,
        related_name='attempts',
        verbose_name='Тест',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='knowledge_test_attempts',
        verbose_name='Пользователь',
    )
    score = models.PositiveIntegerField('Правильных ответов', default=0)
    total = models.PositiveIntegerField('Всего вопросов', default=0)
    answers = models.JSONField('Ответы пользователя', default=dict, blank=True)
    started_at = models.DateTimeField('Начало', auto_now_add=True)
    completed_at = models.DateTimeField('Завершено', auto_now=True)

    class Meta:
        verbose_name = 'Результат теста'
        verbose_name_plural = 'Результаты тестов'
        ordering = ['-completed_at']

    def __str__(self):
        return f'{self.user} — {self.test} ({self.score}/{self.total})'

    @property
    def percent(self):
        if not self.total:
            return 0
        return round((self.score / self.total) * 100, 2)


class DocumentTemplate(models.Model):
    title = models.CharField('Название шаблона', max_length=255)
    description = models.TextField('Описание для менеджера', blank=True)
    file = models.FileField('Файл шаблона (DOCX)', upload_to='templates/')
    is_active = models.BooleanField('Активен', default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = 'Шаблон документа'
        verbose_name_plural = 'Шаблоны документов'


class TemplateField(models.Model):
    FIELD_TYPES = (
        ('text', 'Строка текста'),
        ('numeric', 'Число'),
        ('date', 'Дата'),
        ('textarea', 'Большой текст'),
    )

    template = models.ForeignKey(
        DocumentTemplate,
        on_delete=models.CASCADE,
        related_name='fields',
        verbose_name='Шаблон',
    )
    key = models.CharField(
        'Ключ (как в docx)',
        max_length=50,
        help_text='Например: client_fio',
    )
    label = models.CharField(
        'Название поля (для менеджера)',
        max_length=255,
        help_text='Например: ФИО Клиента',
    )
    field_type = models.CharField(
        'Тип поля',
        max_length=20,
        choices=FIELD_TYPES,
        default='text',
    )
    is_required = models.BooleanField('Обязательное', default=True)
    order = models.PositiveIntegerField('Порядок вывода', default=0)

    class Meta:
        verbose_name = 'Поле шаблона'
        verbose_name_plural = 'Поля шаблона'
        ordering = ['order']

    def __str__(self):
        return f'{self.label} ({self.key})'


class GeneratedDocument(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Создан / Ожидает'),
        ('generated', 'Сгенерирован'),
        ('approved', 'Одобрен администратором'),
        ('error', 'Ошибка генерации'),
    )

    template = models.ForeignKey(
        DocumentTemplate,
        on_delete=models.CASCADE,
        related_name='documents',
        verbose_name='Шаблон',
    )
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='my_documents',
        verbose_name='Менеджер',
    )
    deal = models.ForeignKey(
        'analytics.Deal',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='generated_documents',
        verbose_name='Сделка',
    )
    title = models.CharField('Название документа', max_length=255, blank=True)
    context_data = models.JSONField('Введённые данные', default=dict, blank=True)
    status = models.CharField(
        'Статус',
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
    )
    generated_file = models.FileField(
        'Готовый документ',
        upload_to='generated_docs/',
        null=True,
        blank=True,
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_documents',
        verbose_name='Одобрено администратором',
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.title:
            return self.title
        if self.deal_id:
            return f'Документ по сделке #{self.deal_id}'
        return f'Документ #{self.id} ({self.template.title})'

    class Meta:
        verbose_name = 'Сгенерированный документ'
        verbose_name_plural = 'Сгенерированные документы'
        ordering = ['-created_at']

    @property
    def can_download(self) -> bool:
        review = safe_get_document_review(self)
        if review:
            return review.status == 'approved' and bool(review.approved_file)
        return self.status == 'approved' and bool(self.generated_file)

    def _parse_context_data(self):
        context = self.context_data or {}
        if isinstance(context, str):
            try:
                context = json.loads(context)
            except json.JSONDecodeError:
                context = {}
        if not isinstance(context, dict):
            context = {}
        return context

    def build_context(self):
        base_context = {}

        if self.deal_id and self.deal:
            client = self.deal.client
            base_context.update({
                'deal_id': self.deal.id,
                'deal_type': self.deal.get_deal_type_display(),
                'deal_total_to_pay_usd': str(self.deal.total_to_pay_usd or ''),
                'deal_paid_amount_usd': str(self.deal.paid_amount_usd or ''),
                'deal_payment_status': self.deal.get_payment_status_display(),
                'client_full_name': client.full_name or '',
                'client_phone': client.phone or '',
                'client_email': client.email or '',
                'client_city': client.city or '',
                'client_citizenship': client.citizenship or '',
                'client_passport_local_num': client.passport_local_num or '',
                'client_passport_inter_num': client.passport_inter_num or '',
                'client_passport_issued_by': client.passport_issued_by or '',
                'client_address_registration': client.address_registration or '',
                'manager_full_name': (
                    f'{self.manager.first_name} {self.manager.last_name}'.strip()
                    or self.manager.email
                ),
                'manager_email': self.manager.email or '',
                'university_name': self.deal.university.name if self.deal.university else '',
                'program_name': self.deal.program.name if self.deal.program else '',
                'service_title': self.deal.service_ref.title if self.deal.service_ref else self.deal.custom_service_name,
            })

        extra_context = self._parse_context_data()
        base_context.update(extra_context)
        return base_context

    def generate_document(self):
        if not self.template.file:
            return False, 'В шаблоне отсутствует файл DOCX.'

        try:
            self.template.file.open('rb')
            template_bytes = self.template.file.read()
            self.template.file.close()

            template_stream = io.BytesIO(template_bytes)
            doc = DocxTemplate(template_stream)

            context = self.build_context()
            doc.render(context)

            buffer = io.BytesIO()
            doc.save(buffer)
            buffer.seek(0)

            safe_title = ''.join(
                c for c in str(self.title or self.template.title)
                if c.isalpha() or c.isdigit() or c in ' -_'
            ).rstrip()

            filename = f'{safe_title or "document"}_{self.id}.docx'.replace(' ', '_')

            self.generated_file.save(filename, ContentFile(buffer.read()), save=False)
            self.status = 'generated'
            self.approved_by = None
            self.approved_at = None
            self.save(update_fields=[
                'generated_file',
                'status',
                'approved_by',
                'approved_at',
                'updated_at',
            ])

            return True, 'Документ успешно сгенерирован.'

        except Exception as e:
            msg = f'Ошибка DocxTemplate: {e}'
            logger.error(msg, exc_info=True)
            self.status = 'error'
            if self.pk:
                self.save(update_fields=['status', 'updated_at'])
            return False, msg


class DocumentReview(models.Model):
    STATUS_CHOICES = (
        ('pending', 'На рассмотрении'),
        ('approved', 'Одобрен'),
        ('rejected', 'Отклонён'),
    )

    document = models.OneToOneField(
        'documents.GeneratedDocument',
        on_delete=models.CASCADE,
        related_name='review',
        verbose_name='Документ',
    )
    status = models.CharField(
        'Статус рассмотрения',
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True,
    )
    rejection_reason = models.TextField('Причина отклонения', blank=True)
    approved_file = models.FileField(
        'Одобренный файл',
        upload_to='generated_documents/approved/',
        blank=True,
        null=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='document_reviews',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Рассмотрение документа'
        verbose_name_plural = 'Рассмотрения документов'

    def __str__(self):
        return f'Review {self.document_id}: {self.status}'

    def mark_approved(self, user, approved_file=None):
        self.status = 'approved'
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.rejection_reason = ''
        if approved_file is not None:
            self.approved_file = approved_file
        self.save()

    def mark_rejected(self, user, reason=''):
        self.status = 'rejected'
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.rejection_reason = reason or ''
        self.save()


def resolve_document_status(document):
    review = safe_get_document_review(document)
    if review:
        if review.status == 'approved':
            return 'approved'
        if review.status == 'rejected':
            return 'rejected'

    return getattr(document, 'status', 'draft') or 'draft'