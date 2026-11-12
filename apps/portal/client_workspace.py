import io
import secrets
from datetime import timedelta
from urllib.parse import urlencode
from PIL import Image, ImageOps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ImproperlyConfigured
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from apps.crm.models import Client, ClientFile, ActivityLog
from apps.crm.credentials import encrypt_external_secret, decrypt_external_secret
from apps.client_onboarding.tasks import post_service
from .models import ClientWorkspaceProfile


def scoped_client(request, pk, edit=False):
    from .views import client_queryset, is_erp_admin
    client = get_object_or_404(client_queryset(request.user), pk=pk)
    if edit and not (is_erp_admin(request.user) or client.manager_id == request.user.pk):
        raise PermissionDenied
    return client


def private(response):
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def workspace_context(client, user):
    from .views import is_erp_admin, client_mobile_user_id, can_access_disk, build_client_disk_url
    profile = ClientWorkspaceProfile.objects.filter(client=client).defer('avatar', 'password_encrypted').first()
    disk_url, disk_ready = build_client_disk_url(client)
    if profile and profile.disk_root:
        disk_url = reverse('portal:disk_sl') + '?' + urlencode({'next': '/web/client/files?' + urlencode({'path': '/' + profile.disk_root.strip('/')})})
        disk_ready = True
    documents = ClientFile.objects.filter(client=client, source='students_life_mobile_app').order_by('-created_at')
    return {'client': client, 'workspace_profile': profile,
            'account_ready': bool(client_mobile_user_id(client)),
            'account_pending': bool(profile and profile.account_status == 'pending' and profile.updated_at > timezone.now() - timedelta(minutes=5)),
            'can_manage': is_erp_admin(user) or client.manager_id == user.pk,
            'can_view_files': can_access_disk(user), 'uploaded_documents': documents[:12] if can_access_disk(user) else [],
            'uploaded_count': documents.count() if can_access_disk(user) else 0,
            'client_folder_url': disk_url, 'client_folder_ready': disk_ready}


