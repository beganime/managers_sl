from uuid import uuid4

from rest_framework import serializers

from .models import (
    Application,
    ApplicationExam,
    Client,
    ClientActivity,
    ClientFile,
    ClientFileReviewEvent,
    ClientFileVersion,
    ClientNote,
    EmailRecord,
    ExternalAccount,
    Lead,
    LeadSource,
    TranslationRecord,
)


class LeadSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeadSource
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class LeadSerializer(serializers.ModelSerializer):
    source_name = serializers.CharField(source='source.name', read_only=True)
    manager_name = serializers.CharField(source='manager.get_full_name', read_only=True)
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)

    class Meta:
        model = Lead
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'converted_at')


class ClientSerializer(serializers.ModelSerializer):
    manager_name = serializers.CharField(source='manager.get_full_name', read_only=True)
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Client
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'public_id')


class ScopedClientRelationMixin:
    """Apply student visibility to writable relations, not just list endpoints."""

    def get_fields(self):
        fields = super().get_fields()
        from .access import visible_clients
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        clients = visible_clients(Client.objects.all(), user)
        if 'client' in fields and not fields['client'].read_only:
            fields['client'].queryset = clients
        if 'application' in fields and not fields['application'].read_only:
            fields['application'].queryset = Application.objects.filter(client__in=clients)
        return fields

    def validate(self, attrs):
        attrs = super().validate(attrs)
        client = attrs.get('client', getattr(self.instance, 'client', None))
        application = attrs.get('application', getattr(self.instance, 'application', None))
        if application and client and application.client_id != client.pk:
            raise serializers.ValidationError({'application': 'Заявка принадлежит другому клиенту.'})
        return attrs


