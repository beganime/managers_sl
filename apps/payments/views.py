from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Sum
from django.shortcuts import redirect
from django.utils import timezone
from django.views.generic import FormView, TemplateView

from apps.core.permissions import get_employee_profile, is_attendance_admin
from apps.attendance.models import EmployeeTelegramAccount
from apps.portal.views import PortalContextMixin, client_queryset

from .forms import PaymentForm
from .models import Payment, PaymentRecipient
from .tasks import queue_payment_admins_notification


class PaymentCreateView(PortalContextMixin, LoginRequiredMixin, FormView):
    template_name = 'portal/payments.html'
    form_class = PaymentForm
    page_title = 'Оплаты'
    active_page = 'payments'

    def dispatch(self, request, *args, **kwargs):
        if get_employee_profile(request.user) is None:
            if is_attendance_admin(request.user):
                return redirect('portal:payments_admin')
            raise PermissionDenied('Оплаты доступны сотрудникам с профилем.')
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        form = PaymentForm()
        form.fields['client'].queryset = client_queryset(self.request.user).order_by('full_name')
        kwargs['prefix'] = 'payment'
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['my_payments'] = (
            Payment.objects
            .select_related('client')
            .filter(manager=self.request.user)[:30]
        )
        context['totals'] = (
            Payment.objects
            .filter(manager=self.request.user, status=Payment.STATUS_CONFIRMED)
            .aggregate(total=Sum('amount'))['total']
        )
        return context

    def form_valid(self, form):
        payment = form.save(commit=False)
        payment.manager = self.request.user
        payment.save()
        queue_payment_admins_notification(payment)
        messages.success(self.request, 'Оплата отправлена на проверку администратору.')
        return redirect('portal:payments')


class PaymentAdminView(PortalContextMixin, LoginRequiredMixin, TemplateView):
    template_name = 'portal/payments_admin.html'
    page_title = 'Проверка оплат'
    active_page = 'payments_admin'

    def dispatch(self, request, *args, **kwargs):
        if not is_attendance_admin(request.user):
            raise PermissionDenied('Эта страница доступна только администратору.')
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        action = request.POST.get('action')
        try:
            payment_id = int(request.POST.get('payment_id') or 0)
        except ValueError:
            payment_id = 0
        if action == 'recipients':
            selected = {int(v) for v in request.POST.getlist('recipient') if str(v).isdigit()}
            current = set(PaymentRecipient.objects.values_list('user_id', flat=True))
            PaymentRecipient.objects.filter(user_id__in=current - selected).delete()
            for user_id in selected - current:
                PaymentRecipient.objects.create(user_id=user_id)
            messages.success(request, 'Получатели уведомлений обновлены.')
            return redirect('portal:payments_admin')
        payment = Payment.objects.filter(pk=payment_id).first()
        if payment is None:
            messages.error(request, 'Оплата не найдена.')
        elif action in {'confirm', 'reject'} and payment.status == Payment.STATUS_PENDING:
            payment.status = Payment.STATUS_CONFIRMED if action == 'confirm' else Payment.STATUS_REJECTED
            payment.reviewed_by = request.user
            payment.reviewed_at = timezone.now()
            payment.review_note = request.POST.get('note', '')[:500]
            payment.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_note', 'updated_at'])
            messages.success(request, f'Оплата {payment.manager.get_full_name() or payment.manager.email} — {payment.get_status_display().lower()}.')
        return redirect('portal:payments_admin')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['pending'] = (
            Payment.objects
            .select_related('manager', 'client', 'reviewed_by')
            .filter(status=Payment.STATUS_PENDING)
        )
        context['recent'] = (
            Payment.objects
            .select_related('manager', 'client', 'reviewed_by')
            .exclude(status=Payment.STATUS_PENDING)[:30]
        )
        month_start = timezone.localdate().replace(day=1)
        totals = (
            Payment.objects
            .filter(status=Payment.STATUS_CONFIRMED)
            .values('manager__email', 'manager__first_name', 'manager__last_name')
            .annotate(total=Sum('amount'), month_total=Sum('amount', filter=Q(created_at__date__gte=month_start)))
            .order_by('-total')
        )
        context['totals'] = totals
        context['month_start'] = month_start
        context['candidate_recipients'] = (
            EmployeeTelegramAccount.objects
            .select_related('employee')
            .filter(is_active=True, employee__is_active=True)
        )
        context['selected_recipients'] = set(PaymentRecipient.objects.values_list('user_id', flat=True))
        return context
