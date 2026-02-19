from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import User, ManagerSalary

@receiver(post_save, sender=User)
def create_user_salary_profile(sender, instance, created, **kwargs):
    """
    Как только создан User, создаем ему кошелек (ManagerSalary).
    """
    if created:
        ManagerSalary.objects.create(manager=instance)

@receiver(post_save, sender=User)
def save_user_salary_profile(sender, instance, **kwargs):
    """
    Сохраняем кошелек при изменении юзера, если он есть.
    """
    if hasattr(instance, 'managersalary'):
        instance.managersalary.save()