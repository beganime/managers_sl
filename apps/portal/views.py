import calendar
import json
from collections import defaultdict
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.core.files.base import ContentFile
from django.http import FileResponse, Http404
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import NoReverseMatch, reverse, reverse_lazy
from django.utils.dateparse import parse_date
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.attendance.models import DailyReport, WorkDay
from apps.core.permissions import get_employee_profile, is_erp_admin
from apps.crm.models import Application, Client, Lead, LeadSource
from apps.education.models import City, Country, Currency, Program, University
from apps.erp_documents.models import DocumentDownloadLog, DocumentTemplate, GeneratedDocument
from apps.erp_notifications.models import Notification
from apps.employees.models import EmployeeProfile
from apps.erp_services.models import Service, ServiceCategory
from apps.finance.models import Cashbox, Deal, Expense, ExpenseCategory, FinancialPeriod, Income, Payment, Transaction
from apps.knowledge.models import KnowledgeArticle, KnowledgeCategory, KnowledgeTestAttempt
from apps.organizations.models import Office
from apps.portal.forms import (
    PortalClientForm,
    PortalDealForm,
    PortalDocumentGenerateForm,
    PortalExpenseForm,
    PortalIncomeForm,
    PortalKnowledgeArticleForm,
    PortalKnowledgeCategoryForm,
    PortalPaymentForm,
    PortalProgramForm,
    PortalProjectForm,
    PortalProjectSectionForm,
    PortalServiceForm,
    PortalTaskAttachmentForm,
    PortalTaskChecklistForm,
    PortalTaskChecklistItemForm,
    PortalTaskCommentForm,
    PortalTaskForm,
    PortalUniversityForm,
)
from apps.projects_v2.models import Project, ProjectSection, ProjectTask, TaskAttachment, TaskChecklist, TaskChecklistItem, TaskComment


PAGE_SIZE = 25
User = get_user_model()


NAV_GROUPS = (
    {
        'key': 'dashboard',
        'label': 'Дашборд',
        'icon': 'layout-dashboard',
        'items': (
            {'name': 'dashboard', 'label': 'Главная', 'icon': 'layout-dashboard'},
            {'name': 'workday', 'label': 'Рабочий день', 'icon': 'timer'},
            {'name': 'calendar', 'label': 'Календарь', 'icon': 'calendar-days'},
            {'name': 'notifications', 'label': 'Уведомления', 'icon': 'bell'},
        ),
    },
    {
        'key': 'crm',
        'label': 'CRM',
        'icon': 'users',
        'items': (
            {'name': 'leads', 'label': 'Лиды', 'icon': 'radar'},
            {'name': 'clients', 'label': 'Клиенты', 'icon': 'users'},
            {'name': 'applications', 'label': 'Заявки', 'icon': 'file-check-2'},
            {'name': 'tasks', 'label': 'Задачи', 'icon': 'check-square'},
            {'name': 'projects', 'label': 'Проекты', 'icon': 'folder-kanban'},
            {'name': 'finance', 'label': 'Финансы', 'icon': 'wallet-cards'},
        ),
    },
    {
        'key': 'rating',
        'label': 'Рейтинг',
        'icon': 'trophy',
        'items': (
            {'name': 'rating', 'label': 'Рейтинг сотрудников', 'icon': 'trophy'},
            {'name': 'reports', 'label': 'Отчёты', 'icon': 'bar-chart-3'},
            {'name': 'finance_reports', 'label': 'Балансы', 'icon': 'circle-dollar-sign'},
        ),
    },
    {
        'key': 'education',
        'label': 'Вузы',
        'icon': 'graduation-cap',
        'items': (
            {'name': 'universities', 'label': 'Вузы', 'icon': 'graduation-cap'},
            {'name': 'programs', 'label': 'Программы', 'icon': 'library-big'},
            {'name': 'services', 'label': 'Услуги', 'icon': 'briefcase-business'},
            {'name': 'knowledge', 'label': 'База знаний', 'icon': 'book-open-check'},
            {'name': 'documents', 'label': 'Документы', 'icon': 'file-text'},
        ),
    },
    {
        'key': 'settings',
        'label': 'Настройки',
        'icon': 'settings',
        'items': (
            {'name': 'profile', 'label': 'Профиль', 'icon': 'user-round'},
            {'name': 'settings', 'label': 'Настройки', 'icon': 'settings'},
            {'name': 'help', 'label': 'Помощь', 'icon': 'circle-help'},
            {'name': 'admin_data_help', 'label': 'Инструкция по админке', 'icon': 'list-checks'},
            {'name': 'admin', 'label': 'Админка', 'icon': 'shield-check', 'url': '/admin/', 'staff_only': True},
        ),
    },
)

MOBILE_NAV = (
    {'section': 'dashboard', 'name': 'dashboard', 'label': 'Дашборд', 'icon': 'layout-dashboard'},
    {'section': 'crm', 'name': 'leads', 'label': 'CRM', 'icon': 'users'},
    {'section': 'rating', 'name': 'rating', 'label': 'Рейтинг', 'icon': 'trophy'},
    {'section': 'education', 'name': 'universities', 'label': 'Вузы', 'icon': 'graduation-cap'},
    {'section': 'settings', 'name': 'settings', 'label': 'Настройки', 'icon': 'settings'},
)

ADMIN_QUICK_ACTIONS = (
    {'label': 'Добавить сотрудника', 'url_name': 'admin:users_user_add', 'icon': 'user-plus'},
    {'label': 'Добавить офис', 'url_name': 'admin:organizations_office_add', 'icon': 'building-2'},
    {'label': 'Добавить ВУЗ', 'url_name': 'admin:education_university_add', 'icon': 'graduation-cap'},
    {'label': 'Добавить программу', 'url_name': 'admin:education_program_add', 'icon': 'library-big'},
    {'label': 'Добавить услугу', 'url_name': 'admin:erp_services_service_add', 'icon': 'briefcase-business'},
    {'label': 'Добавить доход', 'url_name': 'portal:finance_income', 'icon': 'plus'},
    {'label': 'Добавить расход', 'url_name': 'portal:finance_expense', 'icon': 'minus'},
    {'label': 'Создать задачу', 'url_name': 'portal:tasks', 'icon': 'check-square'},
    {'label': 'Создать проект', 'url_name': 'admin:projects_v2_project_add', 'icon': 'folder-plus'},
    {'label': 'Перейти в админку', 'url': '/admin/', 'icon': 'shield-check'},
    {'label': 'Проверить документы', 'url_name': 'admin:erp_documents_generateddocument_changelist', 'icon': 'file-check-2'},
    {'label': 'Посмотреть отчёты', 'url_name': 'portal:reports', 'icon': 'bar-chart-3'},
)


def full_name(user):
    return user.get_full_name() or getattr(user, 'email', '') or str(user)


def bool_param(value):
    if value in ('1', 'true', 'True', 'yes', 'on'):
        return True
    if value in ('0', 'false', 'False', 'no', 'off'):
        return False
    return None


def safe_reverse(name, fallback='#'):
    try:
        return reverse(name)
    except NoReverseMatch:
        return fallback


def resolve_nav_url(item):
    if item.get('url'):
        return item['url']
    return safe_reverse(f'portal:{item["name"]}')


def build_nav_groups(user, active_page):
    groups = []
    for group in NAV_GROUPS:
        items = []
        is_group_active = False
        for item in group['items']:
            if item.get('staff_only') and not (user.is_staff or user.is_superuser):
                continue
            resolved = {**item, 'url': resolve_nav_url(item)}
            resolved['is_active'] = item['name'] == active_page
            is_group_active = is_group_active or resolved['is_active']
            items.append(resolved)
        if items:
            groups.append({**group, 'items': items, 'is_active': is_group_active})
    return groups


def get_active_section(active_page):
    for group in NAV_GROUPS:
        if any(item['name'] == active_page for item in group['items']):
            return group['key']
    return 'dashboard'


def build_mobile_nav(active_page):
    active_section = get_active_section(active_page)
    return [
        {
            **item,
            'url': safe_reverse(f'portal:{item["name"]}'),
            'is_active': item['section'] == active_section,
        }
        for item in MOBILE_NAV
    ]


def build_admin_quick_actions():
    actions = []
    for item in ADMIN_QUICK_ACTIONS:
        url = item.get('url') or safe_reverse(item['url_name'])
        if url != '#':
            actions.append({**item, 'url': url})
    return actions


def employee_scope_q(user, *, company_field='company', office_field='office', manager_field=None):
    if is_erp_admin(user):
        return Q()

    employee = get_employee_profile(user)
    if not employee:
        if manager_field:
            return Q(**{manager_field: user})
        return Q(pk__isnull=True)

    access = getattr(employee, 'access', None)
    role_type = employee.role.role_type if employee.role_id else None

    if role_type == 'company_owner' or (access and access.can_see_all_company):
        return Q(**{company_field: employee.company})

    if role_type == 'office_director' or (access and access.can_see_all_office):
        if employee.office_id and office_field:
            return Q(**{company_field: employee.company, office_field: employee.office})
        return Q(**{company_field: employee.company})

    if manager_field:
        return Q(**{manager_field: user})

    if employee.office_id and office_field:
        return Q(**{company_field: employee.company, office_field: employee.office})
    return Q(**{company_field: employee.company})


def lead_queryset(user):
    return Lead.objects.select_related('company', 'office', 'source', 'manager').filter(
        employee_scope_q(user, manager_field='manager'),
    )


def client_queryset(user):
    qs = Client.objects.select_related('company', 'office', 'manager')
    if is_erp_admin(user):
        return qs

    employee = get_employee_profile(user)
    if not employee:
        return qs.filter(Q(manager=user) | Q(shared_with=user)).distinct()

    scope = employee_scope_q(user, manager_field='manager')
    return qs.filter(scope | Q(shared_with=user)).distinct()


def application_queryset(user):
    return Application.objects.select_related('company', 'office', 'client', 'manager').filter(
        employee_scope_q(user, manager_field='manager'),
    )


