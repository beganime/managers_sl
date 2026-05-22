from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import parsers, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.permissions import get_employee_profile, is_erp_admin
from apps.organizations.models import Company, Office

from .models import (
    Project,
    ProjectNote,
    ProjectSection,
    ProjectTask,
    TaskAttachment,
    TaskChecklist,
    TaskChecklistItem,
    TaskComment,
    TaskWatcher,
)
from .serializers import (
    ProjectNoteSerializer,
    ProjectSectionSerializer,
    ProjectSerializer,
    ProjectTaskSerializer,
    TaskAttachmentSerializer,
    TaskChecklistItemSerializer,
    TaskChecklistSerializer,
    TaskCommentSerializer,
    TaskWatcherSerializer,
)

User = get_user_model()


def employee_scope_filter(user):
    if is_erp_admin(user):
        return Q()

    employee = get_employee_profile(user)
    if not employee:
        return Q(created_by=user) | Q(owner=user) | Q(participants=user) | Q(responsible_users=user)

    access = getattr(employee, 'access', None)
    role_type = employee.role.role_type if employee.role_id else None

    if role_type == 'company_owner' or (access and access.can_see_all_company):
        return Q(company=employee.company)

    if role_type == 'office_director' or (access and access.can_see_all_office):
        if employee.office_id:
            return Q(company=employee.company, office=employee.office)
        return Q(company=employee.company)

    return Q(created_by=user) | Q(owner=user) | Q(participants=user) | Q(responsible_users=user) | Q(tasks__assigned_to=user) | Q(tasks__watchers__user=user)


def resolve_company_office(user, data=None):
    data = data or {}
    employee = get_employee_profile(user)
    if employee and not is_erp_admin(user):
        return employee.company, employee.office

    company_id = data.get('company') or (employee.company_id if employee else None)
    if not company_id:
        raise ValidationError({'company': 'Company is required.'})

    company = Company.objects.filter(pk=company_id).first()
    if not company:
        raise ValidationError({'company': 'Company not found.'})

    office = None
    office_id = data.get('office') or (employee.office_id if employee else None)
    if office_id:
        office = Office.objects.filter(pk=office_id, company=company).first()
        if not office:
            raise ValidationError({'office': 'Office does not belong to selected company.'})
    return company, office


def project_queryset_for_user(user):
    qs = Project.objects.select_related('company', 'office', 'created_by', 'owner').prefetch_related(
        'participants',
        'responsible_users',
        'sections',
        'notes',
    )
    return qs.filter(employee_scope_filter(user)).distinct()


def apply_project_filters(qs, request):
    company = request.query_params.get('company')
    if company:
        qs = qs.filter(company_id=company)

    office = request.query_params.get('office')
    if office:
        qs = qs.filter(office_id=office)

    status_value = request.query_params.get('status')
    if status_value:
        qs = qs.filter(status=status_value)

    owner = request.query_params.get('owner')
    if owner:
        qs = qs.filter(owner_id=owner)

    participant = request.query_params.get('participant')
    if participant:
        qs = qs.filter(participants__id=participant)

    search = request.query_params.get('search')
    if search:
        qs = qs.filter(Q(title__icontains=search) | Q(code__icontains=search) | Q(description__icontains=search))

    return qs


def apply_task_filters(qs, request):
    project = request.query_params.get('project')
    if project:
        qs = qs.filter(project_id=project)

    section = request.query_params.get('section')
    if section:
        qs = qs.filter(section_id=section)

    status_value = request.query_params.get('status')
    if status_value:
        qs = qs.filter(status=status_value)

    priority = request.query_params.get('priority')
    if priority:
        qs = qs.filter(priority=priority)

    assigned_to = request.query_params.get('assigned_to') or request.query_params.get('assignee')
    if assigned_to:
        qs = qs.filter(assigned_to_id=assigned_to)

    date_from = request.query_params.get('date_from')
    if date_from:
        qs = qs.filter(created_at__gte=date_from)

    date_to = request.query_params.get('date_to')
    if date_to:
        qs = qs.filter(created_at__lte=date_to)

    search = request.query_params.get('search')
    if search:
        qs = qs.filter(Q(title__icontains=search) | Q(description__icontains=search) | Q(project__title__icontains=search))

    return qs


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = project_queryset_for_user(self.request.user)
        return apply_project_filters(qs, self.request).order_by('-is_pinned', '-updated_at')

    def perform_create(self, serializer):
        company, office = resolve_company_office(self.request.user, self.request.data)
        owner = serializer.validated_data.get('owner') or self.request.user
        serializer.save(company=company, office=office, created_by=self.request.user, owner=owner)


class ProjectSectionViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSectionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        project_ids = project_queryset_for_user(self.request.user).values('id')
        qs = ProjectSection.objects.select_related('project', 'project__company', 'project__office').filter(project_id__in=project_ids)
        project = self.request.query_params.get('project')
        if project:
            qs = qs.filter(project_id=project)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(description__icontains=search))
        return qs.order_by('project__title', 'sort_order', 'title')


class ProjectTaskViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectTaskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        project_ids = project_queryset_for_user(self.request.user).values('id')
        qs = ProjectTask.objects.select_related(
            'project',
            'section',
            'parent',
            'assigned_to',
            'created_by',
            'completed_by',
        ).prefetch_related('checklists', 'watchers').filter(project_id__in=project_ids)
        return apply_task_filters(qs, self.request).distinct().order_by('project__title', 'section__sort_order', 'sort_order', '-updated_at')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'], url_path='add_comment')
    def add_comment(self, request, pk=None):
        task = self.get_object()
        text = request.data.get('text') or request.data.get('comment') or ''
        if not str(text).strip():
            raise ValidationError({'text': 'Comment text is required.'})
        comment = TaskComment.objects.create(task=task, author=request.user, text=text)
        return Response(TaskCommentSerializer(comment, context={'request': request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='complete_task')
    def complete_task(self, request, pk=None):
        task = self.get_object()
        task.complete(user=request.user)
        return Response(self.get_serializer(task).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='reopen_task')
    def reopen_task(self, request, pk=None):
        task = self.get_object()
        task.reopen()
        return Response(self.get_serializer(task).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='assign')
    def assign(self, request, pk=None):
        task = self.get_object()
        user_id = request.data.get('user') or request.data.get('assigned_to')
        if not user_id:
            raise ValidationError({'user': 'User id is required.'})
        user = User.objects.filter(pk=user_id).first()
        if not user:
            raise ValidationError({'user': 'User not found.'})
        task.assigned_to = user
        task.save(update_fields=['assigned_to', 'updated_at'])
        TaskWatcher.objects.get_or_create(task=task, user=user)
        return Response(self.get_serializer(task).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='add_watcher')
    def add_watcher(self, request, pk=None):
        task = self.get_object()
        user_id = request.data.get('user') or request.data.get('watcher') or request.user.id
        user = User.objects.filter(pk=user_id).first()
        if not user:
            raise ValidationError({'user': 'User not found.'})
        watcher, _ = TaskWatcher.objects.get_or_create(task=task, user=user)
        return Response(TaskWatcherSerializer(watcher, context={'request': request}).data, status=status.HTTP_201_CREATED)


class TaskCommentViewSet(viewsets.ModelViewSet):
    serializer_class = TaskCommentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        project_ids = project_queryset_for_user(self.request.user).values('id')
        qs = TaskComment.objects.select_related('task', 'author', 'task__project').filter(task__project_id__in=project_ids)
        task = self.request.query_params.get('task')
        if task:
            qs = qs.filter(task_id=task)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(text__icontains=search) | Q(task__title__icontains=search) | Q(author__email__icontains=search))
        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class TaskChecklistViewSet(viewsets.ModelViewSet):
    serializer_class = TaskChecklistSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        project_ids = project_queryset_for_user(self.request.user).values('id')
        qs = TaskChecklist.objects.select_related('task', 'task__project').prefetch_related('items').filter(task__project_id__in=project_ids)
        task = self.request.query_params.get('task')
        if task:
            qs = qs.filter(task_id=task)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(task__title__icontains=search))
        return qs.order_by('task__title', 'sort_order', 'title')


class TaskChecklistItemViewSet(viewsets.ModelViewSet):
    serializer_class = TaskChecklistItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        project_ids = project_queryset_for_user(self.request.user).values('id')
        qs = TaskChecklistItem.objects.select_related('checklist', 'checklist__task', 'done_by').filter(checklist__task__project_id__in=project_ids)
        checklist = self.request.query_params.get('checklist')
        if checklist:
            qs = qs.filter(checklist_id=checklist)
        is_done = self.request.query_params.get('is_done')
        if is_done in ('1', 'true', 'True', '0', 'false', 'False'):
            qs = qs.filter(is_done=is_done in ('1', 'true', 'True'))
        return qs.order_by('checklist__title', 'sort_order', 'title')


class TaskAttachmentViewSet(viewsets.ModelViewSet):
    serializer_class = TaskAttachmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.JSONParser, parsers.FormParser, parsers.MultiPartParser]

    def get_queryset(self):
        project_ids = project_queryset_for_user(self.request.user).values('id')
        qs = TaskAttachment.objects.select_related('task', 'uploaded_by', 'task__project').filter(task__project_id__in=project_ids)
        task = self.request.query_params.get('task')
        if task:
            qs = qs.filter(task_id=task)
        attachment_type = self.request.query_params.get('attachment_type')
        if attachment_type:
            qs = qs.filter(attachment_type=attachment_type)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(url__icontains=search) | Q(note__icontains=search) | Q(task__title__icontains=search))
        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)


class ProjectNoteViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectNoteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        project_ids = project_queryset_for_user(self.request.user).values('id')
        qs = ProjectNote.objects.select_related('project', 'author').filter(project_id__in=project_ids)
        if not is_erp_admin(self.request.user):
            qs = qs.filter(Q(is_private=False) | Q(author=self.request.user))
        project = self.request.query_params.get('project')
        if project:
            qs = qs.filter(project_id=project)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(content__icontains=search))
        return qs.order_by('-is_pinned', '-created_at')

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class TaskWatcherViewSet(viewsets.ModelViewSet):
    serializer_class = TaskWatcherSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        project_ids = project_queryset_for_user(self.request.user).values('id')
        qs = TaskWatcher.objects.select_related('task', 'user', 'task__project').filter(task__project_id__in=project_ids)
        task = self.request.query_params.get('task')
        if task:
            qs = qs.filter(task_id=task)
        user = self.request.query_params.get('user')
        if user:
            qs = qs.filter(user_id=user)
        return qs.order_by('-created_at')
