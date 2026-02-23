# leads/admin.py
from django.contrib import admin
from django.contrib import messages
from django.db.models import Q
from unfold.admin import ModelAdmin
from unfold.decorators import display, action
from .models import Lead
from clients.models import Client # <-- Импортируем модель Клиента

@admin.register(Lead)
class LeadAdmin(ModelAdmin):
    list_display = ("full_name", "phone", "display_direction", "manager", "status", "status_badge", "created_at_fmt")
    list_filter = ("status", "direction", "manager", "created_at")
    search_fields = ("full_name", "phone", "email")
    
    # Две кнопки-действия для менеджера
    actions = ["take_lead", "convert_to_client"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        # Менеджер видит НОВЫЕ (свободные) ИЛИ СВОИ (которые он забрал)
        return qs.filter(Q(manager__isnull=True) | Q(manager=request.user))

    @action(description="🙋‍♂️ Забрать заявку в работу")
    def take_lead(self, request, queryset):
        unassigned_leads = queryset.filter(manager__isnull=True)
        count = unassigned_leads.count()
        if count == 0:
            self.message_user(request, "Заявка уже в работе у другого менеджера!", messages.WARNING)
            return
        # Закрепляем за собой
        unassigned_leads.update(manager=request.user, status='contacted')
        self.message_user(request, f"Успешно взято в работу заявок: {count}", messages.SUCCESS)

    @action(description="✅ Сделать Клиентом")
    def convert_to_client(self, request, queryset):
        count = 0
        for lead in queryset:
            if lead.status != 'converted':
                # Автоматически создаем клиента
                Client.objects.create(
                    full_name=lead.full_name,
                    phone=lead.phone,
                    email=lead.email,
                    city=lead.country, # Если города нет, пишем страну
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