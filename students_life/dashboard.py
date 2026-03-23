# students_life/dashboard.py
import datetime
from django.utils import timezone
from django.db.models import Sum, Count
from django.db.models.functions import TruncDay

from users.models import User, ManagerSalary
from clients.models import Client
from analytics.models import Payment, Deal, FinancialPeriod
from catalog.models import University, Program
from tasks.models import Task
from timetracking.models import WorkShift
from reports.models import DailyReport
from leads.models import Lead


# ─── Дашборд ─────────────────────────────────────────────────────────────────

def dashboard_callback(request, context):
    user  = request.user
    now   = timezone.now()
    today = now.date()
    tomorrow = now + datetime.timedelta(days=1)

    # Автозакрытие забытых смен
    for shift in WorkShift.objects.filter(is_active=True):
        is_past     = shift.date < today
        is_late     = shift.date == today and now.time() >= datetime.time(22, 0)
        if is_past or is_late:
            shift.time_out      = timezone.make_aware(datetime.datetime.combine(shift.date, datetime.time(22, 0)))
            shift.is_auto_closed = True
            shift.save()
            forgets = WorkShift.objects.filter(employee=shift.employee, is_auto_closed=True).count()
            if forgets >= 3:
                shift.employee.is_effective = False
                shift.employee.save()

    # Горящие задачи
    context['hot_tasks'] = Task.objects.filter(
        status__in=['todo', 'process'],
        deadline__lte=tomorrow,
    ).order_by('deadline')[:5]

    # ── Суперадмин ────────────────────────────────────────────────────────────
    if user.is_superuser:
        last_week    = now - datetime.timedelta(days=7)
        payments_data = (
            Payment.objects.filter(payment_date__gte=last_week, is_confirmed=True)
            .annotate(day=TruncDay('payment_date'))
            .values('day')
            .annotate(total=Sum('amount_usd'))
            .order_by('day')
        )
        days    = [p['day'].strftime('%d.%m') for p in payments_data]
        amounts = [float(p['total']) for p in payments_data]

        period      = FinancialPeriod.objects.filter(is_closed=False).last()
        total_rev   = float(period.total_revenue) if period else 0
        net_profit  = float(period.net_profit)    if period else 0

        active_deals   = Deal.objects.filter(payment_status__in=['process', 'waiting_payment']).count()
        total_clients  = Client.objects.count()
        pending_pays   = Payment.objects.filter(is_confirmed=False).count()

        context.update({
            'kpi': [
                {'title': 'Выручка (период)',   'metric': f'${total_rev:,.2f}',  'footer': 'Текущий финансовый период', 'color': 'primary'},
                {'title': 'Чистая прибыль',     'metric': f'${net_profit:,.2f}', 'footer': 'Свободные деньги',          'color': 'success'},
                {'title': 'Активные сделки',    'metric': active_deals,           'footer': 'Деньги в пути',             'color': 'warning'},
                {'title': 'Клиентов всего',     'metric': total_clients,           'footer': 'Общая база',                'color': 'info'},
                {'title': 'Ждут подтверждения', 'metric': pending_pays,            'footer': 'Неподтверждённые платежи',  'color': 'danger'},
            ],
            'chart': {
                'name': 'Доходы за 7 дней', 'type': 'line', 'labels': days,
                'datasets': [{
                    'label': 'Выручка (USD)', 'data': amounts,
                    'borderColor': '#10B981', 'backgroundColor': 'rgba(16,185,129,0.1)',
                }],
            },
        })

    # ── Менеджер ──────────────────────────────────────────────────────────────
    else:
        sal = getattr(user, 'managersalary', None)
        balance  = float(sal.current_balance)          if sal else 0
        fixed    = float(sal.fixed_salary)             if sal else 0
        plan     = float(sal.monthly_plan)             if sal else 1000
        revenue  = float(sal.current_month_revenue)    if sal else 0
        mot_t    = float(sal.motivation_target)         if sal else 0
        mot_r    = float(sal.motivation_reward)         if sal else 0
        progress = min(int((revenue / plan) * 100), 100) if plan > 0 else 0
        left_mot = max(mot_t - revenue, 0)

        context['raw_balance']     = balance
        context['has_active_shift']= WorkShift.objects.filter(employee=user, date=today, is_active=True).exists()
        context['has_report_today']= DailyReport.objects.filter(employee=user, date=today).exists()
        context['forgets_count']   = WorkShift.objects.filter(employee=user, is_auto_closed=True).count()

        context['new_leads']  = Lead.objects.filter(status='new', manager__isnull=True).order_by('-created_at')[:5]
        context['my_clients'] = Client.objects.filter(manager=user).order_by('-created_at')[:5]
        context['my_deals']   = Deal.objects.filter(manager=user).order_by('-updated_at')[:5]
        context['my_tasks']   = Task.objects.filter(assigned_to=user).exclude(status='done').order_by('deadline')[:5]

        mot_text, mot_val, mot_color = (
            ('Выполнено! 🎉', f'+${mot_r:,.0f}', 'success')
            if left_mot <= 0 and mot_t > 0
            else (f'До бонуса +${mot_r:,.0f}', f'${left_mot:,.0f}', 'warning')
        )

        context.update({
            'kpi': [
                {'title': 'ЗП (Оклад + Бонус)', 'metric': f'${balance + fixed:,.2f}', 'footer': f'Оклад: ${fixed:,.0f} | Бонус: ${balance:,.0f}', 'color': 'success'},
                {'title': 'Выручка за месяц',   'metric': f'${revenue:,.2f}',          'footer': f'План: ${plan:,.0f}',                              'color': 'primary'},
                {'title': 'Мотивация',           'metric': mot_val,                     'footer': mot_text,                                           'color': mot_color},
            ],
            'progress': [{
                'title':       'Выполнение плана продаж',
                'description': f'Вы принесли ${revenue:,.2f} из ${plan:,.0f}',
                'value':       progress,
                'color':       'success' if progress >= 100 else 'primary',
            }],
        })

    return context


