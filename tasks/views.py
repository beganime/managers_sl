from django.db.models import Q
from django.utils.dateparse import parse_datetime
from rest_framework import parsers, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Project, ProjectAttachment, ProjectTask, Task
from .serializers import (
    ProjectAttachmentSerializer,
    ProjectSerializer,
    ProjectTaskSerializer,
    TaskSerializer,
)


def is_admin_user(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or user.is_staff or getattr(user, 'role', None) == 'admin')
    )


class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def _is_admin(self, user):
        return is_admin_user(user)

    def _can_manage_task(self, user, task):
        if self._is_admin(user):
            return True
        return task.created_by_id == user.id or task.assigned_to_id == user.id

    def get_queryset(self):
        user = self.request.user
        qs = Task.objects.select_related('assigned_to', 'created_by', 'client')

        if not self._is_admin(user):
            qs = qs.filter(Q(assigned_to=user) | Q(created_by=user))

        params = self.request.query_params

        mine = str(params.get('mine', '')).lower()
        created_by_me = str(params.get('created_by_me', '')).lower()
        pinned = str(params.get('pinned', '')).lower()

        if mine in ('1', 'true', 'yes'):
            qs = qs.filter(assigned_to=user)

        if created_by_me in ('1', 'true', 'yes'):
            qs = qs.filter(created_by=user)

        if pinned in ('1', 'true', 'yes'):
            qs = qs.filter(is_pinned=True)

        task_status = params.get('status')
        if task_status:
            qs = qs.filter(status=task_status)

        updated_after = params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)

        return qs.order_by('-is_pinned', '-updated_at')

    def perform_create(self, serializer):
        assigned_to = serializer.validated_data.get('assigned_to') or self.request.user
        serializer.save(assigned_to=assigned_to, created_by=self.request.user)

    def perform_update(self, serializer):
        task = self.get_object()
        if not self._can_manage_task(self.request.user, task):
            raise permissions.PermissionDenied('Недостаточно прав для изменения задачи')
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        task = self.get_object()
        if not self._can_manage_task(request.user, task):
            return Response({'detail': 'Недостаточно прав для удаления задачи'}, status=status.HTTP_403_FORBIDDEN)
        self.perform_destroy(task)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='toggle-pin')
    def toggle_pin(self, request, pk=None):
        task = self.get_object()
        if not self._can_manage_task(request.user, task):
            return Response({'detail': 'Недостаточно прав'}, status=status.HTTP_403_FORBIDDEN)

        task.is_pinned = not task.is_pinned
        task.save(update_fields=['is_pinned', 'updated_at'])
        return Response(self.get_serializer(task).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='toggle-done')
    def toggle_done(self, request, pk=None):
        task = self.get_object()
        if not self._can_manage_task(request.user, task):
            return Response({'detail': 'Недостаточно прав'}, status=status.HTTP_403_FORBIDDEN)

        task.status = 'done' if task.status != 'done' else 'todo'
        task.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(task).data, status=status.HTTP_200_OK)


class ProjectAccessMixin:
    def is_admin(self, user):
        return is_admin_user(user)

    def can_access_project(self, user, project):
        if not user or not user.is_authenticated or not project:
            return False

        if self.is_admin(user):
            return True

        return (
            project.created_by_id == user.id
            or project.participants.filter(id=user.id).exists()
            or project.responsible_users.filter(id=user.id).exists()
        )

    def can_manage_project(self, user, project):
        if not user or not user.is_authenticated or not project:
            return False

        if self.is_admin(user):
            return True

        return project.created_by_id == user.id

    def can_manage_project_task(self, user, task):
        if not user or not user.is_authenticated or not task:
            return False

        if self.is_admin(user):
            return True

        return task.created_by_id == user.id

    def is_status_only_update(self, request):
        if request.method not in ('PATCH', 'PUT'):
            return False

        keys = set((request.data or {}).keys())
        return bool(keys) and keys.issubset({'status'})


