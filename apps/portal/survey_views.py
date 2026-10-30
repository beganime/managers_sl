from urllib.parse import urlsplit
from django import forms
from django.contrib import messages
from django.shortcuts import redirect
from django.views.generic import TemplateView
from .content_views import ContentAdminMixin, news_request
from .forms import PortalFormMixin


class SurveyForm(PortalFormMixin, forms.Form):
    title = forms.CharField(label='Название анкеты', max_length=255)
    description = forms.CharField(label='Описание', max_length=1000, required=False, widget=forms.Textarea(attrs={'rows': 3}))
    form_url = forms.URLField(label='Ссылка для заполнения Google Forms', max_length=2000)
    status = forms.ChoiceField(label='Показывать в приложении', choices=[('draft', 'Черновик'), ('published', 'Опубликовать'), ('closed', 'Скрыть')])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()

    def clean_form_url(self):
        value = self.cleaned_data['form_url']
        try:
            u = urlsplit(value)
            valid = u.scheme == 'https' and not u.username and not u.password and u.port in (None, 443) and (
                (u.hostname == 'forms.gle' and bool(u.path.strip('/'))) or
                (u.hostname == 'docs.google.com' and u.path.startswith('/forms/d/') and u.path.endswith('/viewform')))
        except ValueError:
            valid = False
        if not valid:
            raise forms.ValidationError('Вставьте ссылку для респондентов forms.gle/... или docs.google.com/forms/d/.../viewform, не ссылку редактора.')
        return value


class ClientFormsView(ContentAdminMixin, TemplateView):
    template_name = 'portal/client_forms.html'
    active_page = 'client_content'
    page_title = 'Анкеты и формы клиентов'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault('form', SurveyForm(initial={'status': 'draft'}))
        try:
            page = max(1, int(self.request.GET.get('page', '1')))
            payload = news_request(f'?page={page}', resource='news/forms/manage/')
            items = payload.get('results', [])
            for item in items:
                item['form'] = SurveyForm(initial=item, auto_id=f'form-{item["id"]}-%s')
            context.update(items=items, previous_page=page-1 if payload.get('previous') else None, next_page=page+1 if payload.get('next') else None)
        except ValueError:
            messages.error(self.request, 'Не удалось загрузить формы. Обновите страницу.')
        return context

    def post(self, request):
        form = SurveyForm(request.POST)
        form_id = request.POST.get('form_id', '')
        if form_id and not form_id.isdigit():
            form.add_error(None, 'Неверный номер формы.')
        if form.is_valid():
            try:
                news_request(f'{form_id}/' if form_id else '', 'PATCH' if form_id else 'POST', resource='news/forms/manage/', json_data=form.cleaned_data)
                messages.success(request, 'Форма сохранена. Опубликованные формы видны в приложении после обновления списка.')
                return redirect('portal:client_polls')
            except ValueError:
                form.add_error(None, 'Сохранение не подтверждено. Обновите список перед повторной отправкой.')
        return self.render_to_response(self.get_context_data(form=form, edit_id=form_id), status=400)
