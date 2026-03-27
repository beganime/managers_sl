from rest_framework import serializers

from .models import ManagerSalary, Office, User


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
    employee_count = serializers.SerializerMethodField()

    class Meta:
        model = Office
        fields = [
            'id',
            'city',
            'address',
            'phone',
            'monthly_revenue',
            'employee_count',
            'updated_at',
        ]

    def get_monthly_revenue(self, obj):
        try:
            value = obj.monthly_revenue
            return str(value if value is not None else 0)
        except Exception:
            return '0.00'

    def get_employee_count(self, obj):
        try:
            return obj.user_set.count()
        except Exception:
            return 0


class UserSerializer(serializers.ModelSerializer):
    managersalary = serializers.SerializerMethodField()
    office = OfficeSerializer(read_only=True)
    office_id = serializers.PrimaryKeyRelatedField(
        source='office',
        queryset=Office.objects.all(),
        allow_null=True,
        required=False,
        write_only=True,
    )
    full_name = serializers.SerializerMethodField()
    is_admin_role = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)

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
        read_only_fields = ('is_superuser', 'is_staff', 'managersalary', 'office')

    def get_full_name(self, obj):
        return f'{obj.first_name} {obj.last_name}'.strip() or obj.email

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

    def validate(self, attrs):
        if self.instance is None and not attrs.get('password'):
            raise serializers.ValidationError({'password': 'Нужно задать пароль для нового сотрудника.'})
        return attrs

    def _apply_role_flags(self, validated_data):
        role = validated_data.get('role')
        if role == 'admin':
            validated_data['is_staff'] = True
            validated_data['is_superuser'] = True
        elif role == 'manager':
            validated_data['is_staff'] = False
            validated_data['is_superuser'] = False
        return validated_data

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        validated_data = self._apply_role_flags(validated_data)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        validated_data = self._apply_role_flags(validated_data)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.save()
        return instance