class ApplicationSerializer(ScopedClientRelationMixin, serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.full_name', read_only=True)
    manager_name = serializers.CharField(source='manager.get_full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Application
        fields = '__all__'
        # Canonical writes will use the separately scoped v2 contract. Do not
        # allow legacy clients to alter identity/catalog mappings implicitly.
        read_only_fields = (
            'created_at', 'updated_at', 'public_id', 'university', 'program',
            'country_reference', 'academic_year', 'current_stage',
        )


class ApplicationExamSerializer(serializers.ModelSerializer):
    application_public_id = serializers.UUIDField(source='application.public_id', read_only=True)
    student_public_id = serializers.UUIDField(source='student.public_id', read_only=True)
    student_sl_id = serializers.CharField(source='student.sl_id', read_only=True)
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    university = serializers.SerializerMethodField()
    program = serializers.SerializerMethodField()
    has_secret = serializers.BooleanField(read_only=True)
    event_id = serializers.UUIDField(write_only=True, required=False)
    secret = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=1000)

    class Meta:
        model = ApplicationExam
        fields = (
            'id', 'public_id', 'application', 'application_public_id', 'student',
            'student_public_id', 'student_sl_id', 'student_name', 'university', 'program',
            'subject', 'scheduled_at', 'timezone', 'join_url', 'login', 'secret',
            'has_secret', 'status', 'result', 'score', 'retake_at', 'comment',
            'responsible', 'created_by', 'source_service', 'source_id', 'source_version',
            'client_acknowledged_at', 'created_at', 'updated_at', 'event_id',
        )
        read_only_fields = (
            'id', 'public_id', 'student', 'created_by', 'client_acknowledged_at',
            'source_service', 'source_id', 'created_at', 'updated_at',
        )

    @staticmethod
    def _catalog_name(reference, legacy):
        return (getattr(reference, 'abbreviation', '') or getattr(reference, 'name', '') or legacy or '')

    def get_university(self, obj):
        return self._catalog_name(obj.application.university, obj.application.university_name)

    def get_program(self, obj):
        return self._catalog_name(obj.application.program, obj.application.program_name)

    def create(self, validated_data):
        from .exam_registry import ExamRegistryError, upsert_application_exam
        event_id = validated_data.pop('event_id', None)
        secret = validated_data.pop('secret', None)
        application = validated_data.pop('application')
        subject = validated_data.pop('subject')
        scheduled_at = validated_data.pop('scheduled_at')
        validated_data['source_service'] = 'manager_api'
        validated_data['source_id'] = f'manager-api-{uuid4()}'
        try:
            exam, _created = upsert_application_exam(
                application=application, subject=subject, scheduled_at=scheduled_at,
                actor=self.context['request'].user, event_id=event_id, secret=secret,
                **validated_data,
            )
        except ExamRegistryError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return exam

    def update(self, instance, validated_data):
        from .exam_registry import ExamRegistryError, upsert_application_exam
        event_id = validated_data.pop('event_id', None)
        secret = validated_data.pop('secret', None)
        application = validated_data.pop('application', instance.application)
        subject = validated_data.pop('subject', instance.subject)
        scheduled_at = validated_data.pop('scheduled_at', instance.scheduled_at)
        validated_data.setdefault('source_service', instance.source_service)
        validated_data.setdefault('source_id', instance.source_id)
        try:
            exam, _created = upsert_application_exam(
                application=application, subject=subject, scheduled_at=scheduled_at,
                actor=self.context['request'].user, event_id=event_id, secret=secret,
                **validated_data,
            )
        except ExamRegistryError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return exam


class TranslationRecordSerializer(serializers.ModelSerializer):
    student_public_id = serializers.UUIDField(source='student.public_id', read_only=True)
    student_sl_id = serializers.CharField(source='student.sl_id', read_only=True)
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    application_public_id = serializers.UUIDField(source='application.public_id', read_only=True)
    document_version_public_id = serializers.UUIDField(
        source='source_document_version.public_id', read_only=True,
    )
    translator_name = serializers.CharField(source='translator.get_full_name', read_only=True)
    reviewer_name = serializers.CharField(source='reviewer.get_full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = TranslationRecord
        fields = (
            'public_id', 'student_public_id', 'student_sl_id', 'student_name',
            'application_public_id', 'document_version_public_id', 'title',
            'source_language', 'target_language', 'template_name', 'version',
            'status', 'status_display', 'source_storage_path', 'result_storage_path',
            'translator_name', 'reviewer_name', 'source_service', 'source_id',
            'source_version', 'created_at', 'updated_at',
        )


class EmailRecordSerializer(serializers.ModelSerializer):
    student_public_id = serializers.UUIDField(source='student.public_id', read_only=True)
    student_sl_id = serializers.CharField(source='student.sl_id', read_only=True)
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    application_public_id = serializers.UUIDField(source='application.public_id', read_only=True)
    responsible_name = serializers.CharField(source='responsible.get_full_name', read_only=True)

    class Meta:
        model = EmailRecord
        fields = (
            'public_id', 'student_public_id', 'student_sl_id', 'student_name',
            'application_public_id', 'responsible_name', 'source_service', 'source_id',
            'mailbox', 'sender_email', 'sender_name', 'recipient_email', 'subject',
            'received_at', 'category', 'importance', 'university_name',
            'attachment_count', 'body_preview', 'source_url', 'is_read', 'is_replied',
            'processed', 'source_version', 'created_at', 'updated_at',
        )

class ExternalAccountSerializer(serializers.ModelSerializer):
    secret = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=1000)
    event_id = serializers.UUIDField(write_only=True, required=False)
    has_secret = serializers.BooleanField(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    student_sl_id = serializers.CharField(source='student.sl_id', read_only=True)
    responsible_name = serializers.CharField(source='responsible.get_full_name', read_only=True)

    class Meta:
        model = ExternalAccount
        fields = (
            'id', 'public_id', 'student', 'student_name', 'student_sl_id', 'application',
            'system', 'provider_name', 'portal_url', 'email', 'login', 'secret', 'has_secret',
            'status', 'status_display', 'last_checked_at', 'issue', 'responsible',
            'responsible_name', 'created_by', 'notes', 'secret_updated_at', 'created_at',
            'updated_at', 'event_id',
        )
        read_only_fields = (
            'id', 'public_id', 'created_by', 'secret_updated_at', 'created_at', 'updated_at',
        )

    def validate(self, attrs):
        student = attrs.get('student') or getattr(self.instance, 'student', None)
        application = attrs.get('application') if 'application' in attrs else getattr(self.instance, 'application', None)
        if application and student and application.client_id != student.pk:
            raise serializers.ValidationError({'application': 'Заявка должна принадлежать выбранному студенту.'})
        return attrs

    def create(self, validated_data):
        from django.core.exceptions import ValidationError as DjangoValidationError
        from .external_accounts import ExternalAccountError, create_external_account
        secret = validated_data.pop('secret', '')
        event_id = validated_data.pop('event_id', None)
        try:
            account, _created = create_external_account(
                actor=self.context['request'].user,
                secret=secret,
                event_id=event_id,
                source_service='manager_api',
                **validated_data,
            )
        except (ExternalAccountError, DjangoValidationError) as exc:
            raise serializers.ValidationError(getattr(exc, 'message_dict', None) or str(exc)) from exc
        return account

    def update(self, instance, validated_data):
        from django.core.exceptions import ValidationError as DjangoValidationError
        from .external_accounts import ExternalAccountError, update_external_account
        secret = validated_data.pop('secret', None)
        event_id = validated_data.pop('event_id', None)
        try:
            account, _changed = update_external_account(
                instance,
                actor=self.context['request'].user,
                secret=secret,
                event_id=event_id,
                source_service='manager_api',
                **validated_data,
            )
        except (ExternalAccountError, DjangoValidationError) as exc:
            raise serializers.ValidationError(getattr(exc, 'message_dict', None) or str(exc)) from exc
        return account


class ClientActivitySerializer(ScopedClientRelationMixin, serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.full_name', read_only=True)
    manager_name = serializers.CharField(source='manager.get_full_name', read_only=True)
    activity_type_display = serializers.CharField(source='get_activity_type_display', read_only=True)

    class Meta:
        model = ClientActivity
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class ClientNoteSerializer(ScopedClientRelationMixin, serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.full_name', read_only=True)
    author_name = serializers.CharField(source='author.get_full_name', read_only=True)

    class Meta:
        model = ClientNote
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')

    def validate_text(self, value):
        value = str(value or '').strip()
        if not value:
            raise serializers.ValidationError('Введите текст заметки.')
        if len(value) > 1000:
            raise serializers.ValidationError('Заметка должна быть не длиннее 1000 символов.')
        return value


class ClientFileSerializer(ScopedClientRelationMixin, serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.full_name', read_only=True)
    uploaded_by_name = serializers.CharField(source='uploaded_by.get_full_name', read_only=True)
    file_url = serializers.SerializerMethodField()
    version_count = serializers.IntegerField(source='current_version_number', read_only=True)

    class Meta:
        model = ClientFile
        fields = '__all__'
        read_only_fields = (
            'created_at', 'updated_at', 'current_version_number', 'status',
            'review_comment', 'reviewed_at', 'reviewed_by', 'external_review_data',
        )

    def get_file_url(self, obj):
        request = self.context.get('request')
        if getattr(obj, 'external_file_url', ''):
            return obj.external_file_url
        if not obj.file:
            return None
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url


class ClientFileVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientFileVersion
        fields = (
            'public_id', 'event_id', 'document', 'application', 'version_number',
            'original_name', 'storage_path', 'folder_url', 'mime_type', 'size_bytes',
            'sha256', 'source_service', 'uploaded_by', 'uploader_data', 'created_at',
        )
        read_only_fields = fields


class ClientFileReviewEventSerializer(serializers.ModelSerializer):
    reviewer_display = serializers.SerializerMethodField()

    class Meta:
        model = ClientFileReviewEvent
        fields = (
            'event_id', 'document', 'version', 'status', 'comment', 'reviewer',
            'reviewer_display', 'reviewer_data', 'source_service', 'created_at',
        )
        read_only_fields = fields

    def get_reviewer_display(self, obj):
        if obj.reviewer_id:
            return obj.reviewer.get_full_name() or obj.reviewer.email
        return (obj.reviewer_data or {}).get('reviewed_by_display', '')
