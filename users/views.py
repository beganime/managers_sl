from rest_framework import parsers, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .access_models import OfficeTarget, UserAccessProfile
from .models import ManagerSalary, Office, User
from .permissions import IsAdminRole, is_admin_user
from .serializers import (
    OfficeDashboardSerializer,
    OfficeSerializer,
    OfficeTargetSerializer,
    UserAccessProfileSerializer,
    UserSerializer,
)


def _copy_payload(data):
    return data.copy() if hasattr(data, 'copy') else dict(data or {})


def _first_file(request, names):
    files = getattr(request, 'FILES', {}) if request else {}
    for name in names:
        if name in files:
            return files[name]
    return None


class OfficeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Office.objects.all().select_related('target_profile')
    serializer_class = OfficeSerializer
    permission_classes = [permissions.IsAuthenticated]


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.select_related('office', 'managersalary', 'access_profile', 'access_profile__managed_office').all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.JSONParser, parsers.FormParser, parsers.MultiPartParser]

    def get_queryset(self):
        qs = super().get_queryset()
        if is_admin_user(self.request.user):
            return qs
        return qs.filter(id=self.request.user.id)

    def perform_create(self, serializer):
        if not is_admin_user(self.request.user):
            raise permissions.PermissionDenied('Только администратор может создавать сотрудников')
        serializer.save()

    def perform_destroy(self, instance):
        if not is_admin_user(self.request.user):
            raise permissions.PermissionDenied('Только администратор может удалять сотрудников')
        instance.delete()

    @action(detail=False, methods=['get', 'patch'], url_path='me')
    def me(self, request):
        if request.method == 'PATCH':
            data = _copy_payload(request.data)
            data.pop('role', None)
            data.pop('is_superuser', None)
            data.pop('is_staff', None)

            avatar = _first_file(request, ('avatar', 'image', 'photo', 'file', 'upload'))
            if avatar:
                data['avatar'] = avatar

            remove_avatar = request.data.get('remove_avatar')
            if remove_avatar in ('1', 'true', 'True', True):
                data['remove_avatar'] = True

            if data.get('dob') in ('', 'null', 'undefined'):
                data['dob'] = None

            serializer = self.get_serializer(request.user, data=data, partial=True, context={'request': request})
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)

        return Response(self.get_serializer(request.user, context={'request': request}).data)

    @action(detail=True, methods=['patch'], url_path='salary', permission_classes=[IsAdminRole])
    def salary(self, request, pk=None):
        user = self.get_object()
        sal, _ = ManagerSalary.objects.get_or_create(manager=user)
        allowed = ('monthly_plan', 'fixed_salary', 'commission_percent', 'motivation_target', 'motivation_reward')
        for field in allowed:
            if field in request.data:
                setattr(sal, field, request.data[field])
        sal.save()
        return Response({'detail': 'Финансы обновлены'})

    @action(detail=True, methods=['patch'], url_path='access_profile', permission_classes=[IsAdminRole])
    def access_profile(self, request, pk=None):
        user = self.get_object()
        profile, _ = UserAccessProfile.objects.get_or_create(user=user)

        serializer = UserAccessProfileSerializer(profile, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()

        managed_office = profile.managed_office
        if managed_office and 'monthly_plan_usd' in request.data:
            target, _ = OfficeTarget.objects.get_or_create(office=managed_office)
            target_serializer = OfficeTargetSerializer(
                target,
                data={
                    'monthly_plan_usd': request.data.get('monthly_plan_usd'),
                    'comment': request.data.get('plan_comment', target.comment),
                },
                partial=True,
            )
            target_serializer.is_valid(raise_exception=True)
            target_serializer.save()

        return Response({'detail': 'Профиль доступа обновлён', 'access_profile': UserAccessProfileSerializer(profile, context={'request': request}).data})

    @action(detail=False, methods=['get'], url_path='me/office_dashboard')
    def office_dashboard(self, request):
        if is_admin_user(request.user):
            office_id = request.query_params.get('office_id')
            if office_id:
                office = Office.objects.select_related('target_profile').filter(id=office_id).first()
                if not office:
                    return Response({'detail': 'Офис не найден'}, status=status.HTTP_404_NOT_FOUND)
            else:
                office = request.user.office
        else:
            profile, _ = UserAccessProfile.objects.get_or_create(user=request.user)
            if not profile.can_view_office_dashboard or not profile.managed_office:
                return Response({'detail': 'Нет доступа к дашборду офиса'}, status=status.HTTP_403_FORBIDDEN)
            office = Office.objects.select_related('target_profile').filter(id=profile.managed_office_id).first()

        if not office:
            return Response({'detail': 'Офис не найден'}, status=status.HTTP_404_NOT_FOUND)

        payload = OfficeDashboardSerializer.build_payload(office)
        serializer = OfficeDashboardSerializer(payload, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='pay_salary', permission_classes=[IsAdminRole])
    def pay_salary(self, request, pk=None):
        user = self.get_object()
        if not hasattr(user, 'managersalary'):
            return Response({'detail': 'Нет финансового профиля'}, status=status.HTTP_400_BAD_REQUEST)

        amount = float(user.managersalary.current_balance)
        if amount <= 0:
            return Response({'detail': 'Нет средств к выплате'}, status=status.HTTP_400_BAD_REQUEST)

        from analytics.models import TransactionHistory

        TransactionHistory.objects.create(manager=user, amount=-amount, description=f'Выплата зарплаты (администратор {request.user.get_full_name()})')
        user.managersalary.reset_balance()
        return Response({'detail': f'Выплачено ${amount:.2f}'})