def project_queryset(user):
    qs = Project.objects.select_related('company', 'office', 'created_by', 'owner').prefetch_related('participants', 'responsible_users')
    if is_erp_admin(user):
        return qs

    employee = get_employee_profile(user)
    if not employee:
        return qs.filter(Q(created_by=user) | Q(owner=user) | Q(participants=user) | Q(responsible_users=user)).distinct()

    scope = employee_scope_q(user)
    personal = Q(created_by=user) | Q(owner=user) | Q(participants=user) | Q(responsible_users=user) | Q(tasks__assigned_to=user) | Q(tasks__watchers__user=user)
    return qs.filter(scope | personal).distinct()


def task_queryset(user):
    projects = project_queryset(user).values('id')
    return ProjectTask.objects.select_related('project', 'section', 'assigned_to', 'created_by').filter(project_id__in=projects)


def deal_queryset(user):
    return Deal.objects.select_related('company', 'office', 'client', 'application', 'manager', 'currency').filter(
        employee_scope_q(user, manager_field='manager'),
    )


def payment_queryset(user):
    return Payment.objects.select_related('company', 'office', 'deal', 'client', 'manager', 'currency').filter(
        employee_scope_q(user, manager_field='manager'),
    )


def expense_queryset(user):
    qs = Expense.objects.select_related('company', 'office', 'category', 'employee', 'currency')
    if is_erp_admin(user):
        return qs
    return qs.filter(employee_scope_q(user, manager_field='employee'))


def document_queryset(user):
    qs = GeneratedDocument.objects.select_related('company', 'office', 'template', 'client', 'manager', 'approval')
    if is_erp_admin(user):
        return qs
    employee = get_employee_profile(user)
    scope = employee_scope_q(user, manager_field='manager')
    if employee:
        return qs.filter(scope | Q(client__shared_with=user)).distinct()
    return qs.filter(Q(manager=user) | Q(client__shared_with=user)).distinct()


def document_template_queryset(user):
    qs = DocumentTemplate.objects.select_related('company').prefetch_related('fields').filter(is_active=True)
    if is_erp_admin(user):
        return qs
    employee = get_employee_profile(user)
    if not employee:
        return qs.filter(company__isnull=True)
    return qs.filter(Q(company=employee.company) | Q(company__isnull=True))


def knowledge_queryset(user):
    qs = KnowledgeArticle.objects.select_related('company', 'office', 'category', 'author').filter(is_active=True)
    if is_erp_admin(user):
        return qs
    employee = get_employee_profile(user)
    if not employee:
        return qs.filter(company__isnull=True, is_public=True, status=KnowledgeArticle.STATUS_PUBLISHED)
    return qs.filter(
        (Q(company=employee.company) | Q(company__isnull=True)),
        (Q(office=employee.office) | Q(office__isnull=True)) if employee.office_id else Q(),
        is_public=True,
        status=KnowledgeArticle.STATUS_PUBLISHED,
    )


def notification_queryset(user):
    qs = Notification.objects.select_related('company', 'office', 'recipient', 'sender')
    if is_erp_admin(user):
        return qs
    return qs.filter(recipient=user)


def workday_queryset(user):
    qs = WorkDay.objects.select_related('company', 'office', 'employee', 'daily_report')
    if is_erp_admin(user):
        return qs
    return qs.filter(employee_scope_q(user, manager_field='employee'))


def employee_queryset(user):
    qs = EmployeeProfile.objects.select_related('user', 'company', 'office', 'department', 'position', 'role')
    if is_erp_admin(user):
        return qs

    employee = get_employee_profile(user)
    if not employee:
        return qs.filter(user=user)

    access = getattr(employee, 'access', None)
    role_type = employee.role.role_type if employee.role_id else None
    if role_type == 'company_owner' or (access and access.can_see_all_company):
        return qs.filter(company=employee.company)
    if role_type == 'office_director' or (access and access.can_see_all_office):
        if employee.office_id:
            return qs.filter(company=employee.company, office=employee.office)
        return qs.filter(company=employee.company)
    if employee.office_id:
        return qs.filter(company=employee.company, office=employee.office)
    return qs.filter(company=employee.company)


def office_queryset(user):
    qs = Office.objects.select_related('company').filter(is_active=True)
    if is_erp_admin(user):
        return qs
    employee = get_employee_profile(user)
    if not employee:
        return qs.none()
    if employee.office_id:
        return qs.filter(company=employee.company, id=employee.office_id)
    return qs.filter(company=employee.company)


def university_queryset(user):
    qs = University.objects.select_related('company', 'country', 'city', 'local_currency')
    if is_erp_admin(user):
        return qs
    employee = get_employee_profile(user)
    if not employee:
        return qs.filter(company__isnull=True)
    return qs.filter(Q(company=employee.company) | Q(company__isnull=True))


def program_queryset(user):
    universities = university_queryset(user).values('id')
    return Program.objects.select_related('university', 'university__country').prefetch_related('fees', 'intakes').filter(university_id__in=universities)


def service_queryset(user):
    qs = Service.objects.select_related('company', 'category', 'currency').prefetch_related('prices')
    if is_erp_admin(user):
        return qs
    employee = get_employee_profile(user)
    if not employee:
        return qs.filter(company__isnull=True, is_public=True)
    return qs.filter(Q(company=employee.company) | Q(company__isnull=True), is_public=True)


def service_category_queryset(user):
    qs = ServiceCategory.objects.select_related('company').filter(is_active=True)
    if is_erp_admin(user):
        return qs
    employee = get_employee_profile(user)
    if not employee:
        return qs.filter(company__isnull=True)
    return qs.filter(Q(company=employee.company) | Q(company__isnull=True))


def knowledge_category_queryset(user):
    qs = KnowledgeCategory.objects.select_related('company', 'parent').filter(is_active=True)
    if is_erp_admin(user):
        return qs
    employee = get_employee_profile(user)
    if not employee:
        return qs.filter(company__isnull=True, is_public=True)
    return qs.filter(Q(company=employee.company) | Q(company__isnull=True), is_public=True)


def cashbox_queryset(user):
    return Cashbox.objects.select_related('company', 'office', 'currency').filter(employee_scope_q(user))


def income_queryset(user):
    return Income.objects.select_related('company', 'office', 'cashbox', 'currency').filter(employee_scope_q(user))


def expense_category_queryset(user):
    qs = ExpenseCategory.objects.select_related('company').filter(is_active=True)
    if is_erp_admin(user):
        return qs
    employee = get_employee_profile(user)
    if not employee:
        return qs.none()
    return qs.filter(company=employee.company)


def project_section_queryset(user):
    return ProjectSection.objects.select_related('project').filter(project__in=project_queryset(user))


def portal_user_queryset(user):
    return User.objects.filter(id__in=employee_queryset(user).values('user_id'), is_active=True).order_by('first_name', 'last_name', 'email')


def can_confirm_finance(user):
    if user.is_staff or user.is_superuser or is_erp_admin(user):
        return True
    employee = get_employee_profile(user)
    access = getattr(employee, 'access', None) if employee else None
    return bool(access and access.can_manage_finance)


def can_delete_admin(user):
    return bool(user.is_staff or user.is_superuser or is_erp_admin(user))


def can_edit_owned(user, owner=None, participants=None):
    if can_delete_admin(user):
        return True
    if owner and owner == user:
        return True
    if participants is not None and participants.filter(pk=user.pk).exists():
        return True
    return False


def request_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_document_download(request, document, file_type):
    DocumentDownloadLog.objects.create(
        document=document,
        user=request.user,
        file_type=file_type,
        ip_address=request_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
    )


def next_annual_date(source_date, today):
    try:
        event_date = date(today.year, source_date.month, source_date.day)
    except ValueError:
        event_date = date(today.year, 2, 28)
    if event_date < today:
        try:
            event_date = date(today.year + 1, source_date.month, source_date.day)
        except ValueError:
            event_date = date(today.year + 1, 2, 28)
    return event_date


def build_calendar_events(user, limit_count=30):
    today = timezone.localdate()
    events = []

    for task in task_queryset(user).filter(deadline__isnull=False, deadline__date__gte=today).order_by('deadline')[:20]:
        events.append({
            'date': task.deadline.date(),
            'type': 'Task',
            'title': task.title,
            'details': task.project.title if task.project_id else '',
            'url': reverse('portal:tasks'),
        })

    for application in application_queryset(user).filter(submitted_at__isnull=False, submitted_at__gte=today).order_by('submitted_at')[:15]:
        events.append({
            'date': application.submitted_at,
            'type': 'Application',
            'title': application.client.full_name,
            'details': application.university_name or application.program_name,
            'url': reverse('portal:applications'),
        })

    for profile in employee_queryset(user).filter(user__dob__isnull=False)[:50]:
        events.append({
            'date': next_annual_date(profile.user.dob, today),
            'type': 'Birthday',
            'title': full_name(profile.user),
            'details': profile.office.name if profile.office_id else profile.company.name,
            'url': reverse('portal:calendar'),
        })

    return sorted(events, key=lambda item: item['date'])[:limit_count]


MONTH_NAMES_RU = (
    '',
    'Январь',
    'Февраль',
    'Март',
    'Апрель',
    'Май',
    'Июнь',
    'Июль',
    'Август',
    'Сентябрь',
    'Октябрь',
    'Ноябрь',
    'Декабрь',
)


def build_events_for_range(user, start_date, end_date):
    events = []

    for task in task_queryset(user).filter(
        deadline__isnull=False,
        deadline__date__gte=start_date,
        deadline__date__lte=end_date,
    ).order_by('deadline')[:200]:
        events.append({
            'date': task.deadline.date(),
            'type': 'Задача',
            'title': task.title,
            'details': task.project.title if task.project_id else '',
            'url': reverse('portal:tasks'),
            'tone': 'warn',
        })

    for application in application_queryset(user).filter(
        submitted_at__isnull=False,
        submitted_at__gte=start_date,
        submitted_at__lte=end_date,
    ).order_by('submitted_at')[:100]:
        events.append({
            'date': application.submitted_at,
            'type': 'Заявка',
            'title': application.client.full_name,
            'details': application.university_name or application.program_name,
            'url': reverse('portal:applications'),
            'tone': 'info',
        })

    for profile in employee_queryset(user).filter(user__dob__isnull=False)[:300]:
        birthday = next_annual_date(profile.user.dob, start_date)
        if start_date <= birthday <= end_date:
            events.append({
                'date': birthday,
                'type': 'День рождения',
                'title': full_name(profile.user),
                'details': profile.office.name if profile.office_id else profile.company.name,
                'url': reverse('portal:calendar'),
                'tone': 'ok',
            })

    for workday in workday_queryset(user).filter(date__gte=start_date, date__lte=end_date).order_by('date')[:300]:
        events.append({
            'date': workday.date,
            'type': 'Рабочий день',
            'title': full_name(workday.employee),
            'details': workday.get_status_display(),
            'url': reverse('portal:workday'),
            'tone': 'ok' if workday.status in (WorkDay.STATUS_CLOSED, WorkDay.STATUS_AUTO_CLOSED) else 'warn',
        })

    return events


