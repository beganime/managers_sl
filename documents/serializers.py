# documents/serializers.py
from rest_framework import serializers
from .models import InfoSnippet, DocumentTemplate, TemplateField, GeneratedDocument

class InfoSnippetSerializer(serializers.ModelSerializer):
    class Meta:
        model = InfoSnippet
        fields = '__all__'

class TemplateFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemplateField
        fields = ('key', 'label', 'field_type', 'is_required', 'order')

class DocumentTemplateSerializer(serializers.ModelSerializer):
    # Вкладываем поля в ответ API, чтобы мобилка могла построить форму
    fields_config = TemplateFieldSerializer(source='fields', many=True, read_only=True)

    class Meta:
        model = DocumentTemplate
        fields = ('id', 'title', 'description', 'file', 'is_active', 'updated_at', 'fields_config')

class GeneratedDocumentSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source='template.title', read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = GeneratedDocument
        fields = '__all__'
        read_only_fields = ('manager', 'status', 'generated_file', 'created_at', 'updated_at')

    def get_file_url(self, obj):
        if obj.generated_file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.generated_file.url)
            return obj.generated_file.url
        return None