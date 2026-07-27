from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import SystemSetting


@admin.register(SystemSetting)
class SystemSettingAdmin(ModelAdmin):
    list_display = ('key', 'short_value', 'description', 'updated_at')
    search_fields = ('key', 'value', 'description')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Основное', {'fields': ('key', 'value', 'description')}),
        ('Служебное', {'fields': ('created_at', 'updated_at')}),
    )

    @admin.display(description='Значение')
    def short_value(self, obj):
        value = obj.value or ''
        return value if len(value) <= 80 else f'{value[:77]}...'
