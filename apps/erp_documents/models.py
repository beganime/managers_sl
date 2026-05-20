import io
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import models, transaction
from django.template.defaultfilters import slugify
from django.utils import timezone
from docx import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Mm
from docxtpl import DocxTemplate

from apps.core.models import ActiveModel, OrderedModel, TimeStampedModel
from apps.crm.models import Application, Client
from apps.finance.models import Deal
from apps.organizations.models import Company, Office


def template_upload_path(instance, filename):
    return f'erp/documents/templates/{instance.company_id or "global"}/{filename}'


def generated_upload_path(instance, filename):
    return f'erp/documents/generated/{instance.company_id or "global"}/{filename}'


def approved_upload_path(instance, filename):
    return f'erp/documents/approved/{instance.company_id or "global"}/{filename}'


def stamp_upload_path(instance, filename):
    return f'erp/documents/stamps/{instance.company_id or "global"}/{filename}'


def safe_text(value):
    if value is None:
        return ''
    return str(value)


def user_display_name(user):
    if not user:
        return ''
    return user.get_full_name() or getattr(user, 'email', '') or safe_text(user)


class DocumentTemplate(TimeStampedModel, ActiveModel):
    company = models.ForeignKey(
        Company,
        verbose_name='Company',
        on_delete=models.PROTECT,
        related_name='erp_document_templates',
        null=True,
        blank=True,
    )
    name = models.CharField('Name', max_length=255, db_index=True)
    code = models.SlugField('Code', max_length=100, db_index=True)
    description = models.TextField('Description', blank=True)
    file = models.FileField('DOCX template', upload_to=template_upload_path)
    requires_approval = models.BooleanField('Requires approval', default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Created by',
        on_delete=models.SET_NULL,
        related_name='erp_document_templates_created',
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = 'Document template'
        verbose_name_plural = 'Document templates'
        ordering = ['company__name', 'name']
        unique_together = [('company', 'code')]
        indexes = [
            models.Index(fields=['company', 'is_active']),
            models.Index(fields=['code']),
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return self.name


class DocumentTemplateField(TimeStampedModel, OrderedModel):
    FIELD_TYPE_TEXT = 'text'
    FIELD_TYPE_TEXTAREA = 'textarea'
    FIELD_TYPE_NUMBER = 'number'
    FIELD_TYPE_DATE = 'date'
    FIELD_TYPE_BOOLEAN = 'boolean'
    FIELD_TYPE_SELECT = 'select'
    FIELD_TYPE_CHOICES = (
        (FIELD_TYPE_TEXT, 'Text'),
        (FIELD_TYPE_TEXTAREA, 'Textarea'),
        (FIELD_TYPE_NUMBER, 'Number'),
        (FIELD_TYPE_DATE, 'Date'),
        (FIELD_TYPE_BOOLEAN, 'Boolean'),
        (FIELD_TYPE_SELECT, 'Select'),
    )

    template = models.ForeignKey(
        DocumentTemplate,
        verbose_name='Template',
        on_delete=models.CASCADE,
        related_name='fields',
    )
    key = models.SlugField('Key', max_length=100)
    label = models.CharField('Label', max_length=255)
    field_type = models.CharField('Field type', max_length=32, choices=FIELD_TYPE_CHOICES, default=FIELD_TYPE_TEXT)
    default_value = models.CharField('Default value', max_length=255, blank=True)
    options = models.JSONField('Options', default=list, blank=True)
    is_required = models.BooleanField('Required', default=True)
    help_text = models.CharField('Help text', max_length=255, blank=True)

    class Meta:
        verbose_name = 'Document template field'
        verbose_name_plural = 'Document template fields'
        ordering = ['sort_order', 'label']
        unique_together = [('template', 'key')]
        indexes = [
            models.Index(fields=['template', 'sort_order']),
        ]

    def __str__(self):
        return f'{self.template}: {self.label}'


class GeneratedDocument(TimeStampedModel):
    STATUS_DRAFT = 'draft'
    STATUS_GENERATED = 'generated'
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_ERROR = 'error'
    STATUS_CHOICES = (
        (STATUS_DRAFT, 'Draft'),
        (STATUS_GENERATED, 'Generated'),
        (STATUS_PENDING, 'Pending approval'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_ERROR, 'Generation error'),
    )

    company = models.ForeignKey(Company, verbose_name='Company', on_delete=models.PROTECT, related_name='erp_generated_documents')
    office = models.ForeignKey(
        Office,
        verbose_name='Office',
        on_delete=models.SET_NULL,
        related_name='erp_generated_documents',
        null=True,
        blank=True,
    )
    template = models.ForeignKey(DocumentTemplate, verbose_name='Template', on_delete=models.PROTECT, related_name='generated_documents')
    client = models.ForeignKey(
        Client,
        verbose_name='Client',
        on_delete=models.PROTECT,
        related_name='erp_generated_documents',
        null=True,
        blank=True,
    )
    application = models.ForeignKey(
        Application,
        verbose_name='Application',
        on_delete=models.SET_NULL,
        related_name='erp_generated_documents',
        null=True,
        blank=True,
    )
    deal = models.ForeignKey(
        Deal,
        verbose_name='Deal',
        on_delete=models.SET_NULL,
        related_name='erp_generated_documents',
        null=True,
        blank=True,
    )
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Manager', on_delete=models.PROTECT, related_name='erp_generated_documents')
    title = models.CharField('Title', max_length=255, blank=True)
    context_data = models.JSONField('Context data', default=dict, blank=True)
    status = models.CharField('Status', max_length=32, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    generated_file = models.FileField('Generated DOCX', upload_to=generated_upload_path, null=True, blank=True)
    approved_file = models.FileField('Approved DOCX', upload_to=approved_upload_path, null=True, blank=True)
    generation_error = models.TextField('Generation error', blank=True)
    submitted_at = models.DateTimeField('Submitted at', null=True, blank=True)
    generated_at = models.DateTimeField('Generated at', null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Approved by',
        on_delete=models.SET_NULL,
        related_name='erp_documents_approved',
        null=True,
        blank=True,
    )
    approved_at = models.DateTimeField('Approved at', null=True, blank=True)

    class Meta:
        verbose_name = 'Generated document'
        verbose_name_plural = 'Generated documents'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'office', 'status']),
            models.Index(fields=['manager', 'status']),
            models.Index(fields=['client', 'status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return self.title or f'{self.template.name} #{self.pk}'

    @property
    def can_download_original(self):
        return bool(self.generated_file and self.status == self.STATUS_APPROVED)

    @property
    def can_download_approved(self):
        return bool(self.approved_file and self.status == self.STATUS_APPROVED)

    @property
    def can_download(self):
        return self.can_download_original or self.can_download_approved

    def build_context(self):
        context = {}
        client = self.client or (self.application.client if self.application_id else None) or (self.deal.client if self.deal_id else None)
        application = self.application or (self.deal.application if self.deal_id else None)
        deal = self.deal
        company = self.company
        office = self.office
        manager = self.manager

        if company:
            context.update({
                'company_name': company.name,
                'company_legal_name': company.legal_name,
                'company_phone': company.phone,
                'company_email': company.email,
                'company_address': company.address,
            })

        if office:
            context.update({
                'office_name': office.name,
                'office_city': office.city,
                'office_address': office.address,
                'office_phone': office.phone,
                'office_email': office.email,
            })

        if manager:
            context.update({
                'manager_name': user_display_name(manager),
                'manager_email': getattr(manager, 'email', ''),
                'manager_phone': getattr(manager, 'phone', ''),
            })

        if client:
            context.update({
                'client_full_name': client.full_name,
                'client_phone': client.phone,
                'client_email': client.email or '',
                'client_citizenship': client.citizenship,
                'client_city': client.city,
                'client_address': client.address,
                'client_passport_local_num': client.passport_local_num,
                'client_passport_inter_num': client.passport_inter_num,
                'client_passport_issued_by': client.passport_issued_by,
                'client_passport_issued_date': safe_text(client.passport_issued_date),
            })

        if application:
            context.update({
                'application_university_name': application.university_name,
                'application_program_name': application.program_name,
                'application_country': application.country,
                'application_degree': application.degree,
                'application_language': application.language,
                'application_intake': application.intake,
                'application_status': application.get_status_display(),
            })

        if deal:
            context.update({
                'deal_title': deal.title,
                'deal_type': deal.get_deal_type_display(),
                'deal_university_name': deal.university_name,
                'deal_program_name': deal.program_name,
                'deal_price_client': safe_text(deal.price_client),
                'deal_total_to_pay_usd': safe_text(deal.total_to_pay_usd),
                'deal_paid_amount_usd': safe_text(deal.paid_amount_usd),
                'deal_payment_status': deal.get_payment_status_display(),
            })

        for field in self.template.fields.all():
            if field.default_value and field.key not in context:
                context[field.key] = field.default_value

        context.update(self.context_data or {})
        return context

    def validate_required_fields(self, context):
        missing = []
        for field in self.template.fields.filter(is_required=True):
            value = context.get(field.key)
            if value in (None, '', []):
                missing.append(field.key)
        return missing

    def generate_file(self):
        if not self.template.file:
            raise ValueError('Template file is required.')

        context = self.build_context()
        missing = self.validate_required_fields(context)
        if missing:
            raise ValueError(f'Missing required template fields: {", ".join(missing)}')

        template_path = Path(self.template.file.path)
        doc = DocxTemplate(template_path)
        doc.render(context)

        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)

        base = slugify(self.title or self.template.name) or 'document'
        filename = f'{base}-{uuid4().hex[:10]}.docx'

        if self.generated_file:
            self.generated_file.delete(save=False)

        self.generated_file.save(filename, ContentFile(buffer.getvalue()), save=False)
        self.status = self.STATUS_GENERATED
        self.generation_error = ''
        self.generated_at = timezone.now()
        if not self.title:
            self.title = self.template.name
        self.save(update_fields=['generated_file', 'status', 'generation_error', 'generated_at', 'title', 'updated_at'])
        return self

    def submit_for_approval(self, user=None, comment=''):
        if not self.generated_file:
            self.generate_file()

        with transaction.atomic():
            approval, _ = DocumentApproval.objects.get_or_create(document=self)
            approval.status = DocumentApproval.STATUS_PENDING
            approval.approval_type = DocumentApproval.TYPE_NOT_SELECTED
            approval.comment = comment or ''
            approval.rejection_reason = ''
            approval.reviewed_by = None
            approval.reviewed_at = None
            approval.save()

            self.status = self.STATUS_PENDING
            self.submitted_at = timezone.now()
            self.approved_by = None
            self.approved_at = None
            if self.approved_file:
                self.approved_file.delete(save=False)
                self.approved_file = None
            self.save(update_fields=['status', 'submitted_at', 'approved_by', 'approved_at', 'approved_file', 'updated_at'])
        return self

    def approve(self, user, with_stamp=False, comment=''):
        if not self.generated_file:
            raise ValueError('Generated file is required before approval.')

        approval_type = DocumentApproval.TYPE_WITH_STAMP if with_stamp else DocumentApproval.TYPE_WITHOUT_STAMP
        approved_file = build_approved_document_file(self, with_stamp=with_stamp)

        with transaction.atomic():
            if self.approved_file:
                self.approved_file.delete(save=False)
            self.approved_file.save(approved_file[0], approved_file[1], save=False)
            self.status = self.STATUS_APPROVED
            self.approved_by = user
            self.approved_at = timezone.now()
            self.generation_error = ''
            self.save(update_fields=['approved_file', 'status', 'approved_by', 'approved_at', 'generation_error', 'updated_at'])

            approval, _ = DocumentApproval.objects.get_or_create(document=self)
            approval.status = DocumentApproval.STATUS_APPROVED
            approval.approval_type = approval_type
            approval.comment = comment or ''
            approval.rejection_reason = ''
            approval.reviewed_by = user
            approval.reviewed_at = self.approved_at
            approval.save()
        return self

    def reject(self, user, reason=''):
        with transaction.atomic():
            self.status = self.STATUS_REJECTED
            self.save(update_fields=['status', 'updated_at'])

            approval, _ = DocumentApproval.objects.get_or_create(document=self)
            approval.status = DocumentApproval.STATUS_REJECTED
            approval.rejection_reason = reason or ''
            approval.reviewed_by = user
            approval.reviewed_at = timezone.now()
            approval.save()
        return self


class DocumentApproval(TimeStampedModel):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    )

    TYPE_NOT_SELECTED = 'not_selected'
    TYPE_WITHOUT_STAMP = 'without_stamp'
    TYPE_WITH_STAMP = 'with_stamp'
    TYPE_CHOICES = (
        (TYPE_NOT_SELECTED, 'Not selected'),
        (TYPE_WITHOUT_STAMP, 'Approve without stamp'),
        (TYPE_WITH_STAMP, 'Approve with stamp'),
    )

    document = models.OneToOneField(GeneratedDocument, verbose_name='Document', on_delete=models.CASCADE, related_name='approval')
    status = models.CharField('Status', max_length=32, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    approval_type = models.CharField('Approval type', max_length=32, choices=TYPE_CHOICES, default=TYPE_NOT_SELECTED)
    comment = models.TextField('Comment', blank=True)
    rejection_reason = models.TextField('Rejection reason', blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Reviewed by',
        on_delete=models.SET_NULL,
        related_name='erp_document_approvals',
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField('Reviewed at', null=True, blank=True)

    class Meta:
        verbose_name = 'Document approval'
        verbose_name_plural = 'Document approvals'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'reviewed_at']),
        ]

    def __str__(self):
        return f'{self.document} - {self.status}'


