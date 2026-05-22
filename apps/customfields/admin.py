from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import CustomField, CustomFieldOption, CustomFieldValue


class CustomFieldOptionInline(TabularInline):
    model = CustomFieldOption
    extra = 0
    fields = ('label', 'value', 'color', 'is_active', 'sort_order')


@admin.register(CustomField)
class CustomFieldAdmin(ModelAdmin):
    list_display = ('name', 'code', 'target_label', 'company', 'office', 'field_type', 'is_required', 'is_active', 'sort_order')
    list_filter = ('field_type', 'is_active', 'is_required', 'is_filterable', 'is_public', 'company', 'office', 'content_type')
    search_fields = ('name', 'code', 'description', 'entity_key', 'company__name')
    autocomplete_fields = ('company', 'office', 'created_by')
    raw_id_fields = ('content_type',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [CustomFieldOptionInline]


@admin.register(CustomFieldOption)
class CustomFieldOptionAdmin(ModelAdmin):
    list_display = ('label', 'value', 'field', 'color', 'is_active', 'sort_order')
    list_filter = ('is_active', 'field__field_type')
    search_fields = ('label', 'value', 'field__name', 'field__code')
    autocomplete_fields = ('field',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(CustomFieldValue)
class CustomFieldValueAdmin(ModelAdmin):
    list_display = ('field', 'content_type', 'object_id', 'company', 'office', 'set_by', 'updated_at')
    list_filter = ('company', 'office', 'content_type', 'field__field_type', 'updated_at')
    search_fields = ('field__name', 'field__code', 'value_search', 'set_by__email')
    autocomplete_fields = ('field', 'company', 'office', 'set_by')
    raw_id_fields = ('content_type',)
    readonly_fields = ('value_search', 'created_at', 'updated_at')
