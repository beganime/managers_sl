from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import CalendarEvent


@admin.register(CalendarEvent)
class CalendarEventAdmin(ModelAdmin):
    list_display = ('title', 'event_date', 'start_time', 'company', 'office', 'owner', 'visibility', 'is_active')
    list_filter = ('visibility', 'is_active', 'company', 'office', 'event_date')
    search_fields = ('title', 'description', 'owner__email', 'owner__first_name', 'owner__last_name')
    autocomplete_fields = ('company', 'office', 'owner', 'participants', 'created_by')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'event_date'
