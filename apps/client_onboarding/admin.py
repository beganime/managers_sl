from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import (
    AcademicYearSequence,
    ClientProvisioningStep,
    ClientServiceIdentity,
    OnboardingReviewEvent,
    OnboardingSubmission,
    OnboardingUniversityChoice,
)


class OnboardingUniversityChoiceInline(TabularInline):
    model = OnboardingUniversityChoice
    extra = 0
    autocomplete_fields = ('university',)
    readonly_fields = ('created_at', 'updated_at')


class OnboardingReviewEventInline(TabularInline):
    model = OnboardingReviewEvent
    extra = 0
    can_delete = False
    readonly_fields = ('decision', 'from_status', 'to_status', 'actor', 'comment', 'created_at', 'updated_at')


class ClientProvisioningStepInline(TabularInline):
    model = ClientProvisioningStep
    extra = 0
    can_delete = False
    readonly_fields = (
        'step', 'status', 'event_id', 'attempt_count', 'started_at',
        'finished_at', 'last_error', 'response_data', 'created_at', 'updated_at',
    )


@admin.register(OnboardingSubmission)
class OnboardingSubmissionAdmin(ModelAdmin):
    list_display = ('full_name', 'stage', 'kind', 'academic_year', 'status', 'client', 'reviewed_by', 'submitted_at')
    list_filter = ('status', 'kind', 'academic_year', 'submitted_at')
    search_fields = ('full_name', 'phone', 'email', 'client__sl_id', 'public_id')
    readonly_fields = ('public_id', 'access_token_hash', 'submitted_at', 'reviewed_at', 'created_at', 'updated_at')
    inlines = (OnboardingUniversityChoiceInline, ClientProvisioningStepInline, OnboardingReviewEventInline)


@admin.register(OnboardingUniversityChoice)
class OnboardingUniversityChoiceAdmin(ModelAdmin):
    list_display = ('submission', 'rank', 'university')
    list_filter = ('university__country',)
    search_fields = ('submission__full_name', 'university__name')
    autocomplete_fields = ('submission', 'university', 'programs')


@admin.register(AcademicYearSequence)
class AcademicYearSequenceAdmin(ModelAdmin):
    list_display = ('academic_year', 'kind', 'last_number')
    list_filter = ('academic_year', 'kind')


@admin.register(ClientServiceIdentity)
class ClientServiceIdentityAdmin(ModelAdmin):
    list_display = ('mobile_login', 'tmmail_email', 'client', 'created_at')
    search_fields = ('mobile_login', 'tmmail_email', 'client__full_name', 'client__sl_id')
    autocomplete_fields = ('submission', 'client')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ClientProvisioningStep)
class ClientProvisioningStepAdmin(ModelAdmin):
    list_display = ('client', 'step', 'status', 'attempt_count', 'finished_at')
    list_filter = ('step', 'status')
    search_fields = ('client__sl_id', 'client__full_name', 'event_id', 'last_error')
    autocomplete_fields = ('submission', 'client')
    readonly_fields = ('event_id', 'attempt_count', 'started_at', 'finished_at', 'response_data', 'created_at', 'updated_at')


@admin.register(OnboardingReviewEvent)
class OnboardingReviewEventAdmin(ModelAdmin):
    list_display = ('submission', 'decision', 'from_status', 'to_status', 'actor', 'created_at')
    list_filter = ('decision', 'from_status', 'to_status')
    search_fields = ('submission__full_name', 'submission__phone', 'actor__email', 'comment')
    autocomplete_fields = ('submission', 'actor')
    readonly_fields = ('created_at', 'updated_at')
