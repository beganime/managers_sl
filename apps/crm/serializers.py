from rest_framework import serializers

from .models import (
    Application,
    Client,
    ClientActivity,
    ClientFile,
    ClientNote,
    Lead,
    LeadSource,
)


class LeadSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeadSource
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class LeadSerializer(serializers.ModelSerializer):
    source_name = serializers.CharField(source='source.name', read_only=True)
    manager_name = serializers.CharField(source='manager.get_full_name', read_only=True)
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)

    class Meta:
        model = Lead
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'converted_at')


class ClientSerializer(serializers.ModelSerializer):
    manager_name = serializers.CharField(source='manager.get_full_name', read_only=True)
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Client
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class ApplicationSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.full_name', read_only=True)
    manager_name = serializers.CharField(source='manager.get_full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Application
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class ClientActivitySerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.full_name', read_only=True)
    manager_name = serializers.CharField(source='manager.get_full_name', read_only=True)
    activity_type_display = serializers.CharField(source='get_activity_type_display', read_only=True)

    class Meta:
        model = ClientActivity
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class ClientNoteSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.full_name', read_only=True)
    author_name = serializers.CharField(source='author.get_full_name', read_only=True)

    class Meta:
        model = ClientNote
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class ClientFileSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.full_name', read_only=True)
    uploaded_by_name = serializers.CharField(source='uploaded_by.get_full_name', read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = ClientFile
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')

    def get_file_url(self, obj):
        request = self.context.get('request')
        if not obj.file:
            return None
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url
