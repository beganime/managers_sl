from django.contrib.auth import get_user_model
from django.conf import settings
from uuid import NAMESPACE_URL, uuid5
import secrets
from django.db.models import Q
from rest_framework import parsers, permissions, serializers as drf_serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import filter_manager_owned, filter_by_office_scope, get_employee_profile, is_erp_admin

from .credentials import decrypt_external_secret
from .email_registry import EmailRegistryError, upsert_email_record
from .external_accounts import ExternalAccountError, update_external_account
from .models import ActivityLog, Application, ApplicationExam, Client, ClientActivity, ClientFile, ClientFileVersion, ClientNote, EmailRecord, ExternalAccount, Lead, LeadSource, TranslationRecord
from .serializers import (
    ApplicationSerializer,
    ApplicationExamSerializer,
    ClientActivitySerializer,
    ClientFileSerializer,
    ClientFileReviewEventSerializer,
    ClientFileVersionSerializer,
    ClientNoteSerializer,
    ClientSerializer,
    EmailRecordSerializer,
    ExternalAccountSerializer,
    LeadSerializer,
    LeadSourceSerializer,
    TranslationRecordSerializer,
)
from .student360 import build_student_360
from .workflow import WorkflowTransitionError, transition_application
from users.disk_auth import can_access_disk


def client_queryset_for_user(user):
    from .access import visible_clients
    qs = Client.objects.select_related(
        'company', 'office', 'manager', 'source_lead', 'lead_source'
    ).prefetch_related('shared_with')
    return visible_clients(qs, user)


