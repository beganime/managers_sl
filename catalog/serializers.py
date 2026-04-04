from rest_framework import serializers

from .models import Currency, University, Program


class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = '__all__'


class ProgramSerializer(serializers.ModelSerializer):
    university_name = serializers.CharField(source='university.name', read_only=True)
    country = serializers.CharField(source='university.country', read_only=True)
    city = serializers.CharField(source='university.city', read_only=True)
    currency = CurrencySerializer(source='university.local_currency', read_only=True)

    class Meta:
        model = Program
        fields = [
            'id',
            'university',
            'university_name',
            'country',
            'city',
            'currency',
            'name',
            'degree',
            'tuition_fee',
            'service_fee',
            'duration',
            'is_active',
            'is_deleted',
            'updated_at',
        ]


class UniversityListSerializer(serializers.ModelSerializer):
    local_currency = CurrencySerializer(read_only=True)
    programs_count = serializers.SerializerMethodField()

    class Meta:
        model = University
        fields = [
            'id',
            'name',
            'country',
            'city',
            'logo',
            'local_currency',
            'programs_count',
            'updated_at',
        ]

    def get_programs_count(self, obj):
        return getattr(obj, 'programs_count', None) or obj.programs.filter(is_deleted=False).count()


class UniversityDetailSerializer(serializers.ModelSerializer):
    local_currency = CurrencySerializer(read_only=True)
    programs = serializers.SerializerMethodField()

    # alias-поля под мобильный экран, чтобы не ломать клиент
    requirements = serializers.CharField(source='required_docs', read_only=True)
    documents_required = serializers.CharField(source='required_docs', read_only=True)
    visa_info = serializers.SerializerMethodField()
    study_languages = serializers.SerializerMethodField()
    hostel_info = serializers.SerializerMethodField()
    scholarship_info = serializers.SerializerMethodField()
    website = serializers.SerializerMethodField()

    class Meta:
        model = University
        fields = '__all__'

    def get_programs(self, obj):
        queryset = obj.programs.filter(is_deleted=False, is_active=True).order_by('name')
        return ProgramSerializer(queryset, many=True, context=self.context).data

    def get_visa_info(self, obj):
        return ''

    def get_study_languages(self, obj):
        return ''

    def get_hostel_info(self, obj):
        return ''

    def get_scholarship_info(self, obj):
        return ''

    def get_website(self, obj):
        return ''