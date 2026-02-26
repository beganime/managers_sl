# leads/admin.py
from django.contrib import admin
from django.contrib import messages
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.decorators import display, action
from .models import Lead
from clients.models import Client

@admin.register(Lead)
class LeadAdmin(ModelAdmin):
    list_display = ("full_name", "phone", "display_direction", "manager", "status", "status_badge", "created_at_fmt")
    list_filter = ("status", "direction", "manager", "created_at")
    search_fields = ("full_name", "phone", "email", "student_name", "parent_name")
    
    actions = ["take_lead", "convert_to_client"]

    # Группируем поля, чтобы менеджеру было удобно читать заявку
    fieldsets = (
        ("Основная информация (Контактное лицо)", {
            "fields": (("full_name", "phone"), ("email", "age"), ("country", "direction"), "relation", "education"),
            "classes": ("tab-tabular",),
        }),
        ("Детали Студента / Родителя", {
            "fields": (("student_name", "parent_name"), ("current_education", "current_university"), "current_country"),
            "classes": ("tab-tabular", "!bg-gray-50"),
        }),
        ("Поездка и Паспорта", {
            "fields": (("has_passport", "passport_expiry"), ("travel_month", "travel_date"), ("departure_city", "arrival_city"), "luggage"),
            "classes": ("tab-tabular",),
        }),
        ("Статус и Управление", {
            "fields": ("manager", "status"),
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(Q(manager__isnull=True) | Q(manager=request.user))

    @action(description="🙋‍♂️ Забрать заявку в работу")
    def take_lead(self, request, queryset):
        unassigned_leads = queryset.filter(manager__isnull=True)
        count = unassigned_leads.count()
        if count == 0:
            self.message_user(request, "Заявка уже в работе у другого менеджера!", messages.WARNING)
            return
        unassigned_leads.update(manager=request.user, status='contacted')
        self.message_user(request, f"Успешно взято в работу заявок: {count}", messages.SUCCESS)

    @action(description="✅ Сделать Клиентом")
    def convert_to_client(self, request, queryset):
        count = 0
        for lead in queryset:
            if lead.status != 'converted':
                # ФОРМИРУЕМ ПОДРОБНЫЙ КОММЕНТАРИЙ СО ВСЕМИ НОВЫМИ ПОЛЯМИ
                lead_details = (
                    f"--- ДАННЫЕ С САЙТА ---\n"
                    f"Направление: {lead.get_direction_display() or '-'}\n"
                    f"Родство: {lead.relation or 'Сам'}\n"
                    f"ФИО студента: {lead.student_name or '-'}\n"
                    f"ФИО родителя: {lead.parent_name or '-'}\n"
                    f"Возраст: {lead.age or '-'}\n"
                    f"Наличие паспорта: {lead.has_passport or '-'}\n"
                    f"Срок действия паспорта: {lead.passport_expiry or '-'}\n"
                    f"Месяц поездки: {lead.travel_month or '-'}\n"
                    f"Дата поездки: {lead.travel_date or '-'}\n"
                    f"Город вылета: {lead.departure_city or '-'}\n"
                    f"Город прибытия: {lead.arrival_city or '-'}\n"
                    f"Багаж: {lead.luggage or '-'}\n"
                    f"Текущее образование: {lead.current_education or '-'}\n"
                    f"Текущий университет: {lead.current_university or '-'}\n"
                    f"Текущая страна: {lead.current_country or '-'}\n"
                )
                
                Client.objects.create(
                    full_name=lead.full_name,
                    phone=lead.phone,
                    email=lead.email,
                    city=lead.country, 
                    comments=lead_details,
                    manager=request.user
                )
                lead.status = 'converted'
                lead.save()
                count += 1
        self.message_user(request, f"Создано новых клиентов: {count}", messages.SUCCESS)

    @display(description="Направление")
    def display_direction(self, obj):
        return obj.get_direction_display() if obj.direction else "—"

    @display(description="Маркер", label=True)
    def status_badge(self, obj):
        colors = {'new': 'danger', 'contacted': 'warning', 'converted': 'success', 'rejected': 'default'}
        return obj.get_status_display(), colors.get(obj.status, 'info')

    @display(description="Дата")
    def created_at_fmt(self, obj):
        return obj.created_at.strftime("%d.%m %H:%M")