class Student360View(APIView):
    """Stable UUID entry point for the canonical, read-only Student 360 view."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, public_id):
        client = client_queryset_for_user(request.user).filter(public_id=public_id).first()
        if not client:
            # Do not disclose whether an out-of-scope student exists.
            from rest_framework.exceptions import NotFound
            raise NotFound('Клиент не найден.')
        return Response(build_student_360(
            client,
            user=request.user,
            include_sensitive=can_access_disk(request.user),
        ))


class EmailRecordServiceView(APIView):
    """Machine contract receiving idempotent metadata from SMTP_SL."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    @staticmethod
    def _authorized(request):
        from users.service_auth import _service_token_is_valid
        return _service_token_is_valid(request, 'SMTP_SL_REGISTRY_TOKEN')

    def post(self, request):
        if not self._authorized(request):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        date_field = drf_serializers.DateTimeField()
        payload = dict(request.data)
        try:
            payload['received_at'] = date_field.run_validation(payload.get('received_at'))
            record, created, changed = upsert_email_record(payload)
        except (KeyError, TypeError, ValueError, EmailRegistryError, ValidationError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                'record': EmailRecordSerializer(record).data,
                'created': created,
                'changed': changed,
                'linked': bool(record.student_id),
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ApplicationExamServiceView(APIView):
    """Server-to-server ExamSL contract; never uses a manager browser session."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    @staticmethod
    def _authorized(request):
        from users.service_auth import _service_token_is_valid
        return _service_token_is_valid(request)

    @staticmethod
    def _resolve_application(payload):
        public_id = str(payload.get('application_public_id') or '').strip()
        queryset = Application.objects.select_related(
            'client', 'university', 'program', 'manager',
        )
        if public_id:
            return queryset.filter(public_id=public_id).first(), None

        sl_id = str(payload.get('sl_id') or '').strip()
        university = str(payload.get('university') or '').strip()
        program = str(payload.get('program') or '').strip()
        if not sl_id:
            return None, 'Укажите application_public_id или SL-ID.'
        queryset = queryset.filter(client__sl_id__iexact=sl_id)
        if university:
            queryset = queryset.filter(
                Q(university_name__iexact=university)
                | Q(university__name__iexact=university)
                | Q(university__abbreviation__iexact=university)
            )
        if program:
            queryset = queryset.filter(
                Q(program_name__iexact=program) | Q(program__name__iexact=program)
            )
        matches = list(queryset[:2])
        if len(matches) == 1:
            return matches[0], None
        if not matches:
            return None, 'Для студента не найдена соответствующая заявка в университет.'
        return None, 'Найдено несколько заявок. Передайте application_public_id.'

    def get(self, request):
        if not self._authorized(request):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        query = str(request.query_params.get('q') or '').strip()
        queryset = Application.objects.select_related('client', 'university', 'program')
        if query:
            queryset = queryset.filter(
                Q(client__sl_id__icontains=query) | Q(client__full_name__icontains=query)
                | Q(university_name__icontains=query) | Q(university__name__icontains=query)
                | Q(university__abbreviation__icontains=query) | Q(program_name__icontains=query)
                | Q(program__name__icontains=query)
            )
        rows = []
        for application in queryset.order_by('-created_at')[:50]:
            rows.append({
                'application_public_id': str(application.public_id),
                'student_public_id': str(application.client.public_id),
                'sl_id': application.client.sl_id,
                'student_name': application.client.full_name,
                'university': (
                    getattr(application.university, 'abbreviation', '')
                    or getattr(application.university, 'name', '') or application.university_name
                ),
                'program': getattr(application.program, 'name', '') or application.program_name,
            })
        return Response({'results': rows})

    def post(self, request):
        if not self._authorized(request):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        if str(request.data.get('action') or '').upper() == 'ACKNOWLEDGE':
            from .exam_registry import ExamRegistryError, acknowledge_application_exam
            source_id = str(request.data.get('source_id') or '').strip()
            exam = ApplicationExam.objects.filter(source_service='exam_sl', source_id=source_id).first()
            if not exam:
                return Response({'detail': 'Экзамен не найден.'}, status=status.HTTP_404_NOT_FOUND)
            date_field = drf_serializers.DateTimeField()
            try:
                acknowledged_at = date_field.run_validation(request.data.get('acknowledged_at'))
                exam, _changed = acknowledge_application_exam(
                    exam, acknowledged_at=acknowledged_at, source_service='students_life',
                    event_id=request.data.get('event_id'),
                )
            except Exception as exc:
                return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            return Response(ApplicationExamSerializer(exam, context={'request': request}).data)
        application, resolution_error = self._resolve_application(request.data)
        if not application:
            return Response({'detail': resolution_error}, status=status.HTTP_409_CONFLICT)

        from .exam_registry import ExamRegistryError, upsert_application_exam
        date_field = drf_serializers.DateTimeField()
        try:
            scheduled_at = date_field.run_validation(request.data.get('scheduled_at'))
            retake_at = request.data.get('retake_at')
            retake_at = date_field.run_validation(retake_at) if retake_at else None
            acknowledged_at = request.data.get('client_acknowledged_at')
            acknowledged_at = date_field.run_validation(acknowledged_at) if acknowledged_at else None
        except Exception as exc:
            return Response({'detail': f'Некорректная дата: {exc}'}, status=status.HTTP_400_BAD_REQUEST)

        responsible = None
        responsible_email = str(request.data.get('responsible_email') or '').strip().lower()
        if responsible_email:
            responsible = get_user_model().objects.filter(email__iexact=responsible_email).first()
        source_id = str(request.data.get('source_id') or '').strip()
        existing = ApplicationExam.objects.filter(source_service='exam_sl', source_id=source_id).first()
        source_version = request.data.get('source_version')
        try:
            source_version = int(source_version) if source_version not in (None, '') else (
                existing.source_version + 1 if existing else 1
            )
            exam, created = upsert_application_exam(
                application=application,
                subject=request.data.get('subject'),
                scheduled_at=scheduled_at,
                timezone=str(request.data.get('timezone') or 'Asia/Ashgabat')[:64],
                join_url=str(request.data.get('join_url') or '')[:1000],
                login=str(request.data.get('login') or '')[:255],
                secret=request.data.get('secret') if 'secret' in request.data else None,
                status=str(request.data.get('status') or ApplicationExam.STATUS_SCHEDULED),
                result=str(request.data.get('result') or '')[:255],
                score=str(request.data.get('score') or '')[:80],
                retake_at=retake_at,
                client_acknowledged_at=acknowledged_at,
                comment=str(request.data.get('comment') or '')[:1000],
                responsible=responsible,
                source_service='exam_sl', source_id=source_id,
                source_version=source_version,
                event_id=request.data.get('event_id'),
            )
        except (ExamRegistryError, TypeError, ValueError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            ApplicationExamSerializer(exam, context={'request': request}).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ApplicationExamSeenServiceView(APIView):
    """Client-app acknowledgement callback accepted with the existing service API key."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request, external_id):
        configured_keys = {
            str(value) for value in (
                getattr(settings, 'STUDENTS_LIFE_API_KEY', ''),
                getattr(settings, 'LEADS_API_KEY', ''),
            ) if value
        }
        supplied = str(request.headers.get('X-API-KEY') or '')
        if not supplied or not any(secrets.compare_digest(key, supplied) for key in configured_keys):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        exam = ApplicationExam.objects.filter(public_id=external_id).first()
        if not exam:
            exam = ApplicationExam.objects.filter(source_service='exam_sl', source_id=external_id).first()
        if not exam:
            return Response({'detail': 'Экзамен не найден.'}, status=status.HTTP_404_NOT_FOUND)
        date_field = drf_serializers.DateTimeField()
        try:
            acknowledged_at = date_field.run_validation(request.data.get('acknowledged_at'))
            from .exam_registry import acknowledge_application_exam
            event_id = uuid5(
                NAMESPACE_URL, f'{exam.public_id}:ack:{acknowledged_at.isoformat()}',
            )
            exam, _changed = acknowledge_application_exam(
                exam, acknowledged_at=acknowledged_at,
                source_service='students_life', event_id=event_id,
            )
        except Exception as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'status': 'ok', 'exam_public_id': str(exam.public_id)})


