from django.utils.dateparse import parse_date
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from users.permissions import is_admin_user
from .finance_models import OfficeFinanceEntry, summarize_office_finances
from .finance_serializers import OfficeFinanceEntrySerializer


class OfficeFinanceEntryViewSet(viewsets.ModelViewSet):
    serializer_class = OfficeFinanceEntrySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = OfficeFinanceEntry.objects.select_related('office', 'created_by', 'currency').all()
        user = self.request.user

        if not is_admin_user(user):
            user_office = getattr(user, 'office', None)
            managed_office_id = getattr(getattr(user, 'access_profile', None), 'managed_office_id', None)

            allowed_ids = [oid for oid in [getattr(user_office, 'id', None), managed_office_id] if oid]
            if allowed_ids:
                qs = qs.filter(office_id__in=allowed_ids)
            else:
                qs = qs.none()

        office_id = self.request.query_params.get('office')
        if office_id:
            qs = qs.filter(office_id=office_id)

        entry_type = self.request.query_params.get('entry_type')
        if entry_type:
            qs = qs.filter(entry_type=entry_type)

        date_from = self.request.query_params.get('date_from')
        if date_from:
            dt = parse_date(date_from)
            if dt:
                qs = qs.filter(entry_date__gte=dt)

        date_to = self.request.query_params.get('date_to')
        if date_to:
            dt = parse_date(date_to)
            if dt:
                qs = qs.filter(entry_date__lte=dt)

        return qs.order_by('-entry_date', '-created_at')

    def perform_create(self, serializer):
        user = self.request.user
        office = serializer.validated_data.get('office')

        if not is_admin_user(user):
            if office is None:
                office = getattr(user, 'office', None)

            allowed = {
                getattr(getattr(user, 'office', None), 'id', None),
                getattr(getattr(user, 'access_profile', None), 'managed_office_id', None),
            }
            allowed.discard(None)
            if not office or office.id not in allowed:
                raise permissions.PermissionDenied('Нельзя создавать операции для этого офиса')

        serializer.save(created_by=user, office=office)

    def perform_update(self, serializer):
        if not is_admin_user(self.request.user):
            raise permissions.PermissionDenied('Редактирование доступно только администратору')
        serializer.save()

    def perform_destroy(self, instance):
        if not is_admin_user(self.request.user):
            raise permissions.PermissionDenied('Удаление доступно только администратору')
        instance.delete()

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        office_id = request.query_params.get('office')
        if not office_id:
            office = getattr(request.user, 'office', None) or getattr(
                getattr(request.user, 'access_profile', None),
                'managed_office',
                None,
            )
        else:
            office = OfficeFinanceEntry.objects.select_related('office').filter(office_id=office_id).first()
            office = office.office if office else None

        if not office:
            return Response({'detail': 'Офис не найден'}, status=status.HTTP_404_NOT_FOUND)

        date_from = parse_date(request.query_params.get('date_from', '')) if request.query_params.get('date_from') else None
        date_to = parse_date(request.query_params.get('date_to', '')) if request.query_params.get('date_to') else None

        data = summarize_office_finances(office=office, date_from=date_from, date_to=date_to)
        payload = {'office_id': office.id, 'office_name': office.city, **{k: str(v) for k, v in data.items()}}
        return Response(payload)