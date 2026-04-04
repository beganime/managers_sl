from django.conf import settings
from django.db import models
from django.utils import timezone


class DocumentReview(models.Model):
    STATUS_CHOICES = (
        ('pending', 'На рассмотрении'),
        ('approved', 'Одобрен'),
        ('rejected', 'Отклонён'),
    )

    document = models.OneToOneField(
        'documents.GeneratedDocument',
        on_delete=models.CASCADE,
        related_name='review',
        verbose_name='Документ',
    )
    status = models.CharField(
        'Статус рассмотрения',
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True,
    )
    rejection_reason = models.TextField('Причина отклонения', blank=True)
    approved_file = models.FileField(
        'Одобренный файл',
        upload_to='generated_documents/approved/',
        blank=True,
        null=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='document_reviews',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Рассмотрение документа'
        verbose_name_plural = 'Рассмотрения документов'

    def __str__(self):
        return f'Review {self.document_id}: {self.status}'

    def mark_approved(self, user, approved_file=None):
        self.status = 'approved'
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.rejection_reason = ''
        if approved_file is not None:
            self.approved_file = approved_file
        self.save()

    def mark_rejected(self, user, reason=''):
        self.status = 'rejected'
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.rejection_reason = reason or ''
        self.save()


def resolve_document_status(document):
    review = getattr(document, 'review', None)
    if review:
        if review.status == 'approved':
            return 'approved'
        if review.status == 'rejected':
            return 'rejected'

    return getattr(document, 'status', 'draft') or 'draft'