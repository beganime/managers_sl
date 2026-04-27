from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import FCMDevice


@admin.register(FCMDevice)
class FCMDeviceAdmin(ModelAdmin):
    list_display = ('user', 'platform', 'device_name', 'is_active', 'last_seen_at', 'created_at')
    list_filter = ('platform', 'is_active', 'created_at')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'token', 'device_name')
    readonly_fields = ('created_at', 'last_seen_at')