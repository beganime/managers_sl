from django.conf import settings
from django.db import models


class OfficeTarget(models.Model):
    office = models.OneToOneField(
        'users.Office',
        on_delete=models.CASCADE,
        related_name='target_profile',
        verbose_name='Офис',
    )
    monthly_plan_usd = models.DecimalField(
        'План офиса на месяц (USD)',
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    comment = models.TextField('Комментарий к плану', blank=True)

    class Meta:
        verbose_name = 'План офиса'
        verbose_name_plural = 'Планы офисов'

    def __str__(self):
        return f'План офиса {self.office.city}'


class UserAccessProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='access_profile',
        verbose_name='Пользователь',
    )
    managed_office = models.ForeignKey(
        'users.Office',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='special_managers',
        verbose_name='Управляемый офис',
    )
    can_view_office_dashboard = models.BooleanField(
        'Может видеть баланс офиса',
        default=False,
    )
    can_be_in_leaderboard = models.BooleanField(
        'Показывать в рейтинге',
        default=True,
    )

    class Meta:
        verbose_name = 'Профиль доступа менеджера'
        verbose_name_plural = 'Профили доступа менеджеров'

    def __str__(self):
        return f'Доступы: {self.user.email}'