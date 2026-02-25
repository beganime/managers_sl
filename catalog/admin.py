# catalog/admin.py
from django.contrib import admin
from django.db import models
from django.db.models import Count
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display
from unfold.contrib.forms.widgets import WysiwygWidget
from unfold.contrib.import_export.forms import ExportForm, ImportForm

from import_export.admin import ImportExportModelAdmin
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget, BooleanWidget

from .models import Currency, University, Program

class UniversityResource(resources.ModelResource):
    class Meta:
        model = University
        import_id_fields = ('name',)
        fields = ('name', 'country', 'city', 'local_currency__code')

class ProgramResource(resources.ModelResource):
    university = fields.Field(column_name='university', attribute='university', widget=ForeignKeyWidget(University, field='name'))
    is_active = fields.Field(column_name='is_active', attribute='is_active', widget=BooleanWidget())

    class Meta:
        model = Program
        fields = ('id', 'university', 'name', 'degree', 'tuition_fee', 'service_fee', 'duration', 'is_active')

class ProgramInline(TabularInline):
    model = Program
    extra = 0
    tab = True 
    fields = ('name', 'degree', 'duration', 'tuition_fee', 'service_fee', 'is_active')

@admin.register(Currency)
class CurrencyAdmin(ModelAdmin):
    list_display = ("code", "symbol", "rate", "updated_preview")
    search_fields = ("code", "name")
    
    @display(description="Обновлено", label=True)
    def updated_preview(self, obj):
        return f"1 USD = {obj.rate} {obj.code}", "info"

@admin.register(University)
class UniversityAdmin(ModelAdmin, ImportExportModelAdmin):
    resource_class = UniversityResource
    import_form_class = ImportForm
    export_form_class = ExportForm
    
    inlines = [ProgramInline]
    list_display = ("name", "country", "city", "display_currency", "display_logo", "program_count")
    list_filter = ("country", "local_currency")
    search_fields = ("name", "country", "city")
    list_per_page = 20
    list_select_related = ("local_currency", "added_by")

    fieldsets = (
        (_("Основная информация"), {
            "fields": (("name", "logo"), ("country", "city"), "local_currency", "added_by"),
            "classes": ("tab-tabular",),
        }),
        (_("Описание"), {
            "fields": ("description", "expenses_info", "invitation_info"),
            "classes": ("collapse",),
        }),
        (_("Контакты"), {"fields": ("contacts",)}),
    )
    formfield_overrides = {models.TextField: {"widget": WysiwygWidget}}

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.annotate(programs_count=Count('programs'))
        return qs

    def save_model(self, request, obj, form, change):
        if not obj.added_by:
            obj.added_by = request.user
        super().save_model(request, obj, form, change)

    @display(description="Лого")
    def display_logo(self, obj):
        if obj.logo:
            return format_html('<img src="{}" style="width: 40px; border-radius: 5px;" />', obj.logo.url)
        return "-"

    @display(description="Валюта", label=True, ordering="local_currency__code")
    def display_currency(self, obj):
        return (obj.local_currency.code, "warning") if obj.local_currency else ("USD", "success")

    @display(description="Программ", ordering="programs_count")
    def program_count(self, obj):
        return obj.programs_count

@admin.register(Program)
class ProgramAdmin(ModelAdmin, ImportExportModelAdmin):
    resource_class = ProgramResource
    import_form_class = ImportForm
    export_form_class = ExportForm

    list_display = ("name", "university", "display_degree", "display_tuition", "display_service_fee", "is_active")
    list_filter = ("degree", "university__country", "is_active", "is_deleted")
    search_fields = ("name", "university__name")
    list_editable = ("is_active",)
    autocomplete_fields = ("university",)
    list_select_related = ("university", "university__local_currency")

    # НОВОЕ: Перехватываем параметр university_id из JS-запроса автокомплита Сделки!
    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        uni_id = request.GET.get('university_id')
        if uni_id:
            queryset = queryset.filter(university_id=uni_id)
        return queryset, use_distinct

    @display(description="Степень", label=True, ordering="degree")
    def display_degree(self, obj):
        colors = {
            'bachelor': 'info', 
            'master': 'purple', 
            'specialist': 'warning', 
            'language': 'success'
        }
        return obj.get_degree_display(), colors.get(obj.degree, 'default')

    @display(description="Обучение", ordering="tuition_fee")
    def display_tuition(self, obj):
        cur = obj.university.local_currency.symbol if obj.university.local_currency else ""
        return f"{obj.tuition_fee:,.0f} {cur}"

    @display(description="Доход (USD)", label=True, ordering="service_fee")
    def display_service_fee(self, obj):
        return f"${obj.service_fee:,.2f}", "success"