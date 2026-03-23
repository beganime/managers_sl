# users/views.py
from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import User, Office, ManagerSalary
from .serializers import UserSerializer, OfficeSerializer


class OfficeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset           = Office.objects.all()
    serializer_class   = OfficeSerializer
    permission_classes = [permissions.IsAuthenticated]


class UserViewSet(viewsets.ModelViewSet):
    queryset           = User.objects.select_related('office', 'managersalary').all()
    serializer_class   = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        # Не-администраторы видят только себя
        if not self.request.user.is_superuser:
            return qs.filter(id=self.request.user.id)
        return qs

    # GET/PATCH /api/users/users/me/
    @action(detail=False, methods=['get', 'patch'], url_path='me')
    def me(self, request):
        if request.method == 'PATCH':
            serializer = self.get_serializer(request.user, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        return Response(self.get_serializer(request.user).data)

    # PATCH /api/users/users/{id}/salary/  — только суперадмин
    @action(detail=True, methods=['patch'], url_path='salary',
            permission_classes=[permissions.IsAdminUser])
    def salary(self, request, pk=None):
        user = self.get_object()
        sal, _ = ManagerSalary.objects.get_or_create(manager=user)

        allowed = (
            'monthly_plan', 'fixed_salary', 'commission_percent',
            'motivation_target', 'motivation_reward',
        )
        for field in allowed:
            if field in request.data:
                setattr(sal, field, request.data[field])
        sal.save()
        return Response({'detail': 'Финансы обновлены'})

    # POST /api/users/users/{id}/pay_salary/  — только суперадмин
    @action(detail=True, methods=['post'], url_path='pay_salary',
            permission_classes=[permissions.IsAdminUser])
    def pay_salary(self, request, pk=None):
        user = self.get_object()
        if not hasattr(user, 'managersalary'):
            return Response({'detail': 'Нет финансового профиля'}, status=status.HTTP_400_BAD_REQUEST)

        amount = float(user.managersalary.current_balance)
        if amount <= 0:
            return Response({'detail': 'Нет средств к выплате'}, status=status.HTTP_400_BAD_REQUEST)

        from analytics.models import TransactionHistory
        TransactionHistory.objects.create(
            manager=user,
            amount=-amount,
            description=f'Выплата зарплаты (администратор {request.user.get_full_name()})',
        )
        user.managersalary.reset_balance()
        return Response({'detail': f'Выплачено ${amount:.2f}'})