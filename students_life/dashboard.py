# students_life/dashboard.py
import datetime

from django.db.models import Q, Sum
from django.db.models.functions import TruncDay
from django.utils import timezone

from analytics.models import Deal, FinancialPeriod, Payment
from clients.models import Client
from documents.models import GeneratedDocument
from leads.models import Lead
from reports.models import DailyReport
from support.models import SupportMessage
from tasks.models import Project, Task
from timetracking.models import WorkShift


def is_admin_user(user):
    return bool(user and user.is_authenticated and (user.is_superuser or getattr(user, 'role', None) == 'admin'))


def close_overdue_shifts():
    now = timezone.localtime()
    today = timezone.localdate()
    tz = timezone.get_current_timezone()

    overdue_shifts = WorkShift.objects.select_related('employee').filter(is_active=True)

    for shift in overdue_shifts:
        should_close = shift.date < today or (shift.date == today and now.time() >= datetime.time(22, 0))
        if not should_close:
            continue

        close_dt = timezone.make_aware(datetime.datetime.combine(shift.date, datetime.time(22, 0)), tz)
        if shift.time_in and close_dt <= shift.time_in:
            close_dt = now

        shift.time_out = close_dt
        shift.is_active = False
        shift.is_auto_closed = True
        shift.save(update_fields=['time_out', 'is_active', 'is_auto_closed', 'hours_worked', 'updated_at'])

        employee = shift.employee
        auto_closed_count = WorkShift.objects.filter(employee=employee, is_auto_closed=True).count()
        if auto_closed_count >= 3 and employee.is_effective:
            employee.is_effective = False
            employee.save(update_fields=['is_effective', 'updated_at'])