def build_month_calendar(user, year, month):
    month_calendar = calendar.Calendar(firstweekday=0)
    weeks = month_calendar.monthdatescalendar(year, month)
    start_date = weeks[0][0]
    end_date = weeks[-1][-1]
    events_by_date = defaultdict(list)
    for event in build_events_for_range(user, start_date, end_date):
        events_by_date[event['date']].append(event)

    today = timezone.localdate()
    built_weeks = []
    for week in weeks:
        built_week = []
        for day in week:
            day_events = events_by_date.get(day, [])
            built_week.append({
                'date': day,
                'number': day.day,
                'in_current_month': day.month == month,
                'is_today': day == today,
                'events': day_events[:4],
                'more_count': max(len(day_events) - 4, 0),
            })
        built_weeks.append(built_week)
    return built_weeks


def apply_search(qs, query, fields):
    if not query:
        return qs
    q = Q()
    for field in fields:
        q |= Q(**{f'{field}__icontains': query})
    return qs.filter(q)


def limit(qs, amount=PAGE_SIZE):
    return qs[:amount]


def get_today_workday(user):
    if not user.is_authenticated:
        return None
    employee = get_employee_profile(user)
    today = timezone.localdate()
    workday = WorkDay.objects.filter(employee=user, date=today).select_related('company', 'office', 'daily_report').first()
    if workday or not employee:
        return workday
    return WorkDay(
        company=employee.company,
        office=employee.office,
        employee=user,
        date=today,
        status=WorkDay.STATUS_NOT_STARTED,
    )


def ensure_today_workday(user):
    employee = get_employee_profile(user)
    if not employee:
        raise ValueError('Employee profile is required.')
    today = timezone.localdate()
    workday, _ = WorkDay.objects.get_or_create(
        company=employee.company,
        employee=user,
        date=today,
        defaults={'office': employee.office, 'status': WorkDay.STATUS_NOT_STARTED},
    )
    if employee.office_id and workday.office_id != employee.office_id:
        workday.office = employee.office
        workday.save(update_fields=['office', 'updated_at'])
    return workday


class PortalContextMixin(LoginRequiredMixin):
    login_url = reverse_lazy('portal:login')
    active_page = ''
    page_title = ''

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = get_employee_profile(self.request.user)
        nav_groups = build_nav_groups(self.request.user, self.active_page)
        nav_items = [item for group in nav_groups for item in group['items']]
        can_access_admin = self.request.user.is_staff or self.request.user.is_superuser
        context.update({
            'active_page': self.active_page,
            'active_section': get_active_section(self.active_page),
            'page_title': self.page_title,
            'nav_groups': nav_groups,
            'nav_items': nav_items,
            'mobile_nav_items': build_mobile_nav(self.active_page),
            'employee_profile': employee,
            'display_name': full_name(self.request.user),
            'unread_notifications_count': notification_queryset(self.request.user).filter(read_at__isnull=True).exclude(status=Notification.STATUS_READ).count(),
            'can_access_admin': can_access_admin,
            'admin_quick_actions': build_admin_quick_actions() if can_access_admin else [],
            'is_htmx': self.request.headers.get('HX-Request') == 'true',
        })
        return context


class PortalIndexView(LoginRequiredMixin, View):
    login_url = reverse_lazy('portal:login')

    def get(self, request):
        return redirect('portal:dashboard')


class PortalHomeView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('portal:dashboard')
        return redirect('portal:login')


class PortalLoginView(LoginView):
    template_name = 'portal/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        return self.get_redirect_url() or reverse('portal:dashboard')


class PortalLogoutView(LoginRequiredMixin, View):
    login_url = reverse_lazy('portal:login')

    def get(self, request):
        logout(request)
        messages.success(request, 'Вы вышли из аккаунта.')
        return redirect('portal:login')

    def post(self, request):
        return self.get(request)


class DashboardView(PortalContextMixin, TemplateView):
    template_name = 'portal/dashboard.html'
    active_page = 'dashboard'
    page_title = 'Дашборд'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = timezone.localdate()
        week_ago = timezone.now() - timedelta(days=7)

        leads = lead_queryset(user)
        clients = client_queryset(user)
        applications = application_queryset(user)
        tasks = task_queryset(user)
        payments = payment_queryset(user)
        expenses = expense_queryset(user)
        projects = project_queryset(user)
        documents = document_queryset(user)
        notifications = notification_queryset(user)
        workdays = workday_queryset(user)
        employee_profiles = employee_queryset(user)
        confirmed_payments = payments.filter(is_confirmed=True)
        confirmed_expenses = expenses.filter(is_confirmed=True)
        revenue_month = confirmed_payments.filter(payment_date__gte=today.replace(day=1)).aggregate(total=Sum('amount_usd'))['total'] or 0
        expense_month = confirmed_expenses.filter(date__gte=today.replace(day=1)).aggregate(total=Sum('amount_usd'))['total'] or 0

        context.update({
            'metrics': [
                {'label': 'Лиды', 'value': leads.exclude(status__in=['converted', 'lost', 'spam']).count(), 'icon': 'radar', 'url': reverse('portal:leads')},
                {'label': 'Клиенты', 'value': clients.exclude(status__in=['archive', 'rejected']).count(), 'icon': 'users', 'url': reverse('portal:clients')},
                {'label': 'Заявки', 'value': applications.exclude(status__in=['cancelled', 'rejected', 'enrolled']).count(), 'icon': 'file-check-2', 'url': reverse('portal:applications')},
                {'label': 'Задачи', 'value': tasks.filter(Q(assigned_to=user) | Q(watchers__user=user)).exclude(status__in=[ProjectTask.STATUS_DONE, ProjectTask.STATUS_CANCELLED]).distinct().count(), 'icon': 'check-square', 'url': reverse('portal:tasks')},
                {'label': 'Платежи за 7 дней', 'value': payments.filter(is_confirmed=True, created_at__gte=week_ago).count(), 'icon': 'wallet-cards', 'url': reverse('portal:finance')},
                {'label': 'Документы', 'value': documents.filter(status__in=[GeneratedDocument.STATUS_PENDING, GeneratedDocument.STATUS_GENERATED]).count(), 'icon': 'file-text', 'url': reverse('portal:documents')},
                {'label': 'Уведомления', 'value': notifications.filter(read_at__isnull=True).exclude(status=Notification.STATUS_READ).count(), 'icon': 'bell', 'url': reverse('portal:notifications')},
            ],
            'admin_metrics': [
                {'label': 'Доходы месяца', 'value': revenue_month, 'icon': 'trending-up', 'money': True},
                {'label': 'Расходы месяца', 'value': expense_month, 'icon': 'trending-down', 'money': True},
                {'label': 'Прибыль', 'value': revenue_month - expense_month, 'icon': 'chart-no-axes-combined', 'money': True},
                {'label': 'Сотрудники', 'value': employee_profiles.filter(is_active=True).count(), 'icon': 'id-card'},
                {'label': 'Начали день', 'value': workdays.filter(date=today).exclude(status=WorkDay.STATUS_NOT_STARTED).count(), 'icon': 'timer'},
                {'label': 'Открытые проекты', 'value': projects.exclude(status__in=[Project.STATUS_DONE, Project.STATUS_ARCHIVED]).count(), 'icon': 'folder-kanban'},
            ] if is_erp_admin(user) or user.is_staff else [],
            'my_leads': limit(leads.exclude(status__in=['converted', 'lost', 'spam']).order_by('-created_at'), 6),
            'my_clients': limit(clients.order_by('-updated_at'), 6),
            'my_applications': limit(applications.order_by('-updated_at'), 6),
            'my_tasks': limit(tasks.filter(Q(assigned_to=user) | Q(watchers__user=user)).exclude(status__in=[ProjectTask.STATUS_DONE, ProjectTask.STATUS_CANCELLED]).distinct().order_by('deadline', '-updated_at'), 6),
            'my_projects': limit(projects.order_by('-updated_at'), 6),
            'workday': get_today_workday(user),
            'recent_payments': limit(payments.order_by('-payment_date', '-created_at'), 6),
            'recent_documents': limit(documents.order_by('-created_at'), 6),
            'notifications': limit(notifications.order_by('-created_at'), 8),
            'birthday_people': employee_profiles.filter(user__dob__month=today.month).order_by('user__dob__day')[:8],
            'calendar_events': build_calendar_events(user, limit_count=8),
            'knowledge_items': limit(knowledge_queryset(user).order_by('-is_featured', '-published_at', '-updated_at'), 5),
            'today': today,
        })
        return context


class ProfileView(PortalContextMixin, TemplateView):
    template_name = 'portal/profile.html'
    active_page = 'profile'
    page_title = 'Профиль'

    def post(self, request, *args, **kwargs):
        user = request.user
        action = request.POST.get('action', 'profile')

        if action == 'password':
            form = PasswordChangeForm(user, request.POST)
            if form.is_valid():
                updated_user = form.save()
                update_session_auth_hash(request, updated_user)
                messages.success(request, 'Пароль обновлён.')
            else:
                messages.error(request, 'Пароль не обновлён. Проверьте поля и попробуйте ещё раз.')
            return redirect('portal:profile')

        user.first_name = request.POST.get('first_name', '').strip()
        user.last_name = request.POST.get('last_name', '').strip()
        user.middle_name = request.POST.get('middle_name', '').strip()
        user.social_contacts = request.POST.get('social_contacts', '').strip()
        user.job_description = request.POST.get('job_description', '').strip()
        user.work_status = request.POST.get('work_status') or user.work_status
        dob = parse_date(request.POST.get('dob') or '')
        user.dob = dob
        if 'avatar' in request.FILES:
            user.avatar = request.FILES['avatar']
        user.save(update_fields=[
            'first_name',
            'last_name',
            'middle_name',
            'social_contacts',
            'job_description',
            'work_status',
            'dob',
            'avatar',
            'updated_at',
        ])
        messages.success(request, 'Профиль обновлён.')
        return redirect('portal:profile')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'work_status_choices': User.STATUS_CHOICES,
            'password_form': PasswordChangeForm(self.request.user),
        })
        return context


