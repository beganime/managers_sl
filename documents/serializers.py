# documents/serializers.py
from rest_framework import serializers
from .models import InfoSnippet, DocumentTemplate, GeneratedDocument

class InfoSnippetSerializer(serializers.ModelSerializer):
    class Meta:
        model = InfoSnippet
        fields = '__all__'

class DocumentTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentTemplate
        fields = '__all__'

class GeneratedDocumentSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source='template.title', read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = GeneratedDocument
        fields = '__all__'
        read_only_fields = ('manager', 'status', 'generated_file', 'created_at', 'updated_at')

    def get_file_url(self, obj):
        # Делаем ссылку абсолютной, чтобы приложение могло легко ее скачать/открыть
        if obj.generated_file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.generated_file.url)
            return obj.generated_file.url
        return None