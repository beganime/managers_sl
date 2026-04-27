from django.db.models import Q
from rest_framework import parsers, permissions, viewsets

from users.permissions import is_admin_user
from .models import SupportMessage
from .serializers import SupportMessageSerializer


def _copy_payload(data):
    return data.copy() if hasattr(data, 'copy') else dict(data or {})


def _first_file(request, names):
    files = getattr(request, 'FILES', {}) if request else {}
    for name in names:
        if name in files:
            return files[name]
    return None


class SupportMessageViewSet(viewsets.ModelViewSet):
    serializer_class = SupportMessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.JSONParser, parsers.FormParser, parsers.MultiPartParser]

    def get_queryset(self):
        user = self.request.user
        qs = SupportMessage.objects.select_related('user').all()

        if not is_admin_user(user):
            qs = qs.filter(user=user)

        status_value = self.request.query_params.get('status')
        if status_value:
            qs = qs.filter(status=status_value)

        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category=category)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(subject__icontains=search)
                | Q(message__icontains=search)
                | Q(admin_note__icontains=search)
                | Q(user__email__icontains=search)
                | Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
            )

        return qs.order_by('-created_at')

    def _normalize_data(self, request):
        data = _copy_payload(request.data)

        if 'photo' not in data:
            photo = _first_file(request, ('photo', 'image', 'picture'))
            if photo:
                data['photo'] = photo

        if 'file' not in data:
            file_obj = _first_file(request, ('file', 'attachment', 'upload', 'document'))
            if file_obj:
                data['file'] = file_obj

        return data

    def _notify_admins(self, message):
        try:
            from notifications.firebase import get_admin_push_tokens, send_push_to_tokens

            tokens = get_admin_push_tokens()
            if not tokens:
                return

            user_label = message.user.email if message.user else 'Сотрудник'
            send_push_to_tokens(
                tokens=tokens,
                title='Новое обращение в поддержку',
                body=f'{user_label}: {message.subject}',
                data={
                    'type': 'support_message',
                    'support_message_id': message.id,
                    'screen': 'support',
                },
            )
        except Exception:
            pass

    def create(self, request, *args, **kwargs):
        data = self._normalize_data(request)
        serializer = self.get_serializer(data=data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        message = serializer.save(user=request.user)
        self._notify_admins(message)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=201, headers=headers)

    def perform_update(self, serializer):
        if not is_admin_user(self.request.user):
            raise permissions.PermissionDenied('Только администратор может менять статус обращения.')
        serializer.save()

    def perform_destroy(self, instance):
        if not is_admin_user(self.request.user):
            raise permissions.PermissionDenied('Удалять обращения может только администратор.')
        instance.delete()