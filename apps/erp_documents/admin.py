import html
import io
import re
import zipfile

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from unfold.admin import ModelAdmin, TabularInline

from .models import (
    DocumentApproval,
    DocumentDownloadLog,
    DocumentTemplate,
    DocumentTemplateField,
    GeneratedDocument,
    StampRule,
)


JINJA_OUTPUT_RE = re.compile(r'{{\s*(.*?)\s*}}', re.DOTALL)
JINJA_VAR_RE = re.compile(r'\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\b')
XML_TAG_RE = re.compile(r'<[^>]+>')

IGNORED_JINJA_TOKENS = {
    'and', 'as', 'block', 'by', 'cycle', 'default', 'dict', 'else', 'elif',
    'endblock', 'endif', 'endfor', 'endset', 'false', 'filter', 'float',
    'for', 'if', 'in', 'int', 'is', 'join', 'length', 'list', 'loop',
    'lower', 'none', 'not', 'or', 'range', 'safe', 'set', 'str', 'string',
    'title', 'true', 'upper', 'with',
}

DATA_SOURCE_BY_ROOT = {
    'client': DocumentTemplateField.SOURCE_CLIENT,
    'application': DocumentTemplateField.SOURCE_APPLICATION,
    'deal': DocumentTemplateField.SOURCE_DEAL,
    'manager': DocumentTemplateField.SOURCE_MANAGER,
    'company': DocumentTemplateField.SOURCE_COMPANY,
    'office': DocumentTemplateField.SOURCE_OFFICE,
}

DATE_HINTS = ('date', 'birthday', 'birth_date', 'deadline', 'issued', 'expiry', 'created_at', 'updated_at')
NUMBER_HINTS = ('amount', 'price', 'fee', 'total', 'count', 'sum', 'cost', 'payment', 'paid')
BOOLEAN_HINTS = ('is_', 'has_', 'can_', 'allow_', 'requires_')


def is_admin_user(user):
    return bool(
        user
        and user.is_authenticated
        and (
            user.is_superuser
            or user.is_staff
            or getattr(user, 'role', None) == 'admin'
        )
    )


def normalize_jinja_variable(token):
    token = str(token or '').strip()
    token = token.strip('()[]{}:,;+-*/%<>=!')
    token = token.split('|', 1)[0].strip()
    token = token.split('(', 1)[0].strip()
    return token[:150]


def is_valid_jinja_variable(token):
    if not token:
        return False
    root = token.split('.', 1)[0].lower()
    if root in IGNORED_JINJA_TOKENS:
        return False
    if token.lower() in IGNORED_JINJA_TOKENS:
        return False
    if token.startswith('_'):
        return False
    return True


def read_docx_template_text(template):
    if not template or not template.file:
        return ''

    try:
        template.file.open('rb')
        raw_bytes = template.file.read()
    finally:
        try:
            template.file.close()
        except Exception:
            pass

    chunks = []
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
        for name in archive.namelist():
            if not name.startswith('word/') or not name.endswith('.xml'):
                continue
            try:
                raw_xml = archive.read(name).decode('utf-8', errors='ignore')
            except Exception:
                continue
            # Word иногда разбивает {{ variable }} XML-тегами.
            # Удаляем XML-теги, чтобы восстановить читаемый текст шаблона.
            text = XML_TAG_RE.sub('', raw_xml)
            chunks.append(html.unescape(text))

    return '\n'.join(chunks)


def extract_jinja_variables_from_docx(template):
    text = read_docx_template_text(template)
    variables = set()

    for expression in JINJA_OUTPUT_RE.findall(text):
        for raw_token in JINJA_VAR_RE.findall(expression):
            token = normalize_jinja_variable(raw_token)
            if is_valid_jinja_variable(token):
                variables.add(token)

    return sorted(variables)


