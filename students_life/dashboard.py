# students_life/dashboard.py

from django.utils import timezone
from django.db.models import Sum, Count
from django.db.models.functions import TruncDay
from datetime import timedelta

# Импорт моделей
from users.models import User, ManagerSalary
from clients.models import Client
from analytics.models import Payment, Deal, FinancialPeriod

def dashboard_callback(request, context):
    """
    Функция для генерации данных на главной странице админки.
    Возвращает словарь с конфигурацией графиков, KPI и прогресс-баров.
    """
    
    # ---------------------------------------------------------
    # 1. ЛОГИКА ДЛЯ СУПЕРПОЛЬЗОВАТЕЛЯ (АДМИНА)
    # ---------------------------------------------------------
    if request.user.is_superuser:
        # --- Данные для графиков (Последние 7 дней) ---
        last_week = timezone.now() - timedelta(days=7)
        
        # Группируем платежи по дням
        payments_data = (
            Payment.objects.filter(payment_date__gte=last_week, is_confirmed=True)
            .annotate(day=TruncDay('payment_date'))
            .values('day')
            .annotate(total=Sum('amount_usd'))
            .order_by('day')
        )

        # Подготовка данных для Chart.js
        days = [p['day'].strftime('%d.%m') for p in payments_data]
        amounts = [float(p['total']) for p in payments_data]

        # --- KPI (Карточки сверху) ---
        # Текущий период (берем из твоей логики FinancialPeriod)
        period = FinancialPeriod.objects.filter(is_closed=False).last()
        total_revenue = period.total_revenue if period else 0
        net_profit = period.net_profit if period else 0
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
                    "footer": "До вычета зарплат",
                    "color": "success",
                },
                {
                    "title": "Активные сделки",
                    "metric": active_deals,
                    "footer": "В работе",
                    "color": "warning",
                },
            ],
            "chart": {
                "name": "Динамика доходов (7 дней)",
                "type": "line",  # line, bar, area
                "labels": days,
                "datasets": [
                    {
                        "label": "Выручка (USD)",
                        "data": amounts,
                        "borderColor": "#4F46E5",
                        "backgroundColor": "rgba(79, 70, 229, 0.1)",
                    }
                ],
            },
        })

    # ---------------------------------------------------------
    # 2. ЛОГИКА ДЛЯ МЕНЕДЖЕРА
    # ---------------------------------------------------------
    else:
        # Получаем профиль зарплаты
        salary_profile = getattr(request.user, 'managersalary', None)
        
        current_balance = 0
        plan = 1000
        revenue = 0
        percent_complete = 0

        if salary_profile:
            current_balance = salary_profile.current_balance
            plan = salary_profile.monthly_plan
            revenue = salary_profile.current_month_revenue
            
            if plan > 0:
                percent_complete = int((revenue / plan) * 100)
                if percent_complete > 100: percent_complete = 100

        # Получаем клиентов менеджера (для таблицы)
        my_clients = Client.objects.filter(manager=request.user).order_by('-created_at')[:10]

        # Добавляем клиентов прямо в контекст шаблона (не в KPI)
        context['custom_clients_table'] = my_clients

        context.update({
            # Карточки KPI
            "kpi": [
                {
                    "title": "Мой Баланс",
                    "metric": f"${current_balance:,.2f}",
                    "footer": "Доступно к выплате",
                    "color": "success", # Зеленый
                },
                {
                    "title": "Выручка за месяц",
                    "metric": f"${revenue:,.2f}",
                    "footer": f"План: ${plan:,.2f}",
                    "color": "primary",
                },
            ],
            # Прогресс бар выполнения плана
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