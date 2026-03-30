from decimal import Decimal, InvalidOperation

from django.db import transaction
from rest_framework import serializers

from .models import Client, ClientRelative
from users.models import User


class ClientRelativeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientRelative
        fields = ('id', 'full_name', 'relation_type', 'phone', 'work_place')
        read_only_fields = ('id',)


class SimpleUserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'email', 'first_name', 'last_name', 'full_name')

    def get_full_name(self, obj):
        full = f"{obj.first_name} {obj.last_name}".strip()
        return full or obj.email


class ClientSerializer(serializers.ModelSerializer):
    relative = ClientRelativeSerializer(required=False, allow_null=True)

    manager = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=False,
        allow_null=True
    )
    manager_data = SimpleUserSerializer(source='manager', read_only=True)

    shared_with = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        many=True,
        required=False
    )
    shared_with_data = SimpleUserSerializer(source='shared_with', many=True, read_only=True)

    class Meta:
        model = Client
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')

    def _to_bool(self, value, default=False):
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)

        text = str(value).strip().lower()
        if text in ('true', '1', 'yes', 'y', 'on', 'да'):
            return True
        if text in ('false', '0', 'no', 'n', 'off', 'нет', ''):
            return False
        return default

    def _to_nullable_str(self, value):
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    def _to_decimal(self, value, default=Decimal('0')):
        if value in (None, ''):
            return default
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value).replace(',', '.').strip())
        except (InvalidOperation, ValueError, TypeError):
            return default

    def _extract_block(self, text, block_title):
        text = str(text or '')
        if not text:
            return ''

        marker = f'{block_title}\n'
        start = text.find(marker)
        if start == -1:
            return ''

        start = start + len(marker)
        rest = text[start:]
        next_idx = rest.find('\n\n===')
        if next_idx != -1:
            rest = rest[:next_idx]
        return rest.strip()

    def _extract_line_value(self, block, label):
        for line in str(block or '').splitlines():
            if line.lower().startswith(f'{label.lower()}:'):
                return line.split(':', 1)[1].strip()
        return ''

    def _relative_from_legacy_comments(self, attrs, instance=None):
        # Если nested relative уже пришёл — используем его
        relative_data = attrs.get('relative', serializers.empty)
        if relative_data is not serializers.empty:
            return relative_data

        comments = attrs.get('comments')
        if comments is None and instance is not None:
            comments = instance.comments

        block = self._extract_block(comments, '=== RELATIVE ===')
        if not block:
            return serializers.empty

        parsed = {
            'full_name': self._extract_line_value(block, 'ФИО'),
            'relation_type': self._extract_line_value(block, 'Кем приходится'),
            'phone': self._extract_line_value(block, 'Телефон'),
            'work_place': self._extract_line_value(block, 'Место работы'),
        }

        has_any = any(str(v or '').strip() and str(v).strip() != '-' for v in parsed.values())
        if not has_any:
            return None

        for key, value in parsed.items():
            if value == '-':
                parsed[key] = ''

        return parsed

    def _normalize_legacy_payload(self, attrs):
        attrs = attrs.copy()

        for key in ['email', 'dob', 'passport_issued_date']:
            if key in attrs:
                attrs[key] = self._to_nullable_str(attrs.get(key))

        for key in [
            'full_name',
            'phone',
            'city',
            'citizenship',
            'passport_local_num',
            'passport_inter_num',
            'passport_issued_by',
            'address_registration',
            'partner_name',
            'current_tasks',
            'comments',
        ]:
            if key in attrs and attrs.get(key) is not None:
                attrs[key] = str(attrs.get(key)).strip()

        if 'is_priority' in attrs:
            attrs['is_priority'] = self._to_bool(attrs.get('is_priority'))
        if 'is_partner_client' in attrs:
            attrs['is_partner_client'] = self._to_bool(attrs.get('is_partner_client'))
        if 'has_discount' in attrs:
            attrs['has_discount'] = self._to_bool(attrs.get('has_discount'))

        if 'discount_amount' in attrs:
            attrs['discount_amount'] = self._to_decimal(attrs.get('discount_amount'))

        return attrs

    def validate(self, attrs):
        attrs = self._normalize_legacy_payload(attrs)

        request = self.context.get('request')
        user = request.user if request else None
        instance = getattr(self, 'instance', None)

        if not user:
            return attrs

        is_admin = user.is_superuser or getattr(user, 'role', None) == 'admin'

        # Совместимость со старым приложением:
        # relative может лежать в comments, а не в nested object
        if 'relative' not in attrs:
            legacy_relative = self._relative_from_legacy_comments(attrs, instance=instance)
            if legacy_relative is not serializers.empty:
                attrs['relative'] = legacy_relative

        if not is_admin:
            if 'manager' in attrs and attrs['manager'] not in (None, user):
                raise serializers.ValidationError({
                    'manager': 'Менеджер не может назначать другого ответственного менеджера.'
                })

            if 'shared_with' in attrs:
                raise serializers.ValidationError({
                    'shared_with': 'Только администратор может управлять shared access.'
                })

        is_partner_client = attrs.get(
            'is_partner_client',
            instance.is_partner_client if instance else False
        )
        partner_name = attrs.get(
            'partner_name',
            instance.partner_name if instance else ''
        )

        if is_partner_client and not str(partner_name or '').strip():
            raise serializers.ValidationError({
                'partner_name': 'Укажите название партнёра.'
            })

        has_discount = attrs.get(
            'has_discount',
            instance.has_discount if instance else False
        )
        discount_amount = attrs.get(
            'discount_amount',
            instance.discount_amount if instance else Decimal('0')
        )

        if not has_discount:
            attrs['discount_amount'] = Decimal('0')

        if has_discount and discount_amount is None:
            raise serializers.ValidationError({
                'discount_amount': 'Укажите размер скидки.'
            })

        relative_data = attrs.get('relative', serializers.empty)
        if relative_data is not serializers.empty and relative_data is not None:
            full_name = str(relative_data.get('full_name') or '').strip()
            relation_type = str(relative_data.get('relation_type') or '').strip()
            phone = str(relative_data.get('phone') or '').strip()
            work_place = str(relative_data.get('work_place') or '').strip()

            has_any_relative_field = any([full_name, relation_type, phone, work_place])

            if has_any_relative_field:
                missing = {}
                if not full_name:
                    missing['full_name'] = 'Укажите ФИО родственника.'
                if not relation_type:
                    missing['relation_type'] = 'Укажите кем приходится родственник.'
                if not phone:
                    missing['phone'] = 'Укажите телефон родственника.'

                if missing:
                    raise serializers.ValidationError({
                        'relative': missing
                    })

        return attrs

    def _normalize_relative_payload(self, relative_data):
        if relative_data is serializers.empty:
            return None

        if relative_data is None:
            return {}

        payload = {
            'full_name': str(relative_data.get('full_name') or '').strip(),
            'relation_type': str(relative_data.get('relation_type') or '').strip(),
            'phone': str(relative_data.get('phone') or '').strip(),
            'work_place': str(relative_data.get('work_place') or '').strip(),
        }

        has_any = any(payload.values())
        if not has_any:
            return {}

        return payload

    @transaction.atomic
    def create(self, validated_data):
        validated_data = self._normalize_legacy_payload(validated_data)

        relative_data = validated_data.pop('relative', serializers.empty)
        shared_with = validated_data.pop('shared_with', [])

        request = self.context.get('request')
        user = request.user if request else None
        is_admin = bool(user and (user.is_superuser or getattr(user, 'role', None) == 'admin'))

        if not is_admin:
            validated_data['manager'] = user
        else:
            validated_data.setdefault('manager', user)

        client = Client.objects.create(**validated_data)

        if is_admin and shared_with:
            client.shared_with.set(shared_with)

        normalized_relative = self._normalize_relative_payload(relative_data)
        if normalized_relative:
            ClientRelative.objects.create(client=client, **normalized_relative)

        return client

    @transaction.atomic
    def update(self, instance, validated_data):
        validated_data = self._normalize_legacy_payload(validated_data)

        relative_data = validated_data.pop('relative', serializers.empty)
        shared_with = validated_data.pop('shared_with', None)

        request = self.context.get('request')
        user = request.user if request else None
        is_admin = bool(user and (user.is_superuser or getattr(user, 'role', None) == 'admin'))

        if not is_admin:
            validated_data.pop('manager', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        if is_admin and shared_with is not None:
            instance.shared_with.set(shared_with)

        normalized_relative = self._normalize_relative_payload(relative_data)
        if normalized_relative is not None:
            existing_relative = getattr(instance, 'relative', None)

            if normalized_relative == {}:
                if existing_relative:
                    existing_relative.delete()
            else:
                if existing_relative:
                    for attr, value in normalized_relative.items():
                        setattr(existing_relative, attr, value)
                    existing_relative.save()
                else:
                    ClientRelative.objects.create(client=instance, **normalized_relative)

        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        relative = getattr(instance, 'relative', None)
        data['relative'] = (
            ClientRelativeSerializer(relative, context=self.context).data
            if relative else None
        )
        return data