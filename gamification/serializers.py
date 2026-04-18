from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import serializers

from analytics.finance_models import OfficeFinanceEntry
from analytics.models import Deal, Expense, Payment
from clients.models import Client
from leads.models import Lead
from timetracking.models import WorkShift

from .models import Leaderboard, Notification, TutorialVideo
from .push_models import DeviceToken, PushBroadcast


def _decimal(value):
    if value is None:
        return Decimal('0')
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal('0')


def _money(value):
    return float(_decimal(value).quantize(Decimal('0.01')))


def _percent_score(value, max_value, max_score):
    value = _decimal(value)
    max_value = _decimal(max_value)
    max_score = _decimal(max_score)

    if max_value <= 0:
        return Decimal('0')

    score = (value / max_value) * max_score
    if score > max_score:
        score = max_score

    if score < 0:
        score = Decimal('0')

    return score.quantize(Decimal('0.01'))


def _count_score(count, points_per_item, max_score):
    score = _decimal(count) * _decimal(points_per_item)
    max_score = _decimal(max_score)

    if score > max_score:
        score = max_score

    if score < 0:
        score = Decimal('0')

    return score.quantize(Decimal('0.01'))


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = (
            'recipient',
            'title',
            'body',
            'created_at',
            'updated_at',
            'fcm_message_id',
        )


class DeviceTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceToken
        fields = (
            'id',
            'token',
            'platform',
            'device_name',
            'is_active',
            'last_seen_at',
            'created_at',
        )
        read_only_fields = ('last_seen_at', 'created_at')


class PushBroadcastSerializer(serializers.ModelSerializer):
    class Meta:
        model = PushBroadcast
        fields = (
            'id',
            'title',
            'body',
            'target_all',
            'sent_count',
            'failed_count',
            'created_at',
            'sent_at',
        )
        read_only_fields = ('sent_count', 'failed_count', 'created_at', 'sent_at')