class StampRule(TimeStampedModel, ActiveModel, OrderedModel):
    company = models.ForeignKey(
        Company,
        verbose_name='Company',
        on_delete=models.CASCADE,
        related_name='erp_document_stamp_rules',
        null=True,
        blank=True,
    )
    office = models.ForeignKey(
        Office,
        verbose_name='Office',
        on_delete=models.CASCADE,
        related_name='erp_document_stamp_rules',
        null=True,
        blank=True,
    )
    template = models.ForeignKey(
        DocumentTemplate,
        verbose_name='Template',
        on_delete=models.CASCADE,
        related_name='stamp_rules',
        null=True,
        blank=True,
    )
    name = models.CharField('Name', max_length=150)
    stamp_image = models.ImageField('Stamp image', upload_to=stamp_upload_path)
    width_mm = models.PositiveIntegerField('Width, mm', default=40)

    class Meta:
        verbose_name = 'Stamp rule'
        verbose_name_plural = 'Stamp rules'
        ordering = ['sort_order', 'name']
        indexes = [
            models.Index(fields=['company', 'office', 'is_active']),
            models.Index(fields=['template', 'is_active']),
        ]

    def __str__(self):
        return self.name


class DocumentDownloadLog(models.Model):
    FILE_TYPE_ORIGINAL = 'original'
    FILE_TYPE_APPROVED = 'approved'
    FILE_TYPE_CHOICES = (
        (FILE_TYPE_ORIGINAL, 'Original'),
        (FILE_TYPE_APPROVED, 'Approved'),
    )

    document = models.ForeignKey(GeneratedDocument, verbose_name='Document', on_delete=models.CASCADE, related_name='download_logs')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='User',
        on_delete=models.SET_NULL,
        related_name='erp_document_download_logs',
        null=True,
        blank=True,
    )
    file_type = models.CharField('File type', max_length=32, choices=FILE_TYPE_CHOICES)
    ip_address = models.GenericIPAddressField('IP address', null=True, blank=True)
    user_agent = models.TextField('User agent', blank=True)
    created_at = models.DateTimeField('Created at', auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Document download log'
        verbose_name_plural = 'Document download logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['document', 'file_type']),
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self):
        return f'{self.document} - {self.file_type}'


