from datetime import timedelta
from django import forms
from django.conf import settings
from django.db import transaction
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch
from django.shortcuts import redirect, get_object_or_404
from django.utils import timezone
from django.views.generic import TemplateView
from apps.core.permissions import is_attendance_admin, get_employee_profile
from apps.employees.models import EmployeeProfile
from apps.attendance.models import WorkDay, DailyReport, EmployeeTelegramAccount, AttendanceTelegramDelivery
from apps.attendance.services import should_track_employee
from apps.crm.models import ActivityLog
from .models import StaffSuggestion, PortalPresence, EmployeeMood, MoodSupport
from .views import PortalContextMixin


def active_manager(user):
    profile = get_employee_profile(user)
    return bool(user.is_authenticated and user.is_active and (is_attendance_admin(user) or
        (profile and profile.is_active and profile.work_status == 'working' and
         (not profile.role_id or profile.role.role_type not in {'viewer'}))))


def daily_context(user):
    today = timezone.localdate()
    phrases = ('Удачного дня 😁', 'У тебя всё получится!', 'Спасибо, что помогаешь студентам идти к цели.',
               'Шаг за шагом — и сложное становится проще.', 'Пусть сегодня будет больше хороших новостей!')
    context = {'daily_encouragement': phrases[(today.toordinal() + user.pk) % len(phrases)],
               'team_admin': is_attendance_admin(user)}
    context['support_moods'] = mood_support_context(user)
    if active_manager(user) and not is_attendance_admin(user):
        _, created = StaffSuggestion.objects.get_or_create(user=user, date=today)
        context['ask_suggestion'] = created
    return context


def support_queryset(user):
    qs = EmployeeMood.objects.filter(score__lte=2, date__gte=timezone.localdate() - timedelta(days=6), user__is_active=True)
    if not active_manager(user):
        return qs.none()
    if not is_attendance_admin(user):
        qs = qs.filter(user__employee_profile__company_id=get_employee_profile(user).company_id)
    return qs


def mood_support_context(user):
    moods = support_queryset(user).select_related('user').prefetch_related(
        Prefetch('support', queryset=MoodSupport.objects.select_related('user').order_by('updated_at'))).order_by('-updated_at')[:20]
    rows = []
    for mood in moods:
        reactions = list(mood.support.all())
        own = next((r for r in reactions if r.user_id == user.pk), None)
        rows.append({'mood': mood, 'likes': sum(r.liked for r in reactions),
                     'liked': bool(own and own.liked), 'own_comment': own.comment if own else '',
                     'comments': [r for r in reactions if r.comment]})
    return rows


def queue_support_notice(reaction, action):
    recipient = reaction.mood.user
    if recipient.pk == reaction.user_id or not settings.ATTENDANCE_TELEGRAM_ENABLED:
        return
    account = EmployeeTelegramAccount.objects.filter(employee=recipient, is_active=True).first()
    profile = get_employee_profile(recipient)
    if not account or not profile:
        return  # Never fall back to the group for a personal message.
    name = reaction.user.get_full_name() or reaction.user.email
    message = f'Вас поддержал(а) {name} 💛'
    if action == 'comment':
        message += f'\n\nКомментарий: {reaction.comment}'
    message += '\n\nhttps://manager-sl.ru/portal/'
    delivery, created = AttendanceTelegramDelivery.objects.get_or_create(
        event_key=f'mood-support:{reaction.pk}:{action}',
        defaults={'event_type': AttendanceTelegramDelivery.EVENT_MOOD_SUPPORT,
                  'company': profile.company, 'office': profile.office, 'employee': recipient,
                  'target_chat_id': account.chat_id, 'message': message})
    if created:
        from apps.attendance.telegram import _enqueue
        _enqueue(delivery)


