from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.db import transaction
from apps.crm.models import ClientQuestionnaire, ActivityLog
from django.http import JsonResponse
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db.models import Avg, Count
from datetime import timedelta
from .models import EmployeeMood


def save_mood(user, score, slot):
    if score not in range(1, 6) or slot not in range(1, 4):
        raise ValueError('Выберите настроение и одну из трёх отметок.')
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=user.pk)
        entry, _ = EmployeeMood.objects.update_or_create(
            user=user, date=timezone.localdate(), slot=slot, defaults={'score': score},
        )
        return entry


class MoodView(LoginRequiredMixin, View):
    login_url = reverse_lazy('portal:login')

    def get(self, request):
        from apps.core.permissions import is_erp_admin
        today = timezone.localdate()
        data = {'entries': list(EmployeeMood.objects.filter(user=request.user, date=today).values('slot', 'score'))}
        if is_erp_admin(request.user):
            week = today - timedelta(days=today.weekday())
            data['week'] = list(EmployeeMood.objects.filter(date__gte=week, date__lte=today)
                .values('user__first_name', 'user__last_name', 'user__email')
                .annotate(average=Avg('score'), count=Count('id')).order_by('user__last_name', 'user__email'))
        return JsonResponse(data)

    def post(self, request):
        from apps.core.permissions import is_erp_admin
        if is_erp_admin(request.user):
            return JsonResponse({'error': 'Администратор видит итоги команды, но не отмечает своё настроение.'}, status=403)
        try:
            save_mood(request.user, int(request.POST.get('score', '')), int(request.POST.get('slot', '')))
        except (ValueError, TypeError) as exc:
            return JsonResponse({'error': str(exc)}, status=400)
        return self.get(request)


class ClientChatView(LoginRequiredMixin, View):
    login_url = reverse_lazy('portal:login')

    def get_client(self, request, pk):
        from .views import client_queryset
        return get_object_or_404(client_queryset(request.user), pk=pk)

    def get(self, request, pk):
        from .views import AkylChatClient, AkylChatError
        client = self.get_client(request, pk)
        if not client.sl_id:
            return JsonResponse({'error': 'У клиента ещё нет аккаунта приложения.'}, status=409)
        try:
            bridge = AkylChatClient()
            data = bridge.messages(client.sl_id)
            bridge.mark_read(client.sl_id)
            return JsonResponse({'messages': data.get('results', [])})
        except AkylChatError:
            return JsonResponse({'error': 'Чат временно недоступен. Повторите загрузку.'}, status=502)

    def post(self, request, pk):
        from .views import AkylChatClient, AkylChatError, full_name, post_service, settings
        client = self.get_client(request, pk)
        text = str(request.POST.get('text') or '').strip()
        upload = request.FILES.get('file')
        if not client.sl_id:
            return JsonResponse({'error': 'У клиента ещё нет аккаунта приложения.'}, status=409)
        if len(text) > 1000 or (not text and not upload):
            return JsonResponse({'error': 'Введите сообщение до 1000 символов или приложите файл.'}, status=400)
        if upload and upload.size > 50 * 1024 * 1024:
            return JsonResponse({'error': 'Максимальный размер файла — 50 МБ.'}, status=400)
        try:
            AkylChatClient().send_message(client.sl_id, text=text, upload=upload, manager_name=full_name(request.user))
        except AkylChatError:
            return JsonResponse({'error': 'Не удалось подтвердить отправку. Обновите чат перед повтором.'}, status=502)
        push_sent = True
        try:
            post_service(settings.STUDENTS_LIFE_PROVISION_API_URL.replace('/provision/', '/notify/'),
                settings.STUDENTS_LIFE_PROVISION_TOKEN,
                {'sl_id': client.sl_id, 'title': f'Менеджер {full_name(request.user)} ответил в чате',
                 'body': text or 'Менеджер отправил файл.', 'notification_type': 'chat_message'})
        except Exception:
            push_sent = False
        return JsonResponse({'sent': True, 'push_sent': push_sent})


def ensure_client_questionnaire(client, actor):
    with transaction.atomic():
        questionnaire, created = ClientQuestionnaire.objects.get_or_create(client=client, defaults={
            'source': 'manager_portal', 'full_name': client.full_name, 'phone': client.phone,
            'email': client.email, 'citizenship': client.citizenship,
            'data': {'full_name': client.full_name, 'phone': client.phone, 'email': client.email},
        })
        if created:
            ActivityLog.objects.create(actor=actor, student=client, service='manager_portal',
                object_type='crm.ClientQuestionnaire', object_id=str(questionnaire.pk), action='QUESTIONNAIRE_DRAFT_CREATED')
        return questionnaire


class ClientQuestionnaireStartView(LoginRequiredMixin, View):
    login_url = reverse_lazy('portal:login')

    @transaction.atomic
    def post(self, request, pk):
        from .views import client_queryset
        client = get_object_or_404(client_queryset(request.user), pk=pk)
        questionnaire = ensure_client_questionnaire(client, request.user)
        return redirect('portal:client_questionnaire_edit', pk=questionnaire.pk)
