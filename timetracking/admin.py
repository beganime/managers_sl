# timetracking/admin.py
from django.contrib import admin
from django.urls import path
from django.shortcuts import redirect
from unfold.admin import ModelAdmin
from unfold.decorators import display, action
from django.utils import timezone
from django.contrib import messages
from .models import WorkShift

@admin.register(WorkShift)
class WorkShiftAdmin(ModelAdmin):
    list_display = ("employee", "date", "time_in_fmt", "time_out_fmt", "hours_worked", "status_badge")
    list_filter = ("date", "is_active", "employee")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser: return qs
        return qs.filter(employee=request.user)

    # === РЕГИСТРИРУЕМ ССЫЛКИ ДЛЯ КНОПОК ===
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('start-shift/', self.admin_site.admin_view(self.start_shift), name='start_shift'),
            path('end-shift/', self.admin_site.admin_view(self.end_shift), name='end_shift'),
        ]
        return custom_urls + urls

    # Логика кнопки "Начать день"
    def start_shift(self, request):
        if request.method == "POST":
            today = timezone.now().date()
            if WorkShift.objects.filter(employee=request.user, date=today, is_active=True).exists():
                messages.warning(request, "Смена уже начата!")
            else:
                WorkShift.objects.create(employee=request.user)
                messages.success(request, "Рабочий день успешно начат! Желаем продуктивной работы.")
        return redirect('/admin/') # Возвращаем на дашборд

    # Логика кнопки "Завершить день"
    def end_shift(self, request):
        if request.method == "POST":
            shift = WorkShift.objects.filter(employee=request.user, is_active=True).first()
            if shift:
                from reports.models import DailyReport
                # ЖЕСТКАЯ ПРОВЕРКА: Написал ли отчет?
                has_report = DailyReport.objects.filter(employee=request.user, date=timezone.now().date()).exists()
                if not has_report:
                    messages.error(request, "🛑 ОШИБКА: Нельзя завершить смену, пока не написан ежедневный отчет!")
                else:
                    shift.time_out = timezone.now()
                    shift.save() # Автоматом посчитает часы (логика в модели)
                    messages.success(request, "Рабочий день успешно завершен. Отдыхайте!")
        return redirect('/admin/')
    
    @display(description="Время прихода")
    def time_in_fmt(self, obj):
        return obj.time_in.strftime("%H:%M") if obj.time_in else "—"

    @display(description="Время ухода")
    def time_out_fmt(self, obj):
        return obj.time_out.strftime("%H:%M") if obj.time_out else "—"

    @display(description="Статус", label=True)
    def status_badge(self, obj):
        if obj.is_active:
            return "В офисе", "success"
        return "Смена закрыта", "default"