from decimal import Decimal

from rest_framework import serializers

from analytics.finance_models import summarize_office_finances
from .access_models import OfficeTarget, UserAccessProfile
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


class OfficeTargetSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfficeTarget
        fields = ('id', 'monthly_plan_usd', 'comment')


class OfficeSerializer(serializers.ModelSerializer):
    monthly_revenue = serializers.SerializerMethodField()
    target_profile = serializers.SerializerMethodField()

    class Meta:
        model = Office
        fields = ['id', 'city', 'address', 'phone', 'monthly_revenue', 'target_profile', 'updated_at']

    def get_monthly_revenue(self, obj):
        try:
            value = obj.monthly_revenue
            return str(value if value is not None else 0)
        except Exception:
            return '0.00'

    def get_target_profile(self, obj):
        target = getattr(obj, 'target_profile', None)
        if not target:
            return None
        return OfficeTargetSerializer(target, context=self.context).data


class UserAccessProfileSerializer(serializers.ModelSerializer):
    managed_office = OfficeSerializer(read_only=True)
    managed_office_id = serializers.PrimaryKeyRelatedField(
        queryset=Office.objects.all(),
        source='managed_office',
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = UserAccessProfile
        fields = ('id', 'managed_office', 'managed_office_id', 'can_view_office_dashboard', 'can_be_in_leaderboard')


class UserSerializer(serializers.ModelSerializer):
    managersalary = serializers.SerializerMethodField()
    office = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    is_admin_role = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)
    remove_avatar = serializers.BooleanField(write_only=True, required=False, default=False)
    office_id = serializers.PrimaryKeyRelatedField(queryset=Office.objects.all(), source='office', write_only=True, required=False, allow_null=True)
    access_profile = serializers.SerializerMethodField()

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
            'avatar_url',
            'remove_avatar',
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
            'access_profile',
            'is_superuser',
            'is_staff',
        ]
        read_only_fields = ('is_superuser', 'is_staff')
        extra_kwargs = {
            'avatar': {'required': False, 'allow_null': True},
            'dob': {'required': False, 'allow_null': True},
            'social_contacts': {'required': False, 'allow_blank': True},
            'job_description': {'required': False, 'allow_blank': True},
            'middle_name': {'required': False, 'allow_blank': True},
            'first_name': {'required': False, 'allow_blank': True},
            'last_name': {'required': False, 'allow_blank': True},
        }

    def get_full_name(self, obj):
        full_name = f'{obj.first_name} {obj.last_name}'.strip()
        return full_name or obj.email

    def get_is_admin_role(self, obj):
        return bool(obj.is_superuser or getattr(obj, 'role', None) == 'admin')

    def get_avatar_url(self, obj):
        try:
            if obj.avatar and hasattr(obj.avatar, 'url'):
                request = self.context.get('request')
                return request.build_absolute_uri(obj.avatar.url) if request else obj.avatar.url
        except Exception:
            return None
        return None

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

    def get_access_profile(self, obj):
        profile, _ = UserAccessProfile.objects.get_or_create(user=obj)
        return UserAccessProfileSerializer(profile, context=self.context).data

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        validated_data.pop('remove_avatar', None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        UserAccessProfile.objects.get_or_create(user=user)
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        remove_avatar = validated_data.pop('remove_avatar', False)

        if remove_avatar in ('1', 'true', 'True', True):
            try:
                if instance.avatar:
                    instance.avatar.delete(save=False)
            except Exception:
                pass
            instance.avatar = None

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.save()
        UserAccessProfile.objects.get_or_create(user=instance)
        return instance


class OfficeDashboardSerializer(serializers.Serializer):
    office = OfficeSerializer()
    total_income_usd = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_expense_usd = serializers.DecimalField(max_digits=14, decimal_places=2)
    net_usd = serializers.DecimalField(max_digits=14, decimal_places=2)
    monthly_revenue_usd = serializers.DecimalField(max_digits=14, decimal_places=2)
    monthly_plan_usd = serializers.DecimalField(max_digits=14, decimal_places=2)
    plan_progress_percent = serializers.DecimalField(max_digits=7, decimal_places=2)
    managers = serializers.ListField(child=serializers.DictField())

    @staticmethod
    def build_payload(office):
        totals = summarize_office_finances(office=office)
        target = getattr(office, 'target_profile', None)
        monthly_revenue = Decimal(str(getattr(office, 'monthly_revenue', 0) or 0))
        monthly_plan = Decimal(str(getattr(target, 'monthly_plan_usd', 0) or 0))
        if monthly_plan > 0:
            plan_progress = (monthly_revenue / monthly_plan) * Decimal('100')
        else:
            plan_progress = Decimal('0')

        managers = []
        for user in office.user_set.select_related('managersalary').all():
            sal = getattr(user, 'managersalary', None)
            revenue = Decimal(str(getattr(sal, 'current_month_revenue', 0) or 0))
            plan = Decimal(str(getattr(sal, 'monthly_plan', 0) or 0))
            progress = (revenue / plan * Decimal('100')) if plan > 0 else Decimal('0')
            managers.append({
                'id': user.id,
                'full_name': f'{user.first_name} {user.last_name}'.strip() or user.email,
                'email': user.email,
                'revenue_usd': str(revenue.quantize(Decimal('0.01'))),
                'plan_usd': str(plan.quantize(Decimal('0.01'))),
                'progress_percent': str(progress.quantize(Decimal('0.01'))),
            })

        return {
            'office': office,
            'total_income_usd': totals['income_usd'],
            'total_expense_usd': totals['expense_usd'],
            'net_usd': totals['net_usd'],
            'monthly_revenue_usd': monthly_revenue.quantize(Decimal('0.01')),
            'monthly_plan_usd': monthly_plan.quantize(Decimal('0.01')),
            'plan_progress_percent': plan_progress.quantize(Decimal('0.01')),
            'managers': managers,
        }