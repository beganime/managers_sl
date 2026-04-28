from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Project, ProjectAttachment, ProjectTask, Task

User = get_user_model()


class TaskUserMiniSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'first_name', 'last_name', 'full_name', 'email')

    def get_full_name(self, obj):
        return f'{obj.first_name} {obj.last_name}'.strip() or obj.email


class TaskSerializer(serializers.ModelSerializer):
    assigned_to_data = TaskUserMiniSerializer(source='assigned_to', read_only=True)
    created_by_data = TaskUserMiniSerializer(source='created_by', read_only=True)

    class Meta:
        model = Task
        fields = (
            'id',
            'title',
            'description',
            'assigned_to',
            'assigned_to_data',
            'created_by',
            'created_by_data',
            'client',
            'status',
            'priority',
            'is_pinned',
            'deadline',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('created_by', 'created_at', 'updated_at')
        extra_kwargs = {
            'assigned_to': {'required': False},
            'client': {'required': False, 'allow_null': True},
            'deadline': {'required': False, 'allow_null': True},
        }


class ProjectAttachmentSerializer(serializers.ModelSerializer):
    uploaded_by_data = TaskUserMiniSerializer(source='uploaded_by', read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = ProjectAttachment
        fields = (
            'id',
            'project',
            'uploaded_by',
            'uploaded_by_data',
            'title',
            'attachment_type',
            'file',
            'file_url',
            'url',
            'note',
            'created_at',
        )
        read_only_fields = ('uploaded_by', 'created_at')
        extra_kwargs = {
            'file': {'required': False, 'allow_null': True},
            'url': {'required': False, 'allow_blank': True},
            'title': {'required': False, 'allow_blank': True},
            'note': {'required': False, 'allow_blank': True},
        }

    def get_file_url(self, obj):
        if not obj.file:
            return None
        try:
            url = obj.file.url
        except Exception:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(url) if request else url

    def validate(self, attrs):
        attachment_type = attrs.get('attachment_type') or getattr(self.instance, 'attachment_type', 'file')
        file_value = attrs.get('file') or getattr(self.instance, 'file', None)
        url_value = attrs.get('url') or getattr(self.instance, 'url', '')

        if attachment_type in ('file', 'image') and not file_value:
            raise serializers.ValidationError({'file': 'Для файла/фото нужно загрузить файл.'})
        if attachment_type == 'link' and not str(url_value or '').strip():
            raise serializers.ValidationError({'url': 'Для ссылки нужно указать URL.'})
        return attrs


class ProjectSubtaskSerializer(serializers.ModelSerializer):
    assigned_to_data = TaskUserMiniSerializer(source='assigned_to', read_only=True)
    created_by_data = TaskUserMiniSerializer(source='created_by', read_only=True)

    class Meta:
        model = ProjectTask
        fields = (
            'id',
            'project',
            'parent',
            'title',
            'description',
            'assigned_to',
            'assigned_to_data',
            'created_by',
            'created_by_data',
            'status',
            'priority',
            'deadline',
            'order',
            'created_at',
            'updated_at',
        )


class ProjectTaskSerializer(serializers.ModelSerializer):
    assigned_to_data = TaskUserMiniSerializer(source='assigned_to', read_only=True)
    created_by_data = TaskUserMiniSerializer(source='created_by', read_only=True)
    subtasks = serializers.SerializerMethodField()
    subtasks_count = serializers.SerializerMethodField()

    class Meta:
        model = ProjectTask
        fields = (
            'id',
            'project',
            'parent',
            'subtasks',
            'subtasks_count',
            'title',
            'description',
            'assigned_to',
            'assigned_to_data',
            'created_by',
            'created_by_data',
            'status',
            'priority',
            'deadline',
            'order',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('created_by', 'created_at', 'updated_at', 'subtasks', 'subtasks_count')
        extra_kwargs = {
            'parent': {'required': False, 'allow_null': True},
            'assigned_to': {'required': False, 'allow_null': True},
            'deadline': {'required': False, 'allow_null': True},
            'order': {'required': False},
        }

    def get_subtasks(self, obj):
        qs = obj.subtasks.select_related('assigned_to', 'created_by').order_by('status', 'order', '-updated_at')
        return ProjectSubtaskSerializer(qs, many=True, context=self.context).data

    def get_subtasks_count(self, obj):
        try:
            return obj.subtasks.count()
        except Exception:
            return 0

    def validate(self, attrs):
        project = attrs.get('project') or getattr(self.instance, 'project', None)
        parent = attrs.get('parent') or getattr(self.instance, 'parent', None)

        if parent and project and parent.project_id != project.id:
            raise serializers.ValidationError({'parent': 'Подзадача должна быть внутри того же проекта.'})

        if self.instance and parent and parent.id == self.instance.id:
            raise serializers.ValidationError({'parent': 'Задача не может быть родителем самой себя.'})

        return attrs


class ProjectSerializer(serializers.ModelSerializer):
    created_by_data = TaskUserMiniSerializer(source='created_by', read_only=True)
    participants_data = TaskUserMiniSerializer(source='participants', many=True, read_only=True)
    responsible_users_data = TaskUserMiniSerializer(source='responsible_users', many=True, read_only=True)
    items = serializers.SerializerMethodField()
    attachments = ProjectAttachmentSerializer(many=True, read_only=True)
    office_city = serializers.CharField(source='office.city', read_only=True)

    class Meta:
        model = Project
        fields = (
            'id',
            'title',
            'description',
            'city',
            'office',
            'office_city',
            'created_by',
            'created_by_data',
            'participants',
            'participants_data',
            'responsible_users',
            'responsible_users_data',
            'status',
            'deadline',
            'is_hidden',
            'is_pinned',
            'items',
            'attachments',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('created_by', 'created_at', 'updated_at', 'items', 'attachments')
        extra_kwargs = {
            'participants': {'required': False},
            'responsible_users': {'required': False},
            'office': {'required': False, 'allow_null': True},
            'deadline': {'required': False, 'allow_null': True},
            'city': {'required': False, 'allow_blank': True},
            'is_hidden': {'required': False},
            'is_pinned': {'required': False},
        }

    def get_items(self, obj):
        qs = obj.items.filter(parent__isnull=True).select_related(
            'assigned_to',
            'created_by',
        ).prefetch_related('subtasks')
        return ProjectTaskSerializer(qs, many=True, context=self.context).data

    def validate(self, attrs):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        is_admin = bool(user and user.is_authenticated and (user.is_superuser or user.is_staff or getattr(user, 'role', None) == 'admin'))

        if not is_admin:
            attrs.pop('is_hidden', None)
            attrs.pop('is_pinned', None)
        return attrs