from decimal import Decimal, ROUND_HALF_UP

from rest_framework import serializers

from .models import (
    City,
    Country,
    Currency,
    Intake,
    Program,
    ProgramFee,
    RequiredDocument,
    University,
    UniversityContact,
)


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class CitySerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source='country.name', read_only=True)

    class Meta:
        model = City
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class ProgramFeeSerializer(serializers.ModelSerializer):
    currency_code = serializers.CharField(source='currency.code', read_only=True)
    currency_name = serializers.CharField(source='currency.name', read_only=True)
    currency_symbol = serializers.CharField(source='currency.symbol', read_only=True)
    currency_rate_to_usd = serializers.DecimalField(source='currency.rate_to_usd', max_digits=14, decimal_places=6, read_only=True)
    tuition_fee_usd = serializers.SerializerMethodField()
    application_fee_usd = serializers.SerializerMethodField()
    dormitory_fee_usd = serializers.SerializerMethodField()
    insurance_fee_usd = serializers.SerializerMethodField()

    class Meta:
        model = ProgramFee
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')

    def convert_to_usd(self, obj, value):
        if value in (None, ''):
            return None

        rate = getattr(obj.currency, 'rate_to_usd', None) or Decimal('1')
        amount = (Decimal(value) * Decimal(rate)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return str(amount)

    def get_tuition_fee_usd(self, obj):
        return self.convert_to_usd(obj, obj.tuition_fee)

    def get_application_fee_usd(self, obj):
        return self.convert_to_usd(obj, obj.application_fee)

    def get_dormitory_fee_usd(self, obj):
        return self.convert_to_usd(obj, obj.dormitory_fee)

    def get_insurance_fee_usd(self, obj):
        return self.convert_to_usd(obj, obj.insurance_fee)


class IntakeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Intake
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class RequiredDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = RequiredDocument
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class UniversityContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = UniversityContact
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class ProgramSerializer(serializers.ModelSerializer):
    university_name = serializers.CharField(source='university.name', read_only=True)
    country_name = serializers.CharField(source='university.country.name', read_only=True)
    degree_display = serializers.CharField(source='get_degree_display', read_only=True)
    fees = ProgramFeeSerializer(many=True, read_only=True)
    intakes = IntakeSerializer(many=True, read_only=True)
    required_documents = RequiredDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = Program
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class UniversitySerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source='country.name', read_only=True)
    city_name = serializers.CharField(source='city.name', read_only=True)
    currency_code = serializers.CharField(source='local_currency.code', read_only=True)
    programs_count = serializers.IntegerField(source='programs.count', read_only=True)
    contacts = UniversityContactSerializer(source='contact_people', many=True, read_only=True)
    required_documents = RequiredDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = University
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class UniversityDetailSerializer(UniversitySerializer):
    programs = ProgramSerializer(many=True, read_only=True)

    class Meta(UniversitySerializer.Meta):
        fields = '__all__'