def make_template_field_key(jinja_key):
    value = str(jinja_key or '').strip().lower().replace('.', '_')
    value = re.sub(r'[^a-z0-9_]+', '_', value)
    value = re.sub(r'_+', '_', value).strip('_')
    return (value or 'field')[:90]


def make_template_field_label(jinja_key):
    value = str(jinja_key or '').strip()
    if not value:
        return 'Field'
    last_part = value.split('.')[-1]
    label = last_part.replace('_', ' ').replace('-', ' ').strip().title()
    return label or value


def guess_template_field_type(jinja_key):
    value = str(jinja_key or '').lower()
    if any(hint in value for hint in DATE_HINTS):
        return DocumentTemplateField.FIELD_TYPE_DATE
    if any(hint in value for hint in NUMBER_HINTS):
        return DocumentTemplateField.FIELD_TYPE_NUMBER
    if any(value.startswith(hint) or f'.{hint}' in value for hint in BOOLEAN_HINTS):
        return DocumentTemplateField.FIELD_TYPE_BOOLEAN
    return DocumentTemplateField.FIELD_TYPE_TEXT


def guess_data_source(jinja_key):
    root = str(jinja_key or '').split('.', 1)[0].lower()
    return DATA_SOURCE_BY_ROOT.get(root, DocumentTemplateField.SOURCE_CUSTOM)


def build_unique_field_key(template, base_key):
    key = base_key[:100]
    if not DocumentTemplateField.objects.filter(template=template, key=key).exists():
        return key

    for index in range(2, 1000):
        suffix = f'_{index}'
        candidate = f'{base_key[:100 - len(suffix)]}{suffix}'
        if not DocumentTemplateField.objects.filter(template=template, key=candidate).exists():
            return candidate

    return f'{base_key[:80]}_{template.fields.count() + 1}'[:100]


def sync_template_fields_from_docx(template):
    variables = extract_jinja_variables_from_docx(template)
    created = 0
    skipped = 0

    if not template.pk:
        return {'variables': variables, 'created': created, 'skipped': skipped}

    existing_jinja_keys = set(
        template.fields.exclude(jinja_key='').values_list('jinja_key', flat=True)
    )
    existing_keys = set(template.fields.values_list('key', flat=True))
    current_count = template.fields.count()

    for index, jinja_key in enumerate(variables, start=1):
        if jinja_key in existing_jinja_keys:
            skipped += 1
            continue

        base_key = make_template_field_key(jinja_key)
        key = base_key
        if key in existing_keys:
            key = build_unique_field_key(template, base_key)

        DocumentTemplateField.objects.create(
            template=template,
            key=key,
            jinja_key=jinja_key,
            data_source=guess_data_source(jinja_key),
            label=make_template_field_label(jinja_key),
            field_type=guess_template_field_type(jinja_key),
            is_required=True,
            help_text='',
            sort_order=(current_count + index) * 10,
        )
        existing_keys.add(key)
        existing_jinja_keys.add(jinja_key)
        created += 1

    DocumentTemplate.objects.filter(pk=template.pk).update(jinja_variables=variables)

    return {'variables': variables, 'created': created, 'skipped': skipped}


class DocumentTemplateAdminForm(forms.ModelForm):
    class Meta:
        model = DocumentTemplate
        fields = '__all__'

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            filename = getattr(file, 'name', '') or ''
            if filename and not filename.lower().endswith('.docx'):
                raise ValidationError('Загрузите файл именно в формате .docx')
        return file

    def clean_jinja_variables(self):
        value = self.cleaned_data.get('jinja_variables')
        if value in (None, ''):
            return []
        if not isinstance(value, list):
            raise ValidationError('Jinja variables должен быть списком JSON, например: []')
        return value

    def clean_stamp_settings(self):
        value = self.cleaned_data.get('stamp_settings')
        if value in (None, ''):
            return {}
        if not isinstance(value, dict):
            raise ValidationError('Stamp settings должен быть JSON-объектом, например: {}')
        return value

    def clean_watermark_settings(self):
        value = self.cleaned_data.get('watermark_settings')
        if value in (None, ''):
            return {}
        if not isinstance(value, dict):
            raise ValidationError('Watermark settings должен быть JSON-объектом, например: {}')
        return value


