import hashlib
from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from .forms import PortalFormMixin
from .models import ClientMotivationProfile


class MotivationForm(PortalFormMixin, forms.ModelForm):
    revision = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = ClientMotivationProfile
        fields = ['track', 'talents', 'hobbies', 'achievements', 'motivation', 'goals', 'next_question']
        widgets = {key: forms.Textarea(attrs={'rows': 3, 'maxlength': 1000}) for key in
                   ('talents', 'hobbies', 'achievements', 'motivation', 'goals')}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()
        if not self.is_bound and self.instance.pk:
            self.initial['revision'] = self.instance.updated_at.isoformat()


def profile_context(client, user, form=None):
    from .views import is_erp_admin
    profile = ClientMotivationProfile.objects.filter(client=client).select_related('updated_by').first()
    fields = ('talents', 'hobbies', 'achievements', 'motivation', 'goals')
    answers = [{'label': ClientMotivationProfile._meta.get_field(key).verbose_name,
                'value': getattr(profile, key, '')} for key in fields]
    return {'client': client, 'motivation_profile': profile, 'motivation_answers': answers,
            'motivation_completed': sum(bool(item['value']) for item in answers),
            'motivation_form': form or MotivationForm(instance=profile),
            'can_edit_motivation': is_erp_admin(user) or client.manager_id == user.pk}


class MotivationEditView(LoginRequiredMixin, View):
    login_url = '/portal/login/'

    def get(self, request, pk):
        from .views import client_queryset
        client = get_object_or_404(client_queryset(request.user), pk=pk)
        template = 'portal/partials/client_motivation.html' if request.headers.get('HX-Request') == 'true' else 'portal/motivation_edit.html'
        response = render(request, template, profile_context(client, request.user))
        response['Cache-Control'] = 'private, no-store'
        return response

    @transaction.atomic
    def post(self, request, pk):
        from .views import client_queryset, is_erp_admin
        from apps.crm.models import ActivityLog, Client
        scoped = get_object_or_404(client_queryset(request.user), pk=pk)
        client = Client.objects.select_for_update().get(pk=scoped.pk)
        if not (is_erp_admin(request.user) or client.manager_id == request.user.pk):
            raise PermissionDenied('Изменять анкету может ответственный менеджер или администратор.')
        profile = ClientMotivationProfile.objects.filter(client=client).first()
        form = MotivationForm(request.POST, instance=profile)
        if form.is_valid():
            expected = profile.updated_at.isoformat() if profile else ''
            if form.cleaned_data['revision'] != expected:
                form.add_error(None, 'Анкета уже изменена другим сотрудником. Откройте карточку заново и сверяйте изменения.')
            else:
                item = form.save(commit=False)
                item.client = client
                item.updated_by = request.user
                item.save()
                ActivityLog.objects.create(actor=request.user, student=client, service='manager_portal',
                    object_type='portal.ClientMotivationProfile', object_id=str(item.pk),
                    action='CLIENT_MOTIVATION_UPDATED', metadata={'fields': [key for key in form.changed_data if key != 'revision']})
                messages.success(request, 'Анкета для мотивационного письма сохранена.')
                return redirect(reverse('portal:client_detail', args=[pk]) + '#motivation')
        response = render(request, 'portal/motivation_edit.html', profile_context(client, request.user, form), status=400)
        response['Cache-Control'] = 'private, no-store'
        return response


class ClientTrackSummaryView(LoginRequiredMixin, View):
    login_url = '/portal/login/'

    def get(self, request):
        from .views import client_queryset
        clients = client_queryset(request.user).exclude(status='archive')
        # Resolve visibility before cache lookup: revoked access never reuses an old scope.
        ids = list(clients.order_by('pk').values_list('pk', flat=True).distinct())
        versions = list(ClientMotivationProfile.objects.filter(client_id__in=ids).order_by('client_id').values_list('client_id', 'updated_at'))
        signature = hashlib.sha256(repr((ids, versions)).encode()).hexdigest()
        key = f'client-track-summary:v1:{request.user.pk}:{signature}'
        rows = cache.get(key)
        if rows is None:
            counts = dict(ClientMotivationProfile.objects.filter(client_id__in=ids).exclude(track='')
                          .values('track').annotate(total=Count('pk')).values_list('track', 'total'))
            rows = [{'label': label, 'count': counts.get(code, 0)} for code, label in ClientMotivationProfile.TRACKS]
            rows.append({'label': 'Не уточнено', 'count': max(0, len(ids) - sum(counts.values()))})
            for row in rows:
                row['percent'] = round(100 * row['count'] / len(ids)) if ids else 0
            cache.set(key, rows, 30)
        response = render(request, 'portal/partials/client_tracks.html', {'track_rows': rows, 'track_total': len(ids)})
        response['Cache-Control'] = 'private, no-store'
        return response
