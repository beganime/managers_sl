from django.db import models
from django.conf import settings
from users.models import Office, User

class Notification(models.Model):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    body = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    fcm_message_id = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"

class TutorialVideo(models.Model):
    title = models.CharField("Тема урока", max_length=255)
    description = models.TextField("Описание", blank=True)
    video_file = models.FileField("Файл видео", upload_to='tutorials/', blank=True, null=True)
    youtube_url = models.URLField("Или ссылка на YouTube", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Видеоурок"
        verbose_name_plural = "Видеоуроки"

class RatingSnapshot(models.Model):
    """
    Архив рейтингов (сохраняется в конце месяца).
    """
    period = models.ForeignKey('analytics.FinancialPeriod', on_delete=models.CASCADE, verbose_name="За период")
    
    top_office = models.ForeignKey(Office, on_delete=models.SET_NULL, null=True)
    top_office_revenue = models.DecimalField("Выручка офиса", max_digits=15, decimal_places=2)
    
    first_place_manager = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='gold_medals', on_delete=models.SET_NULL, null=True)
    first_place_revenue = models.DecimalField("Выручка 1 места", max_digits=12, decimal_places=2)
    
    # --- ДОБАВЛЕННЫЕ ПОЛЯ (которых не хватало) ---
    second_place_manager = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='silver_medals', on_delete=models.SET_NULL, null=True, blank=True)
    second_place_revenue = models.DecimalField("Выручка 2 места", max_digits=12, decimal_places=2, default=0.00)
    
    third_place_manager = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='bronze_medals', on_delete=models.SET_NULL, null=True, blank=True)
    third_place_revenue = models.DecimalField("Выручка 3 места", max_digits=12, decimal_places=2, default=0.00)

    class Meta:
        verbose_name = "Рейтинг (Архив)"
        verbose_name_plural = "Рейтинги (Архив)"

class Leaderboard(User):
    """
    Прокси-модель для отображения текущего рейтинга.
    Берет данные из таблицы User, но сортирует их иначе.
    """
    class Meta:
        proxy = True
        verbose_name = "🏆 Рейтинг (Текущий)"
        verbose_name_plural = "🏆 Рейтинг (Текущий)"
        # Сортировка по выручке в текущем месяце (от большего к меньшему)
        ordering = ('-managersalary__current_month_revenue',)