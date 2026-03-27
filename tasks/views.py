from django.utils.dateparse import parse_datetime
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Task
from .serializers import TaskSerializer


class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Task.objects.select_related('assigned_to', 'created_by', 'client').all()
        params = self.request.query_params
        user = self.request.user

        mine = str(params.get('mine', '')).lower()
        created_by_me = str(params.get('created_by_me', '')).lower()
        pinned = str(params.get('pinned', '')).lower()

        if mine in ('1', 'true', 'yes'):
            qs = qs.filter(assigned_to=user)

        if created_by_me in ('1', 'true', 'yes'):
            qs = qs.filter(created_by=user)

        if pinned in ('1', 'true', 'yes'):
            qs = qs.filter(is_pinned=True)

        task_status = params.get('status')
        if task_status:
            qs = qs.filter(status=task_status)

        updated_after = params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)

        return qs.order_by('-is_pinned', '-updated_at')

    def _is_admin(self, user):
        return bool(
            user and (
                user.is_superuser
                or user.is_staff
                or getattr(user, 'role', None) == 'admin'
            )
        )

    def _can_manage_task(self, user, task):
        if self._is_admin(user):
            return True
        return task.created_by_id == user.id or task.assigned_to_id == user.id

    def perform_create(self, serializer):
        assigned_to = serializer.validated_data.get('assigned_to') or self.request.user
        serializer.save(
            assigned_to=assigned_to,
            created_by=self.request.user,
        )

    def perform_update(self, serializer):
        task = self.get_object()
        if not self._can_manage_task(self.request.user, task):
            raise permissions.PermissionDenied('Недостаточно прав для изменения задачи')
        serializer.save()

    def perform_destroy(self, instance):
        if not self._can_manage_task(self.request.user, instance):
            raise permissions.PermissionDenied('Недостаточно прав для удаления задачи')
        instance.delete()

    @action(detail=True, methods=['post'], url_path='toggle-pin')
    def toggle_pin(self, request, pk=None):
        task = self.get_object()
        if not self._can_manage_task(request.user, task):
            return Response(
                {'detail': 'Недостаточно прав'},
                status=status.HTTP_403_FORBIDDEN,
            )

        task.is_pinned = not task.is_pinned
        task.save(update_fields=['is_pinned', 'updated_at'])
        return Response(self.get_serializer(task).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='toggle-done')
    def toggle_done(self, request, pk=None):
        task = self.get_object()
        if not self._can_manage_task(request.user, task):
            return Response(
                {'detail': 'Недостаточно прав'},
                status=status.HTTP_403_FORBIDDEN,
            )

        task.status = 'done' if task.status != 'done' else 'todo'
        task.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(task).data, status=status.HTTP_200_OK)