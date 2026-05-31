from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.mail import send_mail
from django.db.models import Q
from django.utils import timezone

from apps.core.permissions import is_erp_admin
from apps.employees.models import EmployeeProfile

from .models import Notification, NotificationLog, NotificationTemplate
from .push import send_push


def user_display_name(user):
    if not user:
        return ''
    return user.get_full_name() or getattr(user, 'email', '') or str(user)


def get_user_scope(user):
    employee = getattr(user, 'employee_profile', None)
    if not employee:
        return None, None
    return employee.company, employee.office


def get_admin_users(company=None, office=None):
    User = get_user_model()
    qs = User.objects.filter(Q(is_superuser=True) | Q(is_staff=True) | Q(role='admin')).distinct()
    employee_ids = []
    if company:
        employee_qs = EmployeeProfile.objects.filter(company=company, is_active=True)
        if office:
            employee_qs = employee_qs.filter(Q(office=office) | Q(office__isnull=True))
        employee_ids = list(employee_qs.values_list('user_id', flat=True))
    if employee_ids:
        qs = (qs | User.objects.filter(id__in=employee_ids, employee_profile__access__can_manage_documents=True)).distinct()
    return qs


def find_template(code=None, notification_type=None, company=None):
    qs = NotificationTemplate.objects.filter(is_active=True)
    if code:
        scoped = qs.filter(code=code).filter(Q(company=company) | Q(company__isnull=True)).order_by('-company_id')
        template = scoped.first()
        if template:
            return template
    if notification_type:
        return qs.filter(notification_type=notification_type).filter(Q(company=company) | Q(company__isnull=True)).order_by('-company_id').first()
    return None


def resolve_related_object(related_object):
    if not related_object:
        return None, None
    return ContentType.objects.get_for_model(related_object, for_concrete_model=False), related_object.pk


def build_context(**kwargs):
    context = {
        'now': timezone.now(),
    }
    context.update(kwargs)
    user = context.get('user') or context.get('recipient')
    if user:
        context['user_name'] = user_display_name(user)
        context['user_email'] = getattr(user, 'email', '')
    return context


def create_notification(
    recipient,
    title='',
    body='',
    *,
    notification_type=NotificationTemplate.TYPE_SYSTEM,
    channel=NotificationTemplate.CHANNEL_IN_APP,
    priority=Notification.PRIORITY_NORMAL,
    data=None,
    target_url='',
    company=None,
    office=None,
    sender=None,
    template_code=None,
    template=None,
    context=None,
    related_object=None,
    batch=None,
    queue=True,
):
    if not recipient:
        return None

    if not company or office is None:
        default_company, default_office = get_user_scope(recipient)
        company = company or default_company
        office = office if office is not None else default_office

    template = template or find_template(template_code, notification_type, company)
    rendered_data = data or {}
    if template:
        rendered = template.render(build_context(recipient=recipient, **(context or {})))
        title = title or rendered['title']
        body = body or rendered['body']
        rendered_data = {**(rendered.get('data') or {}), **rendered_data}
        channel = template.channel or channel
        notification_type = template.notification_type or notification_type

    content_type, object_id = resolve_related_object(related_object)
    notification = Notification.objects.create(
        company=company,
        office=office,
        recipient=recipient,
        sender=sender,
        template=template,
        batch=batch,
        notification_type=notification_type,
        channel=channel,
        priority=priority,
        title=title,
        body=body,
        data=rendered_data,
        target_url=target_url,
        content_type=content_type,
        object_id=object_id,
    )
    if queue:
        notification.queue()
    return notification


def create_notifications(recipients, **kwargs):
    notifications = []
    for recipient in recipients:
        notification = create_notification(recipient, **kwargs)
        if notification:
            notifications.append(notification)
    return notifications


def send_notification(notification):
    if notification.status == Notification.STATUS_CANCELLED:
        return False

    try:
        sent_any = False

        if notification.channel == NotificationTemplate.CHANNEL_PUSH:
            sent_any = send_push(notification) > 0
        elif notification.channel == NotificationTemplate.CHANNEL_EMAIL:
            if not notification.recipient.email:
                NotificationLog.objects.create(
                    notification=notification,
                    channel=NotificationTemplate.CHANNEL_EMAIL,
                    status=NotificationLog.STATUS_SKIPPED,
                    provider='smtp',
                    recipient=str(notification.recipient_id),
                    error_message='Recipient email is empty.',
                )
            else:
                send_mail(
                    notification.title,
                    notification.body,
                    None,
                    [notification.recipient.email],
                    fail_silently=False,
                )
                sent_any = True
                NotificationLog.objects.create(
                    notification=notification,
                    channel=NotificationTemplate.CHANNEL_EMAIL,
                    status=NotificationLog.STATUS_SUCCESS,
                    provider='smtp',
                    recipient=notification.recipient.email,
                    sent_at=timezone.now(),
                )
        else:
            sent_any = True
            NotificationLog.objects.create(
                notification=notification,
                channel=NotificationTemplate.CHANNEL_IN_APP,
                status=NotificationLog.STATUS_SUCCESS,
                provider='database',
                recipient=str(notification.recipient_id),
                sent_at=timezone.now(),
            )

        if sent_any:
            notification.mark_sent()
        else:
            notification.mark_failed('No delivery channel succeeded.')
        return sent_any
    except Exception as exc:
        notification.mark_failed(str(exc))
        NotificationLog.objects.create(
            notification=notification,
            channel=notification.channel,
            status=NotificationLog.STATUS_FAILED,
            provider=notification.channel,
            recipient=str(notification.recipient_id),
            error_message=str(exc),
        )
        return False


def notify_admins(title, body='', *, company=None, office=None, related_object=None, data=None, notification_type=NotificationTemplate.TYPE_SYSTEM):
    return create_notifications(
        get_admin_users(company=company, office=office),
        title=title,
        body=body,
        company=company,
        office=office,
        related_object=related_object,
        data=data or {},
        notification_type=notification_type,
        channel=NotificationTemplate.CHANNEL_IN_APP,
        priority=Notification.PRIORITY_HIGH,
    )


def user_can_see_notification(user, notification):
    return bool(is_erp_admin(user) or notification.recipient_id == user.id)
