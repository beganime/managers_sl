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

    class Meta:
        model = Country
        fields = ('id', 'name', 'code', 'flag', 'description')

    def get_flag(self, obj):
        return absolute_file_url(self.context.get('request'), obj.flag)


class ClientCitySerializer(serializers.ModelSerializer):
    country = serializers.IntegerField(source='country_id', read_only=True)
    country_name = serializers.CharField(source='country.name', read_only=True)

    class Meta:
        model = City
        fields = ('id', 'country', 'country_name', 'name', 'description')


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
            'valid_from',
            'valid_to',
            'notes',
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
    public_contacts = serializers.SerializerMethodField()
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
            'website',
            'address',
            'admission_requirements',
            'invitation_info',
            'dormitory_info',
            'expenses_info',
            'age_limit',
            'public_contacts',
            'programs',
            'required_documents',
        )

    def get_logo(self, obj):
        return absolute_file_url(self.context.get('request'), obj.logo)

    def get_cover(self, obj):
        return absolute_file_url(self.context.get('request'), obj.cover_image)

    def get_public_contacts(self, obj):
        return {
            'website': obj.website,
            'email': obj.email,
            'phone': obj.phone,
            'address': obj.address,
        }


class ClientProgramSerializer(ClientProgramShortSerializer):
    university_logo = serializers.SerializerMethodField()

    class Meta(ClientProgramShortSerializer.Meta):
        fields = ClientProgramShortSerializer.Meta.fields + ('university_logo',)

    def get_university_logo(self, obj):
        return absolute_file_url(self.context.get('request'), obj.university.logo)


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
