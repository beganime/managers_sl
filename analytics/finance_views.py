from django.db.models import Q
from django.utils.dateparse import parse_date
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from users.models import Office
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

        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category=category)

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

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(title__icontains=search)
                | Q(comment__icontains=search)
                | Q(office__city__icontains=search)
                | Q(created_by__first_name__icontains=search)
                | Q(created_by__last_name__icontains=search)
                | Q(created_by__email__icontains=search)
            )

        ordering = self.request.query_params.get('ordering')
        allowed_ordering = {
            'entry_date',
            '-entry_date',
            'created_at',
            '-created_at',
            'amount_usd',
            '-amount_usd',
            'category',
            '-category',
            'title',
            '-title',
        }

        if ordering in allowed_ordering:
            return qs.distinct().order_by(ordering, '-created_at')

        return qs.distinct().order_by('-entry_date', '-created_at')

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

        if office_id:
            office = Office.objects.filter(id=office_id).first()
        else:
            office = getattr(request.user, 'office', None) or getattr(
                getattr(request.user, 'access_profile', None),
                'managed_office',
                None,
            )

        if not office:
            return Response({'detail': 'Офис не найден'}, status=status.HTTP_404_NOT_FOUND)

        if not is_admin_user(request.user):
            allowed = {
                getattr(getattr(request.user, 'office', None), 'id', None),
                getattr(getattr(request.user, 'access_profile', None), 'managed_office_id', None),
            }
            allowed.discard(None)

            if office.id not in allowed:
                raise permissions.PermissionDenied('Нет доступа к этому офису')

        date_from = parse_date(request.query_params.get('date_from', '')) if request.query_params.get('date_from') else None
        date_to = parse_date(request.query_params.get('date_to', '')) if request.query_params.get('date_to') else None
        category = request.query_params.get('category') or None

        data = summarize_office_finances(
            office=office,
            date_from=date_from,
            date_to=date_to,
            category=category,
        )

        payload = {
            'office_id': office.id,
            'office_name': office.city,
            'category': category,
            **{k: str(v) for k, v in data.items()},
        }
        return Response(payload)