"""Client content workspace; catalog stays in ERP, news in the client backend."""
from urllib.parse import urlencode
import requests
from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.http import Http404
from django.views.generic import TemplateView
from apps.education.models import University, Program
from .forms import PortalFormMixin
from .views import PortalContextMixin, is_erp_admin, students_life_api_url


class ContentAdminMixin(PortalContextMixin):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not is_erp_admin(request.user):
            raise PermissionDenied('Управление приложением доступно только администратору.')
        return super().dispatch(request, *args, **kwargs)


class ClientContentView(PortalContextMixin, TemplateView):
    def dispatch(self, request, *args, **kwargs):
        from .views import can_manage_catalog
        if request.user.is_authenticated and not can_manage_catalog(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
    template_name = 'portal/client_content.html'
    active_page = 'client_content'
    page_title = 'Клиентское приложение'

    def get_context_data(self, **kwargs):
        from .views import university_queryset
        universities = university_queryset(self.request.user)
        return super().get_context_data(content_admin=is_erp_admin(self.request.user), university_count=universities.filter(is_active=True).count(),
            program_count=Program.objects.filter(university__in=universities, is_active=True, is_archived=False, university__is_active=True).count(), **kwargs)


class CatalogRemoveView(ContentAdminMixin, TemplateView):
    template_name = 'portal/content_remove.html'
    active_page = 'client_content'
    page_title = 'Удаление из приложения'

    def get_object(self):
        if self.kwargs['kind'] not in ('university', 'program'):
            raise Http404
        model = University if self.kwargs['kind'] == 'university' else Program
        return get_object_or_404(model, pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        return super().get_context_data(item=self.get_object(), **kwargs)

    def post(self, request, **kwargs):
        item = self.get_object()
        item.is_active = False
        if isinstance(item, Program):
            item.is_archived = True
        item.save()  # Signal invalidates the public catalog cache.
        messages.success(request, 'Запись скрыта в приложении. История заявок сохранена.')
        return redirect('portal:universities' if isinstance(item, University) else 'portal:programs')


class NewsForm(PortalFormMixin, forms.Form):
    title = forms.CharField(label='Заголовок', max_length=255)
    short_description = forms.CharField(label='Краткое описание', max_length=500, required=False)
    content_markdown = forms.CharField(label='Текст новости', max_length=30000, widget=forms.Textarea(attrs={'rows': 12}))
    cover_image = forms.ImageField(label='Обложка (до 5 МБ)', required=False)
    status = forms.ChoiceField(label='Публикация', choices=(('draft', 'Черновик'), ('published', 'Опубликовать'), ('hidden', 'Скрыть')))
    is_important = forms.BooleanField(label='Важная новость', required=False)

    def __init__(self, *args, **kwargs):
        self.has_cover = kwargs.pop('has_cover', False)
        super().__init__(*args, **kwargs)
        self.fields['cover_image'].required = not self.has_cover
        self.fields['cover_image'].help_text = 'Баннер обязателен. При редактировании можно оставить текущий.'
        self.style_fields()

    def clean_cover_image(self):
        image = self.cleaned_data.get('cover_image')
        if image and image.size > 5 * 1024 * 1024:
            raise forms.ValidationError('Максимальный размер — 5 МБ.')
        return image


def news_request(path='', method='GET', data=None, image=None, resource='news/manage/', json_data=None):
    key = getattr(settings, 'STUDENTS_LIFE_API_KEY', '') or getattr(settings, 'LEADS_API_KEY', '')
    url = students_life_api_url(resource + path)
    if not key or not url:
        raise ValueError('Связь с приложением не настроена.')
    files = {'cover_image': (image.name, image, image.content_type)} if image else None
    try:
        response = requests.request(method, url, headers={'X-API-KEY': key}, data=data, json=json_data, files=files, timeout=(5, 15))
        response.raise_for_status()
        return response.json() if response.content else {}
    except (requests.RequestException, ValueError) as exc:
        raise ValueError('Сервис новостей недоступен или отклонил запрос. Изменение не подтверждено; проверьте список перед повтором.') from exc


class ClientNewsView(ContentAdminMixin, TemplateView):
    template_name = 'portal/client_news.html'
    active_page = 'client_news'
    page_title = 'Новости приложения'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            query = urlencode({'search': self.request.GET.get('search', '')[:255], 'page': self.request.GET.get('page', '1')})
            payload = news_request('?' + query)
            page = max(1, int(self.request.GET.get('page', 1)))
            context.update(items=payload.get('results', []), search=self.request.GET.get('search', ''),
                previous_page=page - 1 if payload.get('previous') else None,
                next_page=page + 1 if payload.get('next') else None)
        except ValueError as exc:
            messages.error(self.request, str(exc))
        return context


class NewsEditView(ContentAdminMixin, TemplateView):
    template_name = 'portal/news_edit.html'
    active_page = 'client_news'
    page_title = 'Редактирование новости'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if 'form' not in context:
            initial = {}
            try:
                if self.kwargs.get('pk'):
                    initial = news_request(f"{self.kwargs['pk']}/")
                context['form'] = NewsForm(initial={k: v for k, v in initial.items() if k != 'cover_image'}, has_cover=bool(initial.get('cover_image')))
                context['news'] = initial
            except ValueError as exc:
                messages.error(self.request, str(exc))
                context['load_failed'] = True
        return context

    def post(self, request, **kwargs):
        existing = {}
        try:
            if self.kwargs.get('pk'):
                existing = news_request(f"{self.kwargs['pk']}/")
        except ValueError as exc:
            messages.error(request, str(exc))
            return self.render_to_response(self.get_context_data(load_failed=True, form=None))
        form = NewsForm(request.POST, request.FILES, has_cover=bool(existing.get('cover_image')))
        if form.is_valid():
            data = dict(form.cleaned_data)
            image = data.pop('cover_image', None)
            data['is_important'] = 'true' if data['is_important'] else 'false'
            try:
                pk = self.kwargs.get('pk')
                news_request(f'{pk}/' if pk else '', 'PATCH' if pk else 'POST', data, image)
                messages.success(request, 'Новость сохранена. В приложении видны только опубликованные новости.')
                return redirect('portal:client_news')
            except ValueError as exc:
                form.add_error(None, str(exc))
        return self.render_to_response(self.get_context_data(form=form))


class NewsDeleteView(ContentAdminMixin, TemplateView):
    template_name = 'portal/news_delete.html'
    active_page = 'client_news'
    page_title = 'Удаление новости'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            context['news'] = news_request(f"{self.kwargs['pk']}/")
        except ValueError as exc:
            messages.error(self.request, str(exc))
        return context

    def post(self, request, **kwargs):
        try:
            news_request(f"{self.kwargs['pk']}/", 'DELETE')
            messages.success(request, 'Новость удалена.')
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect('portal:client_news')