class TutorialVideoSerializer(serializers.ModelSerializer):
    class Meta:
        model = TutorialVideo
        fields = (
            'id',
            'title',
            'description',
            'video_file',
            'youtube_url',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('created_at', 'updated_at')

    def validate(self, attrs):
        video_file = attrs.get('video_file')
        youtube_url = attrs.get('youtube_url')

        instance = getattr(self, 'instance', None)
        if instance:
            if video_file is None:
                video_file = instance.video_file
            if youtube_url is None:
                youtube_url = instance.youtube_url

        if not video_file and not youtube_url:
            raise serializers.ValidationError(
                'Нужно указать либо файл видео, либо ссылку YouTube.'
            )

        return attrs


class LeaderboardSerializer(serializers.ModelSerializer):
    rank = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    email = serializers.EmailField(read_only=True)
    phone = serializers.SerializerMethodField()
    office_name = serializers.SerializerMethodField()
    office = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()
    revenue = serializers.SerializerMethodField()
    expense = serializers.SerializerMethodField()
    net_profit = serializers.SerializerMethodField()
    total_score = serializers.SerializerMethodField()
    kpi = serializers.SerializerMethodField()
    details = serializers.SerializerMethodField()
    access_profile = serializers.SerializerMethodField()

    class Meta:
        model = Leaderboard
        fields = (
            'id',
            'rank',
            'first_name',
            'last_name',
            'middle_name',
            'full_name',
            'email',
            'phone',
            'avatar_url',
            'office_name',
            'office',
            'work_status',
            'is_effective',
            'revenue',
            'expense',
            'net_profit',
            'total_score',
            'kpi',
            'details',
            'access_profile',
        )

    def _period(self):
        date_from = self.context.get('kpi_date_from')
        date_to = self.context.get('kpi_date_to')

        today = timezone.localdate()

        if not date_to:
            date_to = today

        if not date_from:
            date_from = date_to.replace(day=1)

        return date_from, date_to

    def _cache(self):
        if not hasattr(self, '_kpi_cache'):
            self._kpi_cache = {}
        return self._kpi_cache

    def _build_metrics(self, obj):
        cache = self._cache()
        if obj.id in cache:
            return cache[obj.id]

        date_from, date_to = self._period()

        shifts_qs = WorkShift.objects.filter(
            employee=obj,
            date__gte=date_from,
            date__lte=date_to,
        ).order_by('-date', '-time_in', '-id')

        present_days_count = shifts_qs.values('date').distinct().count()
        shifts_count = shifts_qs.count()
        closed_workdays_count = shifts_qs.filter(
            time_out__isnull=False,
            is_auto_closed=False,
        ).count()
        forgot_to_close_count = shifts_qs.filter(
            Q(time_out__isnull=True) | Q(is_auto_closed=True)
        ).count()

        total_hours = shifts_qs.aggregate(total=Sum('hours_worked'))['total'] or Decimal('0')

        attendance_days = []
        for shift in shifts_qs[:31]:
            time_in = None
            time_out = None

            if shift.time_in:
                local_in = timezone.localtime(shift.time_in)
                time_in = local_in.strftime('%H:%M')

            if shift.time_out:
                local_out = timezone.localtime(shift.time_out)
                time_out = local_out.strftime('%H:%M')

            attendance_days.append(
                {
                    'id': shift.id,
                    'date': shift.date.isoformat() if shift.date else None,
                    'time_in': time_in,
                    'time_out': time_out,
                    'hours_worked': _money(shift.hours_worked),
                    'is_closed': bool(shift.time_out and not shift.is_auto_closed),
                    'is_auto_closed': bool(shift.is_auto_closed),
                    'is_active': bool(shift.is_active),
                }
            )

        clients_total_count = Client.objects.filter(manager=obj).count()
        clients_period_count = Client.objects.filter(
            manager=obj,
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
        ).count()

        leads_count = Lead.objects.filter(
            manager=obj,
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
        ).count()

        deals_count = Deal.objects.filter(
            manager=obj,
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
        ).count()

        confirmed_payments = Payment.objects.filter(
            manager=obj,
            is_confirmed=True,
            payment_date__gte=date_from,
            payment_date__lte=date_to,
        )

        payment_amount_usd = confirmed_payments.aggregate(
            total=Sum('amount_usd')
        )['total'] or Decimal('0')

        payment_net_income_usd = confirmed_payments.aggregate(
            total=Sum('net_income_usd')
        )['total'] or Decimal('0')

        old_expenses_usd = Expense.objects.filter(
            manager=obj,
            date__gte=date_from,
            date__lte=date_to,
        ).aggregate(total=Sum('amount_usd'))['total'] or Decimal('0')

        office_income_usd = OfficeFinanceEntry.objects.filter(
            created_by=obj,
            entry_type='income',
            is_confirmed=True,
            entry_date__gte=date_from,
            entry_date__lte=date_to,
        ).aggregate(total=Sum('amount_usd'))['total'] or Decimal('0')

        office_expense_usd = OfficeFinanceEntry.objects.filter(
            created_by=obj,
            entry_type='expense',
            is_confirmed=True,
            entry_date__gte=date_from,
            entry_date__lte=date_to,
        ).aggregate(total=Sum('amount_usd'))['total'] or Decimal('0')

        income_usd = _decimal(payment_net_income_usd) + _decimal(office_income_usd)
        expense_usd = _decimal(old_expenses_usd) + _decimal(office_expense_usd)
        net_profit_usd = income_usd - expense_usd

        salary = getattr(obj, 'managersalary', None)
        monthly_plan = _decimal(getattr(salary, 'monthly_plan', 0) if salary else 0)
        current_month_revenue = _decimal(
            getattr(salary, 'current_month_revenue', 0) if salary else 0
        )

        plan_base = monthly_plan if monthly_plan > 0 else Decimal('5000')
        income_for_score = income_usd if income_usd > 0 else current_month_revenue

        revenue_score = _percent_score(income_for_score, plan_base, 35)
        clients_score = _count_score(clients_total_count, 2, 15)
        leads_score = _count_score(leads_count, 2, 15)
        deals_score = _count_score(deals_count, 4, 15)
        attendance_score = _count_score(present_days_count, 1.5, 10)
        workday_close_score = _count_score(closed_workdays_count, 1.5, 10)
        forgot_penalty = _count_score(forgot_to_close_count, 3, 15)

        total_score = (
            revenue_score
            + clients_score
            + leads_score
            + deals_score
            + attendance_score
            + workday_close_score
            - forgot_penalty
        )

        if total_score < 0:
            total_score = Decimal('0')

        total_score = total_score.quantize(Decimal('0.01'))

        qualities = [
            {
                'key': 'revenue',
                'label': 'Доход / выполнение плана',
                'score': _money(revenue_score),
                'max_score': 35,
                'value': _money(income_for_score),
                'hint': f'Доход за период. План: ${_money(plan_base)}',
            },
            {
                'key': 'clients',
                'label': 'Клиенты',
                'score': _money(clients_score),
                'max_score': 15,
                'value': clients_total_count,
                'hint': 'Общее количество клиентов у сотрудника',
            },
            {
                'key': 'leads',
                'label': 'Заявки',
                'score': _money(leads_score),
                'max_score': 15,
                'value': leads_count,
                'hint': 'Заявки, закреплённые за сотрудником за период',
            },
            {
                'key': 'deals',
                'label': 'Оформленные сделки',
                'score': _money(deals_score),
                'max_score': 15,
                'value': deals_count,
                'hint': 'Сделки, оформленные сотрудником за период',
            },
            {
                'key': 'attendance',
                'label': 'Приходы в офис',
                'score': _money(attendance_score),
                'max_score': 10,
                'value': present_days_count,
                'hint': 'Количество дней, когда сотрудник начинал рабочий день',
            },
            {
                'key': 'workday_close',
                'label': 'Закрытие рабочего дня',
                'score': _money(workday_close_score),
                'max_score': 10,
                'value': closed_workdays_count,
                'hint': 'Сколько раз сотрудник не забывал закрыть рабочий день',
            },
            {
                'key': 'forgot_close_penalty',
                'label': 'Штраф за незакрытый день',
                'score': -_money(forgot_penalty),
                'max_score': 0,
                'value': forgot_to_close_count,
                'hint': 'Сколько раз рабочий день не был закрыт или был закрыт автоматически',
            },
        ]

        metrics = {
            'period': {
                'date_from': date_from.isoformat() if date_from else None,
                'date_to': date_to.isoformat() if date_to else None,
            },
            'total_score': _money(total_score),
            'income_usd': _money(income_usd),
            'expense_usd': _money(expense_usd),
            'net_profit_usd': _money(net_profit_usd),
            'payment_amount_usd': _money(payment_amount_usd),
            'payment_net_income_usd': _money(payment_net_income_usd),
            'office_income_usd': _money(office_income_usd),
            'office_expense_usd': _money(office_expense_usd),
            'old_expenses_usd': _money(old_expenses_usd),
            'current_month_revenue': _money(current_month_revenue),
            'monthly_plan': _money(monthly_plan),
            'clients_total_count': clients_total_count,
            'clients_period_count': clients_period_count,
            'leads_count': leads_count,
            'deals_count': deals_count,
            'present_days_count': present_days_count,
            'shifts_count': shifts_count,
            'closed_workdays_count': closed_workdays_count,
            'forgot_to_close_count': forgot_to_close_count,
            'total_hours': _money(total_hours),
            'attendance_days': attendance_days,
            'qualities': qualities,
        }

        cache[obj.id] = metrics
        return metrics

    def get_rank(self, obj):
        return self.context.get('rank_map', {}).get(obj.id)

    def get_full_name(self, obj):
        full = f'{obj.first_name} {obj.last_name}'.strip()
        return full or obj.email or f'Сотрудник #{obj.id}'

    def get_phone(self, obj):
        contacts = str(getattr(obj, 'social_contacts', '') or '').strip()
        if contacts:
            return contacts

        office = getattr(obj, 'office', None)
        office_phone = str(getattr(office, 'phone', '') or '').strip()
        if office_phone:
            return office_phone

        return ''

    def get_revenue(self, obj):
        return self._build_metrics(obj)['income_usd']

    def get_expense(self, obj):
        return self._build_metrics(obj)['expense_usd']

    def get_net_profit(self, obj):
        return self._build_metrics(obj)['net_profit_usd']

    def get_total_score(self, obj):
        return self._build_metrics(obj)['total_score']

    def get_kpi(self, obj):
        metrics = self._build_metrics(obj)

        return {
            'period': metrics['period'],
            'total_score': metrics['total_score'],
            'income_usd': metrics['income_usd'],
            'expense_usd': metrics['expense_usd'],
            'net_profit_usd': metrics['net_profit_usd'],
            'qualities': metrics['qualities'],
            'counts': {
                'clients_total': metrics['clients_total_count'],
                'clients_period': metrics['clients_period_count'],
                'leads': metrics['leads_count'],
                'deals': metrics['deals_count'],
                'present_days': metrics['present_days_count'],
                'closed_workdays': metrics['closed_workdays_count'],
                'forgot_to_close': metrics['forgot_to_close_count'],
                'shifts': metrics['shifts_count'],
                'hours': metrics['total_hours'],
            },
        }

    def get_details(self, obj):
        metrics = self._build_metrics(obj)

        return {
            'period': metrics['period'],
            'income_usd': metrics['income_usd'],
            'expense_usd': metrics['expense_usd'],
            'net_profit_usd': metrics['net_profit_usd'],
            'payment_amount_usd': metrics['payment_amount_usd'],
            'payment_net_income_usd': metrics['payment_net_income_usd'],
            'office_income_usd': metrics['office_income_usd'],
            'office_expense_usd': metrics['office_expense_usd'],
            'old_expenses_usd': metrics['old_expenses_usd'],
            'current_month_revenue': metrics['current_month_revenue'],
            'monthly_plan': metrics['monthly_plan'],
            'clients_total_count': metrics['clients_total_count'],
            'clients_period_count': metrics['clients_period_count'],
            'leads_count': metrics['leads_count'],
            'deals_count': metrics['deals_count'],
            'present_days_count': metrics['present_days_count'],
            'shifts_count': metrics['shifts_count'],
            'closed_workdays_count': metrics['closed_workdays_count'],
            'forgot_to_close_count': metrics['forgot_to_close_count'],
            'total_hours': metrics['total_hours'],
            'attendance_days': metrics['attendance_days'],
        }

    def get_office_name(self, obj):
        office = getattr(obj, 'office', None)
        if office:
            return office.city or 'Без офиса'
        return 'Без офиса'

    def get_office(self, obj):
        office = getattr(obj, 'office', None)
        if not office:
            return None

        return {
            'id': office.id,
            'city': office.city or 'Без офиса',
            'address': office.address or '',
            'phone': office.phone or '',
        }

    def get_avatar_url(self, obj):
        try:
            if hasattr(obj, 'avatar') and obj.avatar and hasattr(obj.avatar, 'url'):
                request = self.context.get('request')
                if request is not None:
                    return request.build_absolute_uri(obj.avatar.url)
                return obj.avatar.url
        except Exception:
            pass

        return None

    def get_access_profile(self, obj):
        profile = getattr(obj, 'access_profile', None)

        if not profile:
            return {
                'can_be_in_leaderboard': True,
                'can_view_office_dashboard': False,
                'managed_office': None,
            }

        managed_office = getattr(profile, 'managed_office', None)

        return {
            'can_be_in_leaderboard': bool(profile.can_be_in_leaderboard),
            'can_view_office_dashboard': bool(profile.can_view_office_dashboard),
            'managed_office': (
                {
                    'id': managed_office.id,
                    'city': managed_office.city,
                    'address': managed_office.address,
                    'phone': managed_office.phone,
                }
                if managed_office
                else None
            ),
        }