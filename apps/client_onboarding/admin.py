from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import AcademicYearSequence, OnboardingSubmission, OnboardingUniversityChoice


class OnboardingUniversityChoiceInline(TabularInline):
    model = OnboardingUniversityChoice
    extra = 0
    autocomplete_fields = ('university',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(OnboardingSubmission)
class OnboardingSubmissionAdmin(ModelAdmin):
    list_display = ('full_name', 'kind', 'academic_year', 'status', 'client', 'reviewed_by', 'submitted_at')
    list_filter = ('status', 'kind', 'academic_year', 'submitted_at')
    search_fields = ('full_name', 'phone', 'email', 'client__sl_id', 'public_id')
    readonly_fields = ('public_id', 'access_token_hash', 'submitted_at', 'reviewed_at', 'created_at', 'updated_at')
    inlines = (OnboardingUniversityChoiceInline,)


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
