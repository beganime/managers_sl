from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import (
    ActivityLog,
    Application,
    ApplicationExam,
    ApplicationExamEvent,
    TranslationEvent,
    TranslationRecord,
    ApplicationStageHistory,
    Client,
    ClientActivity,
    ClientFile,
    ClientFileReviewEvent,
    ClientFileVersion,
    ClientNote,
    ClientQuestionnaire,
    EmailRecord,
    ExternalAccount,
    Lead,
    LeadSource,
    ManagerDocumentCredit,
    ManagerDocumentPlan,
)


@admin.register(LeadSource)
class LeadSourceAdmin(ModelAdmin):
    list_display = ('name', 'code', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'code', 'description')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Lead)
class LeadAdmin(ModelAdmin):
    list_display = ('full_name', 'phone', 'company', 'office', 'manager', 'source', 'status', 'direction', 'is_archived', 'created_at')
    list_filter = ('status', 'direction', 'is_archived', 'company', 'office', 'source', 'created_at')
    search_fields = ('full_name', 'phone', 'email', 'country', 'city', 'interested_country', 'interested_program')
    autocomplete_fields = ('company', 'office', 'source', 'manager', 'archived_by')
    readonly_fields = ('created_at', 'updated_at', 'taken_at', 'converted_at', 'archived_at')
    date_hierarchy = 'created_at'
    fieldsets = (
        ('Контакт', {
            'fields': ('full_name', ('phone', 'email'), ('country', 'city'))
        }),
        ('CRM', {
            'fields': ('company', 'office', 'source', 'manager', ('status', 'direction'), 'taken_at', 'interested_country', 'interested_program')
        }),
        ('Архив', {
            'fields': ('is_archived', 'archived_at', 'archived_by', 'archive_reason')
        }),
        ('Комментарий', {
            'fields': ('comment', 'custom_data')
        }),
        ('Техническая информация', {
            'fields': ('submitter_ip', 'submitter_user_agent', 'submitter_referer', 'submitter_origin', 'api_source', 'converted_at', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.action(description='Архивировать выбранные лиды')
    def archive_leads(self, request, queryset):
        for lead in queryset:
            lead.archive(user=request.user, reason='Архивировано через админку')

    @admin.action(description='Восстановить выбранные лиды')
    def restore_leads(self, request, queryset):
        for lead in queryset:
            lead.restore_from_archive(user=request.user, note='Восстановлено через админку')

    actions = ('archive_leads', 'restore_leads')


class ApplicationInline(TabularInline):
    model = Application
    extra = 0
    fields = ('university_name', 'program_name', 'country', 'status', 'submitted_at', 'decision_at')
    readonly_fields = ()


class ClientNoteInline(TabularInline):
    model = ClientNote
    extra = 0
    fields = ('author', 'text', 'is_private', 'created_at')
    readonly_fields = ('created_at',)


class ClientFileInline(TabularInline):
    model = ClientFile
    extra = 0
    fields = ('title', 'file', 'external_file_url', 'file_type', 'source', 'status', 'uploaded_by', 'created_at')
    readonly_fields = ('created_at',)


class ClientQuestionnaireInline(TabularInline):
    model = ClientQuestionnaire
    extra = 0
    fields = ('status', 'full_name', 'phone', 'citizenship', 'desired_program', 'generated_file', 'submitted_at', 'last_synced_at')
    readonly_fields = ('submitted_at', 'last_synced_at')


@admin.register(Client)
class ClientAdmin(ModelAdmin):
    list_display = ('full_name', 'phone', 'company', 'office', 'manager', 'status', 'mobile_app_source', 'is_priority', 'is_partner_client', 'created_at')
    list_filter = ('status', 'company', 'office', 'manager', 'mobile_app_source', 'is_priority', 'is_partner_client', 'created_at')
    search_fields = ('full_name', 'phone', 'email', 'passport_local_num', 'passport_inter_num', 'partner_name', 'mobile_app_user_id')
    autocomplete_fields = ('company', 'office', 'manager', 'shared_with', 'source_lead')
    readonly_fields = ('created_at', 'updated_at')
    filter_horizontal = ('shared_with',)
    inlines = [ApplicationInline, ClientNoteInline, ClientFileInline, ClientQuestionnaireInline]
    date_hierarchy = 'created_at'
    fieldsets = (
        ('Основная информация', {
            'fields': ('company', 'office', 'manager', 'shared_with', 'source_lead', ('status', 'is_priority'))
        }),
        ('Контакты', {
            'fields': ('full_name', ('phone', 'email'), 'dob', 'citizenship', 'city')
        }),
        ('Адреса', {
            'fields': ('address', 'address_registration')
        }),
        ('Паспорт', {
            'fields': ('passport_local_num', 'passport_inter_num', 'passport_issued_by', 'passport_issued_date')
        }),
        ('Партнёр', {
            'fields': ('is_partner_client', 'partner_name')
        }),
        ('Комментарии и доп. данные', {
            'fields': ('comments', 'custom_data')
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


    def get_fieldsets(self, request, obj=None):
        fieldsets = list(super().get_fieldsets(request, obj))
        if not any('mobile_app_source' in item[1].get('fields', ()) for item in fieldsets):
            fieldsets.append((
                'Mobile app',
                {
                    'fields': ('mobile_app_source', 'mobile_app_user_id'),
                    'classes': ('collapse',),
                },
            ))
        return fieldsets


@admin.register(Application)
class ApplicationAdmin(ModelAdmin):
    list_display = ('client', 'university_name', 'program_name', 'country', 'manager', 'current_stage', 'status', 'submitted_at', 'created_at')
    list_filter = ('current_stage', 'status', 'company', 'office', 'country', 'degree', 'language', 'created_at')
    search_fields = ('client__full_name', 'client__phone', 'university_name', 'program_name', 'country')
    autocomplete_fields = ('client', 'company', 'office', 'manager')
    # Admission stages may only change through crm.workflow so every change is
    # validated and written to the immutable history/activity tables.
    readonly_fields = ('current_stage', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'


class ImmutableAuditAdmin(ModelAdmin):
    """Read-only admin base for append-only workflow audit records."""

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm(f'{self.opts.app_label}.view_{self.opts.model_name}')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)


@admin.register(ApplicationStageHistory)
class ApplicationStageHistoryAdmin(ImmutableAuditAdmin):
    list_display = ('application', 'old_stage', 'new_stage', 'actor', 'source_service', 'created_at')
    list_filter = ('old_stage', 'new_stage', 'source_service', 'created_at')
    search_fields = ('application__client__full_name', 'application__client__sl_id', 'comment', 'event_id')
    date_hierarchy = 'created_at'


@admin.register(ApplicationExam)
class ApplicationExamAdmin(ModelAdmin):
    list_display = ('subject', 'student', 'application', 'scheduled_at', 'status', 'responsible', 'source_service')
    list_filter = ('status', 'source_service', 'scheduled_at')
    search_fields = ('student__full_name', 'student__sl_id', 'subject', 'application__university_name')
    exclude = ('secret_ciphertext',)
    readonly_fields = (
        'public_id', 'application', 'student', 'subject', 'scheduled_at', 'timezone',
        'join_url', 'login', 'status', 'result', 'score', 'retake_at', 'comment',
        'responsible', 'created_by', 'source_service', 'source_id', 'source_version',
        'client_acknowledged_at', 'created_at', 'updated_at',
    )
    date_hierarchy = 'scheduled_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ApplicationExamEvent)
class ApplicationExamEventAdmin(ImmutableAuditAdmin):
    list_display = ('action', 'exam', 'actor', 'source_service', 'created_at')
    list_filter = ('action', 'source_service', 'created_at')
    search_fields = ('exam__student__full_name', 'exam__student__sl_id', 'event_id')
    date_hierarchy = 'created_at'


@admin.register(TranslationRecord)
class TranslationRecordAdmin(ModelAdmin):
    list_display = ('title', 'student', 'status', 'translator', 'reviewer', 'source_service', 'updated_at')
    list_filter = ('status', 'source_service', 'created_at')
    search_fields = ('title', 'student__full_name', 'student__sl_id', 'source_id')
    readonly_fields = (
        'public_id', 'student', 'application', 'source_document_version', 'title',
        'source_language', 'target_language', 'template_name', 'version', 'status',
        'source_storage_path', 'result_storage_path', 'translator', 'reviewer',
        'source_service', 'source_id', 'source_version', 'created_at', 'updated_at',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TranslationEvent)
class TranslationEventAdmin(ImmutableAuditAdmin):
    list_display = ('action', 'translation', 'actor', 'source_service', 'created_at')
    list_filter = ('action', 'source_service', 'created_at')
    search_fields = ('translation__title', 'translation__student__full_name', 'translation__student__sl_id', 'event_id')
    date_hierarchy = 'created_at'


@admin.register(EmailRecord)
class EmailRecordAdmin(ModelAdmin):
    list_display = ('subject', 'student', 'mailbox', 'sender_email', 'importance', 'processed', 'received_at')
    list_filter = ('importance', 'category', 'processed', 'is_read', 'is_replied', 'received_at')
    search_fields = ('student__full_name', 'student__sl_id', 'mailbox', 'sender_email', 'subject', 'university_name')
    readonly_fields = tuple(field.name for field in EmailRecord._meta.fields)
    date_hierarchy = 'received_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ActivityLog)
class ActivityLogAdmin(ImmutableAuditAdmin):
    list_display = ('action', 'student', 'application', 'actor', 'service', 'created_at')
    list_filter = ('action', 'service', 'object_type', 'created_at')
    search_fields = ('student__full_name', 'student__sl_id', 'object_id', 'event_id')
    date_hierarchy = 'created_at'


@admin.register(ExternalAccount)
class ExternalAccountAdmin(ModelAdmin):
    list_display = ('system', 'provider_name', 'student', 'application', 'status', 'responsible', 'last_checked_at')
    list_filter = ('system', 'status', 'created_at', 'last_checked_at')
    search_fields = ('student__full_name', 'student__sl_id', 'provider_name', 'email', 'login')
    autocomplete_fields = ('student', 'application', 'responsible', 'created_by')
    readonly_fields = ('public_id', 'secret_ciphertext', 'secret_updated_at', 'created_by', 'created_at', 'updated_at')
    exclude = ('secret_ciphertext',)
    date_hierarchy = 'created_at'


@admin.register(ClientActivity)
class ClientActivityAdmin(ModelAdmin):
    list_display = ('client', 'activity_type', 'title', 'manager', 'due_at', 'completed_at', 'created_at')
    list_filter = ('activity_type', 'completed_at', 'created_at')
    search_fields = ('client__full_name', 'client__phone', 'title', 'description')
    autocomplete_fields = ('client', 'manager')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ClientNote)
class ClientNoteAdmin(ModelAdmin):
    list_display = ('client', 'author', 'is_private', 'created_at')
    list_filter = ('is_private', 'created_at')
    search_fields = ('client__full_name', 'client__phone', 'text')
    autocomplete_fields = ('client', 'author')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ClientFile)
class ClientFileAdmin(ModelAdmin):
    list_display = ('title', 'client', 'application', 'file_type', 'source', 'status', 'reviewed_by', 'created_at')
    list_filter = ('file_type', 'source', 'status', 'created_at')
    search_fields = ('title', 'client__full_name', 'client__phone', 'comment', 'external_mobile_document_id', 'external_mobile_user_id')
    autocomplete_fields = ('client', 'application', 'uploaded_by', 'reviewed_by')
    readonly_fields = ('current_version_number', 'created_at', 'updated_at')


@admin.register(ClientFileVersion)
class ClientFileVersionAdmin(ImmutableAuditAdmin):
    list_display = ('document', 'version_number', 'original_name', 'size_bytes', 'source_service', 'created_at')
    list_filter = ('source_service', 'mime_type', 'created_at')
    search_fields = ('document__client__full_name', 'document__client__sl_id', 'original_name', 'storage_path', 'sha256')
    date_hierarchy = 'created_at'


@admin.register(ClientFileReviewEvent)
class ClientFileReviewEventAdmin(ImmutableAuditAdmin):
    list_display = ('document', 'version', 'status', 'reviewer', 'source_service', 'created_at')
    list_filter = ('status', 'source_service', 'created_at')
    search_fields = ('document__client__full_name', 'document__client__sl_id', 'comment', 'event_id')
    date_hierarchy = 'created_at'


@admin.register(ClientQuestionnaire)
class ClientQuestionnaireAdmin(ModelAdmin):
    list_display = ('client', 'full_name', 'phone', 'citizenship', 'desired_program', 'status', 'submitted_at', 'last_synced_at')
    list_filter = ('status', 'source', 'submitted_at', 'last_synced_at')
    search_fields = ('client__full_name', 'client__phone', 'full_name', 'phone', 'email', 'desired_program', 'desired_country')
    autocomplete_fields = ('client',)
    readonly_fields = ('created_at', 'updated_at', 'last_synced_at')


@admin.register(ManagerDocumentPlan)
class ManagerDocumentPlanAdmin(ModelAdmin):
    list_display = ('employee', 'period_type', 'start_date', 'end_date', 'target_clients', 'is_active')
    list_filter = ('period_type', 'is_active', 'start_date', 'end_date')
    search_fields = ('employee__user__first_name', 'employee__user__last_name', 'employee__user__email', 'admin_comment')
    autocomplete_fields = ('employee',)
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'start_date'


@admin.register(ManagerDocumentCredit)
class ManagerDocumentCreditAdmin(ModelAdmin):
    list_display = ('employee', 'client', 'event_type', 'period_start', 'period_end', 'credited_by', 'credited_at')
    list_filter = ('event_type', 'period_start', 'period_end', 'credited_at')
    search_fields = ('employee__user__first_name', 'employee__user__last_name', 'employee__user__email', 'client__full_name', 'client__phone', 'comment')
    autocomplete_fields = ('employee', 'client', 'plan', 'credited_by')
    readonly_fields = ('created_at', 'updated_at', 'credited_at')
    date_hierarchy = 'credited_at'