def find_stamp_rule(document):
    qs = StampRule.objects.filter(is_active=True)
    candidates = [
        {'template': document.template, 'office': document.office, 'company': document.company},
        {'template': document.template, 'office__isnull': True, 'company': document.company},
        {'template': document.template, 'office__isnull': True, 'company__isnull': True},
        {'template__isnull': True, 'office': document.office, 'company': document.company},
        {'template__isnull': True, 'office__isnull': True, 'company': document.company},
        {'template__isnull': True, 'office__isnull': True, 'company__isnull': True},
    ]
    for filters in candidates:
        rule = qs.filter(**filters).order_by('sort_order', 'id').first()
        if rule:
            return rule
    return None


def copy_generated_file(document):
    document.generated_file.open('rb')
    try:
        content = document.generated_file.read()
    finally:
        document.generated_file.close()

    base = slugify(document.title or document.template.name) or 'approved-document'
    return f'{base}-approved-{uuid4().hex[:10]}.docx', ContentFile(content)


def build_approved_document_file(document, with_stamp=False):
    if not with_stamp:
        return copy_generated_file(document)

    rule = find_stamp_rule(document)
    if not rule or not rule.stamp_image:
        raise ValueError('Active stamp rule with stamp image is required for approval with stamp.')

    source_path = Path(document.generated_file.path)
    docx = DocxDocument(source_path)
    for section in docx.sections:
        footer = section.footer
        paragraph = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
        run = paragraph.add_run()
        run.add_picture(rule.stamp_image.path, width=Mm(rule.width_mm))

    buffer = io.BytesIO()
    docx.save(buffer)
    buffer.seek(0)

    base = slugify(document.title or document.template.name) or 'approved-document'
    return f'{base}-stamped-{uuid4().hex[:10]}.docx', ContentFile(buffer.getvalue())
