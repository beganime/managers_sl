from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import parsers, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.attendance.models import WorkDay
from apps.core.permissions import filter_manager_owned, get_employee_profile, is_erp_admin
from apps.crm.models import Client, Lead
from apps.education.models import Program, University
from apps.employees.models import EmployeeProfile
from apps.erp_documents.models import GeneratedDocument
from apps.erp_notifications.models import Notification
from apps.finance.models import Deal
from apps.organizations.models import Company, Office
from apps.portal.models import CalendarEvent
from apps.projects_v2.models import ProjectTask
from users.serializers import UserSerializer


User = get_user_model()


class CalendarEventSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source='owner.get_full_name', read_only=True)
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)
    participants_names = serializers.SerializerMethodField()
    participants = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=User.objects.all(),
        required=False,
    )
    office = serializers.PrimaryKeyRelatedField(
        queryset=Office.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = CalendarEvent
        fields = (
            'id',
            'title',
            'description',
            'event_date',
            'start_time',
            'end_time',
            'visibility',
            'is_active',
            'company',
            'company_name',
            'office',
            'office_name',
            'owner',
            'owner_name',
            'participants',
            'participants_names',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('company', 'owner', 'created_at', 'updated_at')

    def get_participants_names(self, obj):
        return [user.get_full_name() or user.email for user in obj.participants.all()]

    def validate(self, attrs):
        start_time = attrs.get('start_time', getattr(self.instance, 'start_time', None))
        end_time = attrs.get('end_time', getattr(self.instance, 'end_time', None))
        if start_time and end_time and end_time < start_time:
            raise serializers.ValidationError({'end_time': 'End time must be later than start time.'})
        return attrs


def default_company():
    return Company.objects.order_by('id').first()


def user_company_office(user):
    employee = get_employee_profile(user)
    if employee:
        return employee.company, employee.office
    return default_company(), None


def calendar_queryset_for_user(user):
    qs = CalendarEvent.objects.select_related('company', 'office', 'owner', 'created_by').prefetch_related('participants').filter(is_active=True)

    if is_erp_admin(user):
        return qs

    employee = get_employee_profile(user)
    visibility_q = Q(owner=user) | Q(participants=user)

    if employee and employee.company_id:
        visibility_q |= Q(company=employee.company, visibility=CalendarEvent.VISIBILITY_COMPANY)
        if employee.office_id:
            visibility_q |= Q(company=employee.company, office=employee.office, visibility=CalendarEvent.VISIBILITY_OFFICE)

    return qs.filter(visibility_q).distinct()


def filtered_calendar_queryset(request):
    qs = calendar_queryset_for_user(request.user)

    day = request.query_params.get('day')
    if day:
        parsed_day = parse_date(day)
        if parsed_day:
            qs = qs.filter(event_date=parsed_day)

    date_from = request.query_params.get('date_from')
    if date_from:
        parsed_from = parse_date(date_from)
        if parsed_from:
            qs = qs.filter(event_date__gte=parsed_from)

    date_to = request.query_params.get('date_to')
    if date_to:
        parsed_to = parse_date(date_to)
        if parsed_to:
            qs = qs.filter(event_date__lte=parsed_to)

    search = request.query_params.get('search')
    if search:
        qs = qs.filter(Q(title__icontains=search) | Q(description__icontains=search))

    return qs.order_by('event_date', 'start_time', 'title')


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.JSONParser, parsers.FormParser, parsers.MultiPartParser]

    def get(self, request):
        return Response(UserSerializer(request.user, context={'request': request}).data)

    def patch(self, request):
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data or {})
        data.pop('role', None)
        data.pop('is_superuser', None)
        data.pop('is_staff', None)

        for file_field in ('avatar', 'image', 'photo', 'file', 'upload'):
            if file_field in request.FILES:
                data['avatar'] = request.FILES[file_field]
                break

        if data.get('dob') in ('', 'null', 'undefined'):
            data['dob'] = None

        serializer = UserSerializer(request.user, data=data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class DashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        today = timezone.localdate()
        employee = get_employee_profile(user)

        leads_qs = filter_manager_owned(Lead.objects.all(), user, manager_field='manager')
        clients_qs = filter_manager_owned(Client.objects.all(), user, manager_field='manager')
        tasks_qs = ProjectTask.objects.select_related('project', 'assigned_to')
        if not is_erp_admin(user):
            tasks_qs = tasks_qs.filter(Q(assigned_to=user) | Q(created_by=user) | Q(watchers__user=user)).distinct()
        deals_qs = filter_manager_owned(Deal.objects.all(), user, manager_field='manager')
        notifications_qs = Notification.objects.filter(recipient=user)
        workday = WorkDay.objects.filter(employee=user, date=today).first()

        salary = getattr(user, 'managersalary', None)
        balance = float(getattr(salary, 'current_balance', 0) or 0)
        rating = float(getattr(employee, 'rating', 0) or 0) if employee else 0

        return Response({
            'workday': {
                'id': workday.id,
                'status': workday.status,
                'started_at': workday.started_at,
                'closed_at': workday.closed_at,
                'date': workday.date,
                'total_minutes': round((workday.total_work_seconds or 0) / 60),
            } if workday else None,
            'stats': {
                'leads': leads_qs.filter(is_archived=False).count(),
                'clients': clients_qs.count(),
                'tasks': tasks_qs.exclude(status='done').count(),
                'deals': deals_qs.count(),
                'notifications': notifications_qs.filter(read_at__isnull=True).exclude(status=Notification.STATUS_READ).count(),
                'rating': rating,
                'balance': balance,
            },
            'today': {
                'tasks': list(
                    tasks_qs.filter(deadline__date=today)
                    .exclude(status='done')
                    .order_by('deadline')
                    .values('id', 'title', 'status', 'priority', 'deadline')[:8]
                ),
                'events': CalendarEventSerializer(
                    calendar_queryset_for_user(user).filter(event_date=today)[:8],
                    many=True,
                    context={'request': request},
                ).data,
            },
            'warnings': [],
        })


class CalendarEventListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        limit = min(int(request.query_params.get('limit', 50) or 50), 200)
        offset = int(request.query_params.get('offset', 0) or 0)
        qs = filtered_calendar_queryset(request)
        count = qs.count()
        serializer = CalendarEventSerializer(qs[offset:offset + limit], many=True, context={'request': request})
        return Response({'count': count, 'next': None, 'previous': None, 'results': serializer.data})

    def post(self, request):
        serializer = CalendarEventSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        company, office = user_company_office(request.user)
        if not company:
            return Response({'detail': 'Company is required to create calendar event.'}, status=status.HTTP_400_BAD_REQUEST)
        event = serializer.save(
            owner=request.user,
            created_by=request.user,
            company=company,
            office=serializer.validated_data.get('office') or office,
        )
        return Response(CalendarEventSerializer(event, context={'request': request}).data, status=status.HTTP_201_CREATED)


class CalendarEventDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, request, pk):
        return get_object_or_404(calendar_queryset_for_user(request.user), pk=pk)

    def get(self, request, pk):
        return Response(CalendarEventSerializer(self.get_object(request, pk), context={'request': request}).data)

    def patch(self, request, pk):
        event = self.get_object(request, pk)
        if event.owner_id != request.user.id and not is_erp_admin(request.user):
            return Response({'detail': 'Only owner or admin can edit this event.'}, status=status.HTTP_403_FORBIDDEN)
        serializer = CalendarEventSerializer(event, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        event = self.get_object(request, pk)
        if event.owner_id != request.user.id and not is_erp_admin(request.user):
            return Response({'detail': 'Only owner or admin can delete this event.'}, status=status.HTTP_403_FORBIDDEN)
        event.is_active = False
        event.save(update_fields=['is_active', 'updated_at'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class MobileBootstrapView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response({
            'user': UserSerializer(request.user, context={'request': request}).data,
            'server_time': timezone.localtime().isoformat(),
            'endpoints': {
                'me': '/api/v1/me/',
                'dashboard': '/api/v1/dashboard/',
                'calendar_events': '/api/v1/calendar/events/',
                'search': '/api/v1/mobile/search/',
                'rating': '/api/v1/rating/',
            },
            'features': {
                'crm': True,
                'education': True,
                'finance': True,
                'documents': True,
                'calendar': True,
                'push_notifications': True,
            },
        })


class MobileSearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        query = (request.query_params.get('q') or request.query_params.get('search') or '').strip()
        if len(query) < 2:
            return Response({'count': 0, 'results': []})

        results = []

        def add(kind, obj_id, title, subtitle='', route=''):
            results.append({
                'type': kind,
                'id': obj_id,
                'title': title,
                'name': title,
                'subtitle': subtitle,
                'route': route,
            })

        for client in filter_manager_owned(Client.objects.all(), request.user, manager_field='manager').filter(
            Q(full_name__icontains=query) | Q(phone__icontains=query) | Q(email__icontains=query)
        )[:8]:
            add('client', client.id, client.full_name, client.phone or client.email, f'/(app)/crm/clients/{client.id}')

        for lead in filter_manager_owned(Lead.objects.all(), request.user, manager_field='manager').filter(
            Q(full_name__icontains=query) | Q(phone__icontains=query) | Q(email__icontains=query)
        )[:8]:
            add('lead', lead.id, lead.full_name, lead.phone or lead.email, f'/(app)/crm/leads/{lead.id}')

        for university in University.objects.filter(Q(name__icontains=query) | Q(country__name__icontains=query) | Q(city__name__icontains=query))[:8]:
            add('university', university.id, university.name, university.country.name, f'/(app)/education/universities/{university.id}')

        for program in Program.objects.select_related('university').filter(Q(name__icontains=query) | Q(faculty__icontains=query) | Q(university__name__icontains=query))[:8]:
            add('program', program.id, program.name, program.university.name, f'/(app)/education/programs/{program.id}')

        task_qs = ProjectTask.objects.filter(Q(title__icontains=query) | Q(description__icontains=query))
        if not is_erp_admin(request.user):
            task_qs = task_qs.filter(
                Q(assigned_to=request.user) |
                Q(created_by=request.user) |
                Q(watchers__user=request.user)
            ).distinct()
        for task in task_qs[:8]:
            add('task', task.id, task.title, task.status, f'/(app)/tasks-v2/{task.id}')

        document_qs = GeneratedDocument.objects.filter(Q(title__icontains=query) | Q(client__full_name__icontains=query))
        if not is_erp_admin(request.user):
            document_qs = document_qs.filter(
                Q(manager=request.user) |
                Q(client__shared_with=request.user)
            ).distinct()
        for document in document_qs[:8]:
            add('document', document.id, document.title, document.status, f'/(app)/documents-v2/generated/{document.id}')

        return Response({'count': len(results), 'results': results[:30]})


class RatingView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = User.objects.select_related('office', 'managersalary').filter(is_active=True)
        search = request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search) |
                Q(job_description__icontains=search) |
                Q(office__city__icontains=search)
            )

        role = request.query_params.get('role')
        if role and role != 'all':
            qs = qs.filter(role=role)

        position = request.query_params.get('position')
        if position and position != 'all':
            qs = qs.filter(Q(job_description__icontains=position) | Q(role__icontains=position))

        users = list(qs.order_by('first_name', 'last_name', 'email'))
        profiles = EmployeeProfile.objects.select_related('company', 'office').filter(user_id__in=[user.id for user in users])
        profile_by_user = {profile.user_id: profile for profile in profiles}

        rows = []
        for user in users:
            profile = profile_by_user.get(user.id)
            salary = getattr(user, 'managersalary', None)
            role_display = user.get_role_display() if hasattr(user, 'get_role_display') else user.role
            job_description = (getattr(user, 'job_description', '') or '').strip()
            position_label = job_description.splitlines()[0].strip() if job_description else role_display
            score = float(getattr(profile, 'rating', 0) or 0) if profile else 0
            rows.append({
                'id': profile.id if profile else user.id,
                'user_id': user.id,
                'name': user.get_full_name() or user.email,
                'full_name': user.get_full_name() or user.email,
                'email': user.email,
                'role': user.role,
                'role_display': role_display,
                'position': position_label,
                'job_description': job_description,
                'office_name': (
                    profile.office.city if profile and profile.office_id
                    else user.office.city if getattr(user, 'office_id', None)
                    else ''
                ),
                'company_name': profile.company.name if profile else '',
                'score': score,
                'revenue_usd': float(getattr(salary, 'current_month_revenue', 0) or 0),
            })

        rows.sort(key=lambda item: (-item['score'], item['name']))
        count = len(rows)
        limit = min(int(request.query_params.get('limit', 50) or 50), 200)
        offset = int(request.query_params.get('offset', 0) or 0)

        results = []
        for index, item in enumerate(rows[offset:offset + limit], start=offset + 1):
            item['rank'] = index
            results.append(item)

        return Response({'count': count, 'next': None, 'previous': None, 'results': results})
