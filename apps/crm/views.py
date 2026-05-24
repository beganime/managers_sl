from django.utils import timezone
from rest_framework import parsers, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import filter_manager_owned, filter_by_office_scope, is_erp_admin

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

        status_value = self.request.query_params.get('status')
        if status_value:
            qs = qs.filter(status=status_value)

        office_id = self.request.query_params.get('office')
        if office_id:
            qs = qs.filter(office_id=office_id)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(full_name__icontains=search) | qs.filter(phone__icontains=search) | qs.filter(email__icontains=search)

        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        user = self.request.user
        data = serializer.validated_data
        if not data.get('manager'):
            serializer.save(manager=user)
        else:
            serializer.save()

    @action(detail=True, methods=['post'], url_path='convert')
    def convert(self, request, pk=None):
        lead = self.get_object()
        if hasattr(lead, 'client') and lead.client:
            return Response({'detail': 'По этому лиду уже создан клиент.', 'client_id': lead.client.id}, status=status.HTTP_400_BAD_REQUEST)

        manager = lead.manager or request.user
        client = Client.objects.create(
            company=lead.company,
            office=lead.office,
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
        lead.status = 'converted'
        lead.converted_at = timezone.now()
        lead.save(update_fields=['status', 'converted_at', 'updated_at'])
        return Response({'detail': 'Лид конвертирован в клиента.', 'client': ClientSerializer(client, context={'request': request}).data})


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
