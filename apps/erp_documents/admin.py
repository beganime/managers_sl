from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import (
    DocumentApproval,
    DocumentDownloadLog,
    DocumentTemplate,
    DocumentTemplateField,
    GeneratedDocument,
    StampRule,
)


class DocumentTemplateFieldInline(TabularInline):
    model = DocumentTemplateField
    extra = 0
    fields = ('label', 'key', 'jinja_key', 'data_source', 'field_type', 'default_value', 'is_required', 'sort_order')


@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(ModelAdmin):
    list_display = ('name', 'document_type', 'code', 'company', 'requires_approval', 'allow_without_stamp', 'allow_with_stamp', 'is_active', 'updated_at')
    list_filter = ('is_active', 'requires_approval', 'allow_without_stamp', 'allow_with_stamp', 'company', 'document_type')
    search_fields = ('name', 'code', 'document_type', 'description', 'company__name')
    autocomplete_fields = ('company', 'created_by')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [DocumentTemplateFieldInline]
    fieldsets = (
        ('Main', {'fields': ('company', 'name', 'code', 'document_type', 'description', 'file', 'is_active')}),
        ('Generation rules', {'fields': ('requires_approval', 'allow_without_stamp', 'allow_with_stamp', 'jinja_variables')}),
        ('Stamp and watermark', {'fields': ('stamp_settings', 'watermark_settings')}),
        ('Audit', {'fields': ('created_by', 'created_at', 'updated_at')}),
    )


@admin.register(DocumentTemplateField)
class DocumentTemplateFieldAdmin(ModelAdmin):
    list_display = ('label', 'key', 'jinja_key', 'data_source', 'template', 'field_type', 'is_required', 'sort_order')
    list_filter = ('field_type', 'data_source', 'is_required', 'template')
    search_fields = ('label', 'key', 'jinja_key', 'template__name')
    autocomplete_fields = ('template',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(GeneratedDocument)
class GeneratedDocumentAdmin(ModelAdmin):
    list_display = ('title', 'template', 'client', 'manager', 'company', 'office', 'status', 'created_at')
    list_filter = ('status', 'company', 'office', 'template', 'created_at')
    search_fields = ('title', 'template__name', 'client__full_name', 'client__phone', 'deal__title')
    autocomplete_fields = ('company', 'office', 'template', 'client', 'application', 'deal', 'manager', 'approved_by')
    readonly_fields = ('generated_at', 'submitted_at', 'approved_at', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'

    @admin.action(description='Submit selected documents for approval')
    def submit_for_approval(self, request, queryset):
        for document in queryset.select_related('template', 'client', 'application', 'deal', 'company', 'office', 'manager'):
            document.submit_for_approval(user=request.user)

    @admin.action(description='Approve selected documents without stamp')
    def approve_without_stamp(self, request, queryset):
        for document in queryset.select_related('template', 'company', 'office'):
            document.approve(user=request.user, with_stamp=False)

    @admin.action(description='Approve selected documents with stamp')
    def approve_with_stamp(self, request, queryset):
        for document in queryset.select_related('template', 'company', 'office'):
            document.approve(user=request.user, with_stamp=True)

    actions = ('submit_for_approval', 'approve_without_stamp', 'approve_with_stamp')


@admin.register(DocumentApproval)
class DocumentApprovalAdmin(ModelAdmin):
    list_display = ('document', 'status', 'approval_type', 'reviewed_by', 'reviewed_at', 'created_at')
    list_filter = ('status', 'approval_type', 'reviewed_at', 'created_at')
    search_fields = ('document__title', 'document__client__full_name', 'comment', 'rejection_reason')
    autocomplete_fields = ('document', 'reviewed_by')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(StampRule)
class StampRuleAdmin(ModelAdmin):
    list_display = ('name', 'company', 'office', 'template', 'position', 'width_mm', 'height_mm', 'sort_order', 'is_active')
    list_filter = ('is_active', 'position', 'watermark_enabled', 'company', 'office', 'template')
    search_fields = ('name', 'company__name', 'office__name', 'template__name')
    autocomplete_fields = ('company', 'office', 'template')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Scope', {'fields': ('company', 'office', 'template', 'name', 'is_active', 'sort_order')}),
        ('Stamp', {'fields': ('stamp_image', 'position', 'width_mm', 'height_mm', 'x_mm', 'y_mm', 'opacity')}),
        ('Watermark', {'fields': ('watermark_enabled', 'watermark_text', 'watermark_image', 'watermark_position', 'watermark_opacity')}),
        ('Audit', {'fields': ('created_at', 'updated_at')}),
    )


@admin.register(DocumentDownloadLog)
class DocumentDownloadLogAdmin(ModelAdmin):
    list_display = ('document', 'user', 'file_type', 'ip_address', 'created_at')
    list_filter = ('file_type', 'created_at')
    search_fields = ('document__title', 'document__client__full_name', 'user__email', 'ip_address')
    autocomplete_fields = ('document', 'user')
    readonly_fields = ('document', 'user', 'file_type', 'ip_address', 'user_agent', 'created_at')
