from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.core.models import ActiveModel, OrderedModel, TimeStampedModel
from apps.education.models import Currency
from apps.organizations.models import Company


class ServiceCategory(TimeStampedModel, ActiveModel, OrderedModel):
    company = models.ForeignKey(
        Company,
        verbose_name='Company',
        on_delete=models.PROTECT,
        related_name='erp_service_categories',
        null=True,
        blank=True,
    )
    name = models.CharField('Name', max_length=150)
    code = models.SlugField('Code', max_length=80, db_index=True)
    description = models.TextField('Description', blank=True)

    class Meta:
        verbose_name = 'Service category'
        verbose_name_plural = 'Service categories'
        ordering = ['sort_order', 'name']
        unique_together = [('company', 'code')]
        indexes = [
            models.Index(fields=['company', 'is_active']),
            models.Index(fields=['code']),
        ]

    def __str__(self):
        return self.name


class Service(TimeStampedModel, ActiveModel, OrderedModel):
    company = models.ForeignKey(
        Company,
        verbose_name='Company',
        on_delete=models.PROTECT,
        related_name='erp_services',
        null=True,
        blank=True,
    )
    category = models.ForeignKey(
        ServiceCategory,
        verbose_name='Category',
        on_delete=models.PROTECT,
        related_name='services',
    )
    title = models.CharField('Title', max_length=255, db_index=True)
    code = models.SlugField('Code', max_length=80, db_index=True)
    description = models.TextField('Description', blank=True)
    price_client = models.DecimalField('Client price', max_digits=14, decimal_places=2, default=Decimal('0.00'))
    real_cost = models.DecimalField('Real cost', max_digits=14, decimal_places=2, default=Decimal('0.00'))
    currency = models.ForeignKey(
        Currency,
        verbose_name='Currency',
        on_delete=models.SET_NULL,
        related_name='erp_services',
        null=True,
        blank=True,
    )
    is_public = models.BooleanField('Public', default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Created by',
        on_delete=models.SET_NULL,
        related_name='erp_services_created',
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Updated by',
        on_delete=models.SET_NULL,
        related_name='erp_services_updated',
        null=True,
        blank=True,
    )
    custom_data = models.JSONField('Custom data', default=dict, blank=True)

    class Meta:
        verbose_name = 'Service'
        verbose_name_plural = 'Services'
        ordering = ['category__sort_order', 'sort_order', 'title']
        unique_together = [('company', 'code')]
        indexes = [
            models.Index(fields=['company', 'is_active', 'is_public']),
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['code']),
            models.Index(fields=['title']),
        ]

    def __str__(self):
        return self.title


class ServicePrice(TimeStampedModel):
    service = models.ForeignKey(
        Service,
        verbose_name='Service',
        on_delete=models.CASCADE,
        related_name='prices',
    )
    currency = models.ForeignKey(
        Currency,
        verbose_name='Currency',
        on_delete=models.PROTECT,
        related_name='erp_service_prices',
    )
    price_client = models.DecimalField('Client price', max_digits=14, decimal_places=2, default=Decimal('0.00'))
    real_cost = models.DecimalField('Real cost', max_digits=14, decimal_places=2, default=Decimal('0.00'))
    valid_from = models.DateField('Valid from', null=True, blank=True)
    valid_to = models.DateField('Valid to', null=True, blank=True)
    notes = models.TextField('Notes', blank=True)

    class Meta:
        verbose_name = 'Service price'
        verbose_name_plural = 'Service prices'
        ordering = ['service__title', '-valid_from', 'currency__code']
        indexes = [
            models.Index(fields=['service', 'currency']),
            models.Index(fields=['valid_from', 'valid_to']),
        ]

    def __str__(self):
        return f'{self.service} - {self.price_client} {self.currency.code}'
