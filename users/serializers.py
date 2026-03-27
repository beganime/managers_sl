from rest_framework import serializers
from .models import User, ManagerSalary, Office


class ManagerSalarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ManagerSalary
        fields = (
            'id',
            'manager',
            'current_balance',
            'fixed_salary',
            'monthly_plan',
            'current_month_revenue',
            'commission_percent',
            'motivation_target',
            'motivation_reward',
        )


class OfficeSerializer(serializers.ModelSerializer):
    monthly_revenue = serializers.SerializerMethodField()

    class Meta:
        model = Office
        fields = ['id', 'city', 'address', 'phone', 'monthly_revenue', 'updated_at']

    def get_monthly_revenue(self, obj):
        try:
            value = obj.monthly_revenue
            return str(value if value is not None else 0)
        except Exception:
            return "0.00"


class UserSerializer(serializers.ModelSerializer):
    managersalary = serializers.SerializerMethodField()
    office = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    is_admin_role = serializers.SerializerMethodField()

    password = serializers.CharField(write_only=True, required=False, allow_blank=False)
    office_id = serializers.PrimaryKeyRelatedField(
        queryset=Office.objects.all(),
        source='office',
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'password',
            'first_name',
            'last_name',
            'middle_name',
            'full_name',
            'avatar',
            'dob',
            'social_contacts',
            'job_description',
            'work_status',
            'is_effective',
            'role',
            'is_admin_role',
            'managersalary',
            'office',
            'office_id',
            'is_superuser',
            'is_staff',
        ]
        read_only_fields = ('is_superuser', 'is_staff')

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip() or obj.email

    def get_is_admin_role(self, obj):
        return bool(obj.is_superuser or getattr(obj, 'role', None) == 'admin')

    def get_managersalary(self, obj):
        try:
            salary = getattr(obj, 'managersalary', None)
            if not salary:
                return None
            return ManagerSalarySerializer(salary, context=self.context).data
        except Exception:
            return None

    def get_office(self, obj):
        try:
            office = getattr(obj, 'office', None)
            if not office:
                return None
            return OfficeSerializer(office, context=self.context).data
        except Exception:
            return None

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.save()
        return instance