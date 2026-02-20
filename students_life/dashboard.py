# dashboard.py

from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncDay
from datetime import timedelta

# Импортируй свои модели из нужных аппок (поправь пути импортов под свою структуру)
from users.models import User, ManagerSalary
from clients.models import Client
from analytics.models import Payment, Deal, FinancialPeriod
from catalog.models import University, Program
# from tasks.models import Task  <-- Раскомментируй и поправь путь к модели Task

def dashboard_callback(request, context):
    """
    Генерация данных для главной страницы Unfold Admin.
    """
    user = request.user

    # ---------------------------------------------------------
    # 1. СУПЕРПОЛЬЗОВАТЕЛЬ (ДИРЕКТОР / ФИНАНСЫ)
    # ---------------------------------------------------------
    if user.is_superuser:
        last_week = timezone.now() - timedelta(days=7)
        
        # График платежей
        payments_data = (
            Payment.objects.filter(payment_date__gte=last_week, is_confirmed=True)
            .annotate(day=TruncDay('payment_date'))
            .values('day')
            .annotate(total=Sum('amount_usd'))
            .order_by('day')
        )

        days = [p['day'].strftime('%d.%m') for p in payments_data]
        amounts = [float(p['total']) for p in payments_data]

        # Финансы
        period = FinancialPeriod.objects.filter(is_closed=False).last()
        total_revenue = period.total_revenue if period else 0
        net_profit = period.net_profit if period else 0
        
        # Обобщенная стата
        total_clients = Client.objects.count()
        active_deals = Deal.objects.filter(payment_status__in=['process', 'waiting_payment']).count()

        context.update({
            "kpi": [
                {
                    "title": "Выручка (Период)",
                    "metric": f"${total_revenue:,.2f}",
                    "footer": "Текущий финансовый период",
                    "color": "primary",
                },
                {
                    "title": "Чистая прибыль",
                    "metric": f"${net_profit:,.2f}",
                    "footer": "Свободные деньги компании",
                    "color": "success",
                },
                {
                    "title": "Активные сделки",
                    "metric": active_deals,
                    "footer": "Деньги в пути",
                    "color": "warning",
                },
                {
                    "title": "Всего клиентов",
                    "metric": total_clients,
                    "footer": "Общая база",
                    "color": "info",
                },
            ],
            "chart": {
                "name": "Динамика подтвержденных доходов (7 дней)",
                "type": "line",
                "labels": days,
                "datasets": [
                    {
                        "label": "Выручка (USD)",
                        "data": amounts,
                        "borderColor": "#10B981", # Зеленый цвет
                        "backgroundColor": "rgba(16, 185, 129, 0.1)",
                    }
                ],
            },
        })

    # ---------------------------------------------------------
    # 2. МЕНЕДЖЕР ПО ПАРТНЕРСТВАМ
    # ---------------------------------------------------------
    elif user.groups.filter(name='Менеджер по партнерствам').exists():
        total_unis = University.objects.count()
        active_programs = Program.objects.filter(is_active=True, is_deleted=False).count()
        
        # Передаем последние добавленные вузы для вывода в таблицу
        context['recent_unis'] = University.objects.order_by('-id')[:5]

        context.update({
            "kpi": [
                {
                    "title": "Университеты в базе",
                    "metric": total_unis,
                    "footer": "Доступно для продаж",
                    "color": "primary",
                },
                {
                    "title": "Активные программы",
                    "metric": active_programs,
                    "footer": "Открыт набор",
                    "color": "success",
                },
            ]
        })

    # ---------------------------------------------------------
    # 3. МЕНЕДЖЕР ПО ПРОДАЖАМ
    # ---------------------------------------------------------
    else:
        # Зарплата и KPI
        salary_profile = getattr(user, 'managersalary', None)
        current_balance, plan, revenue, percent_complete = 0, 1000, 0, 0

        if salary_profile:
            current_balance = salary_profile.current_balance
            plan = salary_profile.monthly_plan
            revenue = salary_profile.current_month_revenue
            if plan > 0:
                percent_complete = min(int((revenue / plan) * 100), 100)

        # Вытаскиваем понемногу из каждой таблицы
        my_clients = Client.objects.filter(manager=user).order_by('-created_at')[:5]
        my_deals = Deal.objects.filter(manager=user).order_by('-updated_at')[:5]
        
        # Берем задачи, которые не 'done' и сортируем по ближайшему дедлайну
        # Если модель Task импортирована корректно:
        # my_tasks = Task.objects.filter(assigned_to=user).exclude(status='done').order_by('deadline')[:5]
        
        # Прокидываем в контекст (чтобы потом отрисовать в HTML)
        context['my_clients'] = my_clients
        context['my_deals'] = my_deals
        # context['my_tasks'] = my_tasks

        context.update({
            "kpi": [
                {
                    "title": "Мой Баланс",
                    "metric": f"${current_balance:,.2f}",
                    "footer": "Доступно к выплате",
                    "color": "success",
                },
                {
                    "title": "Выручка за месяц",
                    "metric": f"${revenue:,.2f}",
                    "footer": f"План: ${plan:,.2f}",
                    "color": "primary",
                },
            ],
            "progress": [
                {
                    "title": "Выполнение плана",
                    "description": f"Вы заработали ${revenue:,.2f} из ${plan:,.2f}",
                    "value": percent_complete,
                    "color": "primary" if percent_complete < 100 else "success",
                }
            ]
        })

    return context