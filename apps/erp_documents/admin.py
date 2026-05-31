from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.utils.html import format_html, format_html_join
from unfold.admin import ModelAdmin, TabularInline

from .models import (
    DocumentApproval,
    DocumentDownloadLog,
    DocumentTemplate,
    DocumentTemplateField,
    GeneratedDocument,
    StampRule,
)


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


class StampRuleInline(TabularInline):
    model = StampRule
    extra = 0
    show_change_link = True
    readonly_fields = ('stamp_preview',)
    fields = (
        'name',
        'stamp_image',
        'stamp_preview',
        'width_mm',
        'height_mm',
        'position',
        'x_mm',
        'y_mm',
        'opacity',
        'watermark_enabled',
        'watermark_text',
        'watermark_image',
        'watermark_position',
        'watermark_width_mm',
        'watermark_height_mm',
        'watermark_opacity',
        'is_active',
        'sort_order',
    )

    @admin.display(description='Предпросмотр')
    def stamp_preview(self, obj):
        if obj and obj.stamp_image:
            return format_html(
                '<img src="{}" style="max-width:120px; max-height:90px; border:1px solid #e5e7eb; border-radius:8px; padding:6px; background:#fff;" />',
                obj.stamp_image.url,
            )
        return 'Печать не загружена'


@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(ModelAdmin):
    form = DocumentTemplateAdminForm

    list_display = (
        'name',
        'document_type',
        'code',
        'company',
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
        # На странице добавления inline-формы часто ломают Unfold/Django admin,
        # потому что parent object ещё не сохранён. Поэтому сначала создаём шаблон,
        # а поля шаблона и печать добавляем уже на странице редактирования.
        if obj is None:
            return []
        return [DocumentTemplateFieldInline, StampRuleInline]

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        return (
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
                        'description': 'Сначала сохраните сам шаблон. Поля шаблона и печать добавляются после первого сохранения.',
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
                    'description': 'Загрузите DOCX-файл. Внутри шаблона используйте Jinja-переменные вида {{ client.full_name }}.',
                },
            ),
            (
                'Подсказки',
                {
                    'fields': (
                        'jinja_examples',
                        'stamp_help',
                        'download_formats',
                    ),
                    'description': 'Поля шаблона и правила печати находятся ниже на этой странице.',
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
                    'description': 'Без печати скачивается DOCX. С электронной печатью скачивается PDF после подтверждения администратора.',
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
        return format_html(
            '<div style="line-height:1.5">'
            '<b>Печать:</b> добавляйте после первого сохранения шаблона через блок Stamp rules ниже или через отдельный раздел Stamp rules.<br>'
            '<b>Важно:</b> если печать не нужна, не создавайте Stamp rule.<br>'
            '<b>Водяной знак:</b> настраивается в том же Stamp rule.'
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
        'approved_by',
    )
    readonly_fields = (
        'generated_at',
        'submitted_at',
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
                    'approved_file',
                )
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

    @admin.action(description='Submit selected documents for approval')
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

    @admin.action(description='Approve selected documents without stamp')
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

    @admin.action(description='Approve selected documents with stamp')
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
