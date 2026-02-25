# students_life/dashboard.py
import datetime
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncDay

from users.models import User, ManagerSalary
from clients.models import Client
from analytics.models import Payment, Deal, FinancialPeriod
from catalog.models import University, Program
from tasks.models import Task
from timetracking.models import WorkShift
from reports.models import DailyReport
from leads.models import Lead

def dashboard_callback(request, context):
    user = request.user
    now = timezone.now()
    today = now.date()
    tomorrow = now + datetime.timedelta(days=1)
    
    # Автозакрытие забытых смен
    active_shifts = WorkShift.objects.filter(is_active=True)
    for shift in active_shifts:
        is_past_day = shift.date < today
        is_late_today = shift.date == today and now.time() >= datetime.time(22, 0)
        
        if is_past_day or is_late_today:
            shift.time_out = timezone.make_aware(datetime.datetime.combine(shift.date, datetime.time(22, 0)))
            shift.is_auto_closed = True
            shift.save()
            
            forgets_count = WorkShift.objects.filter(employee=shift.employee, is_auto_closed=True).count()
            if forgets_count >= 3:
                shift.employee.is_effective = False
                shift.employee.save()

    # Горящие задачи
    hot_tasks = Task.objects.filter(
        status__in=['todo', 'process'], 
        deadline__lte=tomorrow
    ).order_by('deadline')[:5]
    
    context['hot_tasks'] = hot_tasks

    if user.is_superuser:
        last_week = now - datetime.timedelta(days=7)
        payments_data = (
            Payment.objects.filter(payment_date__gte=last_week, is_confirmed=True)
            .annotate(day=TruncDay('payment_date'))
            .values('day')
            .annotate(total=Sum('amount_usd'))
            .order_by('day')
        )
        days = [p['day'].strftime('%d.%m') for p in payments_data]
        amounts = [float(p['total']) for p in payments_data]

        period = FinancialPeriod.objects.filter(is_closed=False).last()
        total_revenue = float(period.total_revenue) if period else 0
        net_profit = float(period.net_profit) if period else 0
        
        total_clients = Client.objects.count()
        active_deals = Deal.objects.filter(payment_status__in=['process', 'waiting_payment']).count()

        context.update({
            "kpi": [
                {"title": "Выручка (Период)", "metric": f"${total_revenue:,.2f}", "footer": "Текущий финансовый период", "color": "primary"},
                {"title": "Чистая прибыль", "metric": f"${net_profit:,.2f}", "footer": "Свободные деньги", "color": "success"},
                {"title": "Активные сделки", "metric": active_deals, "footer": "Деньги в пути", "color": "warning"},
                {"title": "Всего клиентов", "metric": total_clients, "footer": "Общая база", "color": "info"},
            ],
            "chart": {
                "name": "Динамика доходов (7 дней)", "type": "line", "labels": days,
                "datasets": [{"label": "Выручка (USD)", "data": amounts, "borderColor": "#10B981", "backgroundColor": "rgba(16, 185, 129, 0.1)"}],
            },
        })

    elif user.groups.filter(name='Менеджер по партнерствам').exists():
        total_unis = University.objects.count()
        active_programs = Program.objects.filter(is_active=True, is_deleted=False).count()
        context['recent_unis'] = University.objects.order_by('-id')[:5]
        context.update({
            "kpi": [
                {"title": "Университеты в базе", "metric": total_unis, "footer": "Доступно для продаж", "color": "primary"},
                {"title": "Активные программы", "metric": active_programs, "footer": "Открыт набор", "color": "success"},
            ]
        })

    else:
        salary_profile = getattr(user, 'managersalary', None)
        current_balance, fixed_salary, plan, revenue, percent_complete = 0, 0, 1000, 0, 0
        mot_target, mot_reward, left_to_mot = 0, 0, 0

        if salary_profile:
            current_balance = float(salary_profile.current_balance)
            fixed_salary = float(salary_profile.fixed_salary)
            plan = float(salary_profile.monthly_plan)
            revenue = float(salary_profile.current_month_revenue)
            mot_target = float(salary_profile.motivation_target)
            mot_reward = float(salary_profile.motivation_reward)
            
            if plan > 0:
                percent_complete = min(int((revenue / plan) * 100), 100)
            left_to_mot = mot_target - revenue if mot_target > revenue else 0

        context['raw_balance'] = current_balance
        context['has_active_shift'] = WorkShift.objects.filter(employee=user, date=today, is_active=True).exists()
        context['has_report_today'] = DailyReport.objects.filter(employee=user, date=today).exists()
        context['forgets_count'] = WorkShift.objects.filter(employee=user, is_auto_closed=True).count()

        context['new_leads'] = Lead.objects.filter(status='new', manager__isnull=True).order_by('-created_at')[:5]
        context['my_clients'] = Client.objects.filter(manager=user).order_by('-created_at')[:5]
        context['my_deals'] = Deal.objects.filter(manager=user).order_by('-updated_at')[:5]
        context['my_tasks'] = Task.objects.filter(assigned_to=user).exclude(status='done').order_by('deadline')[:5]
        
        if left_to_mot <= 0 and mot_target > 0:
            mot_text, mot_metric, mot_color = "Выполнено! 🎉", f"+${mot_reward:,.0f}", "success"
        else:
            mot_text, mot_metric, mot_color = f"Осталось до бонуса +${mot_reward:,.0f}", f"${left_to_mot:,.0f}", "warning"

        context.update({
            "kpi": [
                {"title": "Зарплата (Оклад + Бонус)", "metric": f"${current_balance + fixed_salary:,.2f}", "footer": f"Оклад: ${fixed_salary:,.0f} | Накоплено: ${current_balance:,.0f}", "color": "success"},
                {"title": "Выручка за месяц", "metric": f"${revenue:,.2f}", "footer": f"План: ${plan:,.0f}", "color": "primary"},
                {"title": "Мотивация", "metric": mot_metric, "footer": mot_text, "color": mot_color},
            ],
            "progress": [
                {"title": "Выполнение плана продаж", "description": f"Вы принесли компании ${revenue:,.2f} из ${plan:,.0f}", "value": percent_complete, "color": "primary" if percent_complete < 100 else "success"}
            ]
        })

    return context


