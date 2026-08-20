import re

from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from rest_framework import serializers

from apps.education.models import Program, University

from .models import OnboardingReviewEvent, OnboardingSubmission, OnboardingUniversityChoice


EXPRESS_COMMENT_MAX_LENGTH = 1000
EMAIL_PATTERN = re.compile(r'^[^\s@]+@[^\s@]+\.(?:com|ru)$', re.IGNORECASE)


class UniversityChoiceInputSerializer(serializers.Serializer):
    university_id = serializers.IntegerField(min_value=1)
    program_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )


class OnboardingSubmissionWriteSerializer(serializers.ModelSerializer):
    university_choices = UniversityChoiceInputSerializer(many=True, required=False)
    stage = serializers.ChoiceField(choices=OnboardingSubmission.STAGE_CHOICES, required=False)

    class Meta:
        model = OnboardingSubmission
        fields = (
            'kind',
            'stage',
            'academic_year',
            'full_name',
            'phone',
            'email',
            'date_of_birth',
            'citizenship',
            'payload',
            'fcm_token',
            'university_choices',
        )

    def validate_academic_year(self, value):
        current_year = timezone.localdate().year
        if value < current_year or value > current_year + 10:
            raise serializers.ValidationError('Год поступления должен быть в пределах ближайших десяти лет.')
        return value

    def validate_email(self, value):
        normalized = str(value or '').strip().lower()
        if normalized and not EMAIL_PATTERN.fullmatch(normalized):
            raise serializers.ValidationError(
                'Укажите Email в формате name@provider.com или name@provider.ru.'
            )
        return normalized

    def validate(self, attrs):
        choices = attrs.get('university_choices', [])
        kind = attrs.get('kind', getattr(self.instance, 'kind', None))
        stage = attrs.get('stage', getattr(self.instance, 'stage', OnboardingSubmission.STAGE_FULL))
        if not self.instance and kind == OnboardingSubmission.KIND_SCHOOL_STUDENT and 'stage' not in self.initial_data:
            stage = OnboardingSubmission.STAGE_EXPRESS
            attrs['stage'] = stage

        if self.instance and kind != self.instance.kind:
            raise serializers.ValidationError({'kind': 'Тип заявки нельзя изменить после отправки.'})

        if stage == OnboardingSubmission.STAGE_EXPRESS:
            if choices:
                raise serializers.ValidationError({'university_choices': 'В экспресс-заявке ВУЗы пока не выбираются.'})
            payload = attrs.get('payload', getattr(self.instance, 'payload', {})) or {}
            email = attrs.get('email', getattr(self.instance, 'email', ''))
            if not str(email or '').strip():
                raise serializers.ValidationError({'email': 'Email обязателен для экспресс-заявки.'})
            services = payload.get('requested_services') or []
            if not isinstance(services, list) or not services:
                raise serializers.ValidationError({'payload': 'Выберите хотя бы одну нужную услугу.'})
            request_text = str(payload.get('request_text') or '').strip()
            if not request_text:
                raise serializers.ValidationError({'payload': 'Кратко напишите, что именно вы хотите.'})
            if len(request_text) > EXPRESS_COMMENT_MAX_LENGTH:
                raise serializers.ValidationError({
                    'payload': f'Комментарий не должен превышать {EXPRESS_COMMENT_MAX_LENGTH} символов.'
                })
            attrs['payload'] = {**payload, 'request_text': request_text}
            return attrs

        if kind == OnboardingSubmission.KIND_SCHOOL_STUDENT:
            raise serializers.ValidationError({'stage': 'Для школьника используется экспресс-заявка.'})

        if kind == OnboardingSubmission.KIND_APPLICANT:
            if not 3 <= len(choices) <= 5:
                raise serializers.ValidationError({'university_choices': 'Нужно выбрать от 3 до 5 ВУЗов.'})
            university_ids = [item['university_id'] for item in choices]
            if len(university_ids) != len(set(university_ids)):
                raise serializers.ValidationError({'university_choices': 'Один ВУЗ нельзя выбрать дважды.'})

            program_ids = [program_id for item in choices for program_id in item['program_ids']]
            if not 3 <= len(set(program_ids)) <= 6 or len(program_ids) != len(set(program_ids)):
                raise serializers.ValidationError({'university_choices': 'Нужно выбрать от 3 до 6 разных программ.'})

            universities = {
                item.id: item
                for item in University.objects.filter(id__in=university_ids, is_active=True)
            }
            if len(universities) != len(university_ids):
                raise serializers.ValidationError({'university_choices': 'Один или несколько ВУЗов недоступны.'})

            programs = {
                item.id: item
                for item in Program.objects.filter(
                    id__in=program_ids,
                    is_active=True,
                    is_archived=False,
                )
            }
            if len(programs) != len(program_ids):
                raise serializers.ValidationError({'university_choices': 'Одна или несколько программ недоступны.'})
            for item in choices:
                if any(programs[program_id].university_id != item['university_id'] for program_id in item['program_ids']):
                    raise serializers.ValidationError({'university_choices': 'Программа должна принадлежать выбранному ВУЗу.'})

        return attrs

    def _replace_choices(self, submission, choices):
        submission.university_choices.all().delete()
        if submission.kind != OnboardingSubmission.KIND_APPLICANT:
            return
        for rank, item in enumerate(choices, start=1):
            choice = OnboardingUniversityChoice.objects.create(
                submission=submission,
                university_id=item['university_id'],
                rank=rank,
            )
            choice.programs.set(item['program_ids'])

    @transaction.atomic
    def create(self, validated_data):
        choices = validated_data.pop('university_choices', [])
        raw_token, token_hash = OnboardingSubmission.issue_access_token()
        submission = OnboardingSubmission.objects.create(access_token_hash=token_hash, **validated_data)
        self._replace_choices(submission, choices)
        submission._raw_access_token = raw_token
        transaction.on_commit(lambda: _enqueue_onboarding_sheet_sync(submission.pk))
        return submission

    @transaction.atomic
    def update(self, instance, validated_data):
        choices = validated_data.pop('university_choices', [])
        promotes_express = (
            instance.kind == OnboardingSubmission.KIND_APPLICANT
            and instance.stage == OnboardingSubmission.STAGE_EXPRESS
            and instance.status == OnboardingSubmission.STATUS_APPROVED
            and validated_data.get('stage') == OnboardingSubmission.STAGE_FULL
        )
        edits_existing_client = bool(
            instance.client_id
            and validated_data.get('stage', instance.stage) == OnboardingSubmission.STAGE_FULL
        )
        if (
            instance.status != OnboardingSubmission.STATUS_CHANGES_REQUESTED
            and not promotes_express
            and not edits_existing_client
        ):
            raise serializers.ValidationError('Изменять можно только анкету, возвращённую менеджером.')
        for field, value in validated_data.items():
            setattr(instance, field, value)
        previous_status = instance.status
        instance.status = OnboardingSubmission.STATUS_SUBMITTED
        instance.review_comment = ''
        instance.reviewed_by = None
        instance.reviewed_at = None
        instance.submitted_at = timezone.now()
        instance.save()
        self._replace_choices(instance, choices)
        if instance.client_id:
            from apps.crm.models import ClientQuestionnaire

            questionnaire_data = dict(instance.payload or {})
            questionnaire_data['university_choices'] = [
                {
                    'university_id': choice.university_id,
                    'university_name': choice.university.name,
                    'programs': [
                        {'id': program.id, 'name': program.name}
                        for program in choice.programs.all()
                    ],
                }
                for choice in instance.university_choices.select_related('university').prefetch_related('programs')
            ]
            ClientQuestionnaire.objects.update_or_create(
                client_id=instance.client_id,
                defaults={
                    'status': ClientQuestionnaire.STATUS_SUBMITTED,
                    'full_name': instance.full_name,
                    'phone': instance.phone,
                    'email': instance.email or None,
                    'citizenship': instance.citizenship,
                    'data': questionnaire_data,
                    'submitted_at': instance.submitted_at,
                    'last_synced_at': timezone.now(),
                },
            )
        OnboardingReviewEvent.objects.create(
            submission=instance,
            decision=OnboardingReviewEvent.DECISION_RESUBMIT,
            from_status=previous_status,
            to_status=OnboardingSubmission.STATUS_SUBMITTED,
        )
        transaction.on_commit(lambda: _enqueue_onboarding_sheet_sync(instance.pk, force_status=promotes_express))
        return instance