class SettingsView(PortalContextMixin, TemplateView):
    template_name = 'portal/settings.html'
    active_page = 'settings'
    page_title = 'Настройки'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = context.get('employee_profile')
        context.update({
            'access': getattr(employee, 'access', None) if employee else None,
            'api_links': [
                {'label': 'CRM API', 'url': '/api/v1/crm/'},
                {'label': 'Education API', 'url': '/api/v1/education/'},
                {'label': 'Services API', 'url': '/api/v1/services/'},
                {'label': 'Finance API', 'url': '/api/v1/finance/'},
                {'label': 'Documents API', 'url': '/api/v1/documents/'},
                {'label': 'Attendance API', 'url': '/api/v1/attendance/'},
            ],
        })
        return context


class HelpView(PortalContextMixin, TemplateView):
    template_name = 'portal/help.html'
    active_page = 'help'
    page_title = 'Помощь'


class AdminDataHelpView(PortalContextMixin, TemplateView):
    template_name = 'portal/help_admin_data.html'
    active_page = 'admin_data_help'
    page_title = 'Инструкция по заполнению базы'


class ListPageMixin(PortalContextMixin, TemplateView):
    template_name = 'portal/list_page.html'
    table_template = ''
    search_fields = ()
    status_choices = ()
    status_field = 'status'
    default_ordering = '-created_at'

    def get_queryset(self):
        raise NotImplementedError

    def get_table_title(self):
        return self.page_title

    def get_extra_context(self, qs):
        return {}

    def filter_queryset(self, qs):
        request = self.request
        qs = apply_search(qs, request.GET.get('q'), self.search_fields)
        status_value = request.GET.get('status')
        if status_value and self.status_field:
            qs = qs.filter(**{self.status_field: status_value})
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = self.filter_queryset(self.get_queryset())
        ordering = self.request.GET.get('ordering') or self.default_ordering
        context.update({
            'items': limit(qs.order_by(ordering)),
            'total_count': qs.count(),
            'table_template': self.table_template,
            'table_title': self.get_table_title(),
            'status_choices': self.status_choices,
            'current_status': self.request.GET.get('status', ''),
            'query': self.request.GET.get('q', ''),
            'ordering': ordering,
        })
        context.update(self.get_extra_context(qs))
        if context['is_htmx']:
            self.template_name = self.table_template
        return context


class UniversitiesView(ListPageMixin):
    template_name = 'portal/universities.html'
    active_page = 'universities'
    page_title = 'Вузы'
    table_template = 'portal/partials/universities_table.html'
    search_fields = ('name', 'legal_name', 'country__name', 'city__name', 'description')
    status_field = ''
    default_ordering = 'country__name'

    def get_queryset(self):
        qs = university_queryset(self.request.user)
        is_active = bool_param(self.request.GET.get('is_active'))
        if is_active is not None:
            qs = qs.filter(is_active=is_active)
        return qs

    def get_edit_object(self):
        edit_id = self.request.GET.get('edit') or self.request.POST.get('object_id')
        if not edit_id:
            return None
        return self.get_queryset().filter(pk=edit_id).first()

    def get_form(self, data=None, instance=None):
        return PortalUniversityForm(
            data=data,
            instance=instance,
            countries=Country.objects.filter(is_active=True).order_by('sort_order', 'name'),
            cities=City.objects.select_related('country').filter(is_active=True).order_by('country__name', 'name'),
            currencies=Currency.objects.order_by('code'),
        )

    def get_extra_context(self, qs):
        edit_object = self.get_edit_object()
        return {
            'form': self.get_form(instance=edit_object),
            'edit_object': edit_object,
            'can_add_program': True,
        }

    def post(self, request, *args, **kwargs):
        edit_object = self.get_edit_object()
        form = self.get_form(data=request.POST, instance=edit_object)
        if form.is_valid():
            university = form.save(commit=False)
            employee = get_employee_profile(request.user)
            if not is_erp_admin(request.user) and employee:
                university.company = employee.company
            elif not university.company_id and employee:
                university.company = employee.company
            university.added_by = request.user
            university.save()
            messages.success(request, 'ВУЗ сохранён.')
            return redirect('portal:universities')
        context = self.get_context_data()
        context['form'] = form
        context['edit_object'] = edit_object
        return self.render_to_response(context)


class ProgramsView(ListPageMixin):
    template_name = 'portal/programs.html'
    active_page = 'programs'
    page_title = 'Программы'
    table_template = 'portal/partials/programs_table.html'
    search_fields = ('name', 'faculty', 'language', 'university__name', 'university__country__name')
    status_choices = Program.DEGREE_CHOICES
    status_field = 'degree'
    default_ordering = 'university__name'

    def get_queryset(self):
        qs = program_queryset(self.request.user)
        university = self.request.GET.get('university')
        if university:
            qs = qs.filter(university_id=university)
        return qs

    def get_edit_object(self):
        edit_id = self.request.GET.get('edit') or self.request.POST.get('object_id')
        if not edit_id:
            return None
        return self.get_queryset().filter(pk=edit_id).first()

    def get_form(self, data=None, instance=None):
        return PortalProgramForm(
            data=data,
            instance=instance,
            universities=university_queryset(self.request.user).filter(is_active=True).order_by('country__name', 'name'),
        )

    def get_extra_context(self, qs):
        edit_object = self.get_edit_object()
        return {
            'form': self.get_form(instance=edit_object),
            'edit_object': edit_object,
            'universities': university_queryset(self.request.user).filter(is_active=True).order_by('country__name', 'name')[:300],
            'selected_university': self.request.GET.get('university', ''),
        }

    def post(self, request, *args, **kwargs):
        edit_object = self.get_edit_object()
        form = self.get_form(data=request.POST, instance=edit_object)
        if form.is_valid():
            form.save()
            messages.success(request, 'Программа сохранена.')
            return redirect('portal:programs')
        context = self.get_context_data()
        context['form'] = form
        context['edit_object'] = edit_object
        return self.render_to_response(context)


class ServicesView(ListPageMixin):
    template_name = 'portal/services.html'
    active_page = 'services'
    page_title = 'Услуги'
    table_template = 'portal/partials/services_table.html'
    search_fields = ('title', 'code', 'description', 'category__name')
    status_field = ''
    default_ordering = 'sort_order'

    def get_queryset(self):
        qs = service_queryset(self.request.user)
        is_active = bool_param(self.request.GET.get('is_active'))
        if is_active is not None:
            qs = qs.filter(is_active=is_active)
        return qs

    def get_edit_object(self):
        edit_id = self.request.GET.get('edit') or self.request.POST.get('object_id')
        if not edit_id:
            return None
        return service_queryset(self.request.user).filter(pk=edit_id).first()

    def get_form(self, data=None, instance=None):
        return PortalServiceForm(
            data=data,
            instance=instance,
            categories=service_category_queryset(self.request.user).order_by('sort_order', 'name'),
            currencies=Currency.objects.order_by('code'),
        )

    def get_extra_context(self, qs):
        edit_object = self.get_edit_object()
        return {
            'form': self.get_form(instance=edit_object),
            'edit_object': edit_object,
            'can_delete_items': can_delete_admin(self.request.user),
        }

    def post(self, request, *args, **kwargs):
        action = request.POST.get('action', 'save')
        service = self.get_edit_object()
        if action == 'delete' and service and can_delete_admin(request.user):
            service.delete()
            messages.success(request, 'Услуга удалена.')
            return redirect('portal:services')

        form = self.get_form(data=request.POST, instance=service)
        if form.is_valid():
            employee = get_employee_profile(request.user)
            category = form.cleaned_data.get('category')
            category_name = (form.cleaned_data.get('category_name') or '').strip()
            if not category and category_name:
                company = employee.company if employee else None
                category, _ = ServiceCategory.objects.get_or_create(
                    company=company,
                    code=(category_name.lower().replace(' ', '-')[:80] or 'service-category'),
                    defaults={'name': category_name, 'description': ''},
                )
            item = form.save(commit=False)
            if employee and not is_erp_admin(request.user):
                item.company = employee.company
            elif employee and not item.company_id:
                item.company = employee.company
            item.category = category
            if not item.code:
                item.code = (item.title.lower().replace(' ', '-')[:80] or f'service-{item.pk or "new"}')
            if not item.pk:
                item.created_by = request.user
            item.updated_by = request.user
            item.save()
            messages.success(request, 'Услуга сохранена.')
            return redirect('portal:services')
        context = self.get_context_data()
        context['form'] = form
        context['edit_object'] = service
        return self.render_to_response(context)


class LeadsView(ListPageMixin):
    active_page = 'leads'
    page_title = 'Лиды'
    table_template = 'portal/partials/leads_table.html'
    search_fields = ('full_name', 'phone', 'email', 'interested_country', 'interested_program', 'comment')
    status_choices = Lead.STATUS_CHOICES

    def get_queryset(self):
        return lead_queryset(self.request.user).select_related('manager', 'source')


