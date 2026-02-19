from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, StackedInline
from unfold.decorators import display
from unfold.contrib.import_export.forms import ExportForm, ImportForm # Для Unfold
from import_export.admin import ImportExportModelAdmin # Базовый класс
from import_export import resources # Ресурсы

from .forms import UserCreationForm, UserChangeForm
from .models import User, Office, ManagerSalary

# --- РЕСУРСЫ (Настройка экспорта) ---
class UserResource(resources.ModelResource):
    class Meta:
        model = User
        fields = ('id', 'email', 'first_name', 'last_name', 'office__city', 'work_status', 'date_joined')
        export_order = ('id', 'email', 'first_name', 'last_name', 'office__city')

# --- INLINES ---
class ManagerSalaryInline(StackedInline):
    model = ManagerSalary
    can_delete = False
    verbose_name_plural = "Финансовый профиль"
    fk_name = "manager"
    fieldsets = (
        (None, {
            "fields": (("current_balance", "monthly_plan", "current_month_revenue","commission_percent"),),
            "classes": ("tab-tabular",),
        }),
    )

@admin.register(Office)
class OfficeAdmin(ModelAdmin):
    list_display = ("city", "address", "phone")
    search_fields = ("city", "address")

# Обрати внимание: наследуемся от BaseUserAdmin и ImportExportModelAdmin
@admin.register(User)
class UserAdmin(BaseUserAdmin, ImportExportModelAdmin, ModelAdmin):
    resource_class = UserResource # Подключаем ресурс экспорта
    import_form_class = ImportForm
    export_form_class = ExportForm

    form = UserChangeForm
    add_form = UserCreationForm 
    inlines = [ManagerSalaryInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(id=request.user.id)

    # Запрещаем менеджеру менять свои права (superuser, staff) или зарплатный план
    def get_readonly_fields(self, request, obj=None):
        if not request.user.is_superuser:
            # Менеджер не может менять себе права, статус работы и финансовый план
            return ("is_superuser", "is_staff", "groups", "user_permissions", "last_login", "date_joined", "work_status", "is_effective")
        return ()

    list_display = (
        "display_header", 
        "email", 
        "office", 
        "display_status", 
        "display_efficiency", 
        "display_balance", 
        "is_staff"
    )
    list_filter = ("office", "work_status", "is_effective", "groups")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("email",)

    # Убираем username из fieldsets, так как его нет
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Персональные данные"), {
            "fields": (("first_name", "last_name", "middle_name"), "avatar", "dob", "office")
        }),
        (_("Рабочий статус"), {
            "fields": (("work_status", "is_effective"), "job_description", "groups", "user_permissions"),
            "classes": ("collapse",),
        }),
        (_("Важные даты"), {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "password", "confirm_password", "first_name", "last_name", "office"),
        }),
    )

    @display(description="Сотрудник", header=True)
    def display_header(self, instance: User):
        return [
            f"{instance.first_name} {instance.last_name}",
            instance.email,
            instance.avatar if instance.avatar else None
        ]

    @display(description="Статус", label=True)
    def display_status(self, instance: User):
        colors = {
            "working": "success", 
            "vacation": "warning",
            "sick": "danger",
        }
        return instance.get_work_status_display(), colors.get(instance.work_status, "info")

    @display(description="Эффективность", boolean=True)
    def display_efficiency(self, instance: User):
        return instance.is_effective

    @display(description="Баланс (USD)")
    def display_balance(self, instance: User):
        if hasattr(instance, 'managersalary'):
            return f"${instance.managersalary.current_balance}"
        return "Нет счета"