class DocumentTemplateFieldInline(TabularInline):
    model = DocumentTemplateField
    extra = 0
    show_change_link = True
    fields = (
        'label',
        'key',
        'jinja_key',
        'data_source',
        'field_type',
        'default_value',
        'options',
        'help_text',
        'is_required',
        'sort_order',
    )


@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(ModelAdmin):
    form = DocumentTemplateAdminForm

    list_display = (
        'name',
        'document_type',
        'code',
        'company',
        'fields_count',
        'requires_approval',
        'allow_without_stamp',
        'allow_with_stamp',
        'is_active',
        'updated_at',
    )
    list_filter = (
        'is_active',
        'requires_approval',
        'allow_without_stamp',
        'allow_with_stamp',
        'company',
        'document_type',
    )
    search_fields = (
        'name',
        'code',
        'document_type',
        'description',
        'company__name',
    )
    autocomplete_fields = (
        'company',
    )

    def get_inlines(self, request, obj=None):
        if obj is None:
            return []
        return [DocumentTemplateFieldInline]

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        return (
            'scan_status',
            'jinja_examples',
            'download_formats',
            'stamp_help',
            'created_by',
            'created_at',
            'updated_at',
        )

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return (
                (
                    'Основное',
                    {
                        'fields': (
                            'company',
                            'name',
                            'code',
                            'document_type',
                            'description',
                            'is_active',
                        ),
                        'description': 'Сначала сохраните сам шаблон. После сохранения система автоматически просканирует DOCX и создаст поля по Jinja-переменным.',
                    },
                ),
                (
                    'Файл шаблона',
                    {
                        'fields': (
                            'file',
                        ),
                        'description': 'Загрузите DOCX-файл. Внутри шаблона используйте Jinja-переменные вида {{ client.full_name }}.',
                    },
                ),
                (
                    'Скачивание и подтверждение',
                    {
                        'fields': (
                            'allow_without_stamp',
                            'allow_with_stamp',
                            'requires_approval',
                        ),
                    },
                ),
            )

        return (
            (
                'Основное',
                {
                    'fields': (
                        'company',
                        'name',
                        'code',
                        'document_type',
                        'description',
                        'is_active',
                    )
                },
            ),
            (
                'Файл шаблона',
                {
                    'fields': (
                        'file',
                    ),
                    'description': 'Если заменить DOCX и сохранить, система снова просканирует Jinja-переменные и добавит новые поля, которых ещё нет.',
                },
            ),
            (
                'Автосканирование полей',
                {
                    'fields': (
                        'scan_status',
                        'jinja_examples',
                    ),
                    'description': 'Найденные поля показываются внизу страницы в блоке Document template fields. Название, help text, тип и обязательность можно править вручную.',
                },
            ),
            (
                'Скачивание и подтверждение',
                {
                    'fields': (
                        'allow_without_stamp',
                        'allow_with_stamp',
                        'requires_approval',
                        'download_formats',
                    ),
                    'description': 'Без печати скачивается DOCX. С электронной печатью скачивается PDF после подтверждения администратора.',
                },
            ),
            (
                'Электронная печать и водяной знак',
                {
                    'fields': (
                        'stamp_help',
                    ),
                    'description': 'Печать теперь добавляется через отдельный раздел Stamp rules, чтобы форма шаблона не падала из-за inline-файлов.',
                },
            ),
            (
                'Расширенные настройки',
                {
                    'fields': (
                        'jinja_variables',
                        'stamp_settings',
                        'watermark_settings',
                    ),
                    'classes': (
                        'collapse',
                    ),
                    'description': 'Технические JSON-поля оставлены для совместимости и редких расширенных сценариев.',
                },
            ),
            (
                'Аудит',
                {
                    'fields': (
                        'created_by',
                        'created_at',
                        'updated_at',
                    ),
                    'classes': (
                        'collapse',
                    ),
                },
            ),
        )

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

        try:
            result = sync_template_fields_from_docx(obj)
        except Exception as exc:
            self.message_user(
                request,
                f'Шаблон сохранён, но автосканирование DOCX не удалось: {exc}',
                messages.WARNING,
            )
            return

        found_count = len(result.get('variables') or [])
        created_count = result.get('created', 0)
        if found_count:
            self.message_user(
                request,
                f'DOCX просканирован: найдено Jinja-переменных {found_count}, новых полей создано {created_count}.',
                messages.SUCCESS if created_count else messages.INFO,
            )
        else:
            self.message_user(
                request,
                'Шаблон сохранён. Jinja-переменные вида {{ client.full_name }} в DOCX не найдены.',
                messages.WARNING,
            )

    @admin.display(description='Полей')
    def fields_count(self, obj):
        return obj.fields.count()

    @admin.display(description='Статус автосканирования')
    def scan_status(self, obj):
        variables = obj.jinja_variables or []
        if not variables:
            return mark_safe(
                '<div style="line-height:1.5">'
                '<b>Jinja-переменные пока не найдены.</b><br>'
                'Проверьте, что в DOCX есть переменные вида <code>{{ client.full_name }}</code>, затем сохраните шаблон ещё раз.'
                '</div>'
            )

        items = format_html_join(
            '',
            '<li><code>{}</code></li>',
            ((item,) for item in variables),
        )
        return format_html(
            '<div style="line-height:1.5">'
            '<b>Найдено Jinja-переменных: {}</b>'
            '<ul style="margin:8px 0 0 18px;">{}</ul>'
            '</div>',
            len(variables),
            items,
        )

    @admin.display(description='Примеры переменных')
    def jinja_examples(self, obj):
        examples = [
            '{{ client.full_name }}',
            '{{ client.phone }}',
            '{{ client.email }}',
            '{{ client.passport_inter_num }}',
            '{{ client.passport_issued_by }}',
            '{{ client.passport_issued_date }}',
            '{{ client.address_registration }}',
            '{{ application.university_name }}',
            '{{ application.program_name }}',
            '{{ manager.first_name }}',
            '{{ company.name }}',
            '{{ office.city }}',
        ]
        return format_html(
            '<div style="display:grid; gap:4px;">{}</div>',
            format_html_join('', '<code>{}</code>', ((item,) for item in examples)),
        )

    @admin.display(description='Подсказка по печати')
    def stamp_help(self, obj):
        return mark_safe(
            '<div style="line-height:1.5">'
            '<b>Электронная печать:</b> добавляйте через отдельный раздел <b>Правила электронной печати</b>.<br>'
            '<b>Важно:</b> если печать не нужна, правило электронной печати создавать не нужно.<br>'
            '<b>Водяной знак:</b> настраивается в том же правиле электронной печати.'
            '</div>'
        )

    @admin.display(description='Форматы скачивания')
    def download_formats(self, obj):
        return 'Без печати: DOCX. С электронной печатью: PDF после подтверждения администратора.'


