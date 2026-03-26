# clients/serializers.py
from rest_framework import serializers
from .models import Client, ClientRelative
from users.models import User


class ClientRelativeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientRelative
        fields = '__all__'
        read_only_fields = ('client',)


class SimpleUserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'email', 'first_name', 'last_name', 'full_name')

    def get_full_name(self, obj):
        full = f"{obj.first_name} {obj.last_name}".strip()
        return full or obj.email


class ClientSerializer(serializers.ModelSerializer):
    relative = ClientRelativeSerializer(read_only=True)

    manager = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=False
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

    def validate(self, attrs):
        request = self.context.get('request')
        user = request.user if request else None

        if not user:
            return attrs

        is_admin = user.is_superuser or getattr(user, 'role', None) == 'admin'

        # Менеджер не может через API менять manager/shared_with
        if not is_admin:
            if 'manager' in attrs and attrs['manager'] != user:
                raise serializers.ValidationError({
                    'manager': 'Менеджер не может назначать другого ответственного менеджера.'
                })

            if 'shared_with' in attrs:
                raise serializers.ValidationError({
                    'shared_with': 'Только администратор может управлять shared access.'
                })

        return attrs

    def create(self, validated_data):
        shared_with = validated_data.pop('shared_with', [])
        request = self.context.get('request')
        user = request.user if request else None
        is_admin = user and (user.is_superuser or getattr(user, 'role', None) == 'admin')

        # Если создаёт не админ — менеджер всегда он сам
        if not is_admin:
            validated_data['manager'] = user
        else:
            validated_data.setdefault('manager', user)

        client = Client.objects.create(**validated_data)

        if is_admin and shared_with:
            client.shared_with.set(shared_with)

        return client

    def update(self, instance, validated_data):
        shared_with = validated_data.pop('shared_with', None)
        request = self.context.get('request')
        user = request.user if request else None
        is_admin = user and (user.is_superuser or getattr(user, 'role', None) == 'admin')

        # Защита от подмены manager менеджером
        if not is_admin:
            validated_data.pop('manager', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        if is_admin and shared_with is not None:
            instance.shared_with.set(shared_with)

        return instance