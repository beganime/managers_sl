from rest_framework import serializers

from .models import (
    DocumentTemplate,
    GeneratedDocument,
    InfoSnippet,
    KnowledgeTest,
    KnowledgeTestAttempt,
    TemplateField,
    TestQuestion,
)


def is_admin_user(user):
    return bool(
        user
        and user.is_authenticated
        and (
            user.is_superuser
            or getattr(user, "role", None) == "admin"
            or user.is_staff
        )
    )


class InfoSnippetSerializer(serializers.ModelSerializer):
    class Meta:
        model = InfoSnippet
        fields = "__all__"


class TemplateFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemplateField
        fields = ("key", "label", "field_type", "is_required", "order")


class DocumentTemplateSerializer(serializers.ModelSerializer):
    fields_config = TemplateFieldSerializer(source="fields", many=True, read_only=True)

    class Meta:
        model = DocumentTemplate
        fields = (
            "id",
            "title",
            "description",
            "file",
            "is_active",
            "updated_at",
            "fields_config",
        )


class TestQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestQuestion
        fields = ("id", "text", "options", "correct", "order")


class KnowledgeTestSerializer(serializers.ModelSerializer):
    questions = TestQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = KnowledgeTest
        fields = (
            "id",
            "title",
            "description",
            "questions",
            "updated_at",
        )


class KnowledgeTestAttemptSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    test_title = serializers.CharField(source="test.title", read_only=True)
    percent = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeTestAttempt
        fields = (
            "id",
            "test",
            "test_title",
            "user",
            "user_name",
            "score",
            "total",
            "percent",
            "answers",
            "started_at",
            "completed_at",
        )
        read_only_fields = fields

    def get_user_name(self, obj):
        full = f"{obj.user.first_name} {obj.user.last_name}".strip()
        return full or obj.user.email or f"ID {obj.user_id}"

    def get_percent(self, obj):
        return obj.percent


class GeneratedDocumentSerializer(serializers.ModelSerializer):
    manager = serializers.PrimaryKeyRelatedField(read_only=True)
    approved_by = serializers.PrimaryKeyRelatedField(read_only=True)

    template_name = serializers.SerializerMethodField()
    manager_name = serializers.SerializerMethodField()
    deal_client_name = serializers.SerializerMethodField()
    can_download = serializers.BooleanField(read_only=True)
    file_url = serializers.SerializerMethodField()
    approved_file_url = serializers.SerializerMethodField()

    class Meta:
        model = GeneratedDocument
        fields = (
            "id",
            "template",
            "template_name",
            "manager",
            "manager_name",
            "deal",
            "deal_client_name",
            "title",
            "context_data",
            "status",
            "generated_file",
            "file_url",
            "approved_file_url",
            "can_download",
            "approved_by",
            "approved_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "manager",
            "manager_name",
            "status",
            "generated_file",
            "file_url",
            "approved_file_url",
            "approved_by",
            "approved_at",
            "created_at",
            "updated_at",
        )
        extra_kwargs = {
            "manager": {"required": False},
        }

    def get_template_name(self, obj):
        if obj.template_id and obj.template:
            return obj.template.title
        return None

    def get_manager_name(self, obj):
        if obj.manager_id and obj.manager:
            full = f"{obj.manager.first_name} {obj.manager.last_name}".strip()
            return full or obj.manager.email or f"ID {obj.manager_id}"
        return None

    def get_deal_client_name(self, obj):
        try:
            if obj.deal_id and obj.deal and obj.deal.client:
                client = obj.deal.client
                return getattr(client, "full_name", None) or (
                    f"{getattr(client, 'first_name', '')} {getattr(client, 'last_name', '')}".strip()
                ) or getattr(client, "email", None)
        except Exception:
            return None
        return None

    def _build_url(self, file_field):
        if not file_field:
            return None

        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(file_field.url)
        return file_field.url

    def get_file_url(self, obj):
        review = getattr(obj, "review", None)
        if review and review.status == "approved" and review.approved_file:
            return self._build_url(review.approved_file)
        if obj.generated_file:
            return self._build_url(obj.generated_file)
        return None

    def get_approved_file_url(self, obj):
        review = getattr(obj, "review", None)
        if review and review.approved_file:
            return self._build_url(review.approved_file)
        return None

    def validate_context_data(self, value):
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("context_data должен быть JSON-объектом.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user if request else None

        instance = getattr(self, "instance", None)
        template = attrs.get("template") if "template" in attrs else (instance.template if instance else None)
        deal = attrs.get("deal") if "deal" in attrs else (instance.deal if instance else None)

        if instance and instance.status == "approved":
            raise serializers.ValidationError("Одобренный документ нельзя редактировать.")

        if template and not template.is_active:
            raise serializers.ValidationError({"template": "Нельзя использовать неактивный шаблон."})

        if deal and user and not is_admin_user(user) and deal.manager_id != user.id:
            raise serializers.ValidationError(
                {"deal": "Менеджер не может создавать документ по чужой сделке."}
            )

        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)

        if data.get("status") in {"draft", "generated"}:
            data["status"] = "pending"

        return data