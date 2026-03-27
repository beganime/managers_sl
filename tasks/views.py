from django.utils.dateparse import parse_datetime
from rest_framework import permissions, viewsets

from .models import Task
from .serializers import TaskSerializer


class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        if user.is_superuser:
            qs = Task.objects.select_related('assigned_to', 'created_by', 'client').all()
        else:
            qs = Task.objects.select_related('assigned_to', 'created_by', 'client').filter(
                assigned_to=user
            )

        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)

        return qs.order_by('-updated_at')

    def perform_create(self, serializer):
        assigned_to = serializer.validated_data.get('assigned_to', self.request.user)
        serializer.save(
            assigned_to=assigned_to,
            created_by=self.request.user,
        )