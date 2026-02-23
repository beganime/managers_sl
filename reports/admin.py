# reports/admin.py
from django.contrib import admin
from django.db import models
from unfold.admin import ModelAdmin
from unfold.contrib.forms.widgets import WysiwygWidget
from .models import DailyReport

@admin.register(DailyReport)
class DailyReportAdmin(ModelAdmin):
    list_display = ("employee", "date", "leads_processed", "deals_closed", "created_at")
    list_filter = ("date", "employee")
    search_fields = ("employee__first_name", "employee__last_name", "content")
    
    formfield_overrides = {
        models.TextField: {"widget": WysiwygWidget},
    }

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(employee=request.user)

    def get_exclude(self, request, obj=None):
        if not request.user.is_superuser:
            return ('employee',)
        return ()

    def save_model(self, request, obj, form, change):
        if not obj.pk and not request.user.is_superuser:
            obj.employee = request.user
        super().save_model(request, obj, form, change)