@admin.register(DocumentTemplateField)
class DocumentTemplateFieldAdmin(ModelAdmin):
    list_display = (
        'label',
        'key',
        'jinja_key',
        'data_source',
        'template',
        'field_type',
        'is_required',
        'sort_order',
    )
    list_filter = (
        'field_type',
        'data_source',
        'is_required',
        'template',
    )
    search_fields = (
        'label',
        'key',
        'jinja_key',
        'template__name',
    )
    autocomplete_fields = (
        'template',
    )
    readonly_fields = (
        'created_at',
        'updated_at',
    )
    fieldsets = (
        (
            'Основное',
            {
                'fields': (
                    'template',
                    'label',
                    'key',
                    'jinja_key',
                    'data_source',
                    'field_type',
                    'default_value',
                    'options',
                    'is_required',
                    'help_text',
                    'sort_order',
                )
            },
        ),
        (
            'Аудит',
            {
                'fields': (
                    'created_at',
                    'updated_at',
                ),
                'classes': (
                    'collapse',
                ),
            },
        ),
    )


@admin.register(GeneratedDocument)
class GeneratedDocumentAdmin(ModelAdmin):
    list_display = (
        'title',
        'template',
        'client',
        'manager',
        'company',
        'office',
        'status',
        'created_at',
    )
    list_filter = (
        'status',
        'company',
        'office',
        'template',
        'created_at',
    )
    search_fields = (
        'title',
        'template__name',
        'client__full_name',
        'client__phone',
        'deal__title',
    )
    autocomplete_fields = (
        'company',
        'office',
        'template',
        'client',
        'application',
        'deal',
        'manager',
        'stamp_preview_generated_by',
        'approved_by',
    )
    readonly_fields = (
        'generated_at',
        'submitted_at',
        'stamp_preview_generated_at',
        'approved_at',
        'generation_error',
        'created_at',
        'updated_at',
    )
    date_hierarchy = 'created_at'
    fieldsets = (
        (
            'Документ',
            {
                'fields': (
                    'company',
                    'office',
                    'template',
                    'client',
                    'application',
                    'deal',
                    'manager',
                    'title',
                    'status',
                )
            },
        ),
        (
            'Файлы',
            {
                'fields': (
                    'generated_file',
                    'stamp_preview_file',
                    'approved_file',
                )
            },
        ),
        (
            'Предпросмотр печати',
            {
                'fields': (
                    'stamp_preview_options',
                    'stamp_preview_generated_by',
                    'stamp_preview_generated_at',
                ),
                'classes': (
                    'collapse',
                ),
            },
        ),
        (
            'Подтверждение',
            {
                'fields': (
                    'submitted_at',
                    'approved_by',
                    'approved_at',
                )
            },
        ),
        (
            'Контекст и ошибки',
            {
                'fields': (
                    'context_data',
                    'generation_error',
                ),
                'classes': (
                    'collapse',
                ),
            },
        ),
        (
            'Аудит',
            {
                'fields': (
                    'generated_at',
                    'created_at',
                    'updated_at',
                ),
                'classes': (
                    'collapse',
                ),
            },
        ),
    )

    @admin.action(description='Отправить выбранные документы на подтверждение')
    def submit_for_approval(self, request, queryset):
        ok = 0
        for document in queryset.select_related('template', 'client', 'application', 'deal', 'company', 'office', 'manager'):
            try:
                document.submit_for_approval(user=request.user)
                ok += 1
            except Exception as exc:
                self.message_user(request, f'Ошибка #{document.id}: {exc}', messages.ERROR)
        if ok:
            self.message_user(request, f'Отправлено на подтверждение: {ok}.', messages.SUCCESS)

    @admin.action(description='Одобрить выбранные документы без печати')
    def approve_without_stamp(self, request, queryset):
        if not is_admin_user(request.user):
            self.message_user(request, 'Нет прав для этой операции.', messages.ERROR)
            return
        ok = 0
        for document in queryset.select_related('template', 'company', 'office'):
            try:
                document.approve(user=request.user, with_stamp=False)
                ok += 1
            except Exception as exc:
                self.message_user(request, f'Ошибка #{document.id}: {exc}', messages.ERROR)
        if ok:
            self.message_user(request, f'Одобрено без печати: {ok}.', messages.SUCCESS)

    @admin.action(description='Одобрить выбранные документы с электронной печатью')
    def approve_with_stamp(self, request, queryset):
        if not is_admin_user(request.user):
            self.message_user(request, 'Нет прав для этой операции.', messages.ERROR)
            return
        ok = 0
        for document in queryset.select_related('template', 'company', 'office'):
            try:
                document.approve(user=request.user, with_stamp=True)
                ok += 1
            except Exception as exc:
                self.message_user(request, f'Ошибка #{document.id}: {exc}', messages.ERROR)
        if ok:
            self.message_user(request, f'Одобрено с печатью: {ok}.', messages.SUCCESS)

    actions = (
        'submit_for_approval',
        'approve_without_stamp',
        'approve_with_stamp',
    )


