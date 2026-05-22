import json

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.core.models import ActiveModel, OrderedModel, TimeStampedModel
from apps.organizations.models import Company, Office


def value_to_search_text(value):
    if value is None:
        return ''
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


class CustomField(TimeStampedModel, ActiveModel, OrderedModel):
    TYPE_TEXT = 'text'
    TYPE_TEXTAREA = 'textarea'
    TYPE_NUMBER = 'number'
    TYPE_DECIMAL = 'decimal'
    TYPE_BOOLEAN = 'boolean'
    TYPE_DATE = 'date'
    TYPE_DATETIME = 'datetime'
    TYPE_SELECT = 'select'
    TYPE_MULTI_SELECT = 'multi_select'
    TYPE_USER = 'user'
    TYPE_FILE = 'file'
    TYPE_JSON = 'json'
    TYPE_CHOICES = (
        (TYPE_TEXT, 'Text'),
        (TYPE_TEXTAREA, 'Textarea'),
        (TYPE_NUMBER, 'Number'),
        (TYPE_DECIMAL, 'Decimal'),
        (TYPE_BOOLEAN, 'Boolean'),
        (TYPE_DATE, 'Date'),
        (TYPE_DATETIME, 'Date and time'),
        (TYPE_SELECT, 'Select'),
        (TYPE_MULTI_SELECT, 'Multi select'),
        (TYPE_USER, 'User'),
        (TYPE_FILE, 'File'),
        (TYPE_JSON, 'JSON'),
    )

    company = models.ForeignKey(
        Company,
        verbose_name='Company',
        on_delete=models.CASCADE,
        related_name='custom_fields',
        null=True,
        blank=True,
    )
    office = models.ForeignKey(
        Office,
        verbose_name='Office',
        on_delete=models.CASCADE,
        related_name='custom_fields',
        null=True,
        blank=True,
    )
    content_type = models.ForeignKey(
        ContentType,
        verbose_name='Target model',
        on_delete=models.CASCADE,
        related_name='erp_custom_fields',
        null=True,
        blank=True,
        help_text='Optional Django model this field belongs to.',
    )
    entity_key = models.SlugField(
        'Entity key',
        max_length=100,
        blank=True,
        db_index=True,
        help_text='Optional non-model entity key, for example client_profile.',
    )
    name = models.CharField('Name', max_length=255, db_index=True)
    code = models.SlugField('Code', max_length=100, db_index=True)
    field_type = models.CharField('Field type', max_length=32, choices=TYPE_CHOICES, default=TYPE_TEXT, db_index=True)
    description = models.TextField('Description', blank=True)
    placeholder = models.CharField('Placeholder', max_length=255, blank=True)
    help_text = models.CharField('Help text', max_length=255, blank=True)
    default_value = models.JSONField('Default value', default=dict, blank=True)
    validation_rules = models.JSONField('Validation rules', default=dict, blank=True)
    is_required = models.BooleanField('Required', default=False, db_index=True)
    is_filterable = models.BooleanField('Filterable', default=False, db_index=True)
    is_public = models.BooleanField('Public', default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Created by',
        on_delete=models.SET_NULL,
        related_name='custom_fields_created',
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = 'Custom field'
        verbose_name_plural = 'Custom fields'
        ordering = ['sort_order', 'name']
        unique_together = [('company', 'office', 'content_type', 'entity_key', 'code')]
        indexes = [
            models.Index(fields=['company', 'office', 'is_active']),
            models.Index(fields=['content_type', 'entity_key']),
            models.Index(fields=['field_type', 'is_required']),
            models.Index(fields=['code']),
            models.Index(fields=['name']),
        ]

    def __str__(self):
        target = self.target_label
        return f'{target}: {self.name}' if target else self.name

    @property
    def target_label(self):
        if self.content_type_id:
            return f'{self.content_type.app_label}.{self.content_type.model}'
        return self.entity_key


class CustomFieldOption(TimeStampedModel, ActiveModel, OrderedModel):
    field = models.ForeignKey(CustomField, verbose_name='Field', on_delete=models.CASCADE, related_name='options')
    label = models.CharField('Label', max_length=255)
    value = models.SlugField('Value', max_length=120)
    color = models.CharField('Color', max_length=32, blank=True)
    extra_data = models.JSONField('Extra data', default=dict, blank=True)

    class Meta:
        verbose_name = 'Custom field option'
        verbose_name_plural = 'Custom field options'
        ordering = ['field__name', 'sort_order', 'label']
        unique_together = [('field', 'value')]
        indexes = [
            models.Index(fields=['field', 'is_active']),
            models.Index(fields=['value']),
        ]

    def __str__(self):
        return f'{self.field}: {self.label}'


class CustomFieldValue(TimeStampedModel):
    field = models.ForeignKey(CustomField, verbose_name='Field', on_delete=models.CASCADE, related_name='values')
    company = models.ForeignKey(
        Company,
        verbose_name='Company',
        on_delete=models.CASCADE,
        related_name='custom_field_values',
        null=True,
        blank=True,
    )
    office = models.ForeignKey(
        Office,
        verbose_name='Office',
        on_delete=models.CASCADE,
        related_name='custom_field_values',
        null=True,
        blank=True,
    )
    content_type = models.ForeignKey(ContentType, verbose_name='Content type', on_delete=models.CASCADE, related_name='erp_custom_field_values')
    object_id = models.PositiveBigIntegerField('Object id', db_index=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    value = models.JSONField('Value', default=dict, blank=True)
    value_search = models.TextField('Search text', blank=True, db_index=True)
    set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Set by',
        on_delete=models.SET_NULL,
        related_name='custom_field_values_set',
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = 'Custom field value'
        verbose_name_plural = 'Custom field values'
        ordering = ['field__sort_order', 'field__name']
        unique_together = [('field', 'content_type', 'object_id')]
        indexes = [
            models.Index(fields=['company', 'office']),
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['field', 'object_id']),
            models.Index(fields=['set_by', 'created_at']),
        ]

    def __str__(self):
        return f'{self.field} -> {self.content_type}:{self.object_id}'

    def save(self, *args, **kwargs):
        self.value_search = value_to_search_text(self.value)
        if not self.company_id and self.field_id:
            self.company = self.field.company
        if not self.office_id and self.field_id:
            self.office = self.field.office
        super().save(*args, **kwargs)
