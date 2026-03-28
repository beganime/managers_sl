# clients/views.py
from django.db.models import Q, Case, When, Value, IntegerField
from django.utils.dateparse import parse_datetime
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

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

        # Неархивные сначала, архивные внизу
        qs = qs.annotate(
            archive_order=Case(
                When(status='archive', then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        )

        return qs.order_by('archive_order', '-updated_at', '-id')

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

    def destroy(self, request, *args, **kwargs):
        """
        МЯГКОЕ УДАЛЕНИЕ:
        вместо реального удаления переводим клиента в статус archive.
        """
        instance = self.get_object()

        if instance.status != 'archive':
            instance.status = 'archive'
            instance.save(update_fields=['status', 'updated_at'])

        serializer = self.get_serializer(instance)
        return Response(
            {
                'detail': 'Клиент переведён в архив.',
                'client': serializer.data,
            },
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['post'], url_path='archive')
    def archive(self, request, pk=None):
        """
        Дополнительный явный endpoint для архивации:
        POST /api/clients/{id}/archive/
        """
        instance = self.get_object()

        if instance.status != 'archive':
            instance.status = 'archive'
            instance.save(update_fields=['status', 'updated_at'])

        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='restore')
    def restore(self, request, pk=None):
        """
        Восстановление клиента из архива.
        Если не передан status, вернём в consultation.
        POST /api/clients/{id}/restore/
        body: {"status": "consultation"}
        """
        instance = self.get_object()
        new_status = request.data.get('status') or 'consultation'

        valid_statuses = [choice[0] for choice in Client.STATUS_CHOICES if choice[0] != 'archive']
        if new_status not in valid_statuses:
            new_status = 'consultation'

        instance.status = new_status
        instance.save(update_fields=['status', 'updated_at'])

        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='set-status')
    def set_status(self, request, pk=None):
        """
        Быстрая смена статуса клиента с карточки.
        POST /api/clients/{id}/set-status/
        body: {"status": "consultation"}
        """
        instance = self.get_object()
        new_status = request.data.get('status')

        valid_statuses = [choice[0] for choice in Client.STATUS_CHOICES]
        if new_status not in valid_statuses:
            return Response(
                {'status': 'Некорректный статус.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        instance.status = new_status
        instance.save(update_fields=['status', 'updated_at'])

        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)