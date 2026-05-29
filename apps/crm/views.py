from django.db.models import Q
from rest_framework import parsers, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.core.permissions import filter_manager_owned, filter_by_office_scope, get_employee_profile, is_erp_admin

from .models import Application, Client, ClientActivity, ClientFile, ClientNote, Lead, LeadSource
from .serializers import (
    ApplicationSerializer,
    ClientActivitySerializer,
    ClientFileSerializer,
    ClientNoteSerializer,
    ClientSerializer,
    LeadSerializer,
    LeadSourceSerializer,
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

    def get_queryset(self):
        qs = Client.objects.select_related('company', 'office', 'manager', 'source_lead').prefetch_related('shared_with')
        user = self.request.user
        if not is_erp_admin(user):
            qs = filter_manager_owned(qs, user, manager_field='manager') | qs.filter(shared_with=user)

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

    @action(detail=True, methods=['get'], url_path='timeline')
    def timeline(self, request, pk=None):
        client = self.get_object()
        activities = ClientActivity.objects.filter(client=client).select_related('manager')[:50]
        notes = ClientNote.objects.filter(client=client).select_related('author')[:50]
        files = ClientFile.objects.filter(client=client).select_related('uploaded_by')[:50]
        applications = Application.objects.filter(client=client).select_related('manager')[:50]
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
        qs = Application.objects.select_related('client', 'company', 'office', 'manager')
        qs = filter_manager_owned(qs, self.request.user, manager_field='manager')

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


class ClientActivityViewSet(viewsets.ModelViewSet):
    serializer_class = ClientActivitySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = ClientActivity.objects.select_related('client', 'manager', 'client__company', 'client__office')
        if not is_erp_admin(self.request.user):
            qs = qs.filter(client__manager=self.request.user) | qs.filter(client__shared_with=self.request.user)

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
        if not is_erp_admin(self.request.user):
            qs = qs.filter(client__manager=self.request.user) | qs.filter(client__shared_with=self.request.user)
            qs = qs.exclude(is_private=True).union(ClientNote.objects.filter(author=self.request.user))

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
        if not is_erp_admin(self.request.user):
            qs = qs.filter(client__manager=self.request.user) | qs.filter(client__shared_with=self.request.user)

        client_id = self.request.query_params.get('client')
        if client_id:
            qs = qs.filter(client_id=client_id)

        application_id = self.request.query_params.get('application')
        if application_id:
            qs = qs.filter(application_id=application_id)

        return qs.distinct().order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)