class ProjectViewSet(ProjectAccessMixin, viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.JSONParser, parsers.FormParser, parsers.MultiPartParser]

    def get_queryset(self):
        user = self.request.user
        qs = Project.objects.select_related('created_by', 'office').prefetch_related(
            'participants',
            'responsible_users',
            'items',
            'items__assigned_to',
            'items__created_by',
            'items__subtasks',
            'items__subtasks__assigned_to',
            'items__subtasks__created_by',
            'attachments',
        )

        if not self.is_admin(user):
            qs = qs.filter(
                Q(created_by=user) | Q(participants=user) | Q(responsible_users=user),
                is_hidden=False,
            ).distinct()

        params = self.request.query_params

        creator = params.get('creator') or params.get('created_by')
        if creator and self.is_admin(user):
            qs = qs.filter(created_by_id=creator)

        city = params.get('city')
        if city:
            qs = qs.filter(Q(city__iexact=city) | Q(office__city__iexact=city))

        office = params.get('office')
        if office:
            qs = qs.filter(office_id=office)

        status_value = params.get('status')
        if status_value:
            qs = qs.filter(status=status_value)

        hidden = str(params.get('hidden', '')).lower()
        if hidden in ('1', 'true', 'yes') and self.is_admin(user):
            qs = qs.filter(is_hidden=True)
        elif hidden in ('0', 'false', 'no'):
            qs = qs.filter(is_hidden=False)

        search = params.get('search')
        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(description__icontains=search))

        updated_after = params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)

        ordering = params.get('ordering') or '-updated_at'
        allowed = {'-updated_at', 'updated_at', '-created_at', 'created_at', 'title', '-title', 'deadline', '-deadline'}
        if ordering not in allowed:
            ordering = '-updated_at'

        return qs.order_by('-is_pinned', ordering)

    def perform_create(self, serializer):
        project = serializer.save(created_by=self.request.user)
        project.participants.add(self.request.user)

    def perform_update(self, serializer):
        project = self.get_object()
        if not self.can_manage_project(self.request.user, project):
            raise permissions.PermissionDenied('Изменять проект может создатель или администратор.')
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        project = self.get_object()
        if not self.can_manage_project(request.user, project):
            return Response({'detail': 'Удалять проект может создатель или администратор.'}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='toggle-hidden')
    def toggle_hidden(self, request, pk=None):
        if not self.is_admin(request.user):
            return Response({'detail': 'Только администратор может скрывать проекты.'}, status=status.HTTP_403_FORBIDDEN)

        project = self.get_object()
        project.is_hidden = not project.is_hidden
        project.save(update_fields=['is_hidden', 'updated_at'])
        return Response(self.get_serializer(project).data)

    @action(detail=True, methods=['post'], url_path='add-participant')
    def add_participant(self, request, pk=None):
        project = self.get_object()
        if not self.can_manage_project(request.user, project):
            return Response({'detail': 'Нет прав'}, status=status.HTTP_403_FORBIDDEN)

        user_id = request.data.get('user') or request.data.get('user_id')
        if not user_id:
            return Response({'detail': 'user_id обязателен'}, status=status.HTTP_400_BAD_REQUEST)

        project.participants.add(user_id)
        return Response(self.get_serializer(project).data)

    @action(detail=True, methods=['post'], url_path='remove-participant')
    def remove_participant(self, request, pk=None):
        project = self.get_object()
        if not self.can_manage_project(request.user, project):
            return Response({'detail': 'Нет прав'}, status=status.HTTP_403_FORBIDDEN)

        user_id = request.data.get('user') or request.data.get('user_id')
        if not user_id:
            return Response({'detail': 'user_id обязателен'}, status=status.HTTP_400_BAD_REQUEST)

        project.participants.remove(user_id)
        return Response(self.get_serializer(project).data)