class ClientAdmissionStatusServiceView(APIView):
    """Read-only admission progress for one authenticated mobile-app user.

    The mobile backend calls this endpoint server-to-server.  It intentionally
    accepts only the numeric mobile user id and never exposes credentials,
    document URLs or internal comments.
    """

    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    @staticmethod
    def _authorized(request):
        configured_keys = {
            str(value) for value in (
                getattr(settings, 'STUDENTS_LIFE_API_KEY', ''),
                getattr(settings, 'LEADS_API_KEY', ''),
            ) if value
        }
        supplied = str(request.headers.get('X-API-KEY') or '')
        return bool(supplied) and any(
            secrets.compare_digest(key, supplied) for key in configured_keys
        )

    def get(self, request):
        if not self._authorized(request):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        raw_mobile_user_id = str(request.query_params.get('mobile_user_id') or '').strip()
        if not raw_mobile_user_id.isdigit() or int(raw_mobile_user_id) < 1:
            return Response(
                {'detail': 'Укажите корректный mobile_user_id.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        client = Client.objects.filter(mobile_app_user_id=int(raw_mobile_user_id)).first()
        if client is None:
            # An empty result is safer than revealing whether another identity
            # exists and lets a newly approved account render a useful state.
            return Response({'client': None, 'results': []})

        applications = (
            Application.objects.filter(client=client)
            .select_related('university', 'program', 'country_reference', 'manager')
            .prefetch_related('stage_history')
            .order_by('-updated_at', '-id')
        )
        rows = []
        for application in applications:
            rows.append({
                'id': str(application.public_id),
                'university': (
                    getattr(application.university, 'abbreviation', '')
                    or getattr(application.university, 'name', '')
                    or application.university_name
                    or 'Вуз пока не указан'
                ),
                'program': (
                    getattr(application.program, 'name', '')
                    or application.program_name
                    or 'Программа пока не указана'
                ),
                'country': (
                    getattr(application.country_reference, 'name', '')
                    if application.country_reference_id else application.country
                ),
                'academic_year': application.academic_year,
                'stage': application.current_stage,
                'stage_label': application.get_current_stage_display(),
                'updated_at': application.updated_at,
                'history': [
                    {
                        'stage': event.new_stage,
                        'stage_label': event.get_new_stage_display(),
                        'created_at': event.created_at,
                    }
                    for event in application.stage_history.all()[:8]
                ],
            })
        return Response({
            'client': {
                'sl_id': client.sl_id,
                'full_name': client.full_name,
            },
            'results': rows,
        })


class TranslationServiceView(APIView):
    """Machine contract joining TranslateSL work to the canonical student card."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    @staticmethod
    def _authorized(request):
        from users.service_auth import _service_token_is_valid
        return _service_token_is_valid(request, 'TRANSLATE_SL_AUTH_SERVICE_TOKEN')

    @staticmethod
    def _resolve_context(payload):
        student = None
        application = None
        document_version = None

        student_public_id = str(payload.get('student_public_id') or '').strip()
        sl_id = str(payload.get('sl_id') or '').strip()
        if student_public_id:
            student = Client.objects.filter(public_id=student_public_id).first()
        elif sl_id:
            student = Client.objects.filter(sl_id__iexact=sl_id).first()
        if (student_public_id or sl_id) and student is None:
            return None, None, None, 'Клиент не найден.'

        application_public_id = str(payload.get('application_public_id') or '').strip()
        if application_public_id:
            application = Application.objects.filter(public_id=application_public_id).first()
            if application is None:
                return None, None, None, 'Заявка в университет не найдена.'
            if student and application.client_id != student.pk:
                return None, None, None, 'Заявка принадлежит другому клиенту.'
            student = student or application.client

        version_public_id = str(payload.get('document_version_public_id') or '').strip()
        storage_path = str(payload.get('source_storage_path') or '').strip()
        versions = ClientFileVersion.objects.select_related('document__client', 'application')
        if version_public_id:
            document_version = versions.filter(public_id=version_public_id).first()
        elif storage_path:
            candidates = versions.filter(storage_path=storage_path)
            if student:
                candidates = candidates.filter(document__client=student)
            document_version = candidates.order_by('-created_at').first()
        if version_public_id and document_version is None:
            return None, None, None, 'Версия исходного документа не найдена.'
        if document_version:
            document_student = document_version.document.client
            if student and document_student.pk != student.pk:
                return None, None, None, 'Исходный документ принадлежит другому клиенту.'
            student = student or document_student
            if document_version.application_id:
                if application and application.pk != document_version.application_id:
                    return None, None, None, 'Документ связан с другой заявкой в университет.'
                application = application or document_version.application
        return student, application, document_version, None

    def get(self, request):
        if not self._authorized(request):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        student, application, document_version, error = self._resolve_context(request.query_params)
        if error:
            return Response({'detail': error}, status=status.HTTP_404_NOT_FOUND)
        if student is None:
            return Response({'detail': 'Укажите SL-ID или UUID клиента.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'student_public_id': str(student.public_id),
            'sl_id': student.sl_id,
            'student_name': student.full_name,
            'manager_email': getattr(student.manager, 'email', '') if student.manager_id else '',
            'application_public_id': str(application.public_id) if application else None,
            'document_version_public_id': str(document_version.public_id) if document_version else None,
        })

    def post(self, request):
        if not self._authorized(request):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        student, application, document_version, error = self._resolve_context(request.data)
        if error:
            return Response({'detail': error}, status=status.HTTP_409_CONFLICT)
        source_id = str(request.data.get('source_id') or '').strip()
        existing = TranslationRecord.objects.filter(source_service='translate_sl', source_id=source_id).first()
        source_version = request.data.get('source_version')
        User = get_user_model()
        translator = User.objects.filter(
            email__iexact=str(request.data.get('translator_email') or '').strip().lower(),
        ).first()
        reviewer = User.objects.filter(
            email__iexact=str(request.data.get('reviewer_email') or '').strip().lower(),
        ).first()
        try:
            source_version = int(source_version) if source_version not in (None, '') else (
                existing.source_version + 1 if existing else 1
            )
            from .translation_registry import TranslationRegistryError, upsert_translation
            translation, created = upsert_translation(
                source_service='translate_sl', source_id=source_id,
                event_id=request.data.get('event_id'), title=request.data.get('title'),
                status=str(request.data.get('status') or TranslationRecord.STATUS_UPLOADED).upper(),
                student=student, application=application, source_document_version=document_version,
                actor=translator or reviewer,
                source_language=str(request.data.get('source_language') or 'tk')[:16],
                target_language=str(request.data.get('target_language') or 'ru')[:16],
                template_name=str(request.data.get('template_name') or '')[:255],
                version=int(request.data.get('version') or 1),
                source_storage_path=str(request.data.get('source_storage_path') or '')[:1000],
                result_storage_path=str(request.data.get('result_storage_path') or '')[:1000],
                translator=translator, reviewer=reviewer, source_version=source_version,
            )
        except (TranslationRegistryError, TypeError, ValueError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            TranslationRecordSerializer(translation).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class LeadSourceViewSet(viewsets.ModelViewSet):
    queryset = LeadSource.objects.all().order_by('name')
    serializer_class = LeadSourceSerializer
    permission_classes = [permissions.IsAuthenticated]


class LeadViewSet(viewsets.ModelViewSet):
    serializer_class = LeadSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Lead.objects.select_related('company', 'office', 'source', 'manager')
        qs = filter_manager_owned(qs, self.request.user, manager_field='manager')

        archive_value = self.request.query_params.get('archive') or 'active'
        action_name = getattr(self, 'action', '')
        if action_name in {'restore', 'internal'} and is_erp_admin(self.request.user):
            pass
        elif archive_value == 'archived':
            qs = qs.filter(is_archived=True)
        elif archive_value == 'all' and is_erp_admin(self.request.user):
            pass
        else:
            qs = qs.filter(is_archived=False)

        status_value = self.request.query_params.get('status')
        if status_value:
            qs = qs.filter(status=status_value)

        office_id = self.request.query_params.get('office')
        if office_id:
            qs = qs.filter(office_id=office_id)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(full_name__icontains=search) | Q(phone__icontains=search) | Q(email__icontains=search))

        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        user = self.request.user
        data = serializer.validated_data
        employee = get_employee_profile(user)
        defaults = {}
        if not data.get('manager'):
            defaults['manager'] = user
        if employee and not data.get('company'):
            defaults['company'] = employee.company
        if employee and not data.get('office'):
            defaults['office'] = employee.office
        lead = serializer.save(**defaults)
        lead.log_action('created_api', user, save=True)

    def ensure_can_manage_lead(self, lead):
        user = self.request.user
        if is_erp_admin(user):
            return
        if lead.manager_id != user.id:
            raise PermissionDenied('Недостаточно прав для изменения этого лида.')

    @action(detail=True, methods=['post'], url_path='convert')
    def convert(self, request, pk=None):
        lead = self.get_object()
        if hasattr(lead, 'client') and lead.client:
            return Response({'detail': 'По этому лиду уже создан клиент.', 'client_id': lead.client.id}, status=status.HTTP_400_BAD_REQUEST)

        employee = get_employee_profile(request.user)
        manager = lead.manager or request.user
        company = lead.company or (employee.company if employee else None)
        office = lead.office or (employee.office if employee else None)
        if not company:
            raise ValidationError('Company is required to create client from lead.')
        client = Client.objects.create(
            company=company,
            office=office,
            manager=manager,
            source_lead=lead,
            lead_source=lead.source,
            direction=lead.direction,
            full_name=lead.full_name,
            phone=lead.phone,
            email=lead.email,
            citizenship=lead.country,
            city=lead.city,
            interested_country=lead.interested_country,
            interested_program=lead.interested_program,
            comments=lead.comment,
            custom_data=lead.custom_data or {},
        )
        lead.manager = manager
        lead.company = company
        lead.office = office
        lead.mark_converted(user=request.user)
        return Response({'detail': 'Лид конвертирован в клиента.', 'client': ClientSerializer(client, context={'request': request}).data})

    @action(detail=True, methods=['post'], url_path='create-client')
    def create_client(self, request, pk=None):
        return self.convert(request, pk=pk)

    @action(detail=True, methods=['post'], url_path='take')
    def take(self, request, pk=None):
        lead = self.get_object()
        if lead.is_archived:
            raise ValidationError('Архивную заявку нельзя взять в работу.')
        if lead.manager_id and lead.manager_id != request.user.id:
            raise ValidationError('Заявка уже в работе у другого менеджера.')
        employee = get_employee_profile(request.user)
        lead.take_responsibility(
            request.user,
            company=employee.company if employee else lead.company,
            office=employee.office if employee else lead.office,
        )
        return Response({'detail': 'Ответственность взята.', 'lead': self.get_serializer(lead).data})

    @action(detail=True, methods=['post'], url_path='release')
    def release(self, request, pk=None):
        lead = self.get_object()
        self.ensure_can_manage_lead(lead)
        if hasattr(lead, 'client') and lead.client:
            raise ValidationError('По лиду уже создан клиент, вернуть его в свободные нельзя.')
        lead.release_responsibility(request.user, note=request.data.get('reason', ''))
        return Response({'detail': 'Заявка возвращена в потенциальные клиенты.', 'lead': self.get_serializer(lead).data})

    @action(detail=True, methods=['post'], url_path='archive')
    def archive(self, request, pk=None):
        lead = self.get_object()
        self.ensure_can_manage_lead(lead)
        lead.archive(user=request.user, reason=request.data.get('reason', ''))
        return Response({'detail': 'Лид перемещён в архив.', 'lead': self.get_serializer(lead).data})

    @action(detail=True, methods=['post'], url_path='restore')
    def restore(self, request, pk=None):
        lead = self.get_object()
        if not is_erp_admin(request.user):
            raise PermissionDenied('Восстановить лид может только администратор.')
        lead.restore_from_archive(user=request.user, note=request.data.get('reason', ''))
        return Response({'detail': 'Лид восстановлен из архива.', 'lead': self.get_serializer(lead).data})

    @action(detail=True, methods=['get'], url_path='internal')
    def internal(self, request, pk=None):
        lead = self.get_object()
        data = LeadSerializer(lead, context={'request': request}).data
        data['action_history'] = lead.action_history
        if is_erp_admin(request.user):
            data['technical'] = {
                'ip': lead.submitter_ip,
                'user_agent': lead.submitter_user_agent,
                'referer': lead.submitter_referer,
                'origin': lead.submitter_origin,
                'api_source': lead.api_source,
                'raw_payload': (lead.custom_data or {}).get('raw_payload'),
            }
        return Response(data)


class IncomingLeadViewSet(LeadViewSet):
    def get_queryset(self):
        qs = Lead.objects.select_related('company', 'office', 'source', 'manager').filter(
            status__in=['new', 'contacted', 'qualified'],
            is_archived=False,
        )
        if not is_erp_admin(self.request.user):
            employee = get_employee_profile(self.request.user)
            personal = Q(manager=self.request.user) | Q(manager__isnull=True)
            if employee and employee.company_id:
                qs = qs.filter(personal | Q(company=employee.company)).distinct()
            else:
                qs = qs.filter(personal).distinct()

        ownership = self.request.query_params.get('ownership')
        if ownership == 'free':
            qs = qs.filter(manager__isnull=True)
        elif ownership == 'mine':
            qs = qs.filter(manager=self.request.user)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(full_name__icontains=search) | Q(phone__icontains=search) | Q(email__icontains=search))

        return qs.order_by('-created_at')


class ClientViewSet(viewsets.ModelViewSet):
    serializer_class = ClientSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        user = self.request.user
        if not is_erp_admin(user):
            employee = get_employee_profile(user)
            if not employee or not employee.company_id:
                raise PermissionDenied('Сначала назначьте сотруднику компанию.')
            expected = {'manager': user.pk, 'company': employee.company_id, 'office': employee.office_id}
            for field, expected_id in expected.items():
                if field in serializer.validated_data and getattr(serializer.validated_data[field], 'pk', None) != expected_id:
                    raise PermissionDenied('Создать клиента можно только в своей компании и офисе.')
        serializer.save()

    def perform_update(self, serializer):
        if not is_erp_admin(self.request.user):
            if serializer.instance.manager_id != self.request.user.pk:
                raise PermissionDenied('Изменять карточку может ответственный менеджер.')
            for field in ('manager', 'company', 'office'):
                incoming = serializer.validated_data.get(field)
                if field in serializer.validated_data and getattr(incoming, 'pk', None) != getattr(serializer.instance, field + '_id'):
                    raise PermissionDenied('Переназначать клиента может администратор.')
        serializer.save()

    def perform_destroy(self, instance):
        if not is_erp_admin(self.request.user) and instance.manager_id != self.request.user.pk:
            raise PermissionDenied('Удалять карточку может ответственный менеджер.')
        instance.delete()

    def get_queryset(self):
        qs = client_queryset_for_user(self.request.user)

        status_value = self.request.query_params.get('status')
        if status_value:
            qs = qs.filter(status=status_value)

        office_id = self.request.query_params.get('office')
        if office_id:
            qs = qs.filter(office_id=office_id)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(full_name__icontains=search) | qs.filter(phone__icontains=search) | qs.filter(email__icontains=search)

        return qs.distinct().order_by('-created_at')

    @action(detail=True, methods=['get'], url_path='360')
    def student_360(self, request, pk=None):
        client = self.get_object()
        return Response(build_student_360(
            client,
            user=request.user,
            include_sensitive=can_access_disk(request.user),
        ))

    @action(detail=True, methods=['get'], url_path='timeline')
    def timeline(self, request, pk=None):
        client = self.get_object()
        activities = ClientActivity.objects.filter(client=client).select_related('manager')[:50]
        notes = ClientNote.objects.filter(client=client).select_related('author')[:50]
        if not getattr(request.user, 'is_admin_role', False):
            notes = ClientNote.objects.filter(client=client).filter(Q(is_private=False) | Q(author=request.user)).select_related('author')[:50]
        files = ClientFile.objects.filter(client=client).select_related('uploaded_by')[:50]
        applications = Application.objects.filter(client=client).select_related(
            'manager', 'university', 'program', 'country_reference'
        )[:50]
        return Response({
            'client': ClientSerializer(client, context={'request': request}).data,
            'applications': ApplicationSerializer(applications, many=True, context={'request': request}).data,
            'activities': ClientActivitySerializer(activities, many=True, context={'request': request}).data,
            'notes': ClientNoteSerializer(notes, many=True, context={'request': request}).data,
            'files': ClientFileSerializer(files, many=True, context={'request': request}).data,
        })


class ApplicationViewSet(viewsets.ModelViewSet):
    serializer_class = ApplicationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Application.objects.select_related(
            'client', 'company', 'office', 'manager',
            'university', 'program', 'country_reference',
        )
        qs = qs.filter(client_id__in=client_queryset_for_user(self.request.user).values('pk'))

        status_value = self.request.query_params.get('status')
        if status_value:
            qs = qs.filter(status=status_value)

        client_id = self.request.query_params.get('client')
        if client_id:
            qs = qs.filter(client_id=client_id)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(client__full_name__icontains=search) | qs.filter(university_name__icontains=search) | qs.filter(program_name__icontains=search)

        return qs.order_by('-created_at')

    @action(detail=True, methods=['post'], url_path='transition')
    def transition(self, request, pk=None):
        application = self.get_object()
        try:
            application, history, changed = transition_application(
                application,
                str(request.data.get('stage') or '').strip(),
                actor=request.user,
                source_service='manager_api',
                comment=str(request.data.get('comment') or '')[:1000],
                event_id=request.data.get('event_id'),
            )
        except WorkflowTransitionError as exc:
            raise ValidationError(str(exc)) from exc
        return Response({
            'changed': changed,
            'history_id': history.pk if history else None,
            'application': self.get_serializer(application).data,
        })


class ApplicationExamViewSet(viewsets.ModelViewSet):
    serializer_class = ApplicationExamSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        visible_clients = client_queryset_for_user(self.request.user).values('pk')
        queryset = ApplicationExam.objects.select_related(
            'application', 'application__university', 'application__program',
            'student', 'responsible', 'created_by',
        ).filter(student_id__in=visible_clients)
        if self.request.query_params.get('student'):
            queryset = queryset.filter(student_id=self.request.query_params['student'])
        if self.request.query_params.get('application'):
            queryset = queryset.filter(application_id=self.request.query_params['application'])
        if self.request.query_params.get('status'):
            queryset = queryset.filter(status=self.request.query_params['status'])
        return queryset.order_by('scheduled_at')

    def _validate_scope(self, serializer):
        application = serializer.validated_data.get('application') or getattr(serializer.instance, 'application', None)
        if not application or not client_queryset_for_user(self.request.user).filter(pk=application.client_id).exists():
            raise PermissionDenied('Нет доступа к выбранной заявке.')

    def perform_create(self, serializer):
        self._validate_scope(serializer)
        serializer.save()

    def perform_update(self, serializer):
        self._validate_scope(serializer)
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        from .exam_registry import ExamRegistryError, upsert_application_exam

        exam = self.get_object()
        try:
            upsert_application_exam(
                application=exam.application,
                subject=exam.subject,
                scheduled_at=exam.scheduled_at,
                source_service=exam.source_service,
                source_id=exam.source_id,
                actor=request.user,
                event_id=request.data.get('event_id'),
                timezone=exam.timezone,
                join_url=exam.join_url,
                login=exam.login,
                status=ApplicationExam.STATUS_CANCELLED,
                result=exam.result,
                score=exam.score,
                retake_at=exam.retake_at,
                comment=(request.data.get('comment') or exam.comment)[:1000],
                responsible=exam.responsible,
                source_version=exam.source_version + 1,
                client_acknowledged_at=exam.client_acknowledged_at,
            )
        except ExamRegistryError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)


class ExternalAccountViewSet(viewsets.ModelViewSet):
    serializer_class = ExternalAccountSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ('get', 'post', 'put', 'patch', 'delete', 'head', 'options')

    def get_queryset(self):
        visible_clients = client_queryset_for_user(self.request.user).values('pk')
        queryset = ExternalAccount.objects.select_related(
            'student', 'application', 'responsible', 'created_by',
        ).filter(student_id__in=visible_clients)
        student = self.request.query_params.get('student')
        application = self.request.query_params.get('application')
        system = self.request.query_params.get('system')
        if student:
            queryset = queryset.filter(student_id=student)
        if application:
            queryset = queryset.filter(application_id=application)
        if system:
            queryset = queryset.filter(system=system)
        return queryset.order_by('-created_at')

    def _validate_write_scope(self, serializer):
        student = serializer.validated_data.get('student') or getattr(serializer.instance, 'student', None)
        if not student or not client_queryset_for_user(self.request.user).filter(pk=student.pk).exists():
            raise PermissionDenied('Нет доступа к выбранному студенту.')
        application = serializer.validated_data.get('application')
        if application and application.client_id != student.pk:
            raise ValidationError({'application': 'Заявка должна принадлежать выбранному студенту.'})

    def perform_create(self, serializer):
        self._validate_write_scope(serializer)
        serializer.save()

    def perform_update(self, serializer):
        self._validate_write_scope(serializer)
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        account = self.get_object()
        try:
            update_external_account(
                account,
                actor=request.user,
                source_service='manager_api',
                status=ExternalAccount.STATUS_ARCHIVED,
                notes=(account.notes or '')[:1000],
            )
        except ExternalAccountError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='reveal-secret')
    def reveal_secret(self, request, pk=None):
        account = self.get_object()
        if not (
            request.user.is_superuser
            or request.user.has_perm('crm.view_externalaccount_secret')
        ):
            raise PermissionDenied('Нет права на просмотр паролей внешних аккаунтов.')
        ActivityLog.objects.create(
            actor=request.user,
            service='manager_api',
            student=account.student,
            application=account.application,
            object_type='ExternalAccount',
            object_id=str(account.pk),
            action='EXTERNAL_ACCOUNT_SECRET_VIEWED',
            metadata={'system': account.system, 'provider_name': account.provider_name},
        )
        response = Response({'secret': decrypt_external_secret(account.secret_ciphertext)})
        response['Cache-Control'] = 'no-store'
        response['Pragma'] = 'no-cache'
        return response


class ClientActivityViewSet(viewsets.ModelViewSet):
    serializer_class = ClientActivitySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = ClientActivity.objects.select_related('client', 'manager', 'client__company', 'client__office')
        qs = qs.filter(client_id__in=client_queryset_for_user(self.request.user).values('pk'))

        client_id = self.request.query_params.get('client')
        if client_id:
            qs = qs.filter(client_id=client_id)

        return qs.distinct().order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(manager=self.request.user)


class ClientNoteViewSet(viewsets.ModelViewSet):
    serializer_class = ClientNoteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = ClientNote.objects.select_related('client', 'author', 'client__company', 'client__office')
        qs = qs.filter(client_id__in=client_queryset_for_user(self.request.user).values('pk'))
        if not getattr(self.request.user, 'is_admin_role', False):
            qs = qs.filter(Q(is_private=False) | Q(author=self.request.user))

        client_id = self.request.query_params.get('client')
        if client_id:
            qs = qs.filter(client_id=client_id)

        return qs.distinct().order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class ClientFileViewSet(viewsets.ModelViewSet):
    serializer_class = ClientFileSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.JSONParser, parsers.FormParser, parsers.MultiPartParser]

    def get_queryset(self):
        qs = ClientFile.objects.select_related('client', 'application', 'uploaded_by', 'client__company', 'client__office')
        qs = qs.filter(client_id__in=client_queryset_for_user(self.request.user).values('pk'))

        client_id = self.request.query_params.get('client')
        if client_id:
            qs = qs.filter(client_id=client_id)

        application_id = self.request.query_params.get('application')
        if application_id:
            qs = qs.filter(application_id=application_id)

        return qs.distinct().order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)

    @action(detail=True, methods=['get'])
    def versions(self, request, pk=None):
        document = self.get_object()
        queryset = document.versions.select_related('application', 'uploaded_by').order_by('-version_number')
        page = self.paginate_queryset(queryset)
        serializer = ClientFileVersionSerializer(page if page is not None else queryset, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='review-history')
    def review_history(self, request, pk=None):
        document = self.get_object()
        queryset = document.review_events.select_related('version', 'reviewer').order_by('-created_at')
        page = self.paginate_queryset(queryset)
        serializer = ClientFileReviewEventSerializer(page if page is not None else queryset, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)
