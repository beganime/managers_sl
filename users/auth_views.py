# users/auth_views.py
import logging

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import UserSerializer

logger = logging.getLogger(__name__)


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = TokenObtainPairSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = getattr(serializer, 'user', None)
        access = serializer.validated_data.get('access')
        refresh = serializer.validated_data.get('refresh')

        try:
            user_data = UserSerializer(user, context={'request': request}).data
        except Exception:
            logger.exception(
                'Login succeeded but user serialization failed for user_id=%s',
                getattr(user, 'id', None),
            )
            user_data = {
                'id': getattr(user, 'id', None),
                'email': getattr(user, 'email', ''),
                'first_name': getattr(user, 'first_name', ''),
                'last_name': getattr(user, 'last_name', ''),
                'full_name': f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
                or getattr(user, 'email', ''),
                'role': getattr(user, 'role', 'manager'),
                'is_superuser': getattr(user, 'is_superuser', False),
                'is_staff': getattr(user, 'is_staff', False),
                'is_admin_role': bool(
                    getattr(user, 'is_superuser', False)
                    or getattr(user, 'role', None) == 'admin'
                ),
                'managersalary': None,
                'office': None,
            }

        return Response(
            {
                'access': str(access),
                'refresh': str(refresh),
                'user': user_data,
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response(
                {'detail': 'refresh token обязателен'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            return Response(
                {'detail': 'Некорректный refresh token'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {'detail': 'Выход выполнен успешно'},
            status=status.HTTP_200_OK,
        )