from django import forms
from django.contrib import messages
from django.shortcuts import redirect
from django.views.generic import TemplateView
from .content_views import ContentAdminMixin, news_request
from .forms import PortalFormMixin


class PollForm(PortalFormMixin, forms.Form):
    question = forms.CharField(label='Вопрос', max_length=255)
    options = forms.CharField(label='Варианты — каждый с новой строки (2–10)', max_length=2560, widget=forms.Textarea(attrs={'rows': 5}))
    status = forms.ChoiceField(label='Статус', choices=[('draft', 'Черновик'), ('published', 'Опубликовать'), ('closed', 'Закрыть')])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()

    def clean_options(self):
        options = [line.strip() for line in self.cleaned_data['options'].splitlines() if line.strip()]
        if not 2 <= len(options) <= 10 or any(len(item) > 255 for item in options):
            raise forms.ValidationError('Нужно от 2 до 10 вариантов, до 255 символов каждый.')
        if len({item.casefold() for item in options}) != len(options):
            raise forms.ValidationError('Варианты не должны повторяться.')
        return options


def poll_request(path='', method='GET', data=None):
    return news_request(path, method, resource='news/polls/manage/', json_data=data)


class ClientPollsView(ContentAdminMixin, TemplateView):
    template_name = 'portal/client_polls.html'
    active_page = 'client_content'
    page_title = 'Опросы клиентов'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault('form', PollForm(initial={'status': 'draft'}))
        try:
            page = max(1, int(self.request.GET.get('page', '1')))
            payload = poll_request(f'?page={page}')
            items = payload.get('results', [])
            for item in items:
                item['results'] = list(zip(item['options'], item['counts']))
                item['total'] = sum(item['counts'])
            context.update(items=items, previous_page=page - 1 if payload.get('previous') else None,
                           next_page=page + 1 if payload.get('next') else None)
        except ValueError:
            messages.error(self.request, 'Не удалось загрузить опросы. Попробуйте обновить страницу.')
        return context

    def post(self, request, **kwargs):
        form = PollForm(request.POST)
        try:
            if request.POST.get('poll_id'):
                poll_id = int(request.POST['poll_id'])
                status = request.POST.get('status')
                if status not in ('draft', 'published', 'closed'):
                    raise ValueError('Неверный статус.')
                poll_request(f'{poll_id}/', 'PATCH', {'status': status})
            elif form.is_valid():
                poll_request(method='POST', data=form.cleaned_data)
            else:
                return self.render_to_response(self.get_context_data(form=form))
            messages.success(request, 'Опрос сохранён.')
            return redirect('portal:client_polls')
        except ValueError:
            form.add_error(None, 'Сохранение не подтверждено. Обновите список перед повторной отправкой.')
            return self.render_to_response(self.get_context_data(form=form))
