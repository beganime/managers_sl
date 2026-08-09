from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import OnboardingSubmission
from .permissions import CanReviewOnboarding
from .serializers import (
    ManagerOnboardingSubmissionSerializer,
    OnboardingSubmissionWriteSerializer,
    PublicOnboardingStatusSerializer,
    ReviewDecisionSerializer,
)
from .services import review_submission


class PublicOnboardingSubmissionCreateView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = OnboardingSubmissionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        submission = serializer.save()
        return Response(
            {
                **PublicOnboardingStatusSerializer(submission).data,
                'access_token': submission._raw_access_token,
            },
            status=status.HTTP_201_CREATED,
        )


class PublicOnboardingSubmissionDetailView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_submission(self, request, public_id):
        submission = OnboardingSubmission.objects.select_related('client', 'service_identity').filter(public_id=public_id).first()
        token = request.headers.get('X-Onboarding-Token', '')
        if not submission or not submission.token_matches(token):
            raise NotFound('Анкета не найдена.')
        return submission

    def get(self, request, public_id):
        return Response(PublicOnboardingStatusSerializer(self.get_submission(request, public_id)).data)

    def put(self, request, public_id):
        submission = self.get_submission(request, public_id)
        serializer = OnboardingSubmissionWriteSerializer(submission, data=request.data)
        serializer.is_valid(raise_exception=True)
        submission = serializer.save()
        return Response(PublicOnboardingStatusSerializer(submission).data)


class ManagerOnboardingSubmissionViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [CanReviewOnboarding]
    serializer_class = ManagerOnboardingSubmissionSerializer
    queryset = (
        OnboardingSubmission.objects.select_related('client', 'reviewed_by', 'service_identity')
        .prefetch_related(
            'university_choices__university',
            'university_choices__programs',
            'review_events__actor',
        )
    )

    def get_queryset(self):
        queryset = super().get_queryset()
        requested_status = self.request.query_params.get('status')
        if requested_status:
            queryset = queryset.filter(status=requested_status)
        return queryset

    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        submission = self.get_object()
        serializer = ReviewDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        decision = serializer.validated_data['decision']
        comment = serializer.validated_data.get('comment', '').strip()

        try:
            submission = review_submission(
                submission,
                request.user,
                decision,
                comment=comment,
                company_id=serializer.validated_data.get('company_id'),
            )
        except DjangoValidationError as exc:
            conflict_messages = {
                'Взять на проверку можно только отправленную анкету.',
                'Решение можно принять только по отправленной анкете или анкете на проверке.',
            }
            response_status = (
                status.HTTP_409_CONFLICT
                if any(message in conflict_messages for message in exc.messages)
                else status.HTTP_400_BAD_REQUEST
            )
            return Response({'detail': exc.messages}, status=response_status)

        return Response(self.get_serializer(submission).data)