class ClientsView(ListPageMixin):
    template_name = 'portal/clients.html'
    active_page = 'clients'
    page_title = 'Клиенты'
    table_template = 'portal/partials/clients_table.html'
    search_fields = ('full_name', 'phone', 'email', 'city', 'citizenship', 'comments')
    status_choices = Client.STATUS_CHOICES

    def get_queryset(self):
        return client_queryset(self.request.user).select_related('manager')

    def get_edit_object(self):
        edit_id = self.request.GET.get('edit') or self.request.POST.get('object_id')
        if not edit_id:
            return None
        return client_queryset(self.request.user).filter(pk=edit_id).first()

    def get_form(self, data=None, instance=None):
        return PortalClientForm(
            data=data,
            instance=instance,
            managers=portal_user_queryset(self.request.user),
            offices=office_queryset(self.request.user),
            sources=LeadSource.objects.filter(is_active=True).order_by('name'),
        )

    def get_extra_context(self, qs):
        edit_object = self.get_edit_object()
        return {
            'form': self.get_form(instance=edit_object),
            'edit_object': edit_object,
        }

    def post(self, request, *args, **kwargs):
        client = self.get_edit_object()
        form = self.get_form(data=request.POST, instance=client)
        if form.is_valid():
            employee = get_employee_profile(request.user)
            item = form.save(commit=False)
            if employee:
                item.company = employee.company
                if not item.office_id and employee.office_id:
                    item.office = employee.office
            if not item.manager_id:
                item.manager = request.user
            item.save()
            form.save_m2m()
            messages.success(request, 'Клиент сохранён.')
            return redirect('portal:clients')
        context = self.get_context_data()
        context['form'] = form
        context['edit_object'] = client
        return self.render_to_response(context)


