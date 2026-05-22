from django.contrib.auth import get_user_model
from rest_framework import serializers

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

User = get_user_model()


class UserMiniSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'first_name', 'last_name', 'full_name', 'email')

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.email


class TaskCommentSerializer(serializers.ModelSerializer):
    author_data = UserMiniSerializer(source='author', read_only=True)
    task_title = serializers.CharField(source='task.title', read_only=True)

    class Meta:
        model = TaskComment
        fields = '__all__'
        read_only_fields = ('author', 'created_at', 'updated_at')


class TaskChecklistItemSerializer(serializers.ModelSerializer):
    done_by_data = UserMiniSerializer(source='done_by', read_only=True)

    class Meta:
        model = TaskChecklistItem
        fields = '__all__'
        read_only_fields = ('done_by', 'done_at', 'created_at', 'updated_at')

    def update(self, instance, validated_data):
        request = self.context.get('request')
        if 'is_done' in validated_data and validated_data['is_done'] and request:
            validated_data['done_by'] = request.user
        return super().update(instance, validated_data)


class TaskChecklistSerializer(serializers.ModelSerializer):
    items = TaskChecklistItemSerializer(many=True, read_only=True)
    items_count = serializers.IntegerField(read_only=True)
    completed_items_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = TaskChecklist
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'items_count', 'completed_items_count')


class TaskAttachmentSerializer(serializers.ModelSerializer):
    uploaded_by_data = UserMiniSerializer(source='uploaded_by', read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = TaskAttachment
        fields = '__all__'
        read_only_fields = ('uploaded_by', 'created_at')

    def get_file_url(self, obj):
        if not obj.file:
            return None
        request = self.context.get('request')
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url

    def validate(self, attrs):
        attachment_type = attrs.get('attachment_type') or getattr(self.instance, 'attachment_type', TaskAttachment.TYPE_FILE)
        file_value = attrs.get('file') or getattr(self.instance, 'file', None)
        url_value = attrs.get('url') or getattr(self.instance, 'url', '')

        if attachment_type in (TaskAttachment.TYPE_FILE, TaskAttachment.TYPE_IMAGE) and not file_value:
            raise serializers.ValidationError({'file': 'File is required for file/image attachments.'})
        if attachment_type == TaskAttachment.TYPE_LINK and not str(url_value or '').strip():
            raise serializers.ValidationError({'url': 'URL is required for link attachments.'})
        return attrs


class TaskWatcherSerializer(serializers.ModelSerializer):
    user_data = UserMiniSerializer(source='user', read_only=True)
    task_title = serializers.CharField(source='task.title', read_only=True)

    class Meta:
        model = TaskWatcher
        fields = '__all__'
        read_only_fields = ('created_at',)


class ProjectTaskSerializer(serializers.ModelSerializer):
    assigned_to_data = UserMiniSerializer(source='assigned_to', read_only=True)
    created_by_data = UserMiniSerializer(source='created_by', read_only=True)
    completed_by_data = UserMiniSerializer(source='completed_by', read_only=True)
    project_title = serializers.CharField(source='project.title', read_only=True)
    section_title = serializers.CharField(source='section.title', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    comments_count = serializers.IntegerField(source='comments.count', read_only=True)
    attachments_count = serializers.IntegerField(source='attachments.count', read_only=True)
    watchers_count = serializers.IntegerField(source='watchers.count', read_only=True)
    checklists = TaskChecklistSerializer(many=True, read_only=True)
    watchers = TaskWatcherSerializer(many=True, read_only=True)

    class Meta:
        model = ProjectTask
        fields = '__all__'
        read_only_fields = ('created_by', 'completed_by', 'completed_at', 'created_at', 'updated_at')

    def validate(self, attrs):
        project = attrs.get('project') or getattr(self.instance, 'project', None)
        section = attrs.get('section') or getattr(self.instance, 'section', None)
        parent = attrs.get('parent') or getattr(self.instance, 'parent', None)

        if section and project and section.project_id != project.id:
            raise serializers.ValidationError({'section': 'Section must belong to the selected project.'})
        if parent and project and parent.project_id != project.id:
            raise serializers.ValidationError({'parent': 'Parent task must belong to the selected project.'})
        if self.instance and parent and parent.id == self.instance.id:
            raise serializers.ValidationError({'parent': 'Task cannot be its own parent.'})
        return attrs


class ProjectSectionSerializer(serializers.ModelSerializer):
    project_title = serializers.CharField(source='project.title', read_only=True)
    tasks_count = serializers.IntegerField(source='tasks.count', read_only=True)

    class Meta:
        model = ProjectSection
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class ProjectNoteSerializer(serializers.ModelSerializer):
    author_data = UserMiniSerializer(source='author', read_only=True)
    project_title = serializers.CharField(source='project.title', read_only=True)

    class Meta:
        model = ProjectNote
        fields = '__all__'
        read_only_fields = ('author', 'created_at', 'updated_at')


class ProjectSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)
    created_by_data = UserMiniSerializer(source='created_by', read_only=True)
    owner_data = UserMiniSerializer(source='owner', read_only=True)
    participants_data = UserMiniSerializer(source='participants', many=True, read_only=True)
    responsible_users_data = UserMiniSerializer(source='responsible_users', many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    tasks_count = serializers.IntegerField(read_only=True)
    completed_tasks_count = serializers.IntegerField(read_only=True)
    progress_percent = serializers.IntegerField(read_only=True)
    sections = ProjectSectionSerializer(many=True, read_only=True)
    notes = ProjectNoteSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = '__all__'
        read_only_fields = ('created_by', 'created_at', 'updated_at')
