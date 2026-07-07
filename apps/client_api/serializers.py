from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from apps.education.models import City, Country, Currency, Intake, Program, ProgramFee, RequiredDocument, University, UniversityContact
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
    flag_url = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()
    cities_count = serializers.SerializerMethodField()
    universities_count = serializers.SerializerMethodField()

    class Meta:
        model = Country
        fields = ('id', 'name', 'code', 'flag', 'flag_url', 'image_url', 'cover_image_url', 'description', 'cities_count', 'universities_count')

    def get_flag(self, obj):
        return absolute_file_url(self.context.get('request'), obj.flag)

    def get_flag_url(self, obj):
        return self.get_flag(obj)

    def get_image_url(self, obj):
        return absolute_file_url(self.context.get('request'), obj.image) or self.get_flag(obj)

    def get_cover_image_url(self, obj):
        return absolute_file_url(self.context.get('request'), obj.cover_image) or self.get_image_url(obj)

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
        return absolute_file_url(self.context.get('request'), obj.image)

    def get_cover_image_url(self, obj):
        return absolute_file_url(self.context.get('request'), obj.cover_image) or self.get_image_url(obj)

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


class ClientUniversityContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = UniversityContact
        fields = ('id', 'full_name', 'position', 'email', 'phone', 'messenger', 'notes')


class ClientProgramShortSerializer(serializers.ModelSerializer):
    program_id = serializers.IntegerField(source='id', read_only=True)
    program_title = serializers.CharField(source='name', read_only=True)
    university_id = serializers.IntegerField(source='university_id', read_only=True)
    university_name = serializers.CharField(source='university.name', read_only=True)
    country = serializers.CharField(source='university.country.name', read_only=True)
    country_name = serializers.CharField(source='university.country.name', read_only=True)
    city = serializers.CharField(source='university.city.name', read_only=True, default='')
    city_name = serializers.CharField(source='university.city.name', read_only=True, default='')
    level = serializers.CharField(source='get_degree_display', read_only=True)
    degree_display = serializers.CharField(source='get_degree_display', read_only=True)
    tuition_fee = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
    currency_symbol = serializers.SerializerMethodField()
    converted_tuition_fee = serializers.SerializerMethodField()
    selected_currency = serializers.SerializerMethodField()
    application_deadline = serializers.SerializerMethodField()
    fees = ClientProgramFeeSerializer(many=True, read_only=True)
    intakes = ClientIntakeSerializer(many=True, read_only=True)
    required_documents = ClientRequiredDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = Program
        fields = (
            'id',
            'program_id',
            'program_title',
            'university',
            'university_id',
            'university_name',
            'country',
            'country_name',
            'city',
            'city_name',
            'name',
            'degree',
            'level',
            'degree_display',
            'faculty',
            'language',
            'duration',
            'description',
            'admission_requirements',
            'tuition_fee',
            'currency',
            'currency_symbol',
            'converted_tuition_fee',
            'selected_currency',
            'application_deadline',
            'fees',
            'intakes',
            'required_documents',
        )

    def _first_fee(self, obj):
        fees_manager = getattr(obj, 'fees', None)
        fees = list(fees_manager.all()) if hasattr(fees_manager, 'all') else []
        return fees[0] if fees else None

    def _first_intake(self, obj):
        intakes_manager = getattr(obj, 'intakes', None)
        intakes = list(intakes_manager.all()) if hasattr(intakes_manager, 'all') else []
        return intakes[0] if intakes else None

    def _target_currency(self):
        request = self.context.get('request')
        code = (request.query_params.get('currency') if request else '') or ''
        code = code.strip().upper()
        if not code:
            return None
        cache = getattr(self, '_target_currency_cache', {})
        if code not in cache:
            cache[code] = Currency.objects.filter(code__iexact=code).first()
            self._target_currency_cache = cache
        return cache[code]

    def get_tuition_fee(self, obj):
        fee = self._first_fee(obj)
        return fee.tuition_fee if fee else None

    def get_currency(self, obj):
        fee = self._first_fee(obj)
        return fee.currency.code if fee and fee.currency_id else ''

    def get_currency_symbol(self, obj):
        fee = self._first_fee(obj)
        return fee.currency.symbol if fee and fee.currency_id else ''

    def get_selected_currency(self, obj):
        target = self._target_currency()
        return target.code if target else ''

    def get_converted_tuition_fee(self, obj):
        fee = self._first_fee(obj)
        target = self._target_currency()
        if not fee or not fee.currency_id or not target:
            return None
        try:
            source_rate = Decimal(fee.currency.rate_to_usd)
            target_rate = Decimal(target.rate_to_usd)
            if source_rate <= 0 or target_rate <= 0:
                return None
            value = (Decimal(fee.tuition_fee) * source_rate) / target_rate
            return value.quantize(Decimal('0.01'))
        except (InvalidOperation, ArithmeticError, TypeError):
            return None

    def get_application_deadline(self, obj):
        intake = self._first_intake(obj)
        return intake.application_deadline if intake else None


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
    contacts = ClientUniversityContactSerializer(source='contact_people', many=True, read_only=True)
    contact_people = ClientUniversityContactSerializer(many=True, read_only=True)
    fees_summary = serializers.SerializerMethodField()
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
            'email',
            'phone',
            'address',
            'admission_requirements',
            'invitation_info',
            'dormitory_info',
            'expenses_info',
            'age_limit',
            'public_contacts',
            'contacts',
            'contact_people',
            'fees_summary',
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

    def get_fees_summary(self, obj):
        fees = []
        programs_manager = getattr(obj, 'programs', None)
        programs = programs_manager.all() if hasattr(programs_manager, 'all') else []
        for program in programs:
            fees_manager = getattr(program, 'fees', None)
            program_fees = fees_manager.all() if hasattr(fees_manager, 'all') else []
            for fee in program_fees:
                fees.append({
                    'program_id': program.id,
                    'program_name': program.name,
                    'currency': fee.currency.code if fee.currency_id else '',
                    'currency_symbol': fee.currency.symbol if fee.currency_id else '',
                    'tuition_fee': fee.tuition_fee,
                    'service_fee_usd': fee.service_fee_usd,
                    'application_fee': fee.application_fee,
                    'dormitory_fee': fee.dormitory_fee,
                    'insurance_fee': fee.insurance_fee,
                })
        return fees

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