# === БЛОК ДЛЯ ДИНАМИЧЕСКОГО МЕНЮ ===
def get_navigation(request):
    """
    Генерация меню боковой панели (сайдбара).
    """
    # 1. Базовое меню (доступно всем: и менеджерам, и админу)
    nav = [
        {
            "title": "Работа с клиентами",
            "separator": True,
            "items": [
                {"title": "Новые заявки", "icon": "mail", "link": "/admin/leads/lead/"},
                {"title": "Клиенты", "icon": "people", "link": "/admin/clients/client/"},
                {"title": "Задачи (Канбан)", "icon": "assignment", "link": "/admin/tasks/task/"},
                {"title": "Сделки и Оплаты", "icon": "attach_money", "link": "/admin/analytics/deal/"},
                {"title": "Платежи", "icon": "money", "link": "/admin/analytics/payment/"},
            ],
        },
        {
            "title": "Документы и Учет",
            "separator": True,
            "items": [
                {"title": "Договоры", "icon": "description", "link": "/admin/documents/contract/"},
                {"title": "Рабочие смены", "icon": "schedule", "link": "/admin/timetracking/workshift/"},
                {"title": "Отчеты", "icon": "summarize", "link": "/admin/reports/dailyreport/"},
            ],
        },
        {
            "title": "Каталог и Услуги",
            "separator": False,
            "items": [
                {"title": "ВУЗы и Страны", "icon": "school", "link": "/admin/catalog/university/"},
                {"title": "Программы обучения", "icon": "school", "link": "/admin/catalog/program/"},
                {"title": "Доп. услуги", "icon": "room_service", "link": "/admin/services/service/"},
                {"title": "База знаний", "icon": "menu_book", "link": "/admin/documents/infosnippet/"},
            ],
        },
        {
            "title": "Обучение и Рейтинг",
            "separator": True,
            "items": [
                {"title": "🏆 Живой рейтинг", "icon": "emoji_events", "link": "/admin/gamification/leaderboard/"},
                {"title": "Видеоуроки", "icon": "play_circle", "link": "/admin/gamification/tutorialvideo/"},
            ],
        },
        {
            "title": "Мой аккаунт",
            "separator": True,
            "items": [
                {
                    "title": "Мой профиль",
                    "icon": "account_circle",
                    "link": "/admin/profile/",
                },
            ],
        }
    ]

    # 2. Админское меню (добавляется ТОЛЬКО для Суперюзера сверху списка)
    if request.user.is_superuser:
        admin_nav = [
            {
                "title": "Управление бизнесом",
                "separator": True,
                "items": [
                    {"title": "Финансы (Дашборд)", "icon": "account_balance", "link": "/admin/analytics/financialperiod/"},
                    {"title": "История действий", "icon": "manage_search", "link": "/admin/analytics/auditlog/"},
                    {"title": "Шаблоны документов", "icon": "folder_copy", "link": "/admin/documents/contracttemplate/"},
                ],
            },
            {
                "title": "HR и Команда",
                "separator": True,
                "items": [
                    {"title": "Сотрудники", "icon": "badge", "link": "/admin/users/user/"},
                    {"title": "Офисы", "icon": "apartment", "link": "/admin/users/office/"},
                    {"title": "Архив рейтингов", "icon": "military_tech", "link": "/admin/gamification/ratingsnapshot/"},
                ],
            },
        ]
        nav = admin_nav + nav

    return nav