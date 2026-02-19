from django.db import models
from django.conf import settings
# Импортируем Client, если нужно привязывать задачи к конкретному клиенту
# from apps.clients.models import Client 

class Task(models.Model):
    KANBAN_STATUS = (
        ('todo', 'Нужно сделать'),
        ('process', 'В работе'),
        ('review', 'На проверке'),
        ('done', 'Готово'),
    )
    
    PRIORITY_CHOICES = (
        ('low', 'Низкий'),
        ('medium', 'Средний'),
        ('high', 'Высокий'),
    )

    title = models.CharField("Заголовок задачи", max_length=200)
    description = models.TextField("Описание", blank=True)
    
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tasks', verbose_name="Исполнитель")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_tasks', verbose_name="Постановщик")
    
    # Опционально: связь с клиентом
    # client = models.ForeignKey('clients.Client', on_delete=models.SET_NULL, null=True, blank=True)
    
    status = models.CharField("Статус (Канбан)", max_length=20, choices=KANBAN_STATUS, default='todo')
    priority = models.CharField("Приоритет", max_length=20, choices=PRIORITY_CHOICES, default='medium')
    deadline = models.DateTimeField("Дедлайн", null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Задача"
        verbose_name_plural = "Задачи"