from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import OnboardingReviewEvent, OnboardingSubmission
from .permissions import CanReviewOnboarding
from .serializers import (
    ManagerOnboardingSubmissionSerializer,
    OnboardingSubmissionWriteSerializer,
    PublicOnboardingStatusSerializer,
    ReviewDecisionSerializer,
)
from .services import approve_submission


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
        submission = OnboardingSubmission.objects.select_related('client').filter(public_id=public_id).first()
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
    @transaction.atomic
    def review(self, request, pk=None):
        submission = OnboardingSubmission.objects.select_for_update().get(pk=self.get_object().pk)
        serializer = ReviewDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        decision = serializer.validated_data['decision']
        comment = serializer.validated_data.get('comment', '').strip()

        if submission.status == OnboardingSubmission.STATUS_APPROVED and decision == 'approve':
            return Response(self.get_serializer(submission).data)

        if decision == 'start_review':
            if (
                submission.status == OnboardingSubmission.STATUS_IN_REVIEW
                and submission.reviewed_by_id == request.user.id
            ):
                return Response(self.get_serializer(submission).data)
            if submission.status != OnboardingSubmission.STATUS_SUBMITTED:
                return Response(
                    {'detail': 'Взять на проверку можно только отправленную анкету.'},
                    status=status.HTTP_409_CONFLICT,
                )
            previous_status = submission.status
            submission.status = OnboardingSubmission.STATUS_IN_REVIEW
            submission.reviewed_by = request.user
            submission.review_comment = ''
            submission.save(update_fields=['status', 'reviewed_by', 'review_comment', 'updated_at'])
            OnboardingReviewEvent.objects.create(
                submission=submission,
                decision=OnboardingReviewEvent.DECISION_START_REVIEW,
                from_status=previous_status,
                to_status=OnboardingSubmission.STATUS_IN_REVIEW,
                actor=request.user,
            )
            return Response(self.get_serializer(submission).data)

        if submission.status not in {
            OnboardingSubmission.STATUS_SUBMITTED,
            OnboardingSubmission.STATUS_IN_REVIEW,
        }:
            return Response(
                {'detail': 'Решение можно принять только по отправленной анкете или анкете на проверке.'},
                status=status.HTTP_409_CONFLICT,
            )

        if decision == 'approve':
            try:
                submission = approve_submission(
                    submission,
                    request.user,
                    company_id=serializer.validated_data.get('company_id'),
                )
            except DjangoValidationError as exc:
                return Response({'detail': exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        else:
            previous_status = submission.status
            submission.status = (
                OnboardingSubmission.STATUS_CHANGES_REQUESTED
                if decision == 'request_changes'
                else OnboardingSubmission.STATUS_REJECTED
            )
            submission.review_comment = comment
            submission.reviewed_by = request.user
            submission.reviewed_at = timezone.now()
            submission.save(update_fields=['status', 'review_comment', 'reviewed_by', 'reviewed_at', 'updated_at'])
            OnboardingReviewEvent.objects.create(
                submission=submission,
                decision=decision,
                from_status=previous_status,
                to_status=submission.status,
                actor=request.user,
                comment=comment,
            )

        return Response(self.get_serializer(submission).data)