# ─── Навигация ────────────────────────────────────────────────────────────────

def get_navigation(request):
    user = request.user

    # Базовое меню — доступно всем
    nav = [
        {
            'title': 'Работа с клиентами',
            'separator': True,
            'collapsible': False,
            'items': [
                {'title': '📋 Заявки с сайта',     'icon': 'mail',           'link': '/admin/leads/lead/'},
                {'title': '👥 Клиенты',            'icon': 'people',         'link': '/admin/clients/client/'},
                {'title': '✅ Задачи (Канбан)',     'icon': 'assignment',     'link': '/admin/tasks/task/kanban/'},
                {'title': '💰 Сделки',             'icon': 'attach_money',   'link': '/admin/analytics/deal/'},
                {'title': '💳 Платежи',            'icon': 'payments',       'link': '/admin/analytics/payment/'},
            ],
        },
        {
            'title': 'Документы и учёт',
            'separator': True,
            'collapsible': True,
            'items': [
                {'title': '📄 Документы',          'icon': 'description',    'link': '/admin/documents/generateddocument/'},
                {'title': '🕐 Рабочие смены',      'icon': 'schedule',       'link': '/admin/timetracking/workshift/'},
                {'title': '📊 Отчёты',             'icon': 'summarize',       'link': '/admin/reports/dailyreport/'},
            ],
        },
        {
            'title': 'Каталог',
            'separator': False,
            'collapsible': True,
            'items': [
                {'title': '🏫 Университеты',       'icon': 'school',         'link': '/admin/catalog/university/'},
                {'title': '📚 Программы',          'icon': 'menu_book',      'link': '/admin/catalog/program/'},
                {'title': '✈️ Доп. услуги',        'icon': 'room_service',   'link': '/admin/services/service/'},
                {'title': '💱 Курсы валют',         'icon': 'currency_exchange','link': '/admin/catalog/currency/'},
                {'title': '📖 База знаний',         'icon': 'library_books',  'link': '/admin/documents/infosnippet/'},
            ],
        },
        {
            'title': 'Обучение и рейтинг',
            'separator': True,
            'collapsible': True,
            'items': [
                {'title': '🏆 Живой рейтинг',      'icon': 'emoji_events',   'link': '/admin/gamification/leaderboard/'},
                {'title': '🎓 Видеоуроки',          'icon': 'play_circle',    'link': '/admin/gamification/tutorialvideo/'},
                {'title': '🧪 Тесты',              'icon': 'quiz',            'link': '/admin/documents/knowledgetest/'},
            ],
        },
        {
            'title': 'Аккаунт',
            'separator': True,
            'collapsible': False,
            'items': [
                {'title': '👤 Мой профиль',        'icon': 'account_circle', 'link': '/admin/profile/'},
            ],
        },
    ]

    # Только для суперадмина
    if user.is_superuser:
        admin_nav = [
            {
                'title': 'Управление бизнесом',
                'separator': True,
                'collapsible': False,
                'items': [
                    {'title': '📈 Финансовые периоды', 'icon': 'account_balance',   'link': '/admin/analytics/financialperiod/'},
                    {'title': '💸 Расходы',           'icon': 'money_off',          'link': '/admin/analytics/expense/'},
                    {'title': '📜 История начислений', 'icon': 'receipt_long',       'link': '/admin/analytics/transactionhistory/'},
                    {'title': '🔍 История действий',   'icon': 'manage_search',      'link': '/admin/analytics/auditlog/'},
                ],
            },
            {
                'title': 'Email рассылка',
                'separator': True,
                'collapsible': False,
                'items': [
                    {'title': '📨 Рассылки',           'icon': 'send',              'link': '/admin/mailing/mailingcampaign/',
                     'badge': _pending_campaigns_count()},
                    {'title': '✉️ Шаблоны писем',      'icon': 'email',             'link': '/admin/mailing/emailtemplate/'},
                    {'title': '📋 История отправок',   'icon': 'history',            'link': '/admin/mailing/mailinglog/'},
                ],
            },
            {
                'title': 'HR и команда',
                'separator': True,
                'collapsible': True,
                'items': [
                    {'title': '👨‍💼 Сотрудники',        'icon': 'badge',             'link': '/admin/users/user/'},
                    {'title': '🏢 Офисы',              'icon': 'apartment',          'link': '/admin/users/office/'},
                    {'title': '🏅 Архив рейтингов',    'icon': 'military_tech',       'link': '/admin/gamification/ratingsnapshot/'},
                    {'title': '📐 Шаблоны документов', 'icon': 'folder_copy',         'link': '/admin/documents/documenttemplate/'},
                ],
            },
        ]
        nav = admin_nav + nav

    return nav


def _pending_campaigns_count() -> str | None:
    """Бейдж с кол-вом черновиков рассылки."""
    try:
        from mailing.models import MailingCampaign
        count = MailingCampaign.objects.filter(status='draft').count()
        return str(count) if count else None
    except Exception:
        return None