class ClientWorkspaceView(LoginRequiredMixin, View):
    login_url = '/portal/login/'
    def get(self, request, pk):
        client = scoped_client(request, pk)
        template = 'portal/partials/client_workspace.html' if request.headers.get('HX-Request') == 'true' else 'portal/client_workspace.html'
        return private(render(request, template, workspace_context(client, request.user)))

    def post(self, request, pk):
        client = scoped_client(request, pk, edit=True)
        action = request.POST.get('action')
        profile, _ = ClientWorkspaceProfile.objects.get_or_create(client=client)
        if action == 'reveal':
            secret = decrypt_external_secret(profile.password_encrypted) if profile.password_encrypted else ''
            if not secret:
                identity = getattr(client, 'service_identity', None)
                secret = identity.shared_password if identity else ''
            ActivityLog.objects.create(student=client, actor=request.user, action='CLIENT_ACCESS_VIEWED', service='manager_portal', object_type='Client', object_id=str(client.pk))
            return private(render(request, 'portal/client_access.html', {'client': client, 'issued_password': secret}))
        if action == 'avatar':
            upload = request.FILES.get('avatar')
            try:
                if not upload or upload.size > 5 * 1024 * 1024:
                    raise ValueError('Выберите JPG, PNG или WebP до 5 МБ.')
                with Image.open(upload) as picture:
                    if picture.format not in {'JPEG', 'PNG', 'WEBP'} or picture.width * picture.height > 20000000:
                        raise ValueError('Нужна фотография JPG, PNG или WebP до 20 мегапикселей.')
                    picture = ImageOps.fit(ImageOps.exif_transpose(picture).convert('RGB'), (256, 256))
                    output = io.BytesIO()
                    picture.save(output, 'JPEG', quality=85)
                profile.avatar = output.getvalue()
                profile.save(update_fields=['avatar', 'updated_at'])
                messages.success(request, 'Фотография обновлена.')
            except (ValueError, OSError, Image.DecompressionBombError):
                messages.error(request, 'Не удалось прочитать фото. Выберите JPG, PNG или WebP до 5 МБ и 20 мегапикселей.')
        elif action == 'folder':
            from .views import can_access_disk, ensure_client_disk_contract_folder
            if not can_access_disk(request.user):
                raise PermissionDenied
            try:
                root = ensure_client_disk_contract_folder(client, event_id=f'client-folder:{client.pk}')
                if not root:
                    raise ValueError('Empty folder')
                profile.disk_root = root
                profile.save(update_fields=['disk_root', 'updated_at'])
                messages.success(request, 'Папка клиента готова.')
            except Exception:
                messages.error(request, 'DiskSL временно недоступен. Повторите создание папки позже.')
        elif action == 'account':
            try:
                self.create_account(request, client)
            except ImproperlyConfigured:
                messages.error(request, 'Безопасное хранение доступа не настроено. Обратитесь к администратору.')
        return redirect(reverse('portal:client_detail', args=[pk]) + '#client-workspace')

    def create_account(self, request, client):
        from .views import client_mobile_user_id
        from apps.client_onboarding.services import allocate_sl_id, split_person_name, latin_name
        with transaction.atomic():
            locked = Client.objects.select_for_update().get(pk=client.pk)
            profile, _ = ClientWorkspaceProfile.objects.get_or_create(client=locked)
            if client_mobile_user_id(locked) or profile.account_status == 'ready' or (profile.account_status == 'pending' and profile.updated_at > timezone.now() - timedelta(minutes=5)):
                messages.info(request, 'Аккаунт уже подключён или создаётся. Повторная отправка не нужна.')
                return
            if not locked.sl_id:
                locked.sl_id = allocate_sl_id(locked.academic_year or timezone.localdate().year, 'applicant')
                locked.save(update_fields=['sl_id', 'updated_at'])
            given_name, _ = split_person_name(locked.full_name)
            password = f'{latin_name(given_name).capitalize()}_0710'
            # Persist before network I/O; no plain-text password in Client.custom_data.
            profile.password_encrypted = encrypt_external_secret(password)
            profile.account_status = 'pending'
            profile.save(update_fields=['password_encrypted', 'account_status', 'updated_at'])
        try:
            result = post_service(settings.STUDENTS_LIFE_PROVISION_API_URL, settings.STUDENTS_LIFE_PROVISION_TOKEN,
                {'sl_id': locked.sl_id, 'password': password, 'activation_mode': 'legacy_password',
                 'create_only': True, 'full_name': locked.full_name, 'email': locked.email or '', 'phone': locked.phone})
            if str(result.get('sl_id', '')).upper() != locked.sl_id.upper() or not result.get('user_id'):
                raise ValueError('Invalid account response')
            with transaction.atomic():
                locked = Client.objects.select_for_update().get(pk=client.pk)
                data = dict(locked.custom_data or {})
                data['mobile_user_id'] = result['user_id']
                locked.custom_data = data
                locked.mobile_app_user_id = int(result['user_id'])
                locked.save(update_fields=['custom_data', 'mobile_app_user_id', 'updated_at'])
                profile.account_status = 'ready'
                if result.get('status') != 'created':
                    profile.password_encrypted = ''
                profile.save(update_fields=['account_status', 'password_encrypted', 'updated_at'])
                ActivityLog.objects.create(student=locked, actor=request.user, action='CLIENT_ACCOUNT_LINKED', service='manager_portal', object_type='Client', object_id=str(locked.pk))
            messages.success(request, 'Личный кабинет подключён. Логин доступен в карточке.')
        except Exception:
            profile.account_status = 'uncertain'
            profile.save(update_fields=['account_status', 'updated_at'])
            messages.warning(request, 'Не удалось подтвердить результат. Аккаунт мог быть создан. Повторная проверка не изменит существующий пароль.')


class ClientAvatarView(LoginRequiredMixin, View):
    login_url = '/portal/login/'
    def get(self, request, pk):
        client = scoped_client(request, pk)
        avatar = ClientWorkspaceProfile.objects.filter(client=client).values_list('avatar', flat=True).first()
        if avatar:
            return private(HttpResponse(bytes(avatar), content_type='image/jpeg'))
        # Deterministic initials, not a fictitious portrait of a real person.
        from html import escape
        initials = ''.join(word[0] for word in client.full_name.split()[:2]).upper() or 'SL'
        color = ['#17496b', '#88433f', '#36665c', '#67527e', '#8a692e'][client.pk % 5]
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96"><rect width="96" height="96" rx="48" fill="{color}"/><text x="48" y="59" text-anchor="middle" font-family="Arial" font-size="30" fill="white">{escape(initials)}</text></svg>'
        return private(HttpResponse(svg, content_type='image/svg+xml'))
