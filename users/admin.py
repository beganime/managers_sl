# users/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from unfold.admin import ModelAdmin, StackedInline
from unfold.decorators import display, action
from unfold.contrib.import_export.forms import ExportForm, ImportForm
from import_export.admin import ImportExportModelAdmin
from import_export import resources

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
        ("Баланс и Оклад", {
            "fields": (("current_balance", "fixed_salary", "commission_percent"),),
            "classes": ("tab-tabular",),
        }),
        ("План и Мотивация", {
            "fields": (("monthly_plan", "current_month_revenue"), ("motivation_target", "motivation_reward")),
            "classes": ("tab-tabular", "!bg-gray-50"),
        }),
    )

@admin.register(Office)
class OfficeAdmin(ModelAdmin):
    list_display = ("city", "address", "phone")
    search_fields = ("city", "address")

@admin.register(User)
class UserAdmin(BaseUserAdmin, ImportExportModelAdmin, ModelAdmin):
    resource_class = UserResource
    import_form_class = ImportForm
    export_form_class = ExportForm

    form = UserChangeForm
    add_form = UserCreationForm 
    inlines = [ManagerSalaryInline]
    
    actions = ['pay_salary']
    
    # Делает удобный выбор групп в виде двух панелей со стрелочками
    filter_horizontal = ("groups", "user_permissions")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(id=request.user.id)

    def get_readonly_fields(self, request, obj=None):
        if not request.user.is_superuser:
            return ("is_superuser", "is_staff", "groups", "user_permissions", "last_login", "date_joined", "work_status", "is_effective")
        return ()

    def get_inline_instances(self, request, obj=None):
        if not obj:
            return []
        return super().get_inline_instances(request, obj)

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

    # ПОЛЯ ПРИ РЕДАКТИРОВАНИИ
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Персональные данные"), {
            "fields": (("first_name", "last_name", "middle_name"), "avatar", "dob", "office")
        }),
        (_("Права доступа"), {
            "fields": (("is_active", "is_staff", "is_superuser"), "groups", "user_permissions"),
        }),
        (_("Рабочий статус"), {
            "fields": (("work_status", "is_effective"), "job_description"),
            "classes": ("collapse",),
        }),
        (_("Важные даты"), {"fields": ("last_login", "date_joined")}),
    )

    # ПОЛЯ ПРИ СОЗДАНИИ НОВОГО СОТРУДНИКА
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "password", "confirm_password", "first_name", "last_name", "office"),
        }),
        (_("Права доступа"), {
            "classes": ("wide",),
            "fields": (("is_staff", "is_superuser"), "groups"),
        }),
    )
    
    @action(description="💸 Выплатить зарплату (Обнулить баланс бонусов)")
    def pay_salary(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(request, "Нет прав для этой операции", messages.ERROR)
            return
        
        count = 0
        for user in queryset:
            if hasattr(user, 'managersalary'):
                user.managersalary.reset_balance()
                count += 1
                
        self.message_user(request, f"Успешно. Балансы обнулены для {count} сотрудников.", messages.SUCCESS)

    @display(description="Сотрудник", header=True)
    def display_header(self, instance: User):
        return [
            f"{instance.first_name} {instance.last_name}",
            instance.email,
            instance.avatar if instance.avatar else None
        ]

    @display(description="Статус", label=True)
    def display_status(self, instance: User):
        colors = {"working": "success", "vacation": "warning", "sick": "danger"}
        return instance.get_work_status_display(), colors.get(instance.work_status, "info")

    @display(description="Эффективность", boolean=True)
    def display_efficiency(self, instance: User):
        return instance.is_effective

    @display(description="Доход (Фикс+Бонус)")
    def display_balance(self, instance: User):
        if hasattr(instance, 'managersalary'):
            total = instance.managersalary.current_balance + instance.managersalary.fixed_salary
            return f"${total:,.2f}"
        return "—"