from rest_framework import serializers

from apps.education.models import City, Country, Intake, Program, ProgramFee, RequiredDocument, University
from apps.erp_services.models import Service


def absolute_file_url(request, file_field):
    if not file_field:
        return None
    try:
        url = file_field.url
    except ValueError:
        return None
    return request.build_absolute_uri(url) if request else url


class ClientCountrySerializer(serializers.ModelSerializer):
    flag = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()
    cities_count = serializers.SerializerMethodField()
    universities_count = serializers.SerializerMethodField()

    class Meta:
        model = Country
        fields = ('id', 'name', 'code', 'flag', 'image_url', 'cover_image_url', 'description', 'cities_count', 'universities_count')

    def get_flag(self, obj):
        return absolute_file_url(self.context.get('request'), obj.flag)

    def get_image_url(self, obj):
        return self.get_flag(obj)

    def get_cover_image_url(self, obj):
        return self.get_flag(obj)

    def get_cities_count(self, obj):
        return getattr(obj, 'cities_count', None) if hasattr(obj, 'cities_count') else obj.cities.filter(is_active=True).count()

    def get_universities_count(self, obj):
        return getattr(obj, 'universities_count', None) if hasattr(obj, 'universities_count') else obj.universities.filter(is_active=True).count()


class ClientCitySerializer(serializers.ModelSerializer):
    country = serializers.IntegerField(source='country_id', read_only=True)
    country_name = serializers.CharField(source='country.name', read_only=True)
    image_url = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()
    universities_count = serializers.SerializerMethodField()

    class Meta:
        model = City
        fields = ('id', 'country', 'country_name', 'name', 'description', 'image_url', 'cover_image_url', 'universities_count')

    def get_image_url(self, obj):
        return None

    def get_cover_image_url(self, obj):
        return None

    def get_universities_count(self, obj):
        return getattr(obj, 'universities_count', None) if hasattr(obj, 'universities_count') else obj.universities.filter(is_active=True).count()


class ClientProgramFeeSerializer(serializers.ModelSerializer):
    currency = serializers.CharField(source='currency.code', read_only=True)
    currency_symbol = serializers.CharField(source='currency.symbol', read_only=True)

    class Meta:
        model = ProgramFee
        fields = (
            'id',
            'currency',
            'currency_symbol',
            'tuition_fee',
            'service_fee_usd',
            'application_fee',
            'dormitory_fee',
            'insurance_fee',
        )


class ClientIntakeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Intake
        fields = ('id', 'title', 'start_date', 'application_deadline', 'notes')


class ClientRequiredDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = RequiredDocument
        fields = ('id', 'title', 'description', 'is_mandatory')


class ClientProgramShortSerializer(serializers.ModelSerializer):
    university_name = serializers.CharField(source='university.name', read_only=True)
    country = serializers.CharField(source='university.country.name', read_only=True)
    city = serializers.CharField(source='university.city.name', read_only=True, default='')
    degree_display = serializers.CharField(source='get_degree_display', read_only=True)
    fees = ClientProgramFeeSerializer(many=True, read_only=True)
    intakes = ClientIntakeSerializer(many=True, read_only=True)
    required_documents = ClientRequiredDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = Program
        fields = (
            'id',
            'university',
            'university_name',
            'country',
            'city',
            'name',
            'degree',
            'degree_display',
            'faculty',
            'language',
            'duration',
            'description',
            'admission_requirements',
            'fees',
            'intakes',
            'required_documents',
        )


class ClientUniversitySerializer(serializers.ModelSerializer):
    country = serializers.IntegerField(source='country_id', read_only=True)
    country_name = serializers.CharField(source='country.name', read_only=True)
    city = serializers.IntegerField(source='city_id', read_only=True)
    city_name = serializers.CharField(source='city.name', read_only=True, default='')
    logo = serializers.SerializerMethodField()
    cover = serializers.SerializerMethodField()
    logo_url = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()
    public_contacts = serializers.SerializerMethodField()
    programs_count = serializers.SerializerMethodField()
    programs = ClientProgramShortSerializer(many=True, read_only=True)
    required_documents = ClientRequiredDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = University
        fields = (
            'id',
            'name',
            'legal_name',
            'country',
            'country_name',
            'city',
            'city_name',
            'description',
            'logo',
            'cover',
            'logo_url',
            'cover_image_url',
            'website',
            'address',
            'admission_requirements',
            'invitation_info',
            'dormitory_info',
            'expenses_info',
            'age_limit',
            'public_contacts',
            'programs_count',
            'programs',
            'required_documents',
        )

    def get_logo(self, obj):
        return absolute_file_url(self.context.get('request'), obj.logo)

    def get_cover(self, obj):
        return absolute_file_url(self.context.get('request'), obj.cover_image)

    def get_logo_url(self, obj):
        return self.get_logo(obj)

    def get_cover_image_url(self, obj):
        return self.get_cover(obj)

    def get_public_contacts(self, obj):
        return {
            'website': obj.website,
            'email': obj.email,
            'phone': obj.phone,
            'address': obj.address,
        }

    def get_programs_count(self, obj):
        return getattr(obj, 'programs_count', None) if hasattr(obj, 'programs_count') else obj.programs.filter(is_active=True, is_archived=False).count()


class ClientProgramSerializer(ClientProgramShortSerializer):
    university_logo = serializers.SerializerMethodField()
    university_cover = serializers.SerializerMethodField()

    class Meta(ClientProgramShortSerializer.Meta):
        fields = ClientProgramShortSerializer.Meta.fields + ('university_logo', 'university_cover')

    def get_university_logo(self, obj):
        return absolute_file_url(self.context.get('request'), obj.university.logo)

    def get_university_cover(self, obj):
        return absolute_file_url(self.context.get('request'), obj.university.cover_image)


class ClientServiceSerializer(serializers.ModelSerializer):
    category = serializers.CharField(source='category.name', read_only=True)
    currency = serializers.CharField(source='currency.code', read_only=True, default='')
    currency_symbol = serializers.CharField(source='currency.symbol', read_only=True, default='')

    class Meta:
        model = Service
        fields = (
            'id',
            'category',
            'title',
            'code',
            'description',
            'price_client',
            'currency',
            'currency_symbol',
            'is_active',
            'is_public',
        )
