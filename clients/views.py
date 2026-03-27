# clients/views.py
from django.db.models import Q
from django.utils.dateparse import parse_datetime
from rest_framework import permissions, viewsets

from .models import Client
from .serializers import ClientSerializer


class ClientViewSet(viewsets.ModelViewSet):
    serializer_class = ClientSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        is_admin = user.is_superuser or getattr(user, 'role', None) == 'admin'

        if is_admin:
            qs = (
                Client.objects
                .select_related('manager', 'relative')
                .prefetch_related('shared_with')
                .all()
            )
        else:
            qs = (
                Client.objects
                .select_related('manager', 'relative')
                .prefetch_related('shared_with')
                .filter(Q(manager=user) | Q(shared_with=user))
                .distinct()
            )

        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)

        status_value = self.request.query_params.get('status')
        if status_value:
            qs = qs.filter(status=status_value)

        manager_id = self.request.query_params.get('manager')
        if manager_id and is_admin:
            qs = qs.filter(manager_id=manager_id)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(full_name__icontains=search) |
                Q(phone__icontains=search) |
                Q(email__icontains=search) |
                Q(city__icontains=search) |
                Q(citizenship__icontains=search) |
                Q(passport_inter_num__icontains=search) |
                Q(passport_local_num__icontains=search) |
                Q(partner_name__icontains=search) |
                Q(relative__full_name__icontains=search) |
                Q(relative__phone__icontains=search)
            )

        return qs.order_by('-updated_at', '-id')

    def perform_create(self, serializer):
        user = self.request.user
        is_admin = user.is_superuser or getattr(user, 'role', None) == 'admin'

        if is_admin:
            serializer.save()
        else:
            serializer.save(manager=user)

    def perform_update(self, serializer):
        """
        Логику manager/shared_with/relative контролирует serializer.
        Здесь просто сохраняем объект.
        """
        serializer.save()