@admin.register(DocumentApproval)
class DocumentApprovalAdmin(ModelAdmin):
    list_display = (
        'document',
        'status',
        'approval_type',
        'reviewed_by',
        'reviewed_at',
        'created_at',
    )
    list_filter = (
        'status',
        'approval_type',
        'reviewed_at',
        'created_at',
    )
    search_fields = (
        'document__title',
        'document__client__full_name',
        'comment',
        'rejection_reason',
    )
    autocomplete_fields = (
        'document',
        'reviewed_by',
    )
    readonly_fields = (
        'created_at',
        'updated_at',
    )


@admin.register(StampRule)
class StampRuleAdmin(ModelAdmin):
    list_display = (
        'name',
        'company',
        'office',
        'template',
        'position',
        'width_mm',
        'height_mm',
        'sort_order',
        'is_active',
    )
    list_filter = (
        'is_active',
        'position',
        'watermark_enabled',
        'company',
        'office',
        'template',
    )
    search_fields = (
        'name',
        'company__name',
        'office__name',
        'template__name',
    )
    autocomplete_fields = (
        'company',
        'office',
        'template',
    )
    readonly_fields = (
        'stamp_preview',
        'watermark_preview',
        'created_at',
        'updated_at',
    )
    fieldsets = (
        (
            'Основное',
            {
                'fields': (
                    'company',
                    'office',
                    'template',
                    'name',
                    'is_active',
                    'sort_order',
                )
            },
        ),
        (
            'Электронная печать',
            {
                'fields': (
                    'stamp_image',
                    'stamp_preview',
                    'width_mm',
                    'height_mm',
                    'position',
                    'x_mm',
                    'y_mm',
                    'opacity',
                )
            },
        ),
        (
            'Водяной знак',
            {
                'fields': (
                    'watermark_enabled',
                    'watermark_text',
                    'watermark_image',
                    'watermark_preview',
                    'watermark_position',
                    'watermark_width_mm',
                    'watermark_height_mm',
                    'watermark_opacity',
                )
            },
        ),
        (
            'Аудит',
            {
                'fields': (
                    'created_at',
                    'updated_at',
                ),
                'classes': (
                    'collapse',
                ),
            },
        ),
    )

    @admin.display(description='Preview печати')
    def stamp_preview(self, obj):
        if obj and obj.stamp_image:
            return format_html(
                '<img src="{}" style="max-width:160px; max-height:120px; border:1px solid #e5e7eb; border-radius:8px; padding:6px; background:#fff;" />',
                obj.stamp_image.url,
            )
        return 'Печать не загружена'

    @admin.display(description='Preview водяного знака')
    def watermark_preview(self, obj):
        if obj and obj.watermark_image:
            return format_html(
                '<img src="{}" style="max-width:160px; max-height:120px; border:1px solid #e5e7eb; border-radius:8px; padding:6px; background:#fff;" />',
                obj.watermark_image.url,
            )
        return 'Изображение водяного знака не загружено'


@admin.register(DocumentDownloadLog)
class DocumentDownloadLogAdmin(ModelAdmin):
    list_display = (
        'document',
        'user',
        'file_type',
        'ip_address',
        'created_at',
    )
    list_filter = (
        'file_type',
        'created_at',
    )
    search_fields = (
        'document__title',
        'document__client__full_name',
        'user__email',
        'ip_address',
    )
    autocomplete_fields = (
        'document',
        'user',
    )
    readonly_fields = (
        'document',
        'user',
        'file_type',
        'ip_address',
        'user_agent',
        'created_at',
    )