def dashboard_callback(request, context):
    user = request.user
    now = timezone.localtime()
    today = timezone.localdate()
    tomorrow = now + datetime.timedelta(days=1)

    close_overdue_shifts()

    context['hot_tasks'] = Task.objects.filter(status__in=['todo', 'process'], deadline__isnull=False, deadline__lte=tomorrow).order_by('deadline')[:5]

    if is_admin_user(user):
        last_week = today - datetime.timedelta(days=6)
        payments_data = (
            Payment.objects.filter(payment_date__gte=last_week, is_confirmed=True)
            .annotate(day=TruncDay('payment_date'))
            .values('day')
            .annotate(total=Sum('amount_usd'))
            .order_by('day')
        )
        days = [p['day'].strftime('%d.%m') for p in payments_data if p['day']]
        amounts = [float(p['total'] or 0) for p in payments_data]

        period = FinancialPeriod.ensure_current_period()
        period.calculate_stats()

        total_rev = float(period.total_revenue or 0)
        net_profit = float(period.net_profit or 0)
        active_deals = Deal.objects.filter(payment_status__in=['new', 'waiting_payment', 'paid_partial']).count()
        total_clients = Client.objects.count()
        pending_pays = Payment.objects.filter(is_confirmed=False).count()
        pending_docs = GeneratedDocument.objects.filter(status='generated').count()
        new_support = SupportMessage.objects.filter(status='new').count()
        active_projects = Project.objects.filter(status='active', is_hidden=False).count()

        context.update({
            'kpi': [
                {'title': 'Выручка (период)', 'metric': f'${total_rev:,.2f}', 'footer': 'Текущий финансовый период', 'color': 'primary'},
                {'title': 'Чистая прибыль', 'metric': f'${net_profit:,.2f}', 'footer': 'Подтверждённые платежи - расходы', 'color': 'success'},
                {'title': 'Активные сделки', 'metric': active_deals, 'footer': 'Новые / ждут оплату / частично оплачены', 'color': 'warning'},
                {'title': 'Проекты', 'metric': active_projects, 'footer': 'Активные внутренние проекты', 'color': 'info'},
                {'title': 'Ждут внимания', 'metric': pending_pays + pending_docs + new_support, 'footer': f'Платежи: {pending_pays} | Документы: {pending_docs} | Поддержка: {new_support}', 'color': 'danger'},
                {'title': 'Клиентов всего', 'metric': total_clients, 'footer': 'Вся клиентская база', 'color': 'default'},
            ],
            'chart': {
                'name': 'Подтверждённые платежи за 7 дней',
                'type': 'line',
                'labels': days,
                'datasets': [{'label': 'USD', 'data': amounts, 'borderColor': '#10B981', 'backgroundColor': 'rgba(16,185,129,0.10)'}],
            },
        })
    else:
        sal = getattr(user, 'managersalary', None)
        balance = float(getattr(sal, 'current_balance', 0) or 0)
        fixed = float(getattr(sal, 'fixed_salary', 0) or 0)
        plan = float(getattr(sal, 'monthly_plan', 0) or 0)
        revenue = float(getattr(sal, 'current_month_revenue', 0) or 0)
        mot_target = float(getattr(sal, 'motivation_target', 0) or 0)
        mot_reward = float(getattr(sal, 'motivation_reward', 0) or 0)

        progress = min(int((revenue / plan) * 100), 100) if plan > 0 else 0
        left_to_motivation = max(mot_target - revenue, 0)

        context['raw_balance'] = balance
        context['has_active_shift'] = WorkShift.objects.filter(employee=user, date=today, is_active=True).exists()
        context['has_report_today'] = DailyReport.objects.filter(employee=user, date=today).exists()
        context['forgets_count'] = WorkShift.objects.filter(employee=user, is_auto_closed=True).count()
        context['new_leads'] = Lead.objects.filter(Q(manager=user) | Q(manager__isnull=True, status='new')).order_by('-created_at')[:5]
        context['my_clients'] = Client.objects.filter(Q(manager=user) | Q(shared_with=user)).distinct().order_by('-updated_at')[:5]
        context['my_deals'] = Deal.objects.filter(manager=user).order_by('-updated_at')[:5]
        context['my_tasks'] = Task.objects.filter(assigned_to=user).exclude(status='done').order_by('deadline', '-updated_at')[:5]

        mot_text, mot_val, mot_color = (
            ('Выполнено! 🎉', f'+${mot_reward:,.0f}', 'success')
            if left_to_motivation <= 0 and mot_target > 0
            else (f'До бонуса +${mot_reward:,.0f}', f'${left_to_motivation:,.0f}', 'warning')
        )

        context.update({
            'kpi': [
                {'title': 'ЗП (Оклад + Бонус)', 'metric': f'${balance + fixed:,.2f}', 'footer': f'Оклад: ${fixed:,.0f} | Бонус: ${balance:,.0f}', 'color': 'success'},
                {'title': 'Выручка за месяц', 'metric': f'${revenue:,.2f}', 'footer': f'План: ${plan:,.0f}', 'color': 'primary'},
                {'title': 'Мотивация', 'metric': mot_val, 'footer': mot_text, 'color': mot_color},
            ],
            'progress': [{'title': 'Выполнение плана продаж', 'description': f'Вы принесли ${revenue:,.2f} из ${plan:,.0f}', 'value': progress, 'color': 'success' if progress >= 100 else 'primary'}],
        })

    return context