def _enqueue_onboarding_sheet_sync(submission_id, force_status=False):
    from apps.sheets_sync.services import enqueue_onboarding_inbox_sync

    enqueue_onboarding_inbox_sync(submission_id, force_status=force_status)


class UniversityChoiceReadSerializer(serializers.ModelSerializer):
    university_id = serializers.IntegerField(source='university.id', read_only=True)
    university_name = serializers.CharField(source='university.name', read_only=True)
    programs = serializers.SerializerMethodField()

    class Meta:
        model = OnboardingUniversityChoice
        fields = ('rank', 'university_id', 'university_name', 'programs')

    def get_programs(self, obj):
        return [{'id': program.id, 'name': program.name} for program in obj.programs.all()]


class PublicOnboardingStatusSerializer(serializers.ModelSerializer):
    sl_id = serializers.CharField(source='client.sl_id', read_only=True)
    university_choices = UniversityChoiceReadSerializer(many=True, read_only=True)
    admission_status = serializers.SerializerMethodField()
    service_credentials = serializers.SerializerMethodField()
    can_fill_full_questionnaire = serializers.SerializerMethodField()

    def get_service_credentials(self, obj):
        try:
            identity = obj.service_identity
        except ObjectDoesNotExist:
            identity = None
        if not identity or obj.status != OnboardingSubmission.STATUS_APPROVED:
            return None
        return {
            'mobile_login': identity.mobile_login,
            'shared_password': identity.shared_password,
        }

    def get_can_fill_full_questionnaire(self, obj):
        return (
            obj.kind == OnboardingSubmission.KIND_APPLICANT
            and obj.stage == OnboardingSubmission.STAGE_EXPRESS
            and obj.status == OnboardingSubmission.STATUS_APPROVED
        )

    def get_admission_status(self, obj):
        client = getattr(obj, 'client', None)
        if not client:
            return None
        try:
            snapshot = client.admission_snapshot
        except ObjectDoesNotExist:
            return None
        return {
            'current_status': snapshot.current_status,
            'invitation_city': snapshot.invitation_city,
            'meeting': snapshot.meeting,
            'current_location': snapshot.current_location,
            'updated_at': snapshot.last_imported_at,
        }

    class Meta:
        model = OnboardingSubmission
        fields = (
            'public_id',
            'kind',
            'stage',
            'status',
            'review_comment',
            'sl_id',
            'university_choices',
            'admission_status',
            'service_credentials',
            'can_fill_full_questionnaire',
            'full_name',
            'phone',
            'email',
            'date_of_birth',
            'citizenship',
            'academic_year',
            'submitted_at',
            'reviewed_at',
        )


class OnboardingReviewEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source='actor.get_full_name', read_only=True)

    class Meta:
        model = OnboardingReviewEvent
        fields = ('decision', 'from_status', 'to_status', 'actor', 'actor_name', 'comment', 'created_at')


class ManagerOnboardingSubmissionSerializer(serializers.ModelSerializer):
    university_choices = UniversityChoiceReadSerializer(many=True, read_only=True)
    sl_id = serializers.CharField(source='client.sl_id', read_only=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.get_full_name', read_only=True)
    review_events = OnboardingReviewEventSerializer(many=True, read_only=True)
    service_credentials = serializers.SerializerMethodField()

    class Meta:
        model = OnboardingSubmission
        fields = '__all__'

    def get_service_credentials(self, obj):
        try:
            identity = obj.service_identity
        except ObjectDoesNotExist:
            identity = None
        if not identity:
            return None
        return {
            'mobile_login': identity.mobile_login,
            'shared_password': identity.shared_password,
            'tmmail_email': identity.tmmail_email,
        }


class ReviewDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=('start_review', 'approve', 'request_changes', 'reject'))
    comment = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    company_id = serializers.IntegerField(required=False, min_value=1)

    def validate(self, attrs):
        if attrs['decision'] in {'request_changes', 'reject'} and not attrs.get('comment', '').strip():
            raise serializers.ValidationError({'comment': 'Для этого решения нужен комментарий менеджера.'})
        return attrs
