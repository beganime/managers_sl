# students_life/api_views.py
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
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
from apps.crm.models import Client as CRMClient
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


def _mobile_exam_client(user, client_id):
    queryset = CRMClient.objects.select_related('manager', 'company', 'office')
    if not is_admin_user(user):
        queryset = queryset.filter(Q(manager=user) | Q(shared_with=user))
    return queryset.distinct().filter(pk=client_id).first()


class ClientExamAPIView(APIView):
    """Authenticated ManagerSL proxy for a client's Student Life exams."""

    permission_classes = [IsAuthenticated]

    def get_client(self, request, client_id):
        client = _mobile_exam_client(request.user, client_id)
        if client:
            return client, None
        return None, Response(
            {'detail': 'Клиент не найден или недоступен этому менеджеру.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    @staticmethod
    def mobile_user_id(client):
        if client.mobile_app_user_id:
            return client.mobile_app_user_id
        data = client.custom_data or {}
        return data.get('mobile_user_id') or data.get('external_mobile_user_id') or data.get('user_id')

    @staticmethod
    def client_payload(client):
        return {
            'id': client.id,
            'full_name': client.full_name,
            'phone': client.phone,
            'email': client.email,
            'mobile_app_user_id': ClientExamAPIView.mobile_user_id(client),
        }

    def get(self, request, client_id):
        client, error = self.get_client(request, client_id)
        if error:
            return error
        mobile_user_id = self.mobile_user_id(client)
        if not mobile_user_id:
            return Response(
                {'detail': 'У клиента ещё нет аккаунта в мобильном приложении.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.portal.views import students_life_api_request

        ok, payload = students_life_api_request(
            f'notifications/clients/{mobile_user_id}/exams/',
            payload=None,
            method='GET',
        )
        if not ok:
            return Response(
                {'detail': payload.get('detail') or 'Не удалось получить экзамены клиента.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({
            'client': self.client_payload(client),
            'exams': payload if isinstance(payload, list) else [],
        })

    def post(self, request, client_id):
        client, error = self.get_client(request, client_id)
        if error:
            return error
        mobile_user_id = self.mobile_user_id(client)
        if not mobile_user_id:
            return Response(
                {'detail': 'У клиента ещё нет аккаунта в мобильном приложении.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        subject = str(request.data.get('subject') or '').strip()
        university = str(request.data.get('university') or '').strip()
        exam_date = str(request.data.get('exam_date') or '').strip()
        exam_time = str(request.data.get('exam_time') or '').strip()
        if not subject or not university or not exam_date or not exam_time:
            return Response(
                {'detail': 'Укажите вуз, название экзамена, дату и время.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(subject) > 255 or len(university) > 255:
            return Response(
                {'detail': 'Название вуза и экзамена не должно превышать 255 символов.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        comment = str(request.data.get('comment') or '').strip()
        if len(comment) > 1000:
            return Response(
                {'detail': 'Комментарий не должен превышать 1000 символов.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = {
            'subject': subject,
            'university': university,
            'exam_date': exam_date,
            'exam_time': exam_time,
            'timezone': str(request.data.get('timezone') or 'Asia/Ashgabat').strip(),
            'comment': comment,
            'repeat_until_acknowledged': bool(request.data.get('repeat_until_acknowledged', True)),
        }
        external_id = str(request.data.get('manager_sl_exam_id') or '').strip()
        if external_id:
            payload['manager_sl_exam_id'] = external_id[:100]

        from apps.portal.views import students_life_api_request

        ok, remote_payload = students_life_api_request(
            f'notifications/clients/{mobile_user_id}/exams/',
            payload=payload,
            method='POST',
        )
        if not ok:
            return Response(
                {'detail': remote_payload.get('detail') or 'Не удалось назначить экзамен.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(
            {'client': self.client_payload(client), 'exam': remote_payload},
            status=status.HTTP_201_CREATED,
        )


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