class ClientDetailView(PortalContextMixin, TemplateView):
    template_name = 'portal/client_detail.html'
    active_page = 'clients'
    page_title = 'Карточка клиента'

    def get_client(self):
        return get_object_or_404(client_queryset(self.request.user), pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = self.get_client()
        context.update({
            'client': client,
            'applications': application_queryset(self.request.user).filter(client=client).order_by('-created_at'),
            'deals': deal_queryset(self.request.user).filter(client=client).order_by('-created_at'),
            'documents': document_queryset(self.request.user).filter(client=client).order_by('-created_at'),
        })
        return context


class ClientDocumentCreateView(PortalContextMixin, TemplateView):
    template_name = 'portal/client_document_form.html'
    active_page = 'documents'
    page_title = 'Создать документ'

    def get_client(self):
        return get_object_or_404(client_queryset(self.request.user), pk=self.kwargs['pk'])

    def get_form(self, data=None):
        client = self.get_client()
        return PortalDocumentGenerateForm(
            data=data,
            templates=document_template_queryset(self.request.user).order_by('name'),
            applications=application_queryset(self.request.user).filter(client=client).order_by('-created_at'),
            deals=deal_queryset(self.request.user).filter(client=client).order_by('-created_at'),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = self.get_client()
        template = document_template_queryset(self.request.user).first()
        preview_document = None
        if template:
            employee = get_employee_profile(self.request.user)
            preview_document = GeneratedDocument(
                company=client.company,
                office=client.office or (employee.office if employee else None),
                template=template,
                client=client,
                manager=client.manager or self.request.user,
            )
        context.update({
            'client': client,
            'form': context.get('form') or self.get_form(),
            'preview_context': preview_document.build_context() if preview_document else {},
        })
        return context

    def post(self, request, *args, **kwargs):
        client = self.get_client()
        form = self.get_form(data=request.POST)
        if form.is_valid():
            template = form.cleaned_data['template']
            application = form.cleaned_data.get('application')
            deal = form.cleaned_data.get('deal')
            context_data = {}
            raw_context = (form.cleaned_data.get('context_data') or '').strip()
            if raw_context:
                try:
                    context_data = json.loads(raw_context)
                except json.JSONDecodeError:
                    messages.error(request, 'Дополнительные данные должны быть валидным JSON.')
                    context = self.get_context_data()
                    context['form'] = form
                    return self.render_to_response(context)

            employee = get_employee_profile(request.user)
            document = GeneratedDocument.objects.create(
                company=client.company,
                office=client.office or (employee.office if employee else None),
                template=template,
                client=client,
                application=application,
                deal=deal,
                manager=request.user,
                title=form.cleaned_data.get('title') or f'{template.name} - {client.full_name}',
                context_data=context_data,
            )
            try:
                document.generate_file()
                messages.success(request, 'Документ создан. DOCX без печати доступен для скачивания.')
            except Exception as exc:
                document.status = GeneratedDocument.STATUS_ERROR
                document.generation_error = str(exc)
                document.save(update_fields=['status', 'generation_error', 'updated_at'])
                messages.error(request, f'Ошибка генерации документа: {exc}')
            return redirect('portal:documents')
        context = self.get_context_data()
        context['form'] = form
        return self.render_to_response(context)


class ApplicationsView(ListPageMixin):
    active_page = 'applications'
    page_title = 'Заявки'
    table_template = 'portal/partials/applications_table.html'
    search_fields = ('client__full_name', 'university_name', 'program_name', 'country', 'comment')
    status_choices = Application.STATUS_CHOICES

    def get_queryset(self):
        return application_queryset(self.request.user).select_related('client', 'manager')


class TasksView(ListPageMixin):
    template_name = 'portal/tasks.html'
    active_page = 'tasks'
    page_title = 'Задачи'
    table_template = 'portal/partials/tasks_table.html'
    search_fields = ('title', 'description', 'project__title', 'assigned_to__email')
    status_choices = ProjectTask.STATUS_CHOICES
    default_ordering = 'deadline'

    def get_queryset(self):
        qs = task_queryset(self.request.user)
        assignee = self.request.GET.get('assignee')
        deadline_from = parse_date(self.request.GET.get('deadline_from') or '')
        deadline_to = parse_date(self.request.GET.get('deadline_to') or '')
        if assignee:
            qs = qs.filter(assigned_to_id=assignee)
        if deadline_from:
            qs = qs.filter(deadline__date__gte=deadline_from)
        if deadline_to:
            qs = qs.filter(deadline__date__lte=deadline_to)
        return qs

    def get_edit_object(self):
        edit_id = self.request.GET.get('edit') or self.request.POST.get('object_id')
        if not edit_id:
            return None
        return task_queryset(self.request.user).filter(pk=edit_id).first()

    def get_form(self, data=None, instance=None):
        projects = project_queryset(self.request.user).filter(is_active=True).order_by('-is_pinned', 'title')
        return PortalTaskForm(
            data=data,
            instance=instance,
            projects=projects,
            sections=ProjectSection.objects.filter(project__in=projects).select_related('project').order_by('project__title', 'sort_order', 'title'),
            employees=portal_user_queryset(self.request.user),
        )

    def get_extra_context(self, qs):
        edit_object = self.get_edit_object()
        return {
            'form': self.get_form(instance=edit_object),
            'edit_object': edit_object,
            'assignees': portal_user_queryset(self.request.user),
            'current_assignee': self.request.GET.get('assignee', ''),
            'deadline_from': self.request.GET.get('deadline_from', ''),
            'deadline_to': self.request.GET.get('deadline_to', ''),
        }

    def post(self, request, *args, **kwargs):
        edit_object = self.get_edit_object()
        form = self.get_form(data=request.POST, instance=edit_object)
        if form.is_valid():
            task = form.save(commit=False)
            if not task.created_by_id:
                task.created_by = request.user
            if task.status == ProjectTask.STATUS_DONE and not task.completed_by_id:
                task.completed_by = request.user
            task.save()
            messages.success(request, 'Задача сохранена.')
            return redirect('portal:tasks')
        context = self.get_context_data()
        context['form'] = form
        context['edit_object'] = edit_object
        return self.render_to_response(context)


class ProjectsView(ListPageMixin):
    template_name = 'portal/projects.html'
    active_page = 'projects'
    page_title = 'Проекты'
    table_template = 'portal/partials/projects_table.html'
    search_fields = ('title', 'code', 'description', 'owner__email')
    status_choices = Project.STATUS_CHOICES
    default_ordering = '-updated_at'

    def get_queryset(self):
        return project_queryset(self.request.user)

    def get_extra_context(self, qs):
        return {'can_delete_items': can_delete_admin(self.request.user)}


class ProjectCreateView(PortalContextMixin, TemplateView):
    template_name = 'portal/project_form.html'
    active_page = 'projects'
    page_title = 'Создать проект'

    def get_object(self):
        pk = self.kwargs.get('pk')
        if not pk:
            return None
        project = get_object_or_404(project_queryset(self.request.user), pk=pk)
        if not can_edit_owned(self.request.user, owner=project.created_by or project.owner, participants=project.participants):
            raise Http404
        return project

    def get_form(self, data=None, instance=None):
        return PortalProjectForm(data=data, instance=instance, employees=portal_user_queryset(self.request.user))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.get_object()
        context.update({
            'project': project,
            'form': context.get('form') or self.get_form(instance=project),
        })
        return context

    def post(self, request, *args, **kwargs):
        project = self.get_object()
        form = self.get_form(data=request.POST, instance=project)
        if form.is_valid():
            employee = get_employee_profile(request.user)
            item = form.save(commit=False)
            if employee and not item.company_id:
                item.company = employee.company
            if employee and employee.office_id and not item.office_id:
                item.office = employee.office
            if not item.created_by_id:
                item.created_by = request.user
            if not item.owner_id:
                item.owner = request.user
            if not item.code:
                item.code = (item.title.lower().replace(' ', '-')[:100] or f'project-{item.pk or "new"}')
            item.save()
            form.save_m2m()
            item.participants.add(request.user)
            messages.success(request, 'Проект сохранён.')
            return redirect('portal:project_detail', pk=item.pk)
        context = self.get_context_data()
        context['form'] = form
        return self.render_to_response(context)


class ProjectDetailView(PortalContextMixin, TemplateView):
    template_name = 'portal/project_detail.html'
    active_page = 'projects'
    page_title = 'Проект'

    def get_project(self):
        return get_object_or_404(project_queryset(self.request.user), pk=self.kwargs['pk'])

    def post(self, request, *args, **kwargs):
        project = self.get_project()
        action = request.POST.get('action')
        if action == 'delete_project' and can_delete_admin(request.user):
            project.delete()
            messages.success(request, 'Проект удалён.')
            return redirect('portal:projects')
        if action == 'add_section':
            form = PortalProjectSectionForm(request.POST)
            if form.is_valid():
                section = form.save(commit=False)
                section.project = project
                section.save()
                messages.success(request, 'Раздел добавлен.')
            else:
                messages.error(request, 'Раздел не сохранён. Проверьте поля.')
        return redirect('portal:project_detail', pk=project.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.get_project()
        tasks = ProjectTask.objects.filter(project=project).select_related('section', 'assigned_to', 'created_by').prefetch_related('comments', 'checklists__items', 'attachments')
        context.update({
            'project': project,
            'sections': project.sections.filter(is_active=True).order_by('sort_order', 'title'),
            'tasks': tasks.order_by('section__sort_order', 'deadline', '-updated_at'),
            'section_form': PortalProjectSectionForm(),
            'can_edit_project': can_edit_owned(self.request.user, owner=project.created_by or project.owner, participants=project.participants),
            'can_delete_project': can_delete_admin(self.request.user),
        })
        return context


class ProjectTaskCreateView(PortalContextMixin, TemplateView):
    template_name = 'portal/project_task_form.html'
    active_page = 'projects'
    page_title = 'Создать задачу'

    def get_project(self):
        return get_object_or_404(project_queryset(self.request.user), pk=self.kwargs['pk'])

    def get_task(self):
        task_id = self.kwargs.get('task_id')
        if not task_id:
            return None
        return get_object_or_404(task_queryset(self.request.user), pk=task_id, project=self.get_project())

    def get_form(self, data=None, instance=None):
        project = self.get_project()
        return PortalTaskForm(
            data=data,
            instance=instance,
            projects=Project.objects.filter(pk=project.pk),
            sections=project.sections.filter(is_active=True).order_by('sort_order', 'title'),
            employees=portal_user_queryset(self.request.user),
        )

    def post(self, request, *args, **kwargs):
        project = self.get_project()
        task = self.get_task()
        if request.POST.get('action') == 'delete' and task and (can_delete_admin(request.user) or task.created_by_id == request.user.id):
            task.delete()
            messages.success(request, 'Задача удалена.')
            return redirect('portal:project_detail', pk=project.pk)
        form = self.get_form(data=request.POST, instance=task)
        if form.is_valid():
            item = form.save(commit=False)
            item.project = project
            if not item.created_by_id:
                item.created_by = request.user
            if item.status == ProjectTask.STATUS_DONE and not item.completed_by_id:
                item.completed_by = request.user
            item.save()
            messages.success(request, 'Задача сохранена.')
            return redirect('portal:project_detail', pk=project.pk)
        context = self.get_context_data()
        context['form'] = form
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        task = self.get_task()
        context.update({
            'project': self.get_project(),
            'task': task,
            'form': context.get('form') or self.get_form(instance=task),
        })
        return context


class ProjectTaskActionView(LoginRequiredMixin, View):
    login_url = reverse_lazy('portal:login')

    def post(self, request, pk, task_id):
        project = get_object_or_404(project_queryset(request.user), pk=pk)
        task = get_object_or_404(task_queryset(request.user), pk=task_id, project=project)
        action = request.POST.get('action')
        if action == 'comment':
            form = PortalTaskCommentForm(request.POST)
            if form.is_valid():
                comment = form.save(commit=False)
                comment.task = task
                comment.author = request.user
                comment.save()
                messages.success(request, 'Комментарий добавлен.')
        elif action == 'checklist':
            form = PortalTaskChecklistForm(request.POST)
            if form.is_valid():
                checklist = form.save(commit=False)
                checklist.task = task
                checklist.save()
                messages.success(request, 'Чек-лист добавлен.')
        elif action == 'checklist_item':
            checklist = get_object_or_404(TaskChecklist, pk=request.POST.get('checklist'), task=task)
            form = PortalTaskChecklistItemForm(request.POST)
            if form.is_valid():
                item = form.save(commit=False)
                item.checklist = checklist
                item.done_by = request.user if item.is_done else None
                item.save()
                messages.success(request, 'Пункт чек-листа добавлен.')
        elif action == 'attachment':
            form = PortalTaskAttachmentForm(request.POST, request.FILES)
            if form.is_valid():
                attachment = form.save(commit=False)
                attachment.task = task
                attachment.uploaded_by = request.user
                attachment.save()
                messages.success(request, 'Файл или ссылка добавлены.')
        elif action == 'complete':
            task.complete(user=request.user)
            messages.success(request, 'Задача закрыта.')
        elif action == 'reopen':
            task.reopen()
            messages.success(request, 'Задача открыта заново.')
        return redirect('portal:project_detail', pk=project.pk)


class FinanceView(PortalContextMixin, TemplateView):
    template_name = 'portal/finance.html'
    active_page = 'finance'
    page_title = 'Финансы'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        payments = payment_queryset(user)
        deals = deal_queryset(user)
        expenses = expense_queryset(user)
        incomes = income_queryset(user)
        current_month = timezone.localdate().replace(day=1)
        cashboxes = cashbox_queryset(user)
        context.update({
            'payment_total_usd': payments.filter(is_confirmed=True, payment_date__gte=current_month).aggregate(total=Sum('amount_usd'))['total'] or 0,
            'income_total_usd': incomes.filter(date__gte=current_month).aggregate(total=Sum('amount_usd'))['total'] or 0,
            'expense_total_usd': expenses.filter(is_confirmed=True, date__gte=current_month).aggregate(total=Sum('amount_usd'))['total'] or 0,
            'open_deals_count': deals.exclude(payment_status__in=[Deal.PAYMENT_STATUS_FULL, Deal.PAYMENT_STATUS_CANCELLED, Deal.PAYMENT_STATUS_REFUNDED]).count(),
            'cashboxes': limit(cashboxes.order_by('office__name', 'name'), 8),
            'recent_payments': limit(payments.order_by('-payment_date', '-created_at')),
            'recent_incomes': limit(incomes.order_by('-date', '-created_at')),
            'recent_deals': limit(deals.order_by('-created_at')),
            'recent_expenses': limit(expenses.order_by('-date', '-created_at')),
        })
        return context


class FinanceIncomeView(PortalContextMixin, TemplateView):
    template_name = 'portal/finance_records.html'
    active_page = 'finance'
    page_title = 'Доходы'

    def get_form(self, data=None):
        return PortalIncomeForm(
            data=data,
            cashboxes=cashbox_queryset(self.request.user).filter(is_active=True).order_by('office__name', 'name'),
            currencies=Currency.objects.order_by('code'),
        )

    def post(self, request, *args, **kwargs):
        form = self.get_form(data=request.POST)
        if form.is_valid():
            income = form.save(commit=False)
            cashbox = form.cleaned_data['cashbox']
            income.company = cashbox.company
            income.office = cashbox.office
            if not income.currency_id:
                income.currency = cashbox.currency
            income.save()
            cashbox.balance = cashbox.balance + income.amount
            cashbox.save(update_fields=['balance', 'updated_at'])
            Transaction.objects.create(
                company=income.company,
                office=income.office,
                cashbox=cashbox,
                transaction_type=Transaction.TYPE_INCOME,
                amount=income.amount,
                currency=income.currency,
                amount_usd=income.amount_usd,
                created_by=request.user,
                comment=income.comment or income.source,
            )
            messages.success(request, 'Доход добавлен.')
            return redirect('portal:finance_income')
        context = self.get_context_data()
        context['form'] = form
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = income_queryset(self.request.user)
        qs = apply_search(qs, self.request.GET.get('q'), ('title', 'source', 'comment', 'cashbox__name'))
        context.update({
            'record_type': 'income',
            'form': context.get('form') or self.get_form(),
            'records': limit(qs.order_by('-date', '-created_at'), 50),
            'total_usd': qs.aggregate(total=Sum('amount_usd'))['total'] or 0,
            'query': self.request.GET.get('q', ''),
        })
        return context


class FinanceExpenseView(PortalContextMixin, TemplateView):
    template_name = 'portal/finance_records.html'
    active_page = 'finance'
    page_title = 'Расходы'

    def get_form(self, data=None):
        return PortalExpenseForm(
            data=data,
            categories=expense_category_queryset(self.request.user).order_by('company__name', 'name'),
            cashboxes=cashbox_queryset(self.request.user).filter(is_active=True).order_by('office__name', 'name'),
            currencies=Currency.objects.order_by('code'),
        )

    def post(self, request, *args, **kwargs):
        form = self.get_form(data=request.POST)
        if form.is_valid():
            expense = form.save(commit=False)
            category = form.cleaned_data['category']
            cashbox = form.cleaned_data.get('cashbox')
            employee = get_employee_profile(request.user)
            expense.company = category.company
            expense.office = cashbox.office if cashbox else (employee.office if employee else None)
            expense.employee = request.user
            if cashbox and not expense.currency_id:
                expense.currency = cashbox.currency
            expense.save()
            if form.cleaned_data.get('confirm_now') and can_confirm_finance(request.user):
                expense.confirm(user=request.user)
                messages.success(request, 'Расход добавлен и подтверждён.')
            else:
                messages.success(request, 'Расход добавлен и ожидает подтверждения.')
            return redirect('portal:finance_expense')
        context = self.get_context_data()
        context['form'] = form
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = expense_queryset(self.request.user)
        qs = apply_search(qs, self.request.GET.get('q'), ('title', 'comment', 'category__name', 'employee__email'))
        context.update({
            'record_type': 'expense',
            'form': context.get('form') or self.get_form(),
            'can_confirm_finance': can_confirm_finance(self.request.user),
            'records': limit(qs.order_by('-date', '-created_at'), 50),
            'total_usd': qs.aggregate(total=Sum('amount_usd'))['total'] or 0,
            'query': self.request.GET.get('q', ''),
        })
        return context


class FinanceDealsView(PortalContextMixin, TemplateView):
    template_name = 'portal/finance_deals.html'
    active_page = 'finance'
    page_title = 'Сделки'

    def get_form(self, data=None):
        return PortalDealForm(
            data=data,
            clients=client_queryset(self.request.user).order_by('-updated_at'),
            applications=application_queryset(self.request.user).order_by('-created_at'),
            services=service_queryset(self.request.user).filter(is_active=True).order_by('category__name', 'title'),
            currencies=Currency.objects.order_by('code'),
        )

    def post(self, request, *args, **kwargs):
        form = self.get_form(data=request.POST)
        if form.is_valid():
            employee = get_employee_profile(request.user)
            deal = form.save(commit=False)
            if employee:
                deal.company = employee.company
                if not deal.office_id:
                    deal.office = employee.office
            else:
                deal.company = deal.client.company
                deal.office = deal.client.office
            deal.manager = request.user
            if deal.service_id:
                service = deal.service
                if not deal.title:
                    deal.title = service.title
                if not deal.price_client:
                    deal.price_client = service.price_client
                if not deal.currency_id and service.currency_id:
                    deal.currency = service.currency
            deal.save()
            messages.success(request, 'Сделка сохранена.')
            return redirect('portal:finance_deals')
        context = self.get_context_data()
        context['form'] = form
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = deal_queryset(self.request.user)
        qs = apply_search(qs, self.request.GET.get('q'), ('title', 'client__full_name', 'service__title', 'comment'))
        context.update({
            'form': context.get('form') or self.get_form(),
            'deals': limit(qs.order_by('-created_at'), 50),
            'query': self.request.GET.get('q', ''),
        })
        return context


class FinancePaymentsView(PortalContextMixin, TemplateView):
    template_name = 'portal/finance_payments.html'
    active_page = 'finance'
    page_title = 'Платежи'

    def get_form(self, data=None):
        return PortalPaymentForm(
            data=data,
            deals=deal_queryset(self.request.user).order_by('-created_at'),
            cashboxes=cashbox_queryset(self.request.user).filter(is_active=True).order_by('office__name', 'name'),
            currencies=Currency.objects.order_by('code'),
        )

    def post(self, request, *args, **kwargs):
        form = self.get_form(data=request.POST)
        if form.is_valid():
            deal = form.cleaned_data['deal']
            payment = form.save(commit=False)
            payment.company = deal.company
            payment.office = deal.office
            payment.client = deal.client
            payment.manager = request.user
            payment.save()
            if request.POST.get('confirm_now') and can_confirm_finance(request.user):
                payment.confirm(user=request.user)
                messages.success(request, 'Платёж добавлен и подтверждён.')
            else:
                messages.success(request, 'Платёж добавлен и ожидает подтверждения.')
            return redirect('portal:finance_payments')
        context = self.get_context_data()
        context['form'] = form
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = payment_queryset(self.request.user)
        qs = apply_search(qs, self.request.GET.get('q'), ('client__full_name', 'deal__title', 'comment'))
        context.update({
            'form': context.get('form') or self.get_form(),
            'payments': limit(qs.order_by('-payment_date', '-created_at'), 50),
            'query': self.request.GET.get('q', ''),
            'can_confirm_finance': can_confirm_finance(self.request.user),
        })
        return context


class FinanceReportsView(PortalContextMixin, TemplateView):
    template_name = 'portal/finance_reports.html'
    active_page = 'finance'
    page_title = 'Финансовые отчёты'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        month_start = timezone.localdate().replace(day=1)
        payments = payment_queryset(self.request.user).filter(is_confirmed=True)
        expenses = expense_queryset(self.request.user).filter(is_confirmed=True)
        incomes = Income.objects.select_related('company', 'office', 'cashbox', 'currency').filter(employee_scope_q(self.request.user))
        office_rows = payments.values('office__name').annotate(total=Sum('amount_usd'), count=Count('id')).order_by('-total')[:12]
        context.update({
            'month_revenue_usd': payments.filter(payment_date__gte=month_start).aggregate(total=Sum('amount_usd'))['total'] or 0,
            'month_income_usd': incomes.filter(date__gte=month_start).aggregate(total=Sum('amount_usd'))['total'] or 0,
            'month_expense_usd': expenses.filter(date__gte=month_start).aggregate(total=Sum('amount_usd'))['total'] or 0,
            'office_rows': office_rows,
            'periods': FinancialPeriod.objects.select_related('company', 'office').filter(employee_scope_q(self.request.user)).order_by('-start_date')[:12],
        })
        return context


class DocumentsView(ListPageMixin):
    template_name = 'portal/documents.html'
    active_page = 'documents'
    page_title = 'Документы'
    table_template = 'portal/partials/documents_table.html'
    search_fields = ('title', 'template__name', 'client__full_name', 'deal__title')
    status_choices = GeneratedDocument.STATUS_CHOICES

    def get_queryset(self):
        return document_queryset(self.request.user)

    def get_extra_context(self, qs):
        return {
            'pending_documents': qs.filter(status=GeneratedDocument.STATUS_PENDING).count(),
            'can_review_documents': can_delete_admin(self.request.user),
        }


class DocumentActionView(LoginRequiredMixin, View):
    login_url = reverse_lazy('portal:login')

    def get_document(self, request, pk):
        return get_object_or_404(document_queryset(request.user), pk=pk)

    def post(self, request, pk, action):
        document = self.get_document(request, pk)
        try:
            if action == 'submit':
                document.submit_for_approval(user=request.user, comment=request.POST.get('comment', ''))
                messages.success(request, 'Документ отправлен на подтверждение.')
            elif action == 'approve':
                if not can_delete_admin(request.user):
                    raise PermissionError('Недостаточно прав.')
                document.approve(user=request.user, with_stamp=request.POST.get('with_stamp') == '1', comment=request.POST.get('comment', ''))
                messages.success(request, 'Документ подтверждён.')
            elif action == 'reject':
                if not can_delete_admin(request.user):
                    raise PermissionError('Недостаточно прав.')
                document.reject(user=request.user, reason=request.POST.get('reason', ''))
                messages.success(request, 'Документ отклонён.')
        except Exception as exc:
            messages.error(request, str(exc))
        return redirect('portal:documents')

    def get(self, request, pk, action):
        document = self.get_document(request, pk)
        if action == 'download-original':
            if not document.can_download_original:
                raise Http404
            log_document_download(request, document, DocumentDownloadLog.FILE_TYPE_ORIGINAL)
            return FileResponse(document.generated_file.open('rb'), as_attachment=True, filename=document.generated_file.name.split('/')[-1])
        if action == 'download-approved':
            if not document.can_download_approved:
                raise Http404
            log_document_download(request, document, DocumentDownloadLog.FILE_TYPE_APPROVED)
            return FileResponse(document.approved_file.open('rb'), as_attachment=True, filename=document.approved_file.name.split('/')[-1])
        raise Http404


class KnowledgeView(PortalContextMixin, TemplateView):
    template_name = 'portal/knowledge.html'
    active_page = 'knowledge'
    page_title = 'База знаний'

    def get_folder(self):
        folder_id = self.kwargs.get('pk')
        if not folder_id:
            return None
        return get_object_or_404(knowledge_category_queryset(self.request.user), pk=folder_id)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        folder = self.get_folder()
        query = self.request.GET.get('q', '')
        categories = knowledge_category_queryset(self.request.user)
        articles = knowledge_queryset(self.request.user)
        if folder:
            child_folders = categories.filter(parent=folder)
            folder_articles = articles.filter(category=folder)
            breadcrumbs = []
            current = folder
            while current:
                breadcrumbs.append(current)
                current = current.parent
            breadcrumbs.reverse()
        else:
            child_folders = categories.filter(parent__isnull=True)
            folder_articles = articles.filter(category__isnull=True)
            breadcrumbs = []
        if query:
            folder_articles = apply_search(articles, query, ('title', 'summary', 'content', 'category__name'))
            child_folders = apply_search(categories, query, ('name', 'description'))
        context.update({
            'folder': folder,
            'breadcrumbs': breadcrumbs,
            'folders': child_folders.order_by('sort_order', 'name'),
            'articles': folder_articles.order_by('-is_featured', '-updated_at')[:80],
            'query': query,
            'can_delete_items': can_delete_admin(self.request.user),
        })
        context['attempts'] = KnowledgeTestAttempt.objects.filter(user=self.request.user).select_related('test').order_by('-created_at')[:8]
        return context


class KnowledgeFolderCreateView(PortalContextMixin, TemplateView):
    template_name = 'portal/knowledge_folder_form.html'
    active_page = 'knowledge'
    page_title = 'Папка базы знаний'

    def get_object(self):
        pk = self.kwargs.get('pk')
        if not pk:
            return None
        return get_object_or_404(knowledge_category_queryset(self.request.user), pk=pk)

    def get_form(self, data=None, instance=None):
        categories = knowledge_category_queryset(self.request.user).exclude(pk=instance.pk if instance else None)
        return PortalKnowledgeCategoryForm(data=data, instance=instance, categories=categories)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        folder = self.get_object()
        context.update({
            'folder': folder,
            'form': context.get('form') or self.get_form(instance=folder),
        })
        return context

    def post(self, request, *args, **kwargs):
        folder = self.get_object()
        if request.POST.get('action') == 'delete' and folder and can_delete_admin(request.user):
            parent_id = folder.parent_id
            folder.delete()
            messages.success(request, 'Папка удалена.')
            return redirect('portal:knowledge_folder', pk=parent_id) if parent_id else redirect('portal:knowledge')
        form = self.get_form(data=request.POST, instance=folder)
        if form.is_valid():
            employee = get_employee_profile(request.user)
            item = form.save(commit=False)
            if employee and not item.company_id:
                item.company = employee.company
            if not item.code:
                item.code = (item.name.lower().replace(' ', '-')[:100] or f'folder-{item.pk or "new"}')
            if not item.created_by_id:
                item.created_by = request.user
            item.save()
            messages.success(request, 'Папка сохранена.')
            return redirect('portal:knowledge_folder', pk=item.pk)
        context = self.get_context_data()
        context['form'] = form
        return self.render_to_response(context)


class KnowledgeArticleCreateView(PortalContextMixin, TemplateView):
    template_name = 'portal/knowledge_article_form.html'
    active_page = 'knowledge'
    page_title = 'Статья базы знаний'

    def get_object(self):
        pk = self.kwargs.get('pk')
        if not pk:
            return None
        return get_object_or_404(knowledge_queryset(self.request.user), pk=pk)

    def get_form(self, data=None, files=None, instance=None):
        return PortalKnowledgeArticleForm(
            data=data,
            files=files,
            instance=instance,
            categories=knowledge_category_queryset(self.request.user).order_by('sort_order', 'name'),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        article = self.get_object()
        context.update({
            'article': article,
            'form': context.get('form') or self.get_form(instance=article),
            'can_delete_article': bool(article and can_delete_admin(self.request.user)),
        })
        return context

    def post(self, request, *args, **kwargs):
        article = self.get_object()
        if request.POST.get('action') == 'delete' and article and can_delete_admin(request.user):
            category_id = article.category_id
            article.delete()
            messages.success(request, 'Статья удалена.')
            return redirect('portal:knowledge_folder', pk=category_id) if category_id else redirect('portal:knowledge')
        form = self.get_form(data=request.POST, files=request.FILES, instance=article)
        if form.is_valid():
            employee = get_employee_profile(request.user)
            item = form.save(commit=False)
            if employee and not item.company_id:
                item.company = employee.company
                item.office = employee.office
            if not item.author_id:
                item.author = request.user
            item.updated_by = request.user
            item.save()
            form.save_attachment(item, request.user)
            messages.success(request, 'Статья сохранена.')
            return redirect('portal:knowledge_article', pk=item.pk)
        context = self.get_context_data()
        context['form'] = form
        return self.render_to_response(context)


class KnowledgeArticleView(PortalContextMixin, TemplateView):
    template_name = 'portal/knowledge_article.html'
    active_page = 'knowledge'
    page_title = 'Статья'

    def get_article(self):
        return get_object_or_404(knowledge_queryset(self.request.user).prefetch_related('attachments'), pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        article = self.get_article()
        article.mark_read(self.request.user)
        context.update({
            'article': article,
            'can_edit_article': True,
            'can_delete_article': can_delete_admin(self.request.user),
        })
        return context


class WorkdayView(PortalContextMixin, TemplateView):
    template_name = 'portal/workday.html'
    active_page = 'workday'
    page_title = 'Рабочий день'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'workday': get_today_workday(self.request.user),
            'reports': DailyReport.objects.filter(employee=self.request.user).select_related('workday').order_by('-date')[:10],
            'history': workday_queryset(self.request.user).order_by('-date')[:10],
        })
        return context


class WorkdayActionMixin(LoginRequiredMixin, View):
    login_url = reverse_lazy('portal:login')
    success_url = 'portal:workday'

    def get_workday(self):
        return ensure_today_workday(self.request.user)

    def redirect_back(self):
        if self.request.headers.get('HX-Request') == 'true':
            return redirect(self.success_url)
        return redirect(self.success_url)


class WorkdayStartView(WorkdayActionMixin):
    def post(self, request):
        try:
            self.get_workday().start(note=request.POST.get('note', ''))
            messages.success(request, 'Workday started.')
        except ValueError as exc:
            messages.error(request, str(exc))
        return self.redirect_back()


class WorkdayReportView(WorkdayActionMixin):
    def post(self, request):
        content = request.POST.get('content') or request.POST.get('report') or ''
        if not content.strip():
            messages.error(request, 'Daily report content is required.')
            return self.redirect_back()
        try:
            self.get_workday().submit_report(
                content,
                results=request.POST.get('results', ''),
                plans=request.POST.get('plans', ''),
                problems=request.POST.get('problems', ''),
                comment=request.POST.get('comment', ''),
            )
            messages.success(request, 'Daily report submitted.')
        except ValueError as exc:
            messages.error(request, str(exc))
        return self.redirect_back()


class WorkdayCloseView(WorkdayActionMixin):
    def post(self, request):
        try:
            workday = self.get_workday()
            if workday.report_required and not workday.has_report and not is_erp_admin(request.user):
                messages.error(request, 'Submit daily report before closing the workday.')
            else:
                workday.close(user=request.user, comment=request.POST.get('comment', ''))
                messages.success(request, 'Workday closed.')
        except ValueError as exc:
            messages.error(request, str(exc))
        return self.redirect_back()


class CalendarView(PortalContextMixin, TemplateView):
    template_name = 'portal/calendar.html'
    active_page = 'calendar'
    page_title = 'Календарь'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        try:
            month = int(self.request.GET.get('month') or today.month)
        except ValueError:
            month = today.month
        try:
            year = int(self.request.GET.get('year') or today.year)
        except ValueError:
            year = today.year
        month = min(max(month, 1), 12)
        year = min(max(year, today.year - 5), today.year + 5)
        prev_month = month - 1
        prev_year = year
        next_month = month + 1
        next_year = year
        if prev_month == 0:
            prev_month = 12
            prev_year -= 1
        if next_month == 13:
            next_month = 1
            next_year += 1

        context.update({
            'calendar_weeks': build_month_calendar(self.request.user, year, month),
            'weekday_labels': ('Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'),
            'selected_month': month,
            'selected_year': year,
            'selected_month_name': MONTH_NAMES_RU[month],
            'month_options': [(number, MONTH_NAMES_RU[number]) for number in range(1, 13)],
            'year_options': range(today.year - 3, today.year + 4),
            'previous_month': prev_month,
            'previous_year': prev_year,
            'next_month': next_month,
            'next_year': next_year,
            'events': build_calendar_events(self.request.user, limit_count=80),
            'upcoming_tasks': task_queryset(self.request.user).filter(deadline__isnull=False, deadline__date__gte=today).order_by('deadline')[:12],
            'birthdays': employee_queryset(self.request.user).filter(user__dob__isnull=False).order_by('user__dob__month', 'user__dob__day')[:50],
        })
        return context


class RatingView(PortalContextMixin, TemplateView):
    template_name = 'portal/rating.html'
    active_page = 'rating'
    page_title = 'Рейтинг'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        month_start = today.replace(day=1)
        rows = []
        for profile in employee_queryset(self.request.user).filter(is_active=True):
            user = profile.user
            leads_count = Lead.objects.filter(manager=user, created_at__date__gte=month_start).count()
            clients_count = Client.objects.filter(manager=user).exclude(status__in=['archive', 'rejected']).count()
            applications_count = Application.objects.filter(manager=user, created_at__date__gte=month_start).count()
            payments_usd = Payment.objects.filter(manager=user, is_confirmed=True, payment_date__gte=month_start).aggregate(total=Sum('amount_usd'))['total'] or 0
            tasks_done = ProjectTask.objects.filter(assigned_to=user, status=ProjectTask.STATUS_DONE, completed_at__date__gte=month_start).count()
            workdays = WorkDay.objects.filter(employee=user, date__gte=month_start)
            started_days = workdays.exclude(status=WorkDay.STATUS_NOT_STARTED).count()
            closed_days = workdays.filter(status__in=[WorkDay.STATUS_CLOSED, WorkDay.STATUS_AUTO_CLOSED]).count()
            missed_days = workdays.filter(status=WorkDay.STATUS_MISSED).count()
            score = (
                leads_count * 2
                + clients_count * 3
                + applications_count * 4
                + int(payments_usd or 0) // 100
                + tasks_done * 3
                + started_days
                + closed_days * 2
                - missed_days * 5
            )
            rows.append({
                'profile': profile,
                'score': score,
                'leads_count': leads_count,
                'clients_count': clients_count,
                'applications_count': applications_count,
                'payments_usd': payments_usd,
                'tasks_done': tasks_done,
                'started_days': started_days,
                'closed_days': closed_days,
                'missed_days': missed_days,
            })
        context['rating_rows'] = sorted(rows, key=lambda item: item['score'], reverse=True)
        return context


class NotificationsView(ListPageMixin):
    active_page = 'notifications'
    page_title = 'Уведомления'
    table_template = 'portal/partials/notifications_table.html'
    search_fields = ('title', 'body', 'recipient__email', 'sender__email')
    status_choices = Notification.STATUS_CHOICES
    default_ordering = '-created_at'

    def get_queryset(self):
        qs = notification_queryset(self.request.user)
        unread = bool_param(self.request.GET.get('unread'))
        if unread is True:
            qs = qs.filter(read_at__isnull=True).exclude(status=Notification.STATUS_READ)
        elif unread is False:
            qs = qs.filter(Q(read_at__isnull=False) | Q(status=Notification.STATUS_READ))
        return qs


class ReportsView(PortalContextMixin, TemplateView):
    template_name = 'portal/reports.html'
    active_page = 'reports'
    page_title = 'Отчёты'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        month_start = timezone.localdate().replace(day=1)
        leads = lead_queryset(user)
        clients = client_queryset(user)
        applications = application_queryset(user)
        tasks = task_queryset(user)
        payments = payment_queryset(user)
        expenses = expense_queryset(user)
        context.update({
            'crm_summary': [
                {'label': 'New leads', 'value': leads.filter(status='new', created_at__date__gte=month_start).count()},
                {'label': 'Converted leads', 'value': leads.filter(status='converted', converted_at__date__gte=month_start).count()},
                {'label': 'Active clients', 'value': clients.exclude(status__in=['archive', 'rejected']).count()},
                {'label': 'Active applications', 'value': applications.exclude(status__in=['cancelled', 'rejected', 'enrolled']).count()},
            ],
            'task_summary': [
                {'label': 'Open tasks', 'value': tasks.exclude(status__in=[ProjectTask.STATUS_DONE, ProjectTask.STATUS_CANCELLED]).count()},
                {'label': 'Done tasks', 'value': tasks.filter(status=ProjectTask.STATUS_DONE, completed_at__date__gte=month_start).count()},
                {'label': 'Overdue tasks', 'value': tasks.exclude(status__in=[ProjectTask.STATUS_DONE, ProjectTask.STATUS_CANCELLED]).filter(deadline__lt=timezone.now()).count()},
            ],
            'finance_summary': [
                {'label': 'Revenue USD', 'value': payments.filter(is_confirmed=True, payment_date__gte=month_start).aggregate(total=Sum('amount_usd'))['total'] or 0},
                {'label': 'Expenses USD', 'value': expenses.filter(is_confirmed=True, date__gte=month_start).aggregate(total=Sum('amount_usd'))['total'] or 0},
                {'label': 'Closed periods', 'value': FinancialPeriod.objects.filter(is_closed=True).count()},
            ],
        })
        return context
