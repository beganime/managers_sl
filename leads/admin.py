from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display
from .models import Lead

@admin.register(Lead)
class LeadAdmin(ModelAdmin):
    # ДОБАВЛЕН "status" перед "status_badge"
    list_display = ("full_name", "phone", "direction", "status", "status_badge", "created_at_fmt")
    list_filter = ("status", "created_at", "country")
    search_fields = ("full_name", "phone", "email")
    list_editable = ("status",) # Теперь ошибка исчезнет!

    @display(description="Маркер", label=True)
    def status_badge(self, obj):
        colors = {
            'new': 'danger',       
            'contacted': 'warning',
            'converted': 'success',
            'rejected': 'default', 
        }
        return obj.get_status_display(), colors.get(obj.status, 'info')

    @display(description="Дата")
    def created_at_fmt(self, obj):
        return obj.created_at.strftime("%d.%m.%Y %H:%M")