class MoodSupportView(PortalContextMixin, TemplateView):
    http_method_names = ['post', 'options']

    @transaction.atomic
    def post(self, request, pk):
        mood = get_object_or_404(support_queryset(request.user), pk=pk)
        action = request.POST.get('action')
        if action == 'like' and request.POST.get('liked') in ('0', '1'):
            changes = {'liked': request.POST['liked'] == '1'}
        elif action == 'comment' and len(request.POST.get('comment', '').strip()) <= 500:
            changes = {'comment': request.POST.get('comment', '').strip()}
        else:
            messages.error(request, 'Комментарий — до 500 символов. Попробуйте ещё раз.')
            return redirect('portal:dashboard')
        reaction, _ = MoodSupport.objects.update_or_create(mood=mood, user=request.user, defaults=changes)
        if changes.get('liked') or changes.get('comment'):
            queue_support_notice(reaction, action)
        messages.success(request, 'Сохранено.')
        return redirect('portal:dashboard')


class SuggestionForm(forms.Form):
    text = forms.CharField(max_length=1000, min_length=3, widget=forms.Textarea, label='Ваше пожелание')


class SuggestionView(PortalContextMixin, TemplateView):
    template_name = 'portal/suggestion.html'
    page_title = 'Пожелание по сайту'

    def post(self, request):
        if not active_manager(request.user):
            raise PermissionDenied
        form = SuggestionForm(request.POST)
        if form.is_valid():
            row, _ = StaffSuggestion.objects.get_or_create(user=request.user, date=timezone.localdate())
            if row.text:
                messages.info(request, 'Сегодня пожелание уже отправлено. Спасибо!')
            else:
                # Atomic conditional update also prevents double form submission.
                StaffSuggestion.objects.filter(pk=row.pk, text='').update(text=form.cleaned_data['text'], submitted_at=timezone.now())
                messages.success(request, 'Спасибо! Администратор увидит ваше пожелание.')
            return redirect('portal:dashboard')
        return self.render_to_response(self.get_context_data(form=form), status=400)

    def get_context_data(self, **kwargs):
        return super().get_context_data(form=kwargs.pop('form', SuggestionForm()), **kwargs)


class AdminOnlyMixin(PortalContextMixin):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not is_attendance_admin(request.user):
            raise PermissionDenied('Эта страница доступна только администратору.')
        return super().dispatch(request, *args, **kwargs)


class SuggestionsAdminView(AdminOnlyMixin, TemplateView):
    template_name = 'portal/staff_suggestions.html'
    page_title = 'Пожелания сотрудников'
    active_page = 'staff_suggestions'

    def get_context_data(self, **kwargs):
        entries = StaffSuggestion.objects.exclude(text='').select_related('user').order_by('-submitted_at')
        return super().get_context_data(entries=Paginator(entries, 30).get_page(self.request.GET.get('page')), **kwargs)


class StaffMetricsView(AdminOnlyMixin, TemplateView):
    template_name = 'portal/staff_metrics.html'
    page_title = 'Показатели сотрудников'
    active_page = 'staff_metrics'

    def get_context_data(self, **kwargs):
        today = timezone.localdate()
        start = today - timedelta(days=27)
        people = EmployeeProfile.objects.filter(is_active=True, user__is_active=True).select_related('user', 'office').order_by('user__last_name', 'user__email')
        page = Paginator(people, 50).get_page(self.request.GET.get('page'))
        ids = [person.user_id for person in page]
        counts = dict(WorkDay.objects.filter(employee_id__in=ids, date__range=(start, today), started_at__isnull=False).values('employee_id').annotate(total=Count('date', distinct=True)).values_list('employee_id', 'total'))
        reports = dict(DailyReport.objects.filter(employee_id__in=ids, date__range=(start, today), submitted_at__isnull=False).values('employee_id').annotate(total=Count('date', distinct=True)).values_list('employee_id', 'total'))
        linked = set(EmployeeTelegramAccount.objects.filter(employee_id__in=ids, is_active=True).values_list('employee_id', flat=True))
        presence = {row.user_id: row for row in PortalPresence.objects.filter(user_id__in=ids)}
        rows = [{'person': person, 'presence': presence.get(person.user_id), 'days': counts.get(person.user_id, 0),
                 'reports': reports.get(person.user_id, 0), 'telegram': person.user_id in linked,
                 'admin': not should_track_employee(person.user)} for person in page]
        # Show only event names and dates, not secrets or client payloads.
        events = ActivityLog.objects.filter(actor_id__in=ids).select_related('actor').order_by('-created_at')[:30]
        return super().get_context_data(rows=rows, page=page, events=events, start=start, end=today, **kwargs)
