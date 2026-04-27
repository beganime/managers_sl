from django.db.models import Q
from rest_framework import permissions, viewsets

from users.permissions import is_admin_user
from .models import SupportMessage
from .serializers import SupportMessageSerializer


class SupportMessageViewSet(viewsets.ModelViewSet):
    serializer_class = SupportMessageSerializer
    permission_classes = [permissions.IsAuthenticated]

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
                | Q(user__email__icontains=search)
                | Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
            )

        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        if not is_admin_user(self.request.user):
            raise permissions.PermissionDenied('Только администратор может менять статус обращения.')
        serializer.save()

    def perform_destroy(self, instance):
        if not is_admin_user(self.request.user):
            raise permissions.PermissionDenied('Удалять обращения может только администратор.')
        instance.delete()