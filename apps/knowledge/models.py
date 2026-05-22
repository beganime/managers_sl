from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import models
from django.db.models import F
from django.template.defaultfilters import slugify
from django.utils import timezone

from apps.core.models import ActiveModel, OrderedModel, TimeStampedModel
from apps.organizations.models import Company, Office


def knowledge_attachment_upload_path(instance, filename):
    return f'erp/knowledge/articles/{instance.article_id or "new"}/{filename}'


def normalize_answer_value(value):
    if isinstance(value, dict):
        if 'value' in value:
            return value.get('value')
        if 'answer' in value:
            return value.get('answer')
        if 'values' in value:
            return value.get('values')
    return value


def normalize_answer_list(value):
    value = normalize_answer_value(value)
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def normalize_bool(value):
    value = normalize_answer_value(value)
    if isinstance(value, bool):
        return value
    if value in (1, '1', 'true', 'True', 'yes', 'on'):
        return True
    if value in (0, '0', 'false', 'False', 'no', 'off'):
        return False
    return None


class KnowledgeCategory(TimeStampedModel, ActiveModel, OrderedModel):
    company = models.ForeignKey(
        Company,
        verbose_name='Company',
        on_delete=models.CASCADE,
        related_name='knowledge_categories',
        null=True,
        blank=True,
    )
    parent = models.ForeignKey(
        'self',
        verbose_name='Parent category',
        on_delete=models.SET_NULL,
        related_name='children',
        null=True,
        blank=True,
    )
    name = models.CharField('Name', max_length=255, db_index=True)
    code = models.SlugField('Code', max_length=100, db_index=True)
    description = models.TextField('Description', blank=True)
    icon = models.CharField('Icon', max_length=64, blank=True)
    color = models.CharField('Color', max_length=32, blank=True)
    is_public = models.BooleanField('Public', default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Created by',
        on_delete=models.SET_NULL,
        related_name='knowledge_categories_created',
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = 'Knowledge category'
        verbose_name_plural = 'Knowledge categories'
        ordering = ['sort_order', 'name']
        unique_together = [('company', 'code')]
        indexes = [
            models.Index(fields=['company', 'is_active', 'is_public']),
            models.Index(fields=['parent', 'sort_order']),
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return self.name


class KnowledgeArticle(TimeStampedModel, ActiveModel):
    STATUS_DRAFT = 'draft'
    STATUS_PUBLISHED = 'published'
    STATUS_ARCHIVED = 'archived'
    STATUS_CHOICES = (
        (STATUS_DRAFT, 'Draft'),
        (STATUS_PUBLISHED, 'Published'),
        (STATUS_ARCHIVED, 'Archived'),
    )

    company = models.ForeignKey(
        Company,
        verbose_name='Company',
        on_delete=models.CASCADE,
        related_name='knowledge_articles',
        null=True,
        blank=True,
    )
    office = models.ForeignKey(
        Office,
        verbose_name='Office',
        on_delete=models.SET_NULL,
        related_name='knowledge_articles',
        null=True,
        blank=True,
    )
    category = models.ForeignKey(
        KnowledgeCategory,
        verbose_name='Category',
        on_delete=models.SET_NULL,
        related_name='articles',
        null=True,
        blank=True,
    )
    title = models.CharField('Title', max_length=255, db_index=True)
    slug = models.SlugField('Slug', max_length=140, blank=True, db_index=True)
    summary = models.TextField('Summary', blank=True)
    content = models.TextField('Content')
    status = models.CharField('Status', max_length=32, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    tags = models.JSONField('Tags', default=list, blank=True)
    is_featured = models.BooleanField('Featured', default=False, db_index=True)
    is_public = models.BooleanField('Public', default=True, db_index=True)
    published_at = models.DateTimeField('Published at', null=True, blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Author',
        on_delete=models.SET_NULL,
        related_name='knowledge_articles_authored',
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Updated by',
        on_delete=models.SET_NULL,
        related_name='knowledge_articles_updated',
        null=True,
        blank=True,
    )
    views_count = models.PositiveIntegerField('Views count', default=0)
    custom_data = models.JSONField('Custom data', default=dict, blank=True)

    class Meta:
        verbose_name = 'Knowledge article'
        verbose_name_plural = 'Knowledge articles'
        ordering = ['-is_featured', '-published_at', '-updated_at']
        unique_together = [('company', 'slug')]
        indexes = [
            models.Index(fields=['company', 'office', 'status']),
            models.Index(fields=['category', 'status']),
            models.Index(fields=['is_active', 'is_public']),
            models.Index(fields=['title']),
            models.Index(fields=['published_at']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:140] or f'article-{self.pk or "new"}'
        if self.status == self.STATUS_PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        if self.status != self.STATUS_PUBLISHED:
            self.published_at = None
        super().save(*args, **kwargs)

    @property
    def attachments_count(self):
        return self.attachments.count()

    @property
    def tests_count(self):
        return self.tests.count()

    def publish(self, user=None):
        self.status = self.STATUS_PUBLISHED
        self.published_at = timezone.now()
        self.updated_by = user or self.updated_by
        self.save(update_fields=['status', 'published_at', 'updated_by', 'updated_at'])
        return self

    def archive(self, user=None):
        self.status = self.STATUS_ARCHIVED
        self.updated_by = user or self.updated_by
        self.save(update_fields=['status', 'updated_by', 'updated_at'])
        return self

    def mark_read(self, user):
        if not user or not getattr(user, 'is_authenticated', False):
            return None
        log, created = ArticleReadLog.objects.get_or_create(article=self, user=user)
        if not created:
            log.read_count = F('read_count') + 1
            log.last_read_at = timezone.now()
            log.save(update_fields=['read_count', 'last_read_at', 'updated_at'])
            log.refresh_from_db()
        KnowledgeArticle.objects.filter(pk=self.pk).update(views_count=F('views_count') + 1)
        self.refresh_from_db(fields=['views_count'])
        return log


class KnowledgeAttachment(TimeStampedModel, OrderedModel):
    TYPE_FILE = 'file'
    TYPE_IMAGE = 'image'
    TYPE_LINK = 'link'
    TYPE_VIDEO = 'video'
    TYPE_CHOICES = (
        (TYPE_FILE, 'File'),
        (TYPE_IMAGE, 'Image'),
        (TYPE_LINK, 'Link'),
        (TYPE_VIDEO, 'Video'),
    )

    article = models.ForeignKey(KnowledgeArticle, verbose_name='Article', on_delete=models.CASCADE, related_name='attachments')
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Uploaded by',
        on_delete=models.SET_NULL,
        related_name='knowledge_attachments',
        null=True,
        blank=True,
    )
    title = models.CharField('Title', max_length=255, blank=True)
    attachment_type = models.CharField('Attachment type', max_length=32, choices=TYPE_CHOICES, default=TYPE_FILE)
    file = models.FileField('File', upload_to=knowledge_attachment_upload_path, null=True, blank=True)
    url = models.URLField('URL', max_length=1000, blank=True)
    note = models.TextField('Note', blank=True)

    class Meta:
        verbose_name = 'Knowledge attachment'
        verbose_name_plural = 'Knowledge attachments'
        ordering = ['article__title', 'sort_order', 'created_at']
        indexes = [
            models.Index(fields=['article', 'sort_order']),
            models.Index(fields=['uploaded_by', 'created_at']),
        ]

    def __str__(self):
        return self.title or self.url or f'Attachment #{self.pk}'


class KnowledgeTest(TimeStampedModel, ActiveModel):
    company = models.ForeignKey(
        Company,
        verbose_name='Company',
        on_delete=models.CASCADE,
        related_name='knowledge_tests',
        null=True,
        blank=True,
    )
    office = models.ForeignKey(
        Office,
        verbose_name='Office',
        on_delete=models.SET_NULL,
        related_name='knowledge_tests',
        null=True,
        blank=True,
    )
    article = models.ForeignKey(
        KnowledgeArticle,
        verbose_name='Article',
        on_delete=models.SET_NULL,
        related_name='tests',
        null=True,
        blank=True,
    )
    title = models.CharField('Title', max_length=255, db_index=True)
    description = models.TextField('Description', blank=True)
    pass_percent = models.DecimalField('Pass percent', max_digits=5, decimal_places=2, default=Decimal('70.00'))
    max_attempts = models.PositiveIntegerField('Max attempts', default=0, help_text='0 means unlimited attempts.')
    time_limit_minutes = models.PositiveIntegerField('Time limit, minutes', default=0, help_text='0 means no time limit.')
    is_required = models.BooleanField('Required', default=False, db_index=True)
    is_public = models.BooleanField('Public', default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Created by',
        on_delete=models.SET_NULL,
        related_name='knowledge_tests_created',
        null=True,
        blank=True,
    )
    custom_data = models.JSONField('Custom data', default=dict, blank=True)

    class Meta:
        verbose_name = 'Knowledge test'
        verbose_name_plural = 'Knowledge tests'
        ordering = ['title']
        indexes = [
            models.Index(fields=['company', 'office', 'is_active']),
            models.Index(fields=['article', 'is_active']),
            models.Index(fields=['is_required', 'is_public']),
            models.Index(fields=['title']),
        ]

    def __str__(self):
        return self.title

    @property
    def questions_count(self):
        return self.questions.filter(is_active=True).count()

    @property
    def max_points(self):
        total = self.questions.filter(is_active=True).aggregate(total=models.Sum('points'))['total']
        return total or Decimal('0.00')

    def user_attempts_count(self, user):
        if not user or not getattr(user, 'is_authenticated', False):
            return 0
        return self.attempts.filter(user=user).count()

    def can_user_start(self, user):
        if not self.max_attempts:
            return True
        return self.user_attempts_count(user) < self.max_attempts


class KnowledgeQuestion(TimeStampedModel, ActiveModel, OrderedModel):
    TYPE_SINGLE = 'single_choice'
    TYPE_MULTIPLE = 'multiple_choice'
    TYPE_TEXT = 'text'
    TYPE_BOOLEAN = 'boolean'
    TYPE_CHOICES = (
        (TYPE_SINGLE, 'Single choice'),
        (TYPE_MULTIPLE, 'Multiple choice'),
        (TYPE_TEXT, 'Text'),
        (TYPE_BOOLEAN, 'Boolean'),
    )

    test = models.ForeignKey(KnowledgeTest, verbose_name='Test', on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField('Question')
    question_type = models.CharField('Question type', max_length=32, choices=TYPE_CHOICES, default=TYPE_SINGLE)
    options = models.JSONField('Options', default=list, blank=True)
    correct_answer = models.JSONField('Correct answer', default=dict, blank=True)
    points = models.DecimalField('Points', max_digits=8, decimal_places=2, default=Decimal('1.00'))
    explanation = models.TextField('Explanation', blank=True)

    class Meta:
        verbose_name = 'Knowledge question'
        verbose_name_plural = 'Knowledge questions'
        ordering = ['test__title', 'sort_order', 'id']
        indexes = [
            models.Index(fields=['test', 'is_active']),
            models.Index(fields=['sort_order']),
        ]

    def __str__(self):
        return f'{self.test}: {self.question_text[:80]}'

    def is_correct(self, answer):
        if self.question_type == self.TYPE_MULTIPLE:
            expected = {item.lower() for item in normalize_answer_list(self.correct_answer)}
            actual = {item.lower() for item in normalize_answer_list(answer)}
            return bool(expected) and expected == actual

        if self.question_type == self.TYPE_BOOLEAN:
            expected = normalize_bool(self.correct_answer)
            actual = normalize_bool(answer)
            return expected is not None and expected == actual

        if self.question_type == self.TYPE_TEXT:
            expected = {item.lower() for item in normalize_answer_list(self.correct_answer)}
            actual = str(normalize_answer_value(answer) or '').strip().lower()
            return bool(expected) and actual in expected

        expected = str(normalize_answer_value(self.correct_answer) or '').strip().lower()
        actual = str(normalize_answer_value(answer) or '').strip().lower()
        return bool(expected) and expected == actual


class KnowledgeTestAttempt(TimeStampedModel):
    STATUS_STARTED = 'started'
    STATUS_SUBMITTED = 'submitted'
    STATUS_CHOICES = (
        (STATUS_STARTED, 'Started'),
        (STATUS_SUBMITTED, 'Submitted'),
    )

    test = models.ForeignKey(KnowledgeTest, verbose_name='Test', on_delete=models.CASCADE, related_name='attempts')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='User', on_delete=models.CASCADE, related_name='erp_knowledge_test_attempts')
    status = models.CharField('Status', max_length=32, choices=STATUS_CHOICES, default=STATUS_STARTED, db_index=True)
    started_at = models.DateTimeField('Started at', default=timezone.now)
    submitted_at = models.DateTimeField('Submitted at', null=True, blank=True)
    answers = models.JSONField('Answers', default=dict, blank=True)
    score_points = models.DecimalField('Score points', max_digits=10, decimal_places=2, default=Decimal('0.00'))
    max_points = models.DecimalField('Max points', max_digits=10, decimal_places=2, default=Decimal('0.00'))
    score_percent = models.DecimalField('Score percent', max_digits=6, decimal_places=2, default=Decimal('0.00'))
    is_passed = models.BooleanField('Passed', default=False, db_index=True)

    class Meta:
        verbose_name = 'Knowledge test attempt'
        verbose_name_plural = 'Knowledge test attempts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['test', 'user', 'status']),
            models.Index(fields=['user', 'is_passed']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f'{self.user} - {self.test} - {self.status}'

    def calculate_score(self):
        questions = self.test.questions.filter(is_active=True)
        score = Decimal('0.00')
        max_points = Decimal('0.00')
        for question in questions:
            max_points += question.points
            answer = (self.answers or {}).get(str(question.id), (self.answers or {}).get(question.id))
            if question.is_correct(answer):
                score += question.points

        percent = Decimal('0.00')
        if max_points > 0:
            percent = ((score / max_points) * Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        self.score_points = score.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self.max_points = max_points.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self.score_percent = percent
        self.is_passed = percent >= self.test.pass_percent
        return self

    def submit(self, answers=None):
        if answers is not None:
            self.answers = answers
        self.calculate_score()
        self.status = self.STATUS_SUBMITTED
        self.submitted_at = timezone.now()
        self.save(update_fields=[
            'answers',
            'score_points',
            'max_points',
            'score_percent',
            'is_passed',
            'status',
            'submitted_at',
            'updated_at',
        ])
        return self


class ArticleReadLog(TimeStampedModel):
    article = models.ForeignKey(KnowledgeArticle, verbose_name='Article', on_delete=models.CASCADE, related_name='read_logs')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='User', on_delete=models.CASCADE, related_name='knowledge_read_logs')
    read_count = models.PositiveIntegerField('Read count', default=1)
    last_read_at = models.DateTimeField('Last read at', default=timezone.now)

    class Meta:
        verbose_name = 'Article read log'
        verbose_name_plural = 'Article read logs'
        ordering = ['-last_read_at']
        unique_together = [('article', 'user')]
        indexes = [
            models.Index(fields=['article', 'user']),
            models.Index(fields=['user', 'last_read_at']),
        ]

    def __str__(self):
        return f'{self.user} read {self.article}'
