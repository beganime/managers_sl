from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from users.disk_auth import can_access_disk
from apps.crm.external_accounts import ExternalAccountError
from apps.crm.mailboxes import bind_mailbox


class ClientMailboxBindView(LoginRequiredMixin, View):
    login_url = reverse_lazy('portal:login')

    def post(self, request, pk):
        from .views import client_queryset
        student = get_object_or_404(client_queryset(request.user), pk=pk)
        if not can_access_disk(request.user):
            raise PermissionDenied('Нет доступа к почте и документам клиентов.')
        try:
            account, count = bind_mailbox(student=student, email=request.POST.get('email'), actor=request.user)
        except (ValidationError, ExternalAccountError) as exc:
            messages.error(request, 'Не удалось привязать почту: ' + '; '.join(getattr(exc, 'messages', [str(exc)])))
        else:
            messages.success(request, f'Почта {account.email} привязана. Найдено писем в реестре: {count}. Если ящик ещё не подключён, добавьте его в SMTPSL.')
        return redirect('portal:client_detail', pk=student.pk)