class ProjectTaskViewSet(ProjectAccessMixin, viewsets.ModelViewSet):
    serializer_class = ProjectTaskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = ProjectTask.objects.select_related(
            'project',
            'parent',
            'assigned_to',
            'created_by',
        ).prefetch_related(
            'subtasks',
            'subtasks__assigned_to',
            'subtasks__created_by',
        )

        if not self.is_admin(user):
            qs = qs.filter(
                Q(project__created_by=user)
                | Q(project__participants=user)
                | Q(project__responsible_users=user)
                | Q(assigned_to=user),
                project__is_hidden=False,
            ).distinct()

        project_id = self.request.query_params.get('project')
        if project_id:
            qs = qs.filter(project_id=project_id)

        parent = self.request.query_params.get('parent')
        if parent:
            if str(parent).lower() in ('root', 'null', 'none', '0'):
                qs = qs.filter(parent__isnull=True)
            else:
                qs = qs.filter(parent_id=parent)

        status_value = self.request.query_params.get('status')
        if status_value:
            qs = qs.filter(status=status_value)

        assigned_to = self.request.query_params.get('assigned_to')
        if assigned_to:
            qs = qs.filter(assigned_to_id=assigned_to)

        return qs.order_by('parent_id', 'status', 'order', '-updated_at')

    def perform_create(self, serializer):
        project = serializer.validated_data.get('project')
        parent = serializer.validated_data.get('parent')

        if not self.can_access_project(self.request.user, project):
            raise permissions.PermissionDenied('Нет доступа к проекту.')

        if parent and parent.project_id != project.id:
            raise permissions.PermissionDenied('Подзадача должна быть внутри того же проекта.')

        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        item = self.get_object()

        if not self.can_access_project(self.request.user, item.project):
            raise permissions.PermissionDenied('Нет доступа к проекту.')

        if self.is_status_only_update(self.request):
            serializer.save()
            return

        if not self.can_manage_project_task(self.request.user, item):
            raise permissions.PermissionDenied('Редактировать задачу может только создатель или администратор.')

        parent = serializer.validated_data.get('parent')
        project = serializer.validated_data.get('project') or item.project

        if parent and parent.project_id != project.id:
            raise permissions.PermissionDenied('Подзадача должна быть внутри того же проекта.')

        if parent and parent.id == item.id:
            raise permissions.PermissionDenied('Задача не может быть родителем самой себя.')

        serializer.save()

    def destroy(self, request, *args, **kwargs):
        item = self.get_object()

        if not self.can_access_project(request.user, item.project):
            return Response({'detail': 'Нет доступа'}, status=status.HTTP_403_FORBIDDEN)

        if not self.can_manage_project_task(request.user, item):
            return Response({'detail': 'Удалять задачу может только создатель или администратор.'}, status=status.HTTP_403_FORBIDDEN)

        return super().destroy(request, *args, **kwargs)


class ProjectAttachmentViewSet(ProjectAccessMixin, viewsets.ModelViewSet):
    serializer_class = ProjectAttachmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.JSONParser, parsers.FormParser, parsers.MultiPartParser]

    def get_queryset(self):
        user = self.request.user
        qs = ProjectAttachment.objects.select_related('project', 'uploaded_by')

        if not self.is_admin(user):
            qs = qs.filter(
                Q(project__created_by=user)
                | Q(project__participants=user)
                | Q(project__responsible_users=user),
                project__is_hidden=False,
            ).distinct()

        project_id = self.request.query_params.get('project')
        if project_id:
            qs = qs.filter(project_id=project_id)

        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        project = serializer.validated_data.get('project')
        if not self.can_access_project(self.request.user, project):
            raise permissions.PermissionDenied('Нет доступа к проекту.')
        serializer.save(uploaded_by=self.request.user)

    def perform_update(self, serializer):
        attachment = self.get_object()
        if not self.can_access_project(self.request.user, attachment.project):
            raise permissions.PermissionDenied('Нет доступа к проекту.')
        serializer.save()