def get_navigation(request):
    user = request.user

    nav = [
        {
            'title': 'Работа с клиентами',
            'separator': True,
            'collapsible': False,
            'items': [
                {'title': ' Заявки с сайта', 'icon': 'mail', 'link': '/admin/leads/lead/'},
                {'title': ' Клиенты', 'icon': 'people', 'link': '/admin/clients/client/'},
                {'title': ' Задачи (Канбан)', 'icon': 'assignment', 'link': '/admin/tasks/task/kanban/'},
                {'title': ' Сделки', 'icon': 'attach_money', 'link': '/admin/analytics/deal/'},
                {'title': ' Платежи', 'icon': 'payments', 'link': '/admin/analytics/payment/'},
            ],
        },
        {
            'title': 'Проекты и поддержка',
            'separator': True,
            'collapsible': False,
            'items': [
                {'title': ' Проекты', 'icon': 'folder_open', 'link': '/admin/tasks/project/'},
                {'title': ' Задачи проектов', 'icon': 'task_alt', 'link': '/admin/tasks/projecttask/'},
                {'title': ' Файлы проектов', 'icon': 'attach_file', 'link': '/admin/tasks/projectattachment/'},
                {'title': ' Поддержка сотрудников', 'icon': 'support_agent', 'link': '/admin/support/supportmessage/'},
            ],
        },
        {
            'title': 'Документы и учёт',
            'separator': True,
            'collapsible': True,
            'items': [
                {'title': ' Документы', 'icon': 'description', 'link': '/admin/documents/generateddocument/'},
                {'title': ' Рабочие смены', 'icon': 'schedule', 'link': '/admin/timetracking/workshift/'},
                {'title': ' Отчёты', 'icon': 'summarize', 'link': '/admin/reports/dailyreport/'},
            ],
        },
        {
            'title': 'Каталог и база знаний',
            'separator': False,
            'collapsible': True,
            'items': [
                {'title': ' Университеты', 'icon': 'school', 'link': '/admin/catalog/university/'},
                {'title': ' Программы', 'icon': 'menu_book', 'link': '/admin/catalog/program/'},
                {'title': ' Доп. услуги', 'icon': 'room_service', 'link': '/admin/services/service/'},
                {'title': ' Курсы валют', 'icon': 'currency_exchange', 'link': '/admin/catalog/currency/'},
                {'title': ' Разделы базы знаний', 'icon': 'account_tree', 'link': '/admin/documents/knowledgesection/'},
                {'title': ' Файлы разделов', 'icon': 'attach_file', 'link': '/admin/documents/knowledgesectionattachment/'},
                {'title': ' Материалы базы знаний', 'icon': 'library_books', 'link': '/admin/documents/infosnippet/'},
                {'title': ' Тесты', 'icon': 'quiz', 'link': '/admin/documents/knowledgetest/'},
            ],
        },
        {
            'title': 'Аккаунт',
            'separator': True,
            'collapsible': False,
            'items': [{'title': ' Мой профиль', 'icon': 'account_circle', 'link': '/admin/profile/'}],
        },
    ]

    if is_admin_user(user):
        admin_nav = [
            {
                'title': 'Управление бизнесом',
                'separator': True,
                'collapsible': False,
                'items': [
                    {'title': ' Финансовые периоды', 'icon': 'account_balance', 'link': '/admin/analytics/financialperiod/'},
                    {'title': ' Расходы', 'icon': 'money_off', 'link': '/admin/analytics/expense/'},
                    {'title': ' История начислений', 'icon': 'receipt_long', 'link': '/admin/analytics/transactionhistory/'},
                    {'title': ' История действий', 'icon': 'manage_search', 'link': '/admin/analytics/auditlog/'},
                    {'title': ' Push-устройства', 'icon': 'notifications', 'link': '/admin/notifications/fcmdevice/'},
                ],
            },
            {
                'title': 'HR и команда',
                'separator': True,
                'collapsible': True,
                'items': [
                    {'title': ' Сотрудники', 'icon': 'badge', 'link': '/admin/users/user/'},
                    {'title': ' Офисы', 'icon': 'apartment', 'link': '/admin/users/office/'},
                    {'title': ' Архив рейтингов', 'icon': 'military_tech', 'link': '/admin/gamification/ratingsnapshot/'},
                    {'title': ' Шаблоны документов', 'icon': 'folder_copy', 'link': '/admin/documents/documenttemplate/'},
                ],
            },
        ]
        nav = admin_nav + nav

    return nav