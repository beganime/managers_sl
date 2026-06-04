from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .cache import clear_education_cache
from .models import City, Country, Currency, Intake, Program, ProgramFee, RequiredDocument, University, UniversityContact


@receiver(post_save, sender=Country)
@receiver(post_delete, sender=Country)
@receiver(post_save, sender=City)
@receiver(post_delete, sender=City)
@receiver(post_save, sender=Currency)
@receiver(post_delete, sender=Currency)
@receiver(post_save, sender=University)
@receiver(post_delete, sender=University)
@receiver(post_save, sender=Program)
@receiver(post_delete, sender=Program)
@receiver(post_save, sender=ProgramFee)
@receiver(post_delete, sender=ProgramFee)
@receiver(post_save, sender=Intake)
@receiver(post_delete, sender=Intake)
@receiver(post_save, sender=RequiredDocument)
@receiver(post_delete, sender=RequiredDocument)
@receiver(post_save, sender=UniversityContact)
@receiver(post_delete, sender=UniversityContact)
def clear_catalog_cache_on_change(**kwargs):
    clear_education_cache()
