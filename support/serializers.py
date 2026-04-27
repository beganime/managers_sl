from rest_framework import serializers

from .models import SupportMessage


def build_file_url(request, file_field):
    if not file_field:
        return None
    try:
        url = file_field.url
    except Exception:
        return None
    return request.build_absolute_uri(url) if request else url


def _copy_payload(data):
    return data.copy() if hasattr(data, 'copy') else dict(data or {})


def _first_file(request, names):
    files = getattr(request, 'FILES', {}) if request else {}
    for name in names:
        if name in files:
            return files[name]
    return None


class SupportMessageSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    user_email = serializers.EmailField(source='user.email', read_only=True)
    photo_url = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = SupportMessage
        fields = (
            'id',
            'user',
            'user_name',
            'user_email',
            'category',
            'subject',
            'message',
            'photo',
            'photo_url',
            'file',
            'file_url',
            'status',
            'admin_note',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('user', 'user_name', 'user_email', 'photo_url', 'file_url', 'status', 'admin_note', 'created_at', 'updated_at')
        extra_kwargs = {
            'photo': {'required': False, 'allow_null': True},
            'file': {'required': False, 'allow_null': True},
            'category': {'required': False},
        }

    def to_internal_value(self, data):
        payload = _copy_payload(data)
        request = self.context.get('request')

        if 'photo' not in payload:
            photo = _first_file(request, ('photo', 'image', 'picture'))
            if photo:
                payload['photo'] = photo

        if 'file' not in payload:
            file_obj = _first_file(request, ('file', 'attachment', 'upload', 'document'))
            if file_obj:
                payload['file'] = file_obj

        return super().to_internal_value(payload)

    def get_user_name(self, obj):
        if not obj.user:
            return None
        full = f'{obj.user.first_name} {obj.user.last_name}'.strip()
        return full or obj.user.email

    def get_photo_url(self, obj):
        return build_file_url(self.context.get('request'), obj.photo)

    def get_file_url(self, obj):
        return build_file_url(self.context.get('request'), obj.file)

    def validate_subject(self, value):
        value = str(value or '').strip()
        if len(value) < 3:
            raise serializers.ValidationError('Укажи тему обращения.')
        return value

    def validate_message(self, value):
        value = str(value or '').strip()
        if len(value) < 5:
            raise serializers.ValidationError('Сообщение слишком короткое.')
        return value