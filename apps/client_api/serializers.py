from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from apps.education.models import City, Country, Currency, Intake, Program, ProgramFee, RequiredDocument, University, UniversityContact
from apps.education.priority_catalog import priority_offer_for_name
from apps.erp_services.models import Service


def absolute_file_url(request, file_field):
    if not file_field:
        return None
    try:
        url = file_field.url
    except (ValueError, AttributeError):
        return None
    try:
        return request.build_absolute_uri(url) if request else url
    except Exception:
        return url


def decimal_to_string(value):
    if value in (None, ''):
        return None
    try:
        return str(Decimal(value).quantize(Decimal('0.01')))
    except (InvalidOperation, ArithmeticError, TypeError, ValueError):
        return str(value)


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
    currency = serializers.SerializerMethodField()
    currency_symbol = serializers.SerializerMethodField()
    tuition_fee = serializers.SerializerMethodField()
    service_fee_usd = serializers.SerializerMethodField()
    application_fee = serializers.SerializerMethodField()
    dormitory_fee = serializers.SerializerMethodField()
    insurance_fee = serializers.SerializerMethodField()

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

    def get_currency(self, obj):
        try:
            return obj.currency.code if obj.currency_id else ''
        except Exception:
            return ''

    def get_currency_symbol(self, obj):
        try:
            return obj.currency.symbol if obj.currency_id else ''
        except Exception:
            return ''

    def get_tuition_fee(self, obj):
        return decimal_to_string(obj.tuition_fee)

    def get_service_fee_usd(self, obj):
        return decimal_to_string(obj.service_fee_usd)

    def get_application_fee(self, obj):
        return decimal_to_string(obj.application_fee)

    def get_dormitory_fee(self, obj):
        return decimal_to_string(obj.dormitory_fee)

    def get_insurance_fee(self, obj):
        return decimal_to_string(obj.insurance_fee)


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
    university_id = serializers.IntegerField(read_only=True)
    university_name = serializers.SerializerMethodField()
    country = serializers.SerializerMethodField()
    country_name = serializers.SerializerMethodField()
    city = serializers.SerializerMethodField()
    city_name = serializers.SerializerMethodField()
    level = serializers.SerializerMethodField()
    degree_display = serializers.SerializerMethodField()
    tuition_fee = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
    currency_symbol = serializers.SerializerMethodField()
    converted_tuition_fee = serializers.SerializerMethodField()
    selected_currency = serializers.SerializerMethodField()
    application_deadline = serializers.SerializerMethodField()
    fees = serializers.SerializerMethodField()
    intakes = serializers.SerializerMethodField()
    required_documents = serializers.SerializerMethodField()
    priority_offer = serializers.SerializerMethodField()

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
            'priority_offer',
        )

    def get_university_name(self, obj):
        return getattr(getattr(obj, 'university', None), 'name', '')

    def get_country(self, obj):
        return getattr(getattr(getattr(obj, 'university', None), 'country', None), 'name', '')

    def get_country_name(self, obj):
        return self.get_country(obj)

    def get_city(self, obj):
        return getattr(getattr(getattr(obj, 'university', None), 'city', None), 'name', '')

    def get_city_name(self, obj):
        return self.get_city(obj)

    def get_level(self, obj):
        try:
            return obj.get_degree_display()
        except Exception:
            return obj.degree or ''

    def get_degree_display(self, obj):
        return self.get_level(obj)

    def _first_fee(self, obj):
        try:
            fees_manager = getattr(obj, 'fees', None)
            fees = list(fees_manager.all()) if hasattr(fees_manager, 'all') else []
            return fees[0] if fees else None
        except Exception:
            return None

    def _first_intake(self, obj):
        try:
            intakes_manager = getattr(obj, 'intakes', None)
            intakes = list(intakes_manager.all()) if hasattr(intakes_manager, 'all') else []
            return intakes[0] if intakes else None
        except Exception:
            return None

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
        return decimal_to_string(fee.tuition_fee) if fee else None

    def get_currency(self, obj):
        fee = self._first_fee(obj)
        try:
            return fee.currency.code if fee and fee.currency_id else ''
        except Exception:
            return ''

    def get_currency_symbol(self, obj):
        fee = self._first_fee(obj)
        try:
            return fee.currency.symbol if fee and fee.currency_id else ''
        except Exception:
            return ''

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
            return decimal_to_string(value)
        except (InvalidOperation, ArithmeticError, TypeError, ValueError):
            return None

    def get_application_deadline(self, obj):
        intake = self._first_intake(obj)
        return intake.application_deadline if intake else None

    def get_fees(self, obj):
        try:
            fees_manager = getattr(obj, 'fees', None)
            fees = fees_manager.all() if hasattr(fees_manager, 'all') else []
            result = list(ClientProgramFeeSerializer(fees, many=True, context=self.context).data)
            offer = priority_offer_for_name(obj.name)
            has_priority_price = any(
                str(item.get('source') or '').casefold() == 'гослиния' or item.get('priority_code')
                for item in result
            )
            if offer and not has_priority_price:
                result.append({
                    'id': f"priority-{offer['code']}",
                    'currency': 'USD',
                    'currency_symbol': '$',
                    'tuition_fee': None,
                    'service_fee_usd': str(offer['service_fee_usd']),
                    'application_fee': '0',
                    'dormitory_fee': '0',
                    'insurance_fee': '0',
                    'source': 'Гослиния',
                })
            return result
        except Exception:
            return []

    def get_priority_offer(self, obj):
        return priority_offer_for_name(obj.name)

    def get_intakes(self, obj):
        try:
            intakes_manager = getattr(obj, 'intakes', None)
            intakes = intakes_manager.all() if hasattr(intakes_manager, 'all') else []
            return ClientIntakeSerializer(intakes, many=True, context=self.context).data
        except Exception:
            return []

    def get_required_documents(self, obj):
        try:
            documents_manager = getattr(obj, 'required_documents', None)
            documents = documents_manager.all() if hasattr(documents_manager, 'all') else []
            return ClientRequiredDocumentSerializer(documents, many=True, context=self.context).data
        except Exception:
            return []


class ClientUniversitySerializer(serializers.ModelSerializer):
    country = serializers.IntegerField(source='country_id', read_only=True)
    country_name = serializers.SerializerMethodField()
    city = serializers.IntegerField(source='city_id', read_only=True)
    city_name = serializers.SerializerMethodField()
    logo = serializers.SerializerMethodField()
    cover = serializers.SerializerMethodField()
    logo_url = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()
    public_contacts = serializers.SerializerMethodField()
    contacts = serializers.SerializerMethodField()
    contact_people = serializers.SerializerMethodField()
    fees_summary = serializers.SerializerMethodField()
    programs_count = serializers.SerializerMethodField()
    programs = serializers.SerializerMethodField()
    required_documents = serializers.SerializerMethodField()

    class Meta:
        model = University
        fields = (
            'id',
            'name',
            'abbreviation',
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

    def get_country_name(self, obj):
        return getattr(getattr(obj, 'country', None), 'name', '')

    def get_city_name(self, obj):
        return getattr(getattr(obj, 'city', None), 'name', '')

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
            'website': obj.website or '',
            'email': obj.email or '',
            'phone': obj.phone or '',
            'address': obj.address or '',
        }

    def get_contacts(self, obj):
        return self.get_contact_people(obj)

    def get_contact_people(self, obj):
        try:
            contacts_manager = getattr(obj, 'contact_people', None)
            contacts = contacts_manager.all() if hasattr(contacts_manager, 'all') else []
            return ClientUniversityContactSerializer(contacts, many=True, context=self.context).data
        except Exception:
            return []

    def get_fees_summary(self, obj):
        fees = []
        try:
            programs_manager = getattr(obj, 'programs', None)
            programs = programs_manager.all() if hasattr(programs_manager, 'all') else []
        except Exception:
            return fees

        for program in programs:
            try:
                fees_manager = getattr(program, 'fees', None)
                program_fees = fees_manager.all() if hasattr(fees_manager, 'all') else []
            except Exception:
                continue
            for fee in program_fees:
                try:
                    fees.append({
                        'program_id': program.id,
                        'program_name': program.name,
                        'currency': fee.currency.code if fee.currency_id else '',
                        'currency_symbol': fee.currency.symbol if fee.currency_id else '',
                        'tuition_fee': decimal_to_string(fee.tuition_fee),
                        'service_fee_usd': decimal_to_string(fee.service_fee_usd),
                        'application_fee': decimal_to_string(fee.application_fee),
                        'dormitory_fee': decimal_to_string(fee.dormitory_fee),
                        'insurance_fee': decimal_to_string(fee.insurance_fee),
                    })
                except Exception:
                    continue
            offer = priority_offer_for_name(program.name)
            if offer:
                fees.append({
                    'program_id': program.id,
                    'program_name': program.name,
                    'currency': 'USD',
                    'currency_symbol': '$',
                    'tuition_fee': None,
                    'service_fee_usd': str(offer['service_fee_usd']),
                    'application_fee': '0',
                    'dormitory_fee': '0',
                    'insurance_fee': '0',
                    'source': 'Гослиния',
                    'priority_code': offer['code'],
                })
        return fees

    def get_programs_count(self, obj):
        return getattr(obj, 'programs_count', None) if hasattr(obj, 'programs_count') else obj.programs.filter(is_active=True, is_archived=False).count()

    def get_programs(self, obj):
        try:
            programs_manager = getattr(obj, 'programs', None)
            programs = programs_manager.all() if hasattr(programs_manager, 'all') else []
        except Exception:
            return []

        serialized = []
        for program in programs:
            try:
                serialized.append(ClientProgramShortSerializer(program, context=self.context).data)
            except Exception:
                continue
        return serialized

    def get_required_documents(self, obj):
        try:
            documents_manager = getattr(obj, 'required_documents', None)
            documents = documents_manager.all() if hasattr(documents_manager, 'all') else []
            return ClientRequiredDocumentSerializer(documents, many=True, context=self.context).data
        except Exception:
            return []


class ClientProgramSerializer(ClientProgramShortSerializer):
    university_logo = serializers.SerializerMethodField()
    university_cover = serializers.SerializerMethodField()

    class Meta(ClientProgramShortSerializer.Meta):
        fields = ClientProgramShortSerializer.Meta.fields + ('university_logo', 'university_cover')

    def get_university_logo(self, obj):
        return absolute_file_url(self.context.get('request'), getattr(obj.university, 'logo', None))

    def get_university_cover(self, obj):
        return absolute_file_url(self.context.get('request'), getattr(obj.university, 'cover_image', None))


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
