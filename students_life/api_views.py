# students_life/api_views.py
from django.db.models import Q
from django.utils import timezone
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from analytics.models import Payment, Deal, FinancialPeriod
from clients.models import Client
from tasks.models import Task
from timetracking.models import WorkShift
from reports.models import DailyReport
from leads.models import Lead
from documents.models import GeneratedDocument
from .dashboard import is_admin_user, close_overdue_shifts


def as_float(value):
    return float(value or 0)


class HealthCheckView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            'status': 'ok',
            'service': 'managers-sl-backend',
            'time': timezone.localtime().isoformat(),
        })


class AppConfigView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            'user': {
                'id': request.user.id,
                'email': request.user.email,
                'role': getattr(request.user, 'role', 'manager'),
                'is_admin': is_admin_user(request.user),
            },
            'notifications': {
                'start_day': '08:00',
                'end_day': '17:50',
                'daily_report': '21:00',
            },
            'endpoints': {
                'login': '/api/auth/login/',
                'logout': '/api/auth/logout/',
                'refresh': '/api/auth/refresh/',
                'dashboard': '/api/app/dashboard/',
                'health': '/api/health/',
            },
        })


class DashboardSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        close_overdue_shifts()

        user = request.user
        today = timezone.localdate()

        if is_admin_user(user):
            period = FinancialPeriod.ensure_current_period()
            period.calculate_stats()

            payload = {
                'role': 'admin',
                'today': str(today),
                'metrics': {
                    'period_revenue_usd': as_float(period.total_revenue),
                    'period_profit_usd': as_float(period.net_profit),
                    'clients_total': Client.objects.count(),
                    'active_deals': Deal.objects.filter(
                        payment_status__in=['new', 'waiting_payment', 'paid_partial']
                    ).count(),
                    'pending_payments': Payment.objects.filter(is_confirmed=False).count(),
                    'pending_documents': GeneratedDocument.objects.filter(status='generated').count(),
                },
                'recent': {
                    'payments': list(
                        Payment.objects.select_related('deal', 'deal__client')
                        .order_by('-payment_date', '-id')
                        .values(
                            'id',
                            'payment_date',
                            'amount_usd',
                            'is_confirmed',
                            'deal_id',
                            'deal__client__full_name',
                        )[:5]
                    ),
                    'leads': list(
                        Lead.objects.order_by('-created_at')
                        .values('id', 'full_name', 'phone', 'status', 'created_at')[:5]
                    ),
                    'tasks': list(
                        Task.objects.filter(status__in=['todo', 'process', 'review'])
                        .order_by('deadline', '-updated_at')
                        .values('id', 'title', 'status', 'priority', 'deadline')[:5]
                    ),
                    'documents': list(
                        GeneratedDocument.objects.select_related('deal', 'deal__client')
                        .order_by('-created_at')
                        .values(
                            'id',
                            'title',
                            'status',
                            'deal_id',
                            'deal__client__full_name',
                            'created_at',
                        )[:5]
                    ),
                }
            }
            return Response(payload)

        sal = getattr(user, 'managersalary', None)
        revenue = as_float(getattr(sal, 'current_month_revenue', 0))
        plan = as_float(getattr(sal, 'monthly_plan', 0))
        progress = min(int((revenue / plan) * 100), 100) if plan > 0 else 0

        payload = {
            'role': 'manager',
            'today': str(today),
            'workday': {
                'has_active_shift': WorkShift.objects.filter(
                    employee=user,
                    date=today,
                    is_active=True
                ).exists(),
                'has_report_today': DailyReport.objects.filter(
                    employee=user,
                    date=today
                ).exists(),
                'forgotten_shift_count': WorkShift.objects.filter(
                    employee=user,
                    is_auto_closed=True
                ).count(),
            },
            'salary': {
                'fixed_salary_usd': as_float(getattr(sal, 'fixed_salary', 0)),
                'bonus_balance_usd': as_float(getattr(sal, 'current_balance', 0)),
                'month_revenue_usd': revenue,
                'month_plan_usd': plan,
                'plan_progress_percent': progress,
                'motivation_target_usd': as_float(getattr(sal, 'motivation_target', 0)),
                'motivation_reward_usd': as_float(getattr(sal, 'motivation_reward', 0)),
            },
            'counts': {
                'clients': Client.objects.filter(
                    Q(manager=user) | Q(shared_with=user)
                ).distinct().count(),
                'deals': Deal.objects.filter(manager=user).count(),
                'pending_payments': Payment.objects.filter(
                    manager=user,
                    is_confirmed=False
                ).count(),
                'tasks': Task.objects.filter(
                    assigned_to=user
                ).exclude(status='done').count(),
            },
            'recent': {
                'clients': list(
                    Client.objects.filter(
                        Q(manager=user) | Q(shared_with=user)
                    ).distinct().order_by('-updated_at')
                    .values('id', 'full_name', 'phone', 'status', 'city')[:5]
                ),
                'deals': list(
                    Deal.objects.filter(manager=user).order_by('-updated_at')
                    .values('id', 'client__full_name', 'deal_type', 'payment_status', 'total_to_pay_usd')[:5]
                ),
                'tasks': list(
                    Task.objects.filter(assigned_to=user).exclude(status='done')
                    .order_by('deadline', '-updated_at')
                    .values('id', 'title', 'status', 'priority', 'deadline')[:5]
                ),
                'leads': list(
                    Lead.objects.filter(
                        Q(manager=user) | Q(manager__isnull=True, status='new')
                    )
                    .order_by('-created_at')
                    .values('id', 'full_name', 'phone', 'status', 'created_at')[:5]
                ),
            }
        }
        return Response(payload)