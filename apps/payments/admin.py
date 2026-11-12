from django.contrib import admin

from .models import Payment, PaymentRecipient


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'manager', 'client', 'amount', 'status', 'reviewed_by', 'reviewed_at')
    list_filter = ('status', 'created_at')
    search_fields = ('manager__email', 'manager__first_name', 'manager__last_name', 'client__full_name', 'note')
    readonly_fields = ('manager', 'client', 'amount', 'photo', 'note', 'created_at', 'updated_at', 'reviewed_by', 'reviewed_at', 'review_note')
    date_hierarchy = 'created_at'


@admin.register(PaymentRecipient)
class PaymentRecipientAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at')
    search_fields = ('user__email', 'user__first_name', 'user__last_name')
