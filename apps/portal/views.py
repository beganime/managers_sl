import calendar
import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import urljoin, urlsplit

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.http import FileResponse, Http404
from django.db.models import Case, Count, IntegerField, Prefetch, Q, Sum, Value, When
from django.shortcuts import get_object_or_404, redirect
from django.urls import NoReverseMatch, reverse, reverse_lazy
from django.utils.dateparse import parse_date, parse_datetime
from django.utils import timezone
from django.utils.text import slugify
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import TemplateView

from apps.attendance.models import DailyReport, WorkDay
from apps.core.models import SystemSetting
from apps.core.permissions import get_employee_profile, is_erp_admin
from apps.crm.models import Application, Client, ClientFile, ClientQuestionnaire, Lead, LeadSource, ManagerDocumentCredit, ManagerDocumentPlan
from apps.education.cache import education_cache_get, education_cache_set, make_education_cache_key
from apps.education.models import City, Country, Currency, Program, ProgramFee, University
from apps.erp_documents.models import DocumentDownloadLog, DocumentTemplate, GeneratedDocument
from apps.erp_notifications.models import Notification, NotificationBatch, NotificationTemplate
from apps.employees.models import EmployeeProfile, EmployeeRating
from apps.erp_services.models import Service, ServiceCategory
from apps.finance.models import Cashbox, Deal, EmployeeCommission, Expense, ExpenseCategory, FinancialPeriod, Income, Payment, Transaction
from apps.knowledge.models import KnowledgeArticle, KnowledgeCategory, KnowledgeTestAttempt
from apps.organizations.models import Company, Office
from apps.portal.forms import (
    PortalCalendarEventForm,
    PortalClientForm,
    PortalDealForm,
    PortalDocumentGenerateForm,
    PortalExpenseForm,
    PortalIncomeForm,
    PortalKnowledgeArticleForm,
    PortalKnowledgeCategoryForm,
    PortalNotificationForm,
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
from apps.portal.models import CalendarEvent
from apps.projects_v2.models import Project, ProjectSection, ProjectTask, TaskAttachment, TaskChecklist, TaskChecklistItem, TaskComment


PAGE_SIZE = 25
User = get_user_model()

QUESTIONNAIRE_FIELD_LABELS = {
    'form_type': 'Тип заявки',
    'application_type': 'Тип заявки',
    'status': 'Статус анкеты',
    'full_name': 'Полное ФИО',
    'birth_date': 'Дата рождения',
    'gender': 'Пол',
    'citizenship': 'Гражданство',
    'marital_status': 'Семейное положение',
    'face_photo_url': 'Фотография лица',
    'residence_country': 'Страна проживания',
    'residence_region': 'Область / регион',
    'residence_city': 'Город / населенный пункт',
    'residence_street': 'Улица',
    'residence_house': 'Дом / квартира',
    'residence_postal_code': 'Почтовый индекс',
    'passport_number': 'Паспорт серия и номер',
    'passport_issued_by': 'Где оформлен паспорт',
    'passport_issue_date': 'Дата начала действия паспорта',
    'passport_expiry_date': 'Дата окончания действия паспорта',
    'phone': 'Основной номер телефона',
    'email': 'Email',
    'extra_phone': 'Дополнительный номер телефона',
    'imo': 'Imo',
    'telegram': 'Telegram',
    'preferred_contact_method': 'Предпочтительный способ связи',
    'parent_full_name': 'ФИО родителя',
    'parent_relation': 'Кем является родитель',
    'parent_contacts': 'Контакты родителя',
    'parent_workplace': 'Кем и где работает родитель',
    'family_members': 'Состав семьи',
    'education_level': 'Уровень образования',
    'school_class': 'Класс',
    'school_name': 'Учебное заведение',
    'school_country': 'Страна учебного заведения',
    'school_city': 'Город учебного заведения',
    'graduation_year': 'Год окончания',
    'education_status': 'Текущий статус образования',
    'achievements': 'Достижения',
    'languages': 'Языки',
    'desired_program': 'Желаемая программа / вуз',
    'admission_goal': 'Цель поступления',
    'desired_city': 'Желаемый город поступления',
    'desired_country': 'Желаемая страна поступления',
    'desired_language': 'Желаемый язык обучения',
    'desired_education_level': 'Желаемый уровень обучения',
    'admission_urgency': 'Срочность поступления',
    'help_needed': 'Нужна помощь с',
    'has_visa': 'Виза имеется или нет',
    'visa_country': 'Страна оформления визы',
    'visa_city': 'Город оформления визы',
    'visa_valid_until': 'Срок действия визы',
    'has_international_passport': 'Есть действующий загранпаспорт',
    'hobbies': 'Любимые хобби',
    'applicant_comment': 'Дополнительный комментарий',
    'referral_source': 'Откуда узнали о Student’s Life',
    'data_processing_consent': 'Согласие на обработку персональных данных',
    'submitted_at': 'Дата отправки анкеты',
    'generated_document_url': 'Документ анкеты',
    'generated_document_at': 'Дата формирования документа',
}

QUESTIONNAIRE_SECTIONS = (
    ('Личные данные', ('full_name', 'birth_date', 'gender', 'citizenship', 'marital_status')),
    ('Адрес проживания', ('residence_country', 'residence_region', 'residence_city', 'residence_street', 'residence_house', 'residence_postal_code')),
    ('Паспортные данные', ('passport_number', 'passport_issued_by', 'passport_issue_date', 'passport_expiry_date', 'has_international_passport')),
    ('Контакты', ('phone', 'email', 'extra_phone', 'imo', 'telegram', 'preferred_contact_method')),
    ('Родители / представители', ('parent_full_name', 'parent_relation', 'parent_contacts', 'parent_workplace', 'family_members')),
    ('Образование', ('education_status', 'education_level', 'school_class', 'school_name', 'school_country', 'school_city', 'graduation_year')),
    ('Достижения и языки', ('achievements', 'languages')),
    ('Поступление', ('desired_program', 'admission_goal', 'desired_country', 'desired_city', 'desired_language', 'desired_education_level', 'admission_urgency', 'help_needed')),
    ('Виза', ('has_visa', 'visa_country', 'visa_city', 'visa_valid_until')),
    ('Дополнительно', ('hobbies', 'applicant_comment', 'referral_source', 'data_processing_consent')),
)


def questionnaire_value_display(value):
    if value in (None, '', [], {}):
        return '-'
    if isinstance(value, bool):
        return 'Да' if value else 'Нет'
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, dict):
                language = item.get('language') or item.get('name') or item.get('title')
                level = item.get('level')
                if language and level:
                    lines.append(f'{language} — {level}')
                elif language:
                    lines.append(str(language))
                else:
                    lines.append(', '.join(f'{QUESTIONNAIRE_FIELD_LABELS.get(str(key), key)}: {questionnaire_value_display(val)}' for key, val in item.items()))
            else:
                lines.append(str(item))
        return '\n'.join(lines) if lines else '-'
    if isinstance(value, dict):
        return '\n'.join(f'{QUESTIONNAIRE_FIELD_LABELS.get(str(key), key)}: {questionnaire_value_display(val)}' for key, val in value.items())
    return str(value)


def build_questionnaire_sections(data):
    data = data or {}
    used_fields = set()
    sections = []
    for title, fields in QUESTIONNAIRE_SECTIONS:
        rows = []
        for field in fields:
            if field not in data:
                continue
            used_fields.add(field)
            rows.append({
                'label': QUESTIONNAIRE_FIELD_LABELS.get(field, field),
                'value': questionnaire_value_display(data.get(field)),
                'filled': data.get(field) not in (None, '', [], {}),
            })
        if rows:
            sections.append({'title': title, 'rows': rows})

    ignored_fields = {
        'id',
        'document_file',
        'generated_document_url',
        'generated_document_at',
        'missing_required_fields',
        'missing_required_field_labels',
        'updated_at',
        'attachments',
    }
    extra_rows = []
    for key, value in sorted(data.items()):
        if key in used_fields or key in ignored_fields:
            continue
        extra_rows.append({
            'label': QUESTIONNAIRE_FIELD_LABELS.get(key, key),
            'value': questionnaire_value_display(value),
            'filled': value not in (None, '', [], {}),
        })
    if extra_rows:
        sections.append({'title': 'Дополнительные синхронизированные поля', 'rows': extra_rows})
    return sections


def questionnaire_generated_document_url(questionnaire):
    data = questionnaire.data or {}
    return (
        data.get('generated_document_url')
        or data.get('document_file')
        or data.get('generated_document')
        or ''
    )


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
            {'name': 'incoming_leads', 'label': 'Потенциальные клиенты', 'icon': 'inbox'},
            {'name': 'clients', 'label': 'Клиенты', 'icon': 'users'},
            {'name': 'client_documents', 'label': 'Документы клиентов', 'icon': 'file-check-2'},
            {'name': 'document_upload_rating', 'label': 'Рейтинг загрузок', 'icon': 'badge-plus'},
            {'name': 'client_questionnaires', 'label': 'Анкеты клиентов', 'icon': 'clipboard-list'},
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
            {'name': 'approvals', 'label': 'Подтверждения', 'icon': 'badge-check'},
            {'name': 'reports', 'label': 'Отчёты', 'icon': 'bar-chart-3'},
            {'name': 'employee_reports', 'label': 'Отчёты сотрудников', 'icon': 'clipboard-list', 'staff_only': True},
            {'name': 'finance_reports', 'label': 'Балансы', 'icon': 'circle-dollar-sign'},
        ),
    },
    {
        'key': 'education',
        'label': 'Вузы',
        'icon': 'graduation-cap',
        'items': (
            {'name': 'countries', 'label': 'Страны', 'icon': 'map'},
            {'name': 'cities', 'label': 'Города', 'icon': 'map-pin'},
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
    {'label': 'Добавить уведомление', 'url_name': 'portal:notification_create', 'icon': 'bell-plus'},
    {'label': 'Создать задачу', 'url_name': 'portal:tasks', 'icon': 'check-square'},
    {'label': 'Создать проект', 'url_name': 'admin:projects_v2_project_add', 'icon': 'folder-plus'},
    {'label': 'Перейти в админку', 'url': '/admin/', 'icon': 'shield-check'},
    {'label': 'Проверить документы', 'url_name': 'admin:erp_documents_generateddocument_changelist', 'icon': 'file-check-2'},
    {'label': 'Посмотреть отчёты', 'url_name': 'portal:reports', 'icon': 'bar-chart-3'},
)


def full_name(user):
    return user.get_full_name() or getattr(user, 'email', '') or str(user)


def fallback_company():
    return Company.objects.order_by('id').first()


def get_system_currency():
    currency, _ = Currency.objects.get_or_create(
        code='USD',
        defaults={
            'name': 'US Dollar',
            'symbol': '$',
            'rate_to_usd': Decimal('1.000000'),
        },
    )
    update_fields = []
    if currency.rate_to_usd != Decimal('1.000000'):
        currency.rate_to_usd = Decimal('1.000000')
        update_fields.append('rate_to_usd')
    if not currency.symbol:
        currency.symbol = '$'
        update_fields.append('symbol')
    if update_fields:
        update_fields.append('updated_at')
        currency.save(update_fields=update_fields)
    return currency


def get_user_company_office(user):
    employee = get_employee_profile(user)
    company = employee.company if employee and employee.company_id else fallback_company()
    office = employee.office if employee and employee.office_id else None
    return employee, company, office


def get_or_create_usd_cashbox(user, *, company=None, office=None):
    _, profile_company, profile_office = get_user_company_office(user)
    company = company or profile_company
    office = office if office is not None else profile_office
    if not company:
        raise ValueError('Сначала создайте компанию и профиль сотрудника.')
    usd = get_system_currency()
    cashbox, created = Cashbox.objects.get_or_create(
        company=company,
        office=office,
        name='USD',
        defaults={'currency': usd, 'balance': Decimal('0.00'), 'is_active': True},
    )
    updates = []
    if cashbox.currency_id != usd.id:
        cashbox.currency = usd
        updates.append('currency')
    if not cashbox.is_active:
        cashbox.is_active = True
        updates.append('is_active')
    if updates:
        updates.append('updated_at')
        cashbox.save(update_fields=updates)
    return cashbox


def unique_code(model, base_text, *, company=None, field='code', max_length=100, exclude_pk=None):
    base = slugify(base_text or '')[:max_length].strip('-') or 'item'
    code = base
    index = 2
    while True:
        filters = {field: code}
        if company is not None and any(f.name == 'company' for f in model._meta.fields):
            filters['company'] = company
        qs = model.objects.filter(**filters)
        if exclude_pk:
            qs = qs.exclude(pk=exclude_pk)
        if not qs.exists():
            return code
        suffix = f'-{index}'
        code = f'{base[:max_length - len(suffix)]}{suffix}'
        index += 1


def get_or_create_default_project_section(project):
    section = project.sections.filter(is_active=True).order_by('sort_order', 'id').first()
    if section:
        return section
    return ProjectSection.objects.create(
        project=project,
        title='Основные задачи',
        description='Автоматический раздел для первых задач проекта.',
        sort_order=0,
    )


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


def lead_queryset(user, include_archived=False):
    qs = Lead.objects.select_related('company', 'office', 'source', 'manager').filter(
        employee_scope_q(user, manager_field='manager'),
    )
    if not include_archived:
        qs = qs.filter(is_archived=False)
    return qs


def incoming_lead_queryset(user):
    qs = Lead.objects.select_related('company', 'office', 'source', 'manager').filter(status__in=['new', 'contacted', 'qualified'], is_archived=False)
    if is_erp_admin(user):
        return qs
    employee = get_employee_profile(user)
    personal = Q(manager=user) | Q(manager__isnull=True)
    if employee and employee.company_id:
        return qs.filter(personal | Q(company=employee.company)).distinct()
    return qs.filter(personal).distinct()


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
    qs = GeneratedDocument.objects.select_related(
        'company',
        'office',
        'template',
        'client',
        'application',
        'deal',
        'manager',
        'approved_by',
        'stamp_preview_generated_by',
        'approval',
    )
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


def own_notification_queryset(user):
    return Notification.objects.select_related('company', 'office', 'recipient', 'sender', 'batch').filter(recipient=user)


def notification_batch_queryset(user):
    qs = NotificationBatch.objects.select_related('company', 'office', 'sender', 'target_user', 'target_office')
    if is_erp_admin(user) or user.is_staff:
        return qs
    return qs.filter(sender=user)


def annotate_notification_batches(qs):
    return qs.annotate(
        recipient_total=Count('notifications', distinct=True),
        read_total=Count(
            'notifications',
            filter=Q(notifications__read_at__isnull=False) | Q(notifications__status=Notification.STATUS_READ),
            distinct=True,
        ),
    )


def calendar_event_queryset(user):
    qs = CalendarEvent.objects.select_related('company', 'office', 'owner', 'created_by').prefetch_related('participants').filter(is_active=True)
    if is_erp_admin(user) or user.is_staff:
        return qs

    employee = get_employee_profile(user)
    if not employee:
        return qs.filter(Q(owner=user) | Q(participants=user), visibility=CalendarEvent.VISIBILITY_PRIVATE).distinct()

    visibility_q = Q(owner=user) | Q(participants=user)
    if employee.office_id:
        visibility_q |= Q(company=employee.company, office=employee.office, visibility=CalendarEvent.VISIBILITY_OFFICE)
    visibility_q |= Q(company=employee.company, visibility=CalendarEvent.VISIBILITY_COMPANY)
    return qs.filter(visibility_q).distinct()


def workday_queryset(user):
    qs = WorkDay.objects.select_related('company', 'office', 'employee', 'daily_report')
    if is_erp_admin(user):
        return qs
    return qs.filter(employee_scope_q(user, manager_field='employee'))


def employee_queryset(user):
    qs = EmployeeProfile.objects.select_related('user', 'company', 'office', 'department', 'position', 'role', 'access')
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
    qs = University.objects.select_related('company', 'country', 'city', 'local_currency').prefetch_related('programs')
    scope = 'admin' if is_erp_admin(user) else 'global'
    if is_erp_admin(user):
        cache_key = make_education_cache_key('portal-universities-base', scope=scope)
        cached_ids = education_cache_get(cache_key)
        if cached_ids is not None:
            return qs.filter(id__in=cached_ids)
        ids = list(qs.values_list('id', flat=True))
        education_cache_set(cache_key, ids)
        return qs.filter(id__in=ids)
    employee = get_employee_profile(user)
    if not employee:
        cache_key = make_education_cache_key('portal-universities-base', scope='anonymous-employee')
        cached_ids = education_cache_get(cache_key)
        if cached_ids is not None:
            return qs.filter(id__in=cached_ids)
        scoped = qs.filter(company__isnull=True)
        ids = list(scoped.values_list('id', flat=True))
        education_cache_set(cache_key, ids)
        return qs.filter(id__in=ids)
    scope = f'company-{employee.company_id}'
    cache_key = make_education_cache_key('portal-universities-base', scope=scope)
    cached_ids = education_cache_get(cache_key)
    if cached_ids is not None:
        return qs.filter(id__in=cached_ids)
    scoped = qs.filter(Q(company=employee.company) | Q(company__isnull=True))
    ids = list(scoped.values_list('id', flat=True))
    education_cache_set(cache_key, ids)
    return qs.filter(id__in=ids)


def program_queryset(user):
    universities = university_queryset(user).values('id')
    base_qs = Program.objects.select_related('university', 'university__country', 'university__city').prefetch_related('fees', 'intakes').filter(university_id__in=universities)
    if is_erp_admin(user):
        scope = 'admin'
    else:
        employee = get_employee_profile(user)
        scope = f'company-{employee.company_id}' if employee and employee.company_id else 'anonymous-employee'
    cache_key = make_education_cache_key('portal-programs-base', scope=scope)
    cached_ids = education_cache_get(cache_key)
    if cached_ids is not None:
        return base_qs.filter(id__in=cached_ids)
    ids = list(base_qs.values_list('id', flat=True))
    education_cache_set(cache_key, ids)
    return base_qs.filter(id__in=ids)


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
    qs = Income.objects.select_related('company', 'office', 'cashbox', 'employee', 'client', 'deal', 'service', 'currency', 'confirmed_by')
    if is_erp_admin(user):
        return qs
    return qs.filter(employee_scope_q(user, manager_field='employee'))


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


def must_track_workday_q():
    return Q(access__must_track_workday=True) | Q(access__isnull=True)


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


def stamp_options_from_post(post_data):
    return {
        'stamp_mode': post_data.get('stamp_mode') or 'executor',
        'stamp_width_mm': post_data.get('stamp_width_mm') or '',
        'stamp_height_mm': post_data.get('stamp_height_mm') or '',
        'stamp_x_percent': post_data.get('stamp_x_percent') or '',
        'stamp_y_percent': post_data.get('stamp_y_percent') or '',
        'stamp_x_mm': post_data.get('stamp_x_mm') or '',
        'stamp_y_mm': post_data.get('stamp_y_mm') or '',
        'page_number': post_data.get('page_number') or '',
    }


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

    for event in calendar_event_queryset(user).filter(event_date__gte=today).order_by('event_date', 'start_time')[:80]:
        events.append({
            'date': event.event_date,
            'type': 'Событие',
            'title': event.title,
            'details': event.start_time.strftime('%H:%M') if event.start_time else event.get_visibility_display(),
            'url': f'{reverse("portal:calendar")}?day={event.event_date.isoformat()}',
            'tone': 'info',
        })

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

    for event in calendar_event_queryset(user).filter(event_date__gte=start_date, event_date__lte=end_date).order_by('event_date', 'start_time')[:300]:
        events.append({
            'date': event.event_date,
            'type': 'Событие',
            'title': event.title,
            'details': event.start_time.strftime('%H:%M') if event.start_time else event.get_visibility_display(),
            'url': f'{reverse("portal:calendar")}?day={event.event_date.isoformat()}',
            'tone': 'info',
        })

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


def paginate_queryset(request, qs, per_page=PAGE_SIZE):
    paginator = Paginator(qs, per_page)
    page_number = request.GET.get('page') or 1
    page_obj = paginator.get_page(page_number)
    query_params = request.GET.copy()
    query_params.pop('page', None)
    return page_obj, query_params.urlencode()


def get_today_workday(user):
    if not user.is_authenticated:
        return None
    employee = get_employee_profile(user)
    today = timezone.localdate()
    workday = WorkDay.objects.filter(employee=user, date=today).select_related('company', 'office', 'daily_report').first()
    if workday or not employee:
        return workday
    access = getattr(employee, 'access', None)
    return WorkDay(
        company=employee.company,
        office=employee.office,
        employee=user,
        date=today,
        status=WorkDay.STATUS_NOT_STARTED,
        report_required=bool(not access or access.must_track_workday),
    )


def ensure_today_workday(user):
    employee = get_employee_profile(user)
    if not employee:
        raise ValueError('Employee profile is required.')
    access = getattr(employee, 'access', None)
    today = timezone.localdate()
    workday, _ = WorkDay.objects.get_or_create(
        company=employee.company,
        employee=user,
        date=today,
        defaults={
            'office': employee.office,
            'status': WorkDay.STATUS_NOT_STARTED,
            'report_required': bool(not access or access.must_track_workday),
        },
    )
    if employee.office_id and workday.office_id != employee.office_id:
        workday.office = employee.office
        workday.save(update_fields=['office', 'updated_at'])
    return workday


class PortalContextMixin(LoginRequiredMixin):
    login_url = reverse_lazy('portal:login')
    active_page = ''
    page_title = ''

    @method_decorator(ensure_csrf_cookie)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

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
            'unread_notifications_count': own_notification_queryset(self.request.user).filter(read_at__isnull=True).exclude(status=Notification.STATUS_READ).count(),
            'recent_header_notifications': own_notification_queryset(self.request.user)
                .annotate(unread_rank=Case(
                    When(Q(read_at__isnull=True) & ~Q(status=Notification.STATUS_READ), then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                ))
                .order_by('unread_rank', '-created_at')[:5],
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

    @method_decorator(ensure_csrf_cookie)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

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
        incomes = income_queryset(user)
        expenses = expense_queryset(user)
        projects = project_queryset(user)
        documents = document_queryset(user)
        notifications = notification_queryset(user)
        workdays = workday_queryset(user)
        employee_profiles = employee_queryset(user)
        confirmed_payments = payments.filter(is_confirmed=True)
        confirmed_expenses = expenses.filter(is_confirmed=True)
        confirmed_incomes = incomes.filter(is_confirmed=True)
        revenue_month = (
            confirmed_payments.filter(payment_date__gte=today.replace(day=1)).aggregate(total=Sum('amount_usd'))['total'] or 0
        ) + (
            confirmed_incomes.filter(date__gte=today.replace(day=1)).aggregate(total=Sum('amount_usd'))['total'] or 0
        )
        expense_month = confirmed_expenses.filter(date__gte=today.replace(day=1)).aggregate(total=Sum('amount_usd'))['total'] or 0

        context.update({
            'metrics': [
                {'label': 'Лиды', 'value': leads.exclude(status__in=['converted', 'lost', 'spam']).count(), 'icon': 'radar', 'url': reverse('portal:leads')},
                {'label': 'Потенциальные', 'value': incoming_lead_queryset(user).filter(manager__isnull=True).count(), 'icon': 'inbox', 'url': reverse('portal:incoming_leads')},
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

    def post(self, request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser):
            messages.error(request, 'Менять сервер Student’s Life может только администратор.')
            return redirect('portal:settings')

        mode = request.POST.get('students_life_api_mode') or 'proxy'
        proxy_url = getattr(settings, 'STUDENTS_LIFE_DEFAULT_API_BASE_URL', 'https://students-life.ru/api2/api/v1/')
        original_url = getattr(settings, 'STUDENTS_LIFE_ORIGINAL_API_BASE_URL', 'https://stud-life.com/api/v1/')
        if mode == 'original':
            value = original_url
        elif mode == 'custom':
            value = request.POST.get('students_life_api_custom_url', '').strip()
        else:
            value = proxy_url

        parsed = urlsplit(value)
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
            messages.error(request, 'Укажите корректный URL сервера, например https://students-life.ru/api2/api/v1/')
            return redirect('portal:settings')

        set_students_life_api_base_url(value)
        messages.success(request, f'Сервер Student’s Life API обновлён: {value.rstrip("/")}/')
        return redirect('portal:settings')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = context.get('employee_profile')
        proxy_url = getattr(settings, 'STUDENTS_LIFE_DEFAULT_API_BASE_URL', 'https://students-life.ru/api2/api/v1/')
        original_url = getattr(settings, 'STUDENTS_LIFE_ORIGINAL_API_BASE_URL', 'https://stud-life.com/api/v1/')
        current_students_life_api_url = get_students_life_api_base_url().rstrip('/') + '/'
        context.update({
            'access': getattr(employee, 'access', None) if employee else None,
            'students_life_proxy_url': proxy_url,
            'students_life_original_url': original_url,
            'current_students_life_api_url': current_students_life_api_url,
            'students_life_api_key_configured': bool(getattr(settings, 'STUDENTS_LIFE_API_KEY', '') or getattr(settings, 'LEADS_API_KEY', '')),
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
    grid_template = ''
    filter_template = ''
    create_url_name = ''
    create_label = 'Добавить'
    search_fields = ()
    status_choices = ()
    status_field = 'status'
    default_ordering = '-created_at'
    page_size = PAGE_SIZE

    def get_queryset(self):
        raise NotImplementedError

    def get_table_title(self):
        return self.page_title

    def get_extra_context(self, qs):
        return {}

    def get_view_mode(self):
        mode = self.request.GET.get('view')
        if mode == 'grid' and self.grid_template:
            return 'grid'
        return 'table'

    def get_content_template(self):
        return self.grid_template if self.get_view_mode() == 'grid' else self.table_template

    def get_switched_query(self, view_mode):
        query_params = self.request.GET.copy()
        query_params['view'] = view_mode
        query_params.pop('page', None)
        return query_params.urlencode()

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
        ordered_qs = qs.order_by(ordering)
        page_obj, page_query = paginate_queryset(self.request, ordered_qs, self.page_size)
        view_mode = self.get_view_mode()
        content_template = self.get_content_template()
        context.update({
            'items': page_obj.object_list,
            'total_count': qs.count(),
            'page_obj': page_obj,
            'paginator': page_obj.paginator,
            'page_query': page_query,
            'table_template': self.table_template,
            'grid_template': self.grid_template,
            'filter_template': self.filter_template,
            'content_template': content_template,
            'view_mode': view_mode,
            'table_view_query': self.get_switched_query('table'),
            'grid_view_query': self.get_switched_query('grid'),
            'table_title': self.get_table_title(),
            'status_choices': self.status_choices,
            'current_status': self.request.GET.get('status', ''),
            'query': self.request.GET.get('q', ''),
            'ordering': ordering,
            'create_url': safe_reverse(self.create_url_name, '') if self.create_url_name else '',
            'create_label': self.create_label,
        })
        context.update(self.get_extra_context(qs))
        if context['is_htmx']:
            self.template_name = content_template
        return context


class PortalFormPageMixin:
    template_name = 'portal/form_page.html'
    cancel_url_name = ''
    form_page_title_create = 'Создать'
    form_page_title_edit = 'Редактировать'
    submit_label = 'Сохранить'

    def get_form_page_title(self, obj):
        return self.form_page_title_edit if obj else self.form_page_title_create

    def get_cancel_url(self):
        return safe_reverse(self.cancel_url_name, '#') if self.cancel_url_name else '#'

    def get_form_groups(self, form):
        return [{'title': 'Основное', 'fields': list(form.visible_fields()), 'open': True}]

    def get_context_data(self, **kwargs):
        context = PortalContextMixin.get_context_data(self, **kwargs)
        edit_object = self.get_edit_object()
        form = context.get('form') or self.get_form(instance=edit_object)
        context.update({
            'form': form,
            'form_groups': self.get_form_groups(form),
            'edit_object': edit_object,
            'page_title': self.get_form_page_title(edit_object),
            'form_title': self.get_form_page_title(edit_object),
            'submit_label': self.submit_label,
            'cancel_url': self.get_cancel_url(),
        })
        return context

    def render_to_response(self, context, **response_kwargs):
        form = context.get('form')
        if form:
            context['form_groups'] = self.get_form_groups(form)
            context.setdefault('form_title', self.get_form_page_title(context.get('edit_object')))
            context.setdefault('submit_label', self.submit_label)
            context.setdefault('cancel_url', self.get_cancel_url())
        return super().render_to_response(context, **response_kwargs)


class CountriesView(ListPageMixin):
    active_page = 'countries'
    page_title = 'Страны'
    table_template = 'portal/partials/countries_table.html'
    grid_template = 'portal/partials/countries_grid.html'
    search_fields = ('name', 'code', 'description')
    status_field = ''
    default_ordering = 'sort_order'

    def get_queryset(self):
        qs = Country.objects.annotate(
            cities_count=Count('cities', distinct=True),
            universities_count=Count('universities', distinct=True),
        )
        is_active = bool_param(self.request.GET.get('is_active'))
        if is_active is not None:
            qs = qs.filter(is_active=is_active)
        return qs


class CitiesView(ListPageMixin):
    active_page = 'cities'
    page_title = 'Города'
    table_template = 'portal/partials/cities_table.html'
    grid_template = 'portal/partials/cities_grid.html'
    search_fields = ('name', 'description', 'country__name')
    status_field = ''
    default_ordering = 'country__name'

    def get_queryset(self):
        qs = City.objects.select_related('country').annotate(
            universities_count=Count('universities', distinct=True),
        )
        country_id = self.request.GET.get('country')
        if country_id:
            qs = qs.filter(country_id=country_id)
        is_active = bool_param(self.request.GET.get('is_active'))
        if is_active is not None:
            qs = qs.filter(is_active=is_active)
        return qs

    def get_extra_context(self, qs):
        return {
            'countries': Country.objects.filter(is_active=True).order_by('sort_order', 'name')[:300],
            'selected_country': self.request.GET.get('country', ''),
        }


class UniversitiesView(ListPageMixin):
    active_page = 'universities'
    page_title = 'Вузы'
    table_template = 'portal/partials/universities_table.html'
    grid_template = 'portal/partials/universities_grid.html'
    create_url_name = 'portal:university_create'
    create_label = 'Добавить ВУЗ'
    search_fields = ('name', 'legal_name', 'country__name', 'city__name', 'description')
    status_field = ''
    default_ordering = 'country__name'

    def get_queryset(self):
        qs = university_queryset(self.request.user)
        country_id = self.request.GET.get('country')
        city_id = self.request.GET.get('city')
        if country_id:
            qs = qs.filter(country_id=country_id)
        if city_id:
            qs = qs.filter(city_id=city_id)
        is_active = bool_param(self.request.GET.get('is_active'))
        if is_active is not None:
            qs = qs.filter(is_active=is_active)
        return qs

    def get_edit_object(self):
        edit_id = self.kwargs.get('pk') or self.request.GET.get('edit') or self.request.POST.get('object_id')
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


class UniversityDetailView(PortalContextMixin, TemplateView):
    template_name = 'portal/university_detail.html'
    active_page = 'universities'
    page_title = 'Карточка ВУЗа'

    def get_university(self):
        qs = university_queryset(self.request.user).prefetch_related(None).select_related('country', 'city', 'local_currency', 'company').prefetch_related(
            'contact_people',
            'required_documents',
            Prefetch(
                'programs',
                queryset=Program.objects.select_related('university').prefetch_related(
                    Prefetch('fees', queryset=ProgramFee.objects.select_related('currency').order_by('-created_at')),
                    'intakes',
                    'required_documents',
                ).filter(is_active=True, is_archived=False).order_by('degree', 'name'),
            ),
        )
        return get_object_or_404(qs, pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        university = self.get_university()
        context.update({
            'university': university,
            'programs': university.programs.all(),
            'contacts': university.contact_people.all(),
            'documents': university.required_documents.filter(program__isnull=True, is_active=True),
            'can_manage_university': is_erp_admin(self.request.user) or self.request.user.is_staff,
        })
        return context


class ProgramsView(ListPageMixin):
    active_page = 'programs'
    page_title = 'Программы'
    table_template = 'portal/partials/programs_table.html'
    grid_template = 'portal/partials/programs_grid.html'
    filter_template = 'portal/partials/programs_filters.html'
    create_url_name = 'portal:program_create'
    create_label = 'Добавить программу'
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
        edit_id = self.kwargs.get('pk') or self.request.GET.get('edit') or self.request.POST.get('object_id')
        if not edit_id:
            return None
        return self.get_queryset().filter(pk=edit_id).first()

    def get_form(self, data=None, instance=None):
        initial = {}
        university_id = self.kwargs.get('university_pk') or self.request.GET.get('university')
        if university_id and not data and not instance:
            initial['university'] = university_id
        return PortalProgramForm(
            data=data,
            instance=instance,
            initial=initial or None,
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
            program = form.save()
            messages.success(request, 'Программа сохранена.')
            if self.kwargs.get('university_pk'):
                return redirect('portal:university_detail', pk=program.university_id)
            return redirect('portal:programs')
        context = self.get_context_data()
        context['form'] = form
        context['edit_object'] = edit_object
        return self.render_to_response(context)


class ServicesView(ListPageMixin):
    active_page = 'services'
    page_title = 'Услуги'
    table_template = 'portal/partials/services_table.html'
    grid_template = 'portal/partials/services_grid.html'
    create_url_name = 'portal:service_create'
    create_label = 'Добавить услугу'
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
        edit_id = self.kwargs.get('pk') or self.request.GET.get('edit') or self.request.POST.get('object_id')
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
                    code=unique_code(ServiceCategory, category_name, company=company, max_length=80),
                    defaults={'name': category_name, 'description': ''},
                )
            item = form.save(commit=False)
            if employee and not is_erp_admin(request.user):
                item.company = employee.company
            elif employee and not item.company_id:
                item.company = employee.company
            item.category = category
            if not item.code:
                item.code = unique_code(Service, item.title, company=item.company, max_length=80, exclude_pk=item.pk)
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
    grid_template = 'portal/partials/leads_grid.html'
    search_fields = ('full_name', 'phone', 'email', 'interested_country', 'interested_program', 'comment')
    status_choices = Lead.STATUS_CHOICES
    archive_choices = (
        ('active', 'Активные'),
        ('archived', 'Архив'),
        ('all', 'Все'),
    )

    def get_queryset(self):
        archive_filter = self.request.GET.get('archive') or 'active'
        qs = lead_queryset(self.request.user, include_archived=True).select_related('manager', 'source', 'archived_by')
        if archive_filter == 'archived':
            return qs.filter(is_archived=True)
        if archive_filter == 'all' and can_delete_admin(self.request.user):
            return qs
        return qs.filter(is_archived=False)

    def get_extra_context(self, qs):
        return {
            'archive_choices': self.archive_choices,
            'current_archive': self.request.GET.get('archive') or 'active',
            'can_restore_leads': can_delete_admin(self.request.user),
            'can_archive_any_lead': can_delete_admin(self.request.user),
        }

    def post(self, request, *args, **kwargs):
        lead = get_object_or_404(lead_queryset(request.user, include_archived=True), pk=request.POST.get('lead_id'))
        action = request.POST.get('action')
        if action == 'archive':
            if not can_delete_admin(request.user) and lead.manager_id != request.user.id:
                messages.error(request, 'Скрыть можно только свой лид.')
            else:
                lead.archive(user=request.user, reason=request.POST.get('archive_reason', ''))
                messages.success(request, 'Лид перемещён в архив.')
        elif action == 'restore':
            if not can_delete_admin(request.user):
                messages.error(request, 'Восстановить лид может только администратор.')
            else:
                lead.restore_from_archive(user=request.user, note='Восстановлено из портала')
                messages.success(request, 'Лид восстановлен.')
        else:
            messages.error(request, 'Неизвестное действие.')
        return redirect('portal:leads')


class LeadDetailView(PortalContextMixin, TemplateView):
    template_name = 'portal/lead_detail.html'
    active_page = 'leads'
    page_title = 'Информация лида'

    def get_lead(self):
        return get_object_or_404(lead_queryset(self.request.user, include_archived=True), pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lead = self.get_lead()
        context.update({
            'lead': lead,
            'custom_items': (lead.custom_data or {}).items(),
            'raw_payload': (lead.custom_data or {}).get('raw_payload') or {},
            'action_history': lead.action_history,
            'can_view_technical': can_delete_admin(self.request.user),
            'can_archive_lead': can_delete_admin(self.request.user) or lead.manager_id == self.request.user.id,
            'can_restore_lead': can_delete_admin(self.request.user),
        })
        return context


class IncomingLeadsView(ListPageMixin):
    active_page = 'incoming_leads'
    page_title = 'Потенциальные клиенты'
    table_template = 'portal/partials/incoming_leads_table.html'
    grid_template = 'portal/partials/incoming_leads_grid.html'
    filter_template = 'portal/partials/incoming_leads_filters.html'
    search_fields = ('full_name', 'phone', 'email', 'interested_country', 'interested_program', 'comment')
    status_choices = Lead.STATUS_CHOICES

    def get_queryset(self):
        status_value = self.request.GET.get('ownership')
        qs = incoming_lead_queryset(self.request.user)
        if status_value == 'free':
            qs = qs.filter(manager__isnull=True)
        elif status_value == 'mine':
            qs = qs.filter(manager=self.request.user)
        return qs

    def get_extra_context(self, qs):
        return {
            'ownership': self.request.GET.get('ownership', ''),
            'free_count': incoming_lead_queryset(self.request.user).filter(manager__isnull=True).count(),
            'mine_count': incoming_lead_queryset(self.request.user).filter(manager=self.request.user).count(),
            'is_admin_user': can_delete_admin(self.request.user),
        }

    def post(self, request, *args, **kwargs):
        lead = get_object_or_404(incoming_lead_queryset(request.user), pk=request.POST.get('lead_id'))
        action = request.POST.get('action')
        employee = get_employee_profile(request.user)

        if action == 'take':
            if lead.manager_id and lead.manager_id != request.user.id:
                messages.error(request, 'Заявка уже в работе у другого менеджера.')
                return redirect('portal:incoming_leads')
            lead.take_responsibility(
                request.user,
                company=employee.company if employee else lead.company,
                office=employee.office if employee else lead.office,
            )
            messages.success(request, 'Вы взяли ответственность за заявку.')
            return redirect('portal:incoming_leads')

        if action == 'release':
            if hasattr(lead, 'client') and lead.client:
                messages.error(request, 'По этой заявке уже создан клиент, вернуть её в свободные нельзя.')
                return redirect('portal:incoming_leads')
            if lead.manager_id != request.user.id and not can_delete_admin(request.user):
                messages.error(request, 'Вернуть можно только свою заявку.')
                return redirect('portal:incoming_leads')
            lead.release_responsibility(request.user, note='Вернули из портала')
            messages.success(request, 'Заявка возвращена в свободные.')
            return redirect('portal:incoming_leads')

        if action == 'convert':
            if lead.manager_id and lead.manager_id != request.user.id and not can_delete_admin(request.user):
                messages.error(request, 'Создать клиента может ответственный менеджер или администратор.')
                return redirect('portal:incoming_leads')
            manager = lead.manager or request.user
            company = lead.company or (employee.company if employee else fallback_company())
            office = lead.office or (employee.office if employee else None)
            if not company:
                messages.error(request, 'Нельзя создать клиента: не найдена компания для привязки.')
                return redirect('portal:incoming_leads')
            client, created = Client.objects.get_or_create(
                source_lead=lead,
                defaults={
                    'company': company,
                    'office': office,
                    'manager': manager,
                    'lead_source': lead.source,
                    'direction': lead.direction,
                    'full_name': lead.full_name,
                    'phone': lead.phone,
                    'email': lead.email,
                    'citizenship': lead.country,
                    'city': lead.city,
                    'interested_country': lead.interested_country,
                    'interested_program': lead.interested_program,
                    'comments': lead.comment,
                    'custom_data': lead.custom_data or {},
                },
            )
            lead.manager = manager
            lead.company = company
            lead.office = office
            lead.mark_converted(user=request.user)
            messages.success(request, 'Клиент создан по заявке.' if created else 'Клиент по этой заявке уже существует.')
            return redirect('portal:client_detail', pk=client.pk)

        messages.error(request, 'Неизвестное действие.')
        return redirect('portal:incoming_leads')


class ClientsView(ListPageMixin):
    active_page = 'clients'
    page_title = 'Клиенты'
    table_template = 'portal/partials/clients_table.html'
    grid_template = 'portal/partials/clients_grid.html'
    create_url_name = 'portal:client_create'
    create_label = 'Добавить клиента'
    search_fields = ('full_name', 'phone', 'email', 'city', 'citizenship', 'comments')
    status_choices = Client.STATUS_CHOICES

    def get_queryset(self):
        return client_queryset(self.request.user).select_related('manager')

    def get_edit_object(self):
        edit_id = self.kwargs.get('pk') or self.request.GET.get('edit') or self.request.POST.get('object_id')
        if not edit_id:
            return None
        return client_queryset(self.request.user).filter(pk=edit_id).first()

    def get_form(self, data=None, instance=None):
        employee = get_employee_profile(self.request.user)
        initial = {}
        if employee:
            initial = {'manager': self.request.user.pk, 'office': employee.office_id}
        managers = portal_user_queryset(self.request.user) if is_erp_admin(self.request.user) or self.request.user.is_staff else User.objects.filter(pk=self.request.user.pk)
        offices = office_queryset(self.request.user) if is_erp_admin(self.request.user) or self.request.user.is_staff else Office.objects.filter(pk=employee.office_id) if employee and employee.office_id else Office.objects.none()
        return PortalClientForm(
            data=data,
            instance=instance,
            initial=initial if not data and not instance else None,
            managers=managers,
            offices=offices,
            sources=LeadSource.objects.filter(is_active=True).order_by('name'),
        )

    def get_extra_context(self, qs):
        edit_object = self.get_edit_object()
        return {
            'form': self.get_form(instance=edit_object),
            'edit_object': edit_object,
            'can_assign_client': is_erp_admin(self.request.user) or self.request.user.is_staff,
        }

    def post(self, request, *args, **kwargs):
        client = self.get_edit_object()
        form = self.get_form(data=request.POST, instance=client)
        if form.is_valid():
            employee = get_employee_profile(request.user)
            item = form.save(commit=False)
            if not is_erp_admin(request.user) and not request.user.is_staff:
                item.manager = request.user
                if employee:
                    item.company = employee.company
                    item.office = employee.office
                elif not item.company_id:
                    item.company = fallback_company()
            elif employee:
                item.company = employee.company
                if not item.office_id and employee.office_id:
                    item.office = employee.office
            elif item.office_id and not item.company_id:
                item.company = item.office.company
            elif not item.company_id:
                item.company = fallback_company()
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
        exams_ok, exams, exams_error = get_client_exams_from_students_life(client)
        context.update({
            'client': client,
            'applications': application_queryset(self.request.user).filter(client=client).order_by('-created_at'),
            'deals': deal_queryset(self.request.user).filter(client=client).order_by('-created_at'),
            'documents': document_queryset(self.request.user).filter(client=client).order_by('-created_at'),
            'questionnaire': getattr(client, 'questionnaire', None),
            'mobile_exams': exams,
            'mobile_exams_ok': exams_ok,
            'mobile_exams_error': exams_error,
            'mobile_user_id': client_mobile_user_id(client),
        })
        return context


class ClientExamPortalView(LoginRequiredMixin, View):
    login_url = reverse_lazy('portal:login')

    def post(self, request, pk):
        client = get_object_or_404(client_queryset(request.user), pk=pk)
        mobile_user_id = client_mobile_user_id(client)
        if not mobile_user_id:
            messages.error(request, 'У клиента нет mobile user id, экзамен нельзя отправить в приложение.')
            return redirect('portal:client_detail', pk=client.pk)

        payload = {
            'subject': request.POST.get('subject', '').strip(),
            'exam_date': request.POST.get('exam_date', '').strip(),
            'exam_time': request.POST.get('exam_time', '').strip(),
            'timezone': request.POST.get('timezone', '').strip() or 'Europe/Moscow',
            'comment': request.POST.get('comment', '').strip(),
            'repeat_until_acknowledged': request.POST.get('repeat_until_acknowledged') == 'on',
        }
        ok, response = students_life_api_request(
            f'notifications/clients/{mobile_user_id}/exams/',
            payload=payload,
            method='POST',
        )
        if ok:
            messages.success(request, 'Экзамен назначен, уведомление отправлено клиенту.')
        else:
            messages.error(request, response.get('detail') or str(response))
        return redirect('portal:client_detail', pk=client.pk)


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
                title=(
                    f'{form.cleaned_data.get("title").strip()} - {client.full_name}'
                    if form.cleaned_data.get('title') and client.full_name.lower() not in form.cleaned_data.get('title').lower()
                    else form.cleaned_data.get('title') or f'{template.name} - {client.full_name}'
                ),
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


STUDENTS_LIFE_API_BASE_SETTING_KEY = 'students_life_api_base_url'


def get_students_life_api_base_url():
    configured = ''
    try:
        configured = (
            SystemSetting.objects
            .filter(key=STUDENTS_LIFE_API_BASE_SETTING_KEY)
            .values_list('value', flat=True)
            .first()
        ) or ''
    except Exception:
        configured = ''
    return str(
        configured
        or getattr(settings, 'STUDENTS_LIFE_API_BASE_URL', '')
        or getattr(settings, 'STUDENTS_LIFE_DEFAULT_API_BASE_URL', '')
    ).strip().rstrip('/')


def set_students_life_api_base_url(value):
    value = str(value or '').strip().rstrip('/')
    SystemSetting.objects.update_or_create(
        key=STUDENTS_LIFE_API_BASE_SETTING_KEY,
        defaults={
            'value': value,
            'description': 'Base URL API Student’s Life для проверки документов и анкет.',
        },
    )
    return value


def portal_user_review_payload(user):
    display_name = full_name(user)
    return {
        'reviewed_by_name': display_name or getattr(user, 'email', '') or str(user),
        'reviewed_by_email': getattr(user, 'email', '') or '',
    }


def parse_api_datetime(value):
    if not value:
        return None
    parsed = parse_datetime(str(value))
    if parsed and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def normalize_students_life_payload(payload):
    if isinstance(payload, dict):
        for key in ('document', 'application_form', 'questionnaire', 'data', 'result'):
            nested = payload.get(key)
            if isinstance(nested, dict):
                merged = dict(nested)
                for exposed_key in (
                    'document_id', 'id', 'status', 'admin_comment', 'comment', 'review_comment',
                    'reviewed_at', 'reviewed_by_id', 'reviewed_by_name', 'reviewed_by_email',
                    'reviewed_by_display', 'generated_document_url', 'document_file',
                ):
                    if exposed_key in payload and exposed_key not in merged:
                        merged[exposed_key] = payload[exposed_key]
                return merged
        return payload
    return {}


def update_client_document_from_students_life(document, payload):
    data = normalize_students_life_payload(payload)
    if not data:
        return document
    status_value = data.get('status')
    if status_value in {ClientFile.STATUS_PENDING, ClientFile.STATUS_APPROVED, ClientFile.STATUS_REJECTED}:
        document.status = status_value
    document.review_comment = data.get('admin_comment') or data.get('comment') or data.get('review_comment') or ''
    reviewed_at = parse_api_datetime(data.get('reviewed_at'))
    if reviewed_at:
        document.reviewed_at = reviewed_at
    elif document.status in {ClientFile.STATUS_APPROVED, ClientFile.STATUS_REJECTED} and not document.reviewed_at:
        document.reviewed_at = timezone.now()
    if data.get('title'):
        document.title = data.get('title')
    file_url = data.get('file_url') or data.get('document_file') or data.get('url')
    if file_url:
        document.external_file_url = file_url
    if data.get('document_id'):
        document.external_mobile_document_id = data.get('document_id')
    document.external_review_data = data
    document.save(update_fields=[
        'status',
        'review_comment',
        'reviewed_at',
        'title',
        'external_file_url',
        'external_mobile_document_id',
        'external_review_data',
        'updated_at',
    ])
    return document


def update_questionnaire_from_students_life(questionnaire, payload):
    data = normalize_students_life_payload(payload)
    if not data:
        return questionnaire
    stored = dict(questionnaire.data or {})
    stored.update(data)
    questionnaire.data = stored
    if data.get('status') in {
        ClientQuestionnaire.STATUS_DRAFT,
        ClientQuestionnaire.STATUS_COMPLETED,
        ClientQuestionnaire.STATUS_SUBMITTED,
        ClientQuestionnaire.STATUS_APPROVED,
        ClientQuestionnaire.STATUS_REJECTED,
        ClientQuestionnaire.STATUS_UPDATED,
    }:
        questionnaire.status = data.get('status')
    questionnaire.full_name = data.get('full_name') or questionnaire.full_name
    questionnaire.submitted_at = parse_api_datetime(data.get('submitted_at')) or questionnaire.submitted_at
    questionnaire.last_synced_at = timezone.now()
    questionnaire.save(update_fields=['data', 'status', 'full_name', 'submitted_at', 'last_synced_at', 'updated_at'])
    return questionnaire


def notify_mobile_document_review(document, user=None):
    base_url = get_students_life_api_base_url()
    api_key = getattr(settings, 'STUDENTS_LIFE_API_KEY', '') or getattr(settings, 'LEADS_API_KEY', '')
    if not base_url or not api_key or not document.external_mobile_document_id:
        return False, 'STUDENTS_LIFE_API_BASE_URL, STUDENTS_LIFE_API_KEY или mobile document id не настроены.'

    callback_url = urljoin(base_url.rstrip('/') + '/', 'documents/external-review/')
    if '/api/v1/' not in callback_url:
        callback_url = urljoin(base_url.rstrip('/') + '/', 'api/v1/documents/external-review/')

    payload_data = {
        'document_id': document.external_mobile_document_id,
        'status': document.status,
        'comment': document.review_comment,
        **(portal_user_review_payload(user) if user else {}),
    }
    payload = json.dumps(payload_data).encode('utf-8')
    request = urlrequest.Request(
        callback_url,
        data=payload,
        headers={'Content-Type': 'application/json', 'Accept': 'application/json', 'X-API-KEY': api_key},
        method='POST',
    )
    try:
        urlrequest.urlopen(request, timeout=8).read()
        return True, 'Статус отправлен в мобильное приложение.'
    except (urlerror.URLError, TimeoutError, ValueError) as exc:
        return False, f'Статус сохранён в Manager SL, но не отправлен в мобильное приложение: {exc}'


def students_life_api_url(path):
    base_url = get_students_life_api_base_url()
    if not base_url:
        return ''
    url = urljoin(base_url.rstrip('/') + '/', path.lstrip('/'))
    if '/api/v1/' not in url:
        url = urljoin(base_url.rstrip('/') + '/', f'api/v1/{path.lstrip("/")}')
    return url


def students_life_api_request(path, payload=None, method='POST'):
    api_key = getattr(settings, 'STUDENTS_LIFE_API_KEY', '') or getattr(settings, 'LEADS_API_KEY', '')
    url = students_life_api_url(path)
    if not url or not api_key:
        return False, {'detail': 'STUDENTS_LIFE_API_BASE_URL или STUDENTS_LIFE_API_KEY не настроены.'}

    body = json.dumps(payload or {}).encode('utf-8') if payload is not None else None
    request = urlrequest.Request(
        url,
        data=body,
        headers={'Content-Type': 'application/json', 'Accept': 'application/json', 'X-API-KEY': api_key},
        method=method.upper(),
    )
    try:
        raw = urlrequest.urlopen(request, timeout=10).read().decode('utf-8')
        return True, json.loads(raw) if raw else {}
    except urlerror.HTTPError as exc:
        raw = exc.read().decode('utf-8', errors='replace')
        try:
            return False, json.loads(raw) if raw else {'detail': exc.reason}
        except json.JSONDecodeError:
            return False, {'detail': raw or exc.reason}
    except (urlerror.URLError, TimeoutError, ValueError) as exc:
        return False, {'detail': str(exc)}


def client_mobile_user_id(client):
    value = getattr(client, 'mobile_app_user_id', None)
    if value:
        return value
    data = client.custom_data or {}
    return data.get('mobile_user_id') or data.get('external_mobile_user_id') or data.get('user_id')


def get_client_exams_from_students_life(client):
    mobile_user_id = client_mobile_user_id(client)
    if not mobile_user_id:
        return False, [], 'У клиента нет mobile user id.'
    ok, payload = students_life_api_request(
        f'notifications/clients/{mobile_user_id}/exams/',
        payload=None,
        method='GET',
    )
    if not ok:
        return False, [], payload.get('detail') or 'Не удалось получить экзамены из Student Life API.'
    return True, payload if isinstance(payload, list) else [], ''


def document_credit_period_for(employee):
    today = timezone.localdate()
    plan = (
        ManagerDocumentPlan.objects
        .filter(employee=employee, is_active=True, start_date__lte=today, end_date__gte=today)
        .order_by('-start_date', '-created_at')
        .first()
    )
    if plan:
        return plan, plan.start_date, plan.end_date
    _, last_day = calendar.monthrange(today.year, today.month)
    return None, today.replace(day=1), today.replace(day=last_day)


def mark_client_documents_loaded(request, client, comment=''):
    employee = getattr(request.user, 'employee_profile', None)
    if not employee:
        return False, 'У пользователя нет профиля сотрудника, зачёт не выполнен.'
    plan, period_start, period_end = document_credit_period_for(employee)
    credit, created = ManagerDocumentCredit.objects.get_or_create(
        employee=employee,
        client=client,
        event_type=ManagerDocumentCredit.EVENT_UPLOADED_CLIENT_DOCUMENTS,
        period_start=period_start,
        period_end=period_end,
        defaults={
            'plan': plan,
            'credited_by': request.user,
            'comment': comment,
        },
    )
    if not created:
        return False, 'Этот клиент уже засчитан менеджеру в текущем периоде.'

    EmployeeRating.objects.create(
        employee=employee,
        date=timezone.localdate(),
        score=Decimal('1.00'),
        source=ManagerDocumentCredit.EVENT_UPLOADED_CLIENT_DOCUMENTS,
        comment=f'Загружены документы клиента: {client.full_name}',
    )
    data = dict(client.custom_data or {})
    data['documents_status'] = 'documents_loaded'
    data['documents_loaded_at'] = timezone.now().isoformat()
    data['documents_loaded_by_user_id'] = request.user.id
    client.custom_data = data
    client.save(update_fields=['custom_data', 'updated_at'])
    return True, 'Клиент засчитан как загруженный в рейтинге менеджера.'


class ClientDocumentsView(PortalContextMixin, TemplateView):
    template_name = 'portal/client_documents.html'
    active_page = 'client_documents'
    page_title = 'Документы клиентов'

    def get_documents(self):
        allowed_clients = client_queryset(self.request.user).values('id')
        qs = (
            ClientFile.objects
            .select_related('client', 'reviewed_by')
            .filter(source='students_life_mobile_app', client_id__in=allowed_clients)
            .order_by('-created_at', '-updated_at')
        )
        status_value = self.request.GET.get('status') or ''
        if status_value in {ClientFile.STATUS_PENDING, ClientFile.STATUS_APPROVED, ClientFile.STATUS_REJECTED}:
            qs = qs.filter(status=status_value)
        query = self.request.GET.get('q') or ''
        if query:
            qs = qs.filter(
                Q(title__icontains=query)
                | Q(client__full_name__icontains=query)
                | Q(client__phone__icontains=query)
                | Q(client__email__icontains=query)
            )
        document_type = self.request.GET.get('type') or ''
        if document_type:
            qs = qs.filter(title__icontains=document_type)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        documents_page, documents_query = paginate_queryset(self.request, self.get_documents(), 24)
        base_qs = ClientFile.objects.filter(source='students_life_mobile_app', client_id__in=client_queryset(self.request.user).values('id'))
        context.update({
            'documents': documents_page.object_list,
            'documents_page_obj': documents_page,
            'documents_page_query': documents_query,
            'query': self.request.GET.get('q', ''),
            'type_query': self.request.GET.get('type', ''),
            'status_filter': self.request.GET.get('status', ''),
            'status_choices': (
                ('', 'Все'),
                (ClientFile.STATUS_PENDING, 'На проверке'),
                (ClientFile.STATUS_APPROVED, 'Принятые'),
                (ClientFile.STATUS_REJECTED, 'Отклонённые'),
            ),
            'total_documents': base_qs.count(),
            'pending_documents': base_qs.filter(status=ClientFile.STATUS_PENDING).count(),
            'approved_documents': base_qs.filter(status=ClientFile.STATUS_APPROVED).count(),
            'rejected_documents': base_qs.filter(status=ClientFile.STATUS_REJECTED).count(),
        })
        return context


class ClientDocumentReviewDetailView(PortalContextMixin, TemplateView):
    template_name = 'portal/client_document_review.html'
    active_page = 'client_documents'
    page_title = 'Проверка документа'

    def get_document(self):
        return get_object_or_404(
            ClientFile.objects.select_related('client', 'reviewed_by').filter(
                source='students_life_mobile_app',
                client_id__in=client_queryset(self.request.user).values('id'),
            ),
            pk=self.kwargs['document_id'],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['document'] = self.get_document()
        return context


class ClientDocumentReviewPortalView(PortalContextMixin, View):
    active_page = 'client_documents'

    def post(self, request, document_id):
        document = get_object_or_404(
            ClientFile.objects.select_related('client').filter(
                source='students_life_mobile_app',
                client_id__in=client_queryset(request.user).values('id'),
            ),
            pk=document_id,
        )
        action = request.POST.get('action') or request.POST.get('status')
        reviewer = portal_user_review_payload(request.user)
        comment = request.POST.get('review_comment', '').strip()
        if action in {'approve', ClientFile.STATUS_APPROVED}:
            api_path = f'documents/{document.external_mobile_document_id}/approve/'
            api_payload = {**reviewer}
        elif action in {'reject', ClientFile.STATUS_REJECTED}:
            if not comment:
                messages.error(request, 'Укажите причину отказа для клиента.')
                return redirect(reverse('portal:client_document_review', args=[document.id]))
            api_path = f'documents/{document.external_mobile_document_id}/reject/'
            api_payload = {'comment': comment, **reviewer}
        else:
            messages.error(request, 'Некорректное действие проверки.')
            return redirect(reverse('portal:client_document_review', args=[document.id]))

        if not document.external_mobile_document_id:
            messages.error(request, 'У документа нет mobile document id, статус нельзя изменить через API клиентского приложения.')
            return redirect(reverse('portal:client_document_review', args=[document.id]))

        ok, payload = students_life_api_request(api_path, payload=api_payload, method='POST')
        if not ok:
            messages.error(request, payload.get('detail') or payload.get('comment') or payload.get('status') or 'Клиентский API не принял изменение статуса.')
            return redirect(reverse('portal:client_document_review', args=[document.id]))

        if isinstance(payload, dict) and 'status' not in normalize_students_life_payload(payload):
            payload = {
                **payload,
                'status': ClientFile.STATUS_APPROVED if action in {'approve', ClientFile.STATUS_APPROVED} else ClientFile.STATUS_REJECTED,
                'comment': comment,
                **reviewer,
                'reviewed_by_display': reviewer['reviewed_by_name'],
                'reviewed_at': timezone.now().isoformat(),
            }
        update_client_document_from_students_life(document, payload)
        messages.success(request, 'Статус документа изменён через API клиентского приложения.')
        return redirect(reverse('portal:client_document_review', args=[document.id]))


class ClientDocumentsLoadedPortalView(PortalContextMixin, View):
    active_page = 'client_documents'

    def post(self, request, client_id):
        client = get_object_or_404(client_queryset(request.user), pk=client_id)
        created, message = mark_client_documents_loaded(
            request,
            client,
            comment=request.POST.get('comment', '').strip(),
        )
        if created:
            messages.success(request, message)
        else:
            messages.info(request, message)
        next_url = request.POST.get('next') or reverse('portal:client_detail', args=[client.id])
        return redirect(next_url)


class DocumentUploadRatingView(PortalContextMixin, TemplateView):
    template_name = 'portal/document_upload_rating.html'
    active_page = 'document_upload_rating'
    page_title = 'Рейтинг загрузок документов'

    def get_period(self):
        today = timezone.localdate()
        period = self.request.GET.get('period') or 'month'
        if period == 'week':
            return period, today - timedelta(days=7), today
        if period == 'quarter':
            return period, today - timedelta(days=90), today
        return 'month', today.replace(day=1), today

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        period, period_start, period_end = self.get_period()
        office_id = self.request.GET.get('office') or ''
        profiles = employee_queryset(self.request.user).filter(is_active=True)
        if office_id:
            profiles = profiles.filter(office_id=office_id)

        rows = []
        for profile in profiles:
            credits = (
                ManagerDocumentCredit.objects
                .filter(
                    employee=profile,
                    event_type=ManagerDocumentCredit.EVENT_UPLOADED_CLIENT_DOCUMENTS,
                    credited_at__date__gte=period_start,
                    credited_at__date__lte=period_end,
                )
                .select_related('client', 'credited_by', 'plan')
                .order_by('-credited_at')
            )
            uploaded_clients = credits.values('client_id').distinct().count()
            plan = (
                ManagerDocumentPlan.objects
                .filter(employee=profile, is_active=True, start_date__lte=period_end, end_date__gte=period_start)
                .order_by('-start_date', '-created_at')
                .first()
            )
            target = plan.target_clients if plan else 0
            remaining = max(target - uploaded_clients, 0) if target else 0
            percent = round((uploaded_clients / target) * 100) if target else 0
            active_clients = Client.objects.filter(manager=profile.user).exclude(status__in=['archive', 'rejected'])
            documents_qs = ClientFile.objects.filter(client__manager=profile.user, source='students_life_mobile_app')
            rows.append({
                'profile': profile,
                'uploaded_clients': uploaded_clients,
                'target': target,
                'remaining': remaining,
                'percent': percent,
                'active_clients': active_clients.count(),
                'complete_clients': active_clients.filter(custom_data__documents_status='documents_loaded').count(),
                'pending_documents': documents_qs.filter(status=ClientFile.STATUS_PENDING).count(),
                'approved_documents': documents_qs.filter(status=ClientFile.STATUS_APPROVED).count(),
                'rejected_documents': documents_qs.filter(status=ClientFile.STATUS_REJECTED).count(),
                'credits': credits[:8],
            })
        rows.sort(key=lambda row: (row['uploaded_clients'], row['percent']), reverse=True)

        context.update({
            'rating_rows': rows,
            'office_options': office_queryset(self.request.user).order_by('name'),
            'current_office': office_id,
            'current_period': period,
            'period_start': period_start,
            'period_end': period_end,
            'team_target': sum(row['target'] for row in rows),
            'team_uploaded': sum(row['uploaded_clients'] for row in rows),
            'team_remaining': max(sum(row['target'] for row in rows) - sum(row['uploaded_clients'] for row in rows), 0),
        })
        return context


class ClientQuestionnairesView(PortalContextMixin, TemplateView):
    template_name = 'portal/client_questionnaires.html'
    active_page = 'client_questionnaires'
    page_title = 'Анкеты клиентов'

    def get_queryset(self):
        qs = ClientQuestionnaire.objects.select_related('client').filter(client_id__in=client_queryset(self.request.user).values('id'))
        query = self.request.GET.get('q') or ''
        if query:
            qs = qs.filter(
                Q(full_name__icontains=query)
                | Q(phone__icontains=query)
                | Q(email__icontains=query)
                | Q(client__full_name__icontains=query)
                | Q(desired_program__icontains=query)
            )
        status_value = self.request.GET.get('status') or ''
        if status_value in {
            ClientQuestionnaire.STATUS_DRAFT,
            ClientQuestionnaire.STATUS_COMPLETED,
            ClientQuestionnaire.STATUS_SUBMITTED,
            ClientQuestionnaire.STATUS_APPROVED,
            ClientQuestionnaire.STATUS_REJECTED,
            ClientQuestionnaire.STATUS_UPDATED,
        }:
            qs = qs.filter(status=status_value)
        return qs.order_by('-updated_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page_obj, query = paginate_queryset(self.request, self.get_queryset(), 24)
        context.update({
            'questionnaires': page_obj.object_list,
            'page_obj': page_obj,
            'page_query': query,
            'query': self.request.GET.get('q', ''),
            'status_filter': self.request.GET.get('status', ''),
            'status_choices': (
                ('', 'Все'),
                (ClientQuestionnaire.STATUS_DRAFT, 'Не заполнена'),
                (ClientQuestionnaire.STATUS_COMPLETED, 'Заполнена'),
                (ClientQuestionnaire.STATUS_SUBMITTED, 'Отправлена'),
                (ClientQuestionnaire.STATUS_APPROVED, 'Принята'),
                (ClientQuestionnaire.STATUS_REJECTED, 'Отклонена'),
                (ClientQuestionnaire.STATUS_UPDATED, 'Обновлена'),
            ),
        })
        return context


class ClientQuestionnaireDetailView(PortalContextMixin, TemplateView):
    template_name = 'portal/client_questionnaire_detail.html'
    active_page = 'client_questionnaires'
    page_title = 'Анкета клиента'

    def get_questionnaire(self):
        return get_object_or_404(
            ClientQuestionnaire.objects.select_related('client').filter(client_id__in=client_queryset(self.request.user).values('id')),
            pk=self.kwargs['pk'],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        questionnaire = self.get_questionnaire()
        context['questionnaire'] = questionnaire
        context['data'] = questionnaire.data or {}
        context['questionnaire_sections'] = build_questionnaire_sections(context['data'])
        context['student_life_document_url'] = questionnaire_generated_document_url(questionnaire)
        return context


class ClientQuestionnaireDownloadView(PortalContextMixin, View):
    active_page = 'client_questionnaires'

    def get(self, request, pk):
        questionnaire = get_object_or_404(
            ClientQuestionnaire.objects.select_related('client').filter(client_id__in=client_queryset(request.user).values('id')),
            pk=pk,
        )
        student_life_url = questionnaire_generated_document_url(questionnaire)
        if student_life_url:
            return redirect(student_life_url)
        if not questionnaire.generated_file:
            questionnaire.generate_file()
        if not questionnaire.generated_file:
            raise Http404('Questionnaire document is not generated.')
        return FileResponse(questionnaire.generated_file.open('rb'), as_attachment=True, filename=f'anketa-{questionnaire.client_id}.docx')


class ClientQuestionnaireRegenerateView(PortalContextMixin, View):
    active_page = 'client_questionnaires'

    def post(self, request, pk):
        questionnaire = get_object_or_404(
            ClientQuestionnaire.objects.select_related('client').filter(client_id__in=client_queryset(request.user).values('id')),
            pk=pk,
        )
        if not questionnaire.mobile_questionnaire_id:
            messages.error(request, 'У анкеты нет mobile questionnaire id, перегенерация через клиентский API невозможна.')
            return redirect(reverse('portal:client_questionnaire_detail', args=[questionnaire.id]))

        ok, payload = students_life_api_request(
            f'questionnaire/application-forms/{questionnaire.mobile_questionnaire_id}/regenerate-document/',
            payload=portal_user_review_payload(request.user),
            method='POST',
        )
        if not ok:
            messages.error(request, payload.get('detail') or 'Клиентский API не смог перегенерировать документ анкеты.')
            return redirect(reverse('portal:client_questionnaire_detail', args=[questionnaire.id]))

        update_questionnaire_from_students_life(questionnaire, payload)
        messages.success(request, 'Документ анкеты перегенерирован через API клиентского приложения.')
        return redirect(reverse('portal:client_questionnaire_detail', args=[questionnaire.id]))


class ClientQuestionnaireReviewView(PortalContextMixin, View):
    active_page = 'client_questionnaires'

    def post(self, request, pk):
        questionnaire = get_object_or_404(
            ClientQuestionnaire.objects.select_related('client').filter(client_id__in=client_queryset(request.user).values('id')),
            pk=pk,
        )
        if not questionnaire.mobile_questionnaire_id:
            messages.error(request, 'У анкеты нет mobile questionnaire id, статус нельзя изменить через Student’s Life API.')
            return redirect(reverse('portal:client_questionnaire_detail', args=[questionnaire.id]))

        action = request.POST.get('action') or request.POST.get('status')
        comment = request.POST.get('review_comment', '').strip()
        reviewer = portal_user_review_payload(request.user)

        if action in {'approve', ClientQuestionnaire.STATUS_APPROVED}:
            api_path = f'questionnaire/application-forms/{questionnaire.mobile_questionnaire_id}/approve/'
            api_payload = {**reviewer}
        elif action in {'reject', ClientQuestionnaire.STATUS_REJECTED}:
            if not comment:
                messages.error(request, 'Укажите причину отклонения анкеты.')
                return redirect(reverse('portal:client_questionnaire_detail', args=[questionnaire.id]))
            api_path = f'questionnaire/application-forms/{questionnaire.mobile_questionnaire_id}/reject/'
            api_payload = {'comment': comment, **reviewer}
        elif action in {ClientQuestionnaire.STATUS_DRAFT, ClientQuestionnaire.STATUS_SUBMITTED, ClientQuestionnaire.STATUS_APPROVED, ClientQuestionnaire.STATUS_REJECTED}:
            if action == ClientQuestionnaire.STATUS_REJECTED and not comment:
                messages.error(request, 'Укажите причину отклонения анкеты.')
                return redirect(reverse('portal:client_questionnaire_detail', args=[questionnaire.id]))
            api_path = f'questionnaire/application-forms/{questionnaire.mobile_questionnaire_id}/status/'
            api_payload = {'status': action, 'comment': comment, **reviewer}
        else:
            messages.error(request, 'Некорректное действие проверки анкеты.')
            return redirect(reverse('portal:client_questionnaire_detail', args=[questionnaire.id]))

        ok, payload = students_life_api_request(api_path, payload=api_payload, method='PATCH' if api_path.endswith('/status/') else 'POST')
        if not ok:
            messages.error(request, payload.get('detail') or payload.get('comment') or payload.get('status') or 'Student’s Life API не принял изменение статуса анкеты.')
            return redirect(reverse('portal:client_questionnaire_detail', args=[questionnaire.id]))

        if isinstance(payload, dict) and 'status' not in normalize_students_life_payload(payload):
            payload = {
                **payload,
                'status': action if action not in {'approve', 'reject'} else (
                    ClientQuestionnaire.STATUS_APPROVED if action == 'approve' else ClientQuestionnaire.STATUS_REJECTED
                ),
                'review_comment': comment,
                **reviewer,
                'reviewed_by_display': reviewer['reviewed_by_name'],
                'reviewed_at': timezone.now().isoformat(),
            }
        update_questionnaire_from_students_life(questionnaire, payload)
        messages.success(request, 'Статус анкеты обновлён через Student’s Life API.')
        return redirect(reverse('portal:client_questionnaire_detail', args=[questionnaire.id]))


class ApplicationsView(ListPageMixin):
    active_page = 'applications'
    page_title = 'Заявки'
    table_template = 'portal/partials/applications_table.html'
    search_fields = ('client__full_name', 'university_name', 'program_name', 'country', 'comment')
    status_choices = Application.STATUS_CHOICES

    def get_queryset(self):
        return application_queryset(self.request.user).select_related('client', 'manager')


class TasksView(ListPageMixin):
    active_page = 'tasks'
    page_title = 'Задачи'
    table_template = 'portal/partials/tasks_table.html'
    grid_template = 'portal/partials/tasks_grid.html'
    filter_template = 'portal/partials/tasks_filters.html'
    create_url_name = 'portal:task_create'
    create_label = 'Создать задачу'
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
        edit_id = self.kwargs.get('pk') or self.request.GET.get('edit') or self.request.POST.get('object_id')
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
            if task.project_id and not task.section_id:
                task.section = get_or_create_default_project_section(task.project)
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
    active_page = 'projects'
    page_title = 'Проекты'
    table_template = 'portal/partials/projects_table.html'
    grid_template = 'portal/partials/projects_grid.html'
    create_url_name = 'portal:project_create'
    create_label = 'Создать проект'
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
            elif not item.company_id:
                item.company = fallback_company()
            if employee and employee.office_id and not item.office_id:
                item.office = employee.office
            if not item.created_by_id:
                item.created_by = request.user
            if not item.owner_id:
                item.owner = request.user
            if not item.code:
                item.code = unique_code(Project, item.title, company=item.company, exclude_pk=item.pk)
            item.save()
            form.save_m2m()
            item.participants.add(request.user)
            get_or_create_default_project_section(item)
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
        get_or_create_default_project_section(project)
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
            if not item.section_id:
                item.section = get_or_create_default_project_section(project)
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
            'income_total_usd': incomes.filter(is_confirmed=True, date__gte=current_month).aggregate(total=Sum('amount_usd'))['total'] or 0,
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

    def get_form(self, data=None, files=None):
        return PortalIncomeForm(
            data=data,
            files=files,
            cashboxes=cashbox_queryset(self.request.user).filter(is_active=True, currency__code='USD').order_by('office__name', 'name'),
            clients=client_queryset(self.request.user).order_by('-updated_at'),
            deals=deal_queryset(self.request.user).order_by('-created_at'),
            services=service_queryset(self.request.user).filter(is_active=True).order_by('category__name', 'title'),
        )

    def post(self, request, *args, **kwargs):
        form = self.get_form(data=request.POST, files=request.FILES)
        if form.is_valid():
            try:
                employee, company, office = get_user_company_office(request.user)
                income = form.save(commit=False)
                cashbox = form.cleaned_data.get('cashbox') or get_or_create_usd_cashbox(request.user, company=company, office=office)
                income.company = cashbox.company
                income.office = cashbox.office
                income.cashbox = cashbox
                income.employee = request.user
                income.currency = get_system_currency()
                income.exchange_rate = Decimal('1.000000')
                income.status = Income.STATUS_PENDING
                income.is_confirmed = False
                income.save()
                messages.success(request, 'Доход добавлен и ожидает подтверждения администратора. Валюта системы: USD.')
                return redirect('portal:finance_income')
            except ValueError as exc:
                messages.error(request, str(exc))
        context = self.get_context_data()
        context['form'] = form
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = income_queryset(self.request.user)
        qs = apply_search(qs, self.request.GET.get('q'), ('title', 'source', 'comment', 'cashbox__name'))
        page_obj, page_query = paginate_queryset(self.request, qs.order_by('-date', '-created_at'), 30)
        context.update({
            'record_type': 'income',
            'form': context.get('form') or self.get_form(),
            'records': page_obj.object_list,
            'page_obj': page_obj,
            'page_query': page_query,
            'total_usd': qs.filter(is_confirmed=True).aggregate(total=Sum('amount_usd'))['total'] or 0,
            'query': self.request.GET.get('q', ''),
            'pending_count': qs.filter(status=Income.STATUS_PENDING).count(),
        })
        return context


class FinanceExpenseView(PortalContextMixin, TemplateView):
    template_name = 'portal/finance_records.html'
    active_page = 'finance'
    page_title = 'Расходы'

    def get_form(self, data=None, files=None):
        return PortalExpenseForm(
            data=data,
            files=files,
            categories=expense_category_queryset(self.request.user).order_by('company__name', 'name'),
        )

    def post(self, request, *args, **kwargs):
        form = self.get_form(data=request.POST, files=request.FILES)
        if form.is_valid():
            try:
                category = form.cleaned_data['category']
                employee, profile_company, office = get_user_company_office(request.user)
                company = category.company or profile_company
                cashbox = get_or_create_usd_cashbox(request.user, company=company, office=office)
                expense = form.save(commit=False)
                expense.company = company
                expense.office = office
                expense.cashbox = cashbox
                expense.employee = request.user
                expense.currency = get_system_currency()
                expense.exchange_rate = Decimal('1.000000')
                expense.save()
                expense.confirm(user=request.user)
                messages.success(request, 'Расход добавлен и сразу учтён в расходах. Валюта системы: USD.')
                return redirect('portal:finance_expense')
            except ValueError as exc:
                messages.error(request, str(exc))
        context = self.get_context_data()
        context['form'] = form
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = expense_queryset(self.request.user)
        qs = apply_search(qs, self.request.GET.get('q'), ('title', 'comment', 'category__name', 'employee__email'))
        page_obj, page_query = paginate_queryset(self.request, qs.order_by('-date', '-created_at'), 30)
        context.update({
            'record_type': 'expense',
            'form': context.get('form') or self.get_form(),
            'can_confirm_finance': can_confirm_finance(self.request.user),
            'records': page_obj.object_list,
            'page_obj': page_obj,
            'page_query': page_query,
            'total_usd': qs.filter(is_confirmed=True).aggregate(total=Sum('amount_usd'))['total'] or 0,
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
            if not deal.currency_id:
                deal.currency = get_system_currency()
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
        page_obj, page_query = paginate_queryset(self.request, qs.order_by('-created_at'), 30)
        context.update({
            'form': context.get('form') or self.get_form(),
            'deals': page_obj.object_list,
            'page_obj': page_obj,
            'page_query': page_query,
            'query': self.request.GET.get('q', ''),
        })
        return context


class FinancePaymentsView(PortalContextMixin, TemplateView):
    template_name = 'portal/finance_payments.html'
    active_page = 'finance'
    page_title = 'Платежи'

    def get_form(self, data=None, files=None):
        return PortalPaymentForm(
            data=data,
            files=files,
            deals=deal_queryset(self.request.user).order_by('-created_at'),
        )

    def post(self, request, *args, **kwargs):
        form = self.get_form(data=request.POST, files=request.FILES)
        if form.is_valid():
            try:
                deal = form.cleaned_data['deal']
                payment = form.save(commit=False)
                cashbox = get_or_create_usd_cashbox(request.user, company=deal.company, office=deal.office)
                payment.company = deal.company
                payment.office = deal.office
                payment.client = deal.client
                payment.manager = request.user
                payment.cashbox = cashbox
                payment.currency = get_system_currency()
                payment.exchange_rate = Decimal('1.000000')
                payment.save()
                if request.POST.get('confirm_now') and can_confirm_finance(request.user):
                    payment.confirm(user=request.user)
                    messages.success(request, 'Платёж добавлен и подтверждён. Валюта системы: USD.')
                else:
                    messages.success(request, 'Платёж добавлен и ожидает подтверждения. Валюта системы: USD.')
                return redirect('portal:finance_payments')
            except ValueError as exc:
                messages.error(request, str(exc))
        context = self.get_context_data()
        context['form'] = form
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = payment_queryset(self.request.user)
        qs = apply_search(qs, self.request.GET.get('q'), ('client__full_name', 'deal__title', 'comment'))
        page_obj, page_query = paginate_queryset(self.request, qs.order_by('-payment_date', '-created_at'), 30)
        context.update({
            'form': context.get('form') or self.get_form(),
            'payments': page_obj.object_list,
            'page_obj': page_obj,
            'page_query': page_query,
            'query': self.request.GET.get('q', ''),
            'can_confirm_finance': can_confirm_finance(self.request.user),
        })
        return context


class ApprovalsView(PortalContextMixin, TemplateView):
    template_name = 'portal/approvals.html'
    active_page = 'approvals'
    page_title = 'Подтверждения'

    def dispatch(self, request, *args, **kwargs):
        if not can_confirm_finance(request.user) and not can_delete_admin(request.user):
            messages.error(request, 'Недостаточно прав для страницы подтверждений.')
            return redirect('portal:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        action = request.POST.get('action')
        try:
            if action == 'confirm_income':
                income = get_object_or_404(income_queryset(request.user), pk=request.POST.get('income_id'))
                income.confirm(user=request.user)
                messages.success(request, 'Доход подтверждён. Комиссия 5% начислена менеджеру.')
            elif action == 'reject_income':
                income = get_object_or_404(income_queryset(request.user), pk=request.POST.get('income_id'))
                income.reject(user=request.user, reason=request.POST.get('reason', ''))
                messages.success(request, 'Доход отклонён.')
            elif action == 'approve_document':
                document = get_object_or_404(document_queryset(request.user), pk=request.POST.get('document_id'))
                with_stamp = request.POST.get('with_stamp') == '1'
                document.approve(
                    user=request.user,
                    with_stamp=with_stamp,
                    comment=request.POST.get('comment', ''),
                    stamp_options=stamp_options_from_post(request.POST) if with_stamp else None,
                )
                messages.success(request, 'Документ подтверждён.')
                return redirect('portal:document_review', pk=document.pk)
            elif action == 'reject_document':
                document = get_object_or_404(document_queryset(request.user), pk=request.POST.get('document_id'))
                document.reject(user=request.user, reason=request.POST.get('reason', ''))
                messages.success(request, 'Документ отклонён.')
                return redirect('portal:document_review', pk=document.pk)
        except Exception as exc:
            messages.error(request, str(exc))
        return redirect('portal:approvals')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        incomes = income_queryset(self.request.user).filter(status=Income.STATUS_PENDING).order_by('-date', '-created_at')
        documents = document_queryset(self.request.user).filter(status=GeneratedDocument.STATUS_PENDING).order_by('-submitted_at', '-created_at')
        payments = payment_queryset(self.request.user).filter(is_confirmed=False).order_by('-payment_date', '-created_at')
        context.update({
            'pending_incomes': limit(incomes, 50),
            'pending_documents': limit(documents, 50),
            'pending_payments': limit(payments, 50),
            'pending_incomes_count': incomes.count(),
            'pending_documents_count': documents.count(),
            'pending_payments_count': payments.count(),
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
        incomes = income_queryset(self.request.user).filter(is_confirmed=True)
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
    active_page = 'documents'
    page_title = 'Документы'
    table_template = 'portal/partials/documents_table.html'
    grid_template = 'portal/partials/documents_grid.html'
    search_fields = ('title', 'template__name', 'client__full_name', 'deal__title')
    status_choices = GeneratedDocument.STATUS_CHOICES

    def get_queryset(self):
        return document_queryset(self.request.user)

    def get_extra_context(self, qs):
        return {
            'pending_documents': qs.filter(status=GeneratedDocument.STATUS_PENDING).count(),
            'can_review_documents': can_delete_admin(self.request.user),
        }


def form_fields(form, names):
    return [form[name] for name in names if name in form.fields]


class UniversityFormView(PortalFormPageMixin, UniversitiesView):
    cancel_url_name = 'portal:universities'
    form_page_title_create = 'Добавить ВУЗ'
    form_page_title_edit = 'Редактировать ВУЗ'
    submit_label = 'Сохранить ВУЗ'

    def get_form_groups(self, form):
        return [
            {'title': 'Основное', 'open': True, 'fields': form_fields(form, ('country', 'city', 'local_currency', 'name', 'legal_name', 'website', 'email', 'phone', 'address', 'is_active'))},
            {'title': 'Описание и поступление', 'open': True, 'fields': form_fields(form, ('description', 'admission_requirements'))},
        ]


class ProgramFormView(PortalFormPageMixin, ProgramsView):
    cancel_url_name = 'portal:programs'
    form_page_title_create = 'Добавить программу'
    form_page_title_edit = 'Редактировать программу'
    submit_label = 'Сохранить программу'

    def get_form_groups(self, form):
        return [
            {'title': 'Основное', 'open': True, 'fields': form_fields(form, ('university', 'name', 'degree', 'faculty', 'language', 'duration'))},
            {'title': 'Описание', 'open': True, 'fields': form_fields(form, ('description', 'admission_requirements', 'is_active', 'is_archived'))},
        ]


class ServiceFormView(PortalFormPageMixin, ServicesView):
    cancel_url_name = 'portal:services'
    form_page_title_create = 'Добавить услугу'
    form_page_title_edit = 'Редактировать услугу'
    submit_label = 'Сохранить услугу'

    def get_form_groups(self, form):
        return [
            {'title': 'Основное', 'open': True, 'fields': form_fields(form, ('category', 'category_name', 'title', 'code', 'description'))},
            {'title': 'Цена и видимость', 'open': True, 'fields': form_fields(form, ('price_client', 'real_cost', 'currency', 'is_active', 'is_public'))},
        ]


class ClientFormView(PortalFormPageMixin, ClientsView):
    cancel_url_name = 'portal:clients'
    form_page_title_create = 'Добавить клиента'
    form_page_title_edit = 'Редактировать клиента'
    submit_label = 'Сохранить клиента'

    def get_form_groups(self, form):
        base_fields = ['full_name', 'phone', 'email', 'direction', 'status', 'lead_source', 'comments']
        if is_erp_admin(self.request.user) or self.request.user.is_staff:
            base_fields.extend(['manager', 'office'])
        return [
            {'title': 'Основное', 'open': True, 'fields': form_fields(form, base_fields)},
            {'title': 'Личные данные', 'open': False, 'fields': form_fields(form, ('dob', 'citizenship', 'city', 'address', 'address_registration'))},
            {'title': 'Паспорт', 'open': False, 'fields': form_fields(form, ('passport_local_num', 'passport_inter_num', 'passport_issued_by', 'passport_issued_date', 'passport_valid_until', 'passport_birth_place'))},
            {'title': 'Родственник и образование', 'open': False, 'fields': form_fields(form, ('relative_full_name', 'relative_relation', 'relative_phone', 'relative_workplace', 'current_education', 'current_school', 'current_study_country', 'interested_country', 'interested_university', 'interested_program'))},
            {'title': 'Документы', 'open': False, 'fields': form_fields(form, ('has_passport', 'has_education_doc', 'has_photo'))},
        ]


class TaskFormView(PortalFormPageMixin, TasksView):
    cancel_url_name = 'portal:tasks'
    form_page_title_create = 'Создать задачу'
    form_page_title_edit = 'Редактировать задачу'
    submit_label = 'Сохранить задачу'

    def get_form_groups(self, form):
        return [
            {'title': 'Основное', 'open': True, 'fields': form_fields(form, ('project', 'section', 'title', 'assigned_to', 'priority', 'status', 'deadline'))},
            {'title': 'Описание', 'open': True, 'fields': form_fields(form, ('description',))},
        ]


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
            elif action == 'regenerate':
                if document.status == GeneratedDocument.STATUS_APPROVED:
                    raise PermissionError('Подтверждённый документ нельзя перегенерировать.')
                document.generate_file()
                messages.success(request, 'Документ повторно сгенерирован.')
            elif action == 'approve':
                if not can_delete_admin(request.user):
                    raise PermissionError('Недостаточно прав.')
                with_stamp = request.POST.get('with_stamp') == '1'
                document.approve(
                    user=request.user,
                    with_stamp=with_stamp,
                    comment=request.POST.get('comment', ''),
                    stamp_options=stamp_options_from_post(request.POST) if with_stamp else None,
                )
                messages.success(request, 'Документ подтверждён.')
            elif action == 'generate-stamp-preview':
                if not can_delete_admin(request.user):
                    raise PermissionError('Недостаточно прав.')
                document.generate_stamp_preview(
                    user=request.user,
                    stamp_options=stamp_options_from_post(request.POST),
                )
                messages.success(request, 'Предпросмотр PDF с печатью создан. Откройте его и проверьте положение печати.')
            elif action == 'approve-stamp-preview':
                if not can_delete_admin(request.user):
                    raise PermissionError('Недостаточно прав.')
                document.approve_stamp_preview(
                    user=request.user,
                    comment=request.POST.get('comment', ''),
                )
                messages.success(request, 'Проверенный PDF с печатью подтверждён и доступен для скачивания.')
            elif action == 'reject':
                if not can_delete_admin(request.user):
                    raise PermissionError('Недостаточно прав.')
                document.reject(user=request.user, reason=request.POST.get('reason', ''))
                messages.success(request, 'Документ отклонён.')
        except Exception as exc:
            messages.error(request, str(exc))
        if action in {'approve', 'reject', 'generate-stamp-preview', 'approve-stamp-preview'}:
            return redirect('portal:document_review', pk=document.pk)
        return redirect('portal:documents')

    def get(self, request, pk, action):
        document = self.get_document(request, pk)
        if action == 'download-original':
            if not document.can_download_original:
                messages.error(request, 'DOCX без печати недоступен для этого документа.')
                return redirect('portal:documents')
            log_document_download(request, document, DocumentDownloadLog.FILE_TYPE_ORIGINAL)
            return FileResponse(document.generated_file.open('rb'), as_attachment=True, filename=document.download_filename(DocumentDownloadLog.FILE_TYPE_ORIGINAL))
        if action == 'download-approved':
            if not document.can_download_approved:
                messages.error(request, 'PDF с печатью доступен только после подтверждения администратора.')
                return redirect('portal:documents')
            log_document_download(request, document, DocumentDownloadLog.FILE_TYPE_APPROVED)
            return FileResponse(document.approved_file.open('rb'), as_attachment=True, filename=document.download_filename(DocumentDownloadLog.FILE_TYPE_APPROVED))
        if action == 'preview-approved':
            if not document.can_preview_approved:
                messages.error(request, 'Предпросмотр доступен только для PDF с печатью. Одобренный DOCX можно скачать без предпросмотра.')
                return redirect('portal:document_review', pk=document.pk)
            log_document_download(request, document, DocumentDownloadLog.FILE_TYPE_APPROVED)
            response = FileResponse(document.approved_file.open('rb'), as_attachment=False, filename=document.download_filename(DocumentDownloadLog.FILE_TYPE_APPROVED))
            response['Content-Type'] = 'application/pdf'
            return response
        if action == 'preview-stamp-preview':
            if not can_delete_admin(request.user):
                messages.error(request, 'Недостаточно прав.')
                return redirect('portal:documents')
            if not document.stamp_preview_file:
                messages.error(request, 'Сначала сгенерируйте предпросмотр PDF с печатью.')
                return redirect('portal:document_review', pk=document.pk)
            response = FileResponse(document.stamp_preview_file.open('rb'), as_attachment=False, filename=document.download_filename(DocumentDownloadLog.FILE_TYPE_APPROVED))
            response['Content-Type'] = 'application/pdf'
            return response
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
        page_obj, page_query = paginate_queryset(self.request, folder_articles.order_by('-is_featured', '-updated_at'), 30)
        context.update({
            'folder': folder,
            'breadcrumbs': breadcrumbs,
            'folders': child_folders.order_by('sort_order', 'name'),
            'articles': page_obj.object_list,
            'page_obj': page_obj,
            'page_query': page_query,
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
                item.code = unique_code(KnowledgeCategory, item.name, company=item.company, exclude_pk=item.pk)
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
        user = self.request.user
        today = timezone.localdate()
        history = workday_queryset(user).order_by('-date')
        if not can_delete_admin(user):
            history = history.filter(employee=user)
        else:
            employee_id = self.request.GET.get('employee') or ''
            office_id = self.request.GET.get('office') or ''
            date_from = parse_date(self.request.GET.get('date_from') or '')
            date_to = parse_date(self.request.GET.get('date_to') or '')
            if employee_id:
                history = history.filter(employee_id=employee_id)
            if office_id:
                history = history.filter(office_id=office_id)
            if date_from:
                history = history.filter(date__gte=date_from)
            if date_to:
                history = history.filter(date__lte=date_to)

        profiles = employee_queryset(user).filter(is_active=True).filter(must_track_workday_q())
        today_workdays = WorkDay.objects.select_related('employee', 'office').filter(
            date=today,
            employee_id__in=profiles.values('user_id'),
        )
        started_user_ids = set(today_workdays.exclude(status=WorkDay.STATUS_NOT_STARTED).values_list('employee_id', flat=True))
        report_user_ids = set(DailyReport.objects.filter(date=today, employee_id__in=profiles.values('user_id')).values_list('employee_id', flat=True))
        closed_user_ids = set(today_workdays.filter(status__in=[WorkDay.STATUS_CLOSED, WorkDay.STATUS_AUTO_CLOSED]).values_list('employee_id', flat=True))

        context.update({
            'workday': get_today_workday(user),
            'reports': DailyReport.objects.filter(employee=user).select_related('workday').order_by('-date')[:10],
            'history': history[:20],
            'employee_options': employee_queryset(user).filter(is_active=True).order_by('user__first_name', 'user__last_name'),
            'office_options': office_queryset(user).order_by('name'),
            'selected_employee': self.request.GET.get('employee', ''),
            'selected_office': self.request.GET.get('office', ''),
            'date_from': self.request.GET.get('date_from', ''),
            'date_to': self.request.GET.get('date_to', ''),
            'today_profiles': profiles.order_by('office__name', 'user__first_name', 'user__last_name')[:120],
            'today_workdays': today_workdays,
            'started_user_ids': started_user_ids,
            'report_user_ids': report_user_ids,
            'closed_user_ids': closed_user_ids,
            'today_started_count': len(started_user_ids),
            'today_not_started_count': profiles.exclude(user_id__in=started_user_ids).count(),
            'can_filter_workday_history': can_delete_admin(user),
        })
        return context


class WorkdayReportsView(PortalContextMixin, TemplateView):
    template_name = 'portal/workday_reports.html'
    active_page = 'workday'
    page_title = 'История отчётов'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        reports = DailyReport.objects.select_related('workday', 'company', 'office', 'employee')

        if can_delete_admin(user):
            employee_id = self.request.GET.get('employee') or ''
            office_id = self.request.GET.get('office') or ''
            reports = reports.filter(employee_scope_q(user, manager_field='employee'))
            if employee_id:
                reports = reports.filter(employee_id=employee_id)
            if office_id:
                reports = reports.filter(office_id=office_id)
        else:
            employee_id = ''
            office_id = ''
            reports = reports.filter(employee=user)

        date_from = parse_date(self.request.GET.get('date_from') or '')
        date_to = parse_date(self.request.GET.get('date_to') or '')
        if date_from:
            reports = reports.filter(date__gte=date_from)
        if date_to:
            reports = reports.filter(date__lte=date_to)

        page_obj, page_query = paginate_queryset(self.request, reports.order_by('-date', '-submitted_at'), 25)
        context.update({
            'reports': page_obj.object_list,
            'page_obj': page_obj,
            'page_query': page_query,
            'total_count': reports.count(),
            'employee_options': employee_queryset(user).filter(is_active=True).order_by('user__first_name', 'user__last_name'),
            'office_options': office_queryset(user).order_by('name'),
            'selected_employee': employee_id,
            'selected_office': office_id,
            'date_from': self.request.GET.get('date_from', ''),
            'date_to': self.request.GET.get('date_to', ''),
            'can_filter_reports': can_delete_admin(user),
        })
        return context


class WorkdayActionMixin(LoginRequiredMixin, View):
    login_url = reverse_lazy('portal:login')
    success_url = 'portal:workday'

    def get_workday(self):
        return ensure_today_workday(self.request.user)

    def redirect_back(self):
        next_url = self.request.POST.get('next') or self.request.GET.get('next')
        if next_url and next_url.startswith('/portal/'):
            return redirect(next_url)
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

    def get_selected_day(self):
        return parse_date(self.request.GET.get('day') or '') or timezone.localdate()

    def get_event_form(self, data=None, instance=None, initial=None):
        return PortalCalendarEventForm(
            data=data,
            instance=instance,
            initial=initial,
            offices=office_queryset(self.request.user).order_by('name'),
            users=portal_user_queryset(self.request.user),
            is_admin=can_delete_admin(self.request.user),
        )

    def post(self, request, *args, **kwargs):
        action = request.POST.get('action', 'save_event')
        if action == 'delete_event':
            event = get_object_or_404(calendar_event_queryset(request.user), pk=request.POST.get('event_id'))
            if event.owner_id != request.user.id and not can_delete_admin(request.user):
                messages.error(request, 'Удалить это событие может только автор или администратор.')
            else:
                event.delete()
                messages.success(request, 'Событие удалено.')
            return redirect(f'{reverse("portal:calendar")}?day={request.POST.get("day") or timezone.localdate().isoformat()}')

        form = self.get_event_form(data=request.POST)
        selected_day = request.POST.get('event_date') or timezone.localdate().isoformat()
        if form.is_valid():
            employee = get_employee_profile(request.user)
            event = form.save(commit=False)
            if employee:
                event.company = employee.company
                if not event.office_id:
                    event.office = employee.office
            elif not event.company_id:
                event.company = fallback_company()
            if not can_delete_admin(request.user):
                event.owner = request.user
                if event.visibility == CalendarEvent.VISIBILITY_COMPANY:
                    event.visibility = CalendarEvent.VISIBILITY_OFFICE
            elif not event.owner_id:
                event.owner = request.user
            if not event.created_by_id:
                event.created_by = request.user
            event.save()
            form.save_m2m()
            event.participants.add(request.user)
            messages.success(request, 'Событие добавлено в календарь.')
            return redirect(f'{reverse("portal:calendar")}?day={event.event_date.isoformat()}&month={event.event_date.month}&year={event.event_date.year}')

        context = self.get_context_data()
        context['event_form'] = form
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        selected_day = self.get_selected_day()
        try:
            month = int(self.request.GET.get('month') or selected_day.month or today.month)
        except ValueError:
            month = today.month
        try:
            year = int(self.request.GET.get('year') or selected_day.year or today.year)
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
            'selected_day': selected_day,
            'selected_month_name': MONTH_NAMES_RU[month],
            'month_options': [(number, MONTH_NAMES_RU[number]) for number in range(1, 13)],
            'year_options': range(today.year - 3, today.year + 4),
            'previous_month': prev_month,
            'previous_year': prev_year,
            'next_month': next_month,
            'next_year': next_year,
            'events': build_calendar_events(self.request.user, limit_count=80),
            'selected_day_events': build_events_for_range(self.request.user, selected_day, selected_day),
            'manual_events': calendar_event_queryset(self.request.user).filter(event_date=selected_day).order_by('start_time', 'title'),
            'event_form': context.get('event_form') or self.get_event_form(initial={'event_date': selected_day}),
            'upcoming_tasks': task_queryset(self.request.user).filter(deadline__isnull=False, deadline__date__gte=today).order_by('deadline')[:12],
            'birthdays': employee_queryset(self.request.user).filter(user__dob__isnull=False).order_by('user__dob__month', 'user__dob__day')[:50],
            'can_manage_calendar': can_delete_admin(self.request.user),
        })
        return context


class EmployeeReportsView(PortalContextMixin, TemplateView):
    template_name = 'portal/employee_reports.html'
    active_page = 'employee_reports'
    page_title = 'Отчёты сотрудников'

    def dispatch(self, request, *args, **kwargs):
        if not can_delete_admin(request.user):
            messages.error(request, 'Эта страница доступна только администратору.')
            return redirect('portal:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get_date_range(self):
        today = timezone.localdate()
        exact_date = parse_date(self.request.GET.get('date') or '')
        if exact_date:
            return exact_date, exact_date
        period = self.request.GET.get('period') or 'week'
        if period == '3days':
            return today - timedelta(days=2), today
        if period == 'month':
            return today.replace(day=1), today
        return today - timedelta(days=6), today

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        start_date, end_date = self.get_date_range()
        employee_id = self.request.GET.get('employee') or ''
        office_id = self.request.GET.get('office') or ''

        profiles = employee_queryset(self.request.user).filter(is_active=True).filter(must_track_workday_q()).order_by('office__name', 'user__first_name', 'user__last_name')
        if office_id:
            profiles = profiles.filter(office_id=office_id)

        workdays = workday_queryset(self.request.user).filter(date__gte=start_date, date__lte=end_date).select_related('employee', 'office', 'daily_report').order_by('-date', 'office__name', 'employee__first_name')
        if employee_id:
            workdays = workdays.filter(employee_id=employee_id)
        if office_id:
            workdays = workdays.filter(office_id=office_id)

        page_obj, page_query = paginate_queryset(self.request, workdays, 30)
        selected_date = parse_date(self.request.GET.get('date') or '') or timezone.localdate()
        submitted_user_ids = set(
            DailyReport.objects.filter(date=selected_date, employee_id__in=profiles.values('user_id')).values_list('employee_id', flat=True)
        )
        workday_user_ids = set(
            WorkDay.objects.filter(date=selected_date, employee_id__in=profiles.values('user_id')).exclude(status=WorkDay.STATUS_NOT_STARTED).values_list('employee_id', flat=True)
        )
        missing_reports = profiles.exclude(user_id__in=submitted_user_ids)
        not_started = profiles.exclude(user_id__in=workday_user_ids)

        context.update({
            'start_date': start_date,
            'end_date': end_date,
            'selected_date': selected_date,
            'current_period': self.request.GET.get('period') or 'week',
            'current_employee': employee_id,
            'current_office': office_id,
            'employee_options': profiles,
            'office_options': office_queryset(self.request.user).order_by('name'),
            'workdays': page_obj.object_list,
            'page_obj': page_obj,
            'page_query': page_query,
            'total_count': workdays.count(),
            'missing_reports': missing_reports[:80],
            'not_started': not_started[:80],
        })
        return context


class RatingView(PortalContextMixin, TemplateView):
    template_name = 'portal/rating.html'
    active_page = 'rating'
    page_title = 'Рейтинг'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        period = self.request.GET.get('period') or 'month'
        office_id = self.request.GET.get('office') or ''
        leaderboard_filter = self.request.GET.get('leaderboard') or 'visible'
        can_view_hidden = is_erp_admin(self.request.user) or self.request.user.is_staff
        if period == 'week':
            period_start = today - timedelta(days=7)
        elif period == 'quarter':
            period_start = today - timedelta(days=90)
        else:
            period_start = today.replace(day=1)
        rows = []
        profiles = employee_queryset(self.request.user).filter(is_active=True)
        if office_id:
            profiles = profiles.filter(office_id=office_id)
        visible_q = Q(access__can_be_in_leaderboard=True) | Q(access__isnull=True)
        if can_view_hidden:
            if leaderboard_filter == 'visible':
                profiles = profiles.filter(visible_q)
            elif leaderboard_filter == 'hidden':
                profiles = profiles.filter(access__can_be_in_leaderboard=False)
        else:
            profiles = profiles.filter(visible_q)
        for profile in profiles:
            user = profile.user
            access = getattr(profile, 'access', None)
            leads_count = Lead.objects.filter(manager=user, created_at__date__gte=period_start).count()
            clients_count = Client.objects.filter(manager=user).exclude(status__in=['archive', 'rejected']).count()
            applications_count = Application.objects.filter(manager=user, created_at__date__gte=period_start).count()
            document_credits = ManagerDocumentCredit.objects.filter(
                employee=profile,
                event_type=ManagerDocumentCredit.EVENT_UPLOADED_CLIENT_DOCUMENTS,
                credited_at__date__gte=period_start,
            )
            document_uploaded_clients = document_credits.values('client_id').distinct().count()
            active_document_plan = (
                ManagerDocumentPlan.objects
                .filter(employee=profile, is_active=True, start_date__lte=today, end_date__gte=today)
                .order_by('-start_date', '-created_at')
                .first()
            )
            document_plan_target = active_document_plan.target_clients if active_document_plan else 0
            document_plan_remaining = max(document_plan_target - document_uploaded_clients, 0) if document_plan_target else 0
            document_plan_percent = round((document_uploaded_clients / document_plan_target) * 100) if document_plan_target else 0
            payments_usd = Payment.objects.filter(manager=user, is_confirmed=True, payment_date__gte=period_start).aggregate(total=Sum('amount_usd'))['total'] or 0
            income_usd = Income.objects.filter(employee=user, is_confirmed=True, date__gte=period_start).aggregate(total=Sum('amount_usd'))['total'] or 0
            commission_usd = EmployeeCommission.objects.filter(employee=user).exclude(status='cancelled').aggregate(total=Sum('amount_usd'))['total'] or 0
            try:
                balance_usd = user.managersalary.current_balance
            except Exception:
                balance_usd = commission_usd
            tasks_done = ProjectTask.objects.filter(assigned_to=user, status=ProjectTask.STATUS_DONE, completed_at__date__gte=period_start).count()
            tasks_total = ProjectTask.objects.filter(assigned_to=user, created_at__date__gte=period_start).count()
            workdays = WorkDay.objects.filter(employee=user, date__gte=period_start)
            started_days = workdays.exclude(status=WorkDay.STATUS_NOT_STARTED).count()
            closed_days = workdays.filter(status__in=[WorkDay.STATUS_CLOSED, WorkDay.STATUS_AUTO_CLOSED]).count()
            must_track = not access or access.must_track_workday
            missed_days = workdays.filter(status=WorkDay.STATUS_MISSED).count() if must_track else 0
            last_workday = workdays.order_by('-date').first()
            score = (
                leads_count * 2
                + clients_count * 3
                + applications_count * 4
                + int((payments_usd or 0) + (income_usd or 0)) // 100
                + document_uploaded_clients
                + tasks_done * 3
                + started_days
                + closed_days * 2
                - missed_days * 5
            )
            priority_enabled = bool(access and access.rating_priority_enabled)
            priority_level = int(access.rating_priority_level or 0) if priority_enabled else 0
            rows.append({
                'profile': profile,
                'score': score,
                'priority_enabled': priority_enabled,
                'priority_level': priority_level,
                'priority_note': access.rating_priority_note if access and access.rating_priority_note else '',
                'leads_count': leads_count,
                'clients_count': clients_count,
                'applications_count': applications_count,
                'document_uploaded_clients': document_uploaded_clients,
                'document_plan_target': document_plan_target,
                'document_plan_remaining': document_plan_remaining,
                'document_plan_percent': document_plan_percent,
                'payments_usd': payments_usd,
                'income_usd': income_usd,
                'commission_usd': commission_usd,
                'balance_usd': balance_usd,
                'tasks_total': tasks_total,
                'tasks_done': tasks_done,
                'started_days': started_days,
                'closed_days': closed_days,
                'missed_days': missed_days,
                'last_workday': last_workday,
                'is_hidden_from_leaderboard': bool(access and not access.can_be_in_leaderboard),
                'avatar_url': user.avatar.url if getattr(user, 'avatar', None) else '',
            })
        rating_rows = sorted(rows, key=lambda item: (item['priority_enabled'], item['priority_level'], item['score']), reverse=True)
        podium_rows = [row for row in rating_rows if not row['is_hidden_from_leaderboard']][:3]
        context.update({
            'rating_rows': rating_rows,
            'podium_rows': podium_rows,
            'office_options': office_queryset(self.request.user).order_by('name'),
            'current_office': office_id,
            'current_period': period,
            'current_leaderboard_filter': leaderboard_filter,
            'can_view_hidden_leaderboard': can_view_hidden,
        })
        return context


class NotificationsView(PortalContextMixin, TemplateView):
    template_name = 'portal/notifications.html'
    active_page = 'notifications'
    page_title = 'Уведомления'

    def get_status_filter(self):
        value = self.request.GET.get('status') or 'all'
        return value if value in {'all', 'unread', 'read'} else 'all'

    def get_my_notifications(self):
        qs = own_notification_queryset(self.request.user)
        status_filter = self.get_status_filter()
        if status_filter == 'unread':
            qs = qs.filter(read_at__isnull=True).exclude(status=Notification.STATUS_READ)
        elif status_filter == 'read':
            qs = qs.filter(Q(read_at__isnull=False) | Q(status=Notification.STATUS_READ))
        query = self.request.GET.get('q') or ''
        qs = apply_search(qs, query, ('title', 'body', 'sender__email'))
        return qs.annotate(
            unread_rank=Case(
                When(Q(read_at__isnull=True) & ~Q(status=Notification.STATUS_READ), then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by('unread_rank', '-created_at')

    def get_sent_batches(self):
        qs = annotate_notification_batches(notification_batch_queryset(self.request.user))
        query = self.request.GET.get('q') or ''
        return apply_search(qs, query, ('title', 'message', 'sender__email', 'target_user__email', 'target_office__name')).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        current_tab = self.request.GET.get('tab') or 'mine'
        can_create = can_delete_admin(self.request.user)
        if current_tab in {'sent', 'create'} and not can_create:
            current_tab = 'mine'

        notifications_page, notifications_query = paginate_queryset(self.request, self.get_my_notifications(), 25)
        batches_page, batches_query = paginate_queryset(self.request, self.get_sent_batches(), 20)
        unread_count = own_notification_queryset(self.request.user).filter(read_at__isnull=True).exclude(status=Notification.STATUS_READ).count()
        read_count = own_notification_queryset(self.request.user).filter(Q(read_at__isnull=False) | Q(status=Notification.STATUS_READ)).count()

        context.update({
            'current_tab': current_tab,
            'status_filter': self.get_status_filter(),
            'query': self.request.GET.get('q', ''),
            'my_notifications': notifications_page.object_list,
            'notifications_page_obj': notifications_page,
            'notifications_page_query': notifications_query,
            'sent_batches': batches_page.object_list,
            'batches_page_obj': batches_page,
            'batches_page_query': batches_query,
            'unread_count': unread_count,
            'read_count': read_count,
            'can_create_notifications': can_create,
        })
        return context


class NotificationReadView(LoginRequiredMixin, View):
    login_url = reverse_lazy('portal:login')

    def post(self, request, pk):
        notification = get_object_or_404(own_notification_queryset(request.user), pk=pk)
        notification.mark_read()
        messages.success(request, 'Уведомление отмечено как прочитанное.')
        return redirect(request.POST.get('next') or 'portal:notifications')


class NotificationBatchDetailView(PortalContextMixin, TemplateView):
    template_name = 'portal/notification_batch_detail.html'
    active_page = 'notifications'
    page_title = 'Статистика уведомления'

    def dispatch(self, request, *args, **kwargs):
        if not can_delete_admin(request.user):
            messages.error(request, 'Статистика отправленных уведомлений доступна только администратору.')
            return redirect('portal:notifications')
        return super().dispatch(request, *args, **kwargs)

    def get_batch(self):
        return get_object_or_404(annotate_notification_batches(notification_batch_queryset(self.request.user)), pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        batch = self.get_batch()
        recipients = batch.notifications.select_related('recipient', 'office').order_by('recipient__first_name', 'recipient__last_name', 'recipient__email')
        context.update({
            'batch': batch,
            'recipients': recipients,
            'recipient_total': getattr(batch, 'recipient_total', batch.recipient_count),
            'read_total': getattr(batch, 'read_total', batch.read_count),
            'unread_total': max(getattr(batch, 'recipient_total', batch.recipient_count) - getattr(batch, 'read_total', batch.read_count), 0),
            'read_percent_value': round((getattr(batch, 'read_total', 0) / getattr(batch, 'recipient_total', 1)) * 100) if getattr(batch, 'recipient_total', 0) else 0,
        })
        return context


class NotificationCreateView(PortalFormPageMixin, PortalContextMixin, TemplateView):
    active_page = 'notifications'
    page_title = 'Новое уведомление'
    cancel_url_name = 'portal:notifications'
    form_page_title_create = 'Добавить уведомление'
    submit_label = 'Создать уведомление'

    def dispatch(self, request, *args, **kwargs):
        if not can_delete_admin(request.user):
            messages.error(request, 'Создавать уведомления может только администратор.')
            return redirect('portal:notifications')
        return super().dispatch(request, *args, **kwargs)

    def get_edit_object(self):
        return None

    def get_form(self, data=None, instance=None):
        return PortalNotificationForm(
            data=data,
            users=portal_user_queryset(self.request.user),
            offices=office_queryset(self.request.user).order_by('name'),
        )

    def get_form_groups(self, form):
        return [
            {'title': 'Сообщение', 'open': True, 'fields': form_fields(form, ('title', 'body', 'notification_kind'))},
            {'title': 'Получатели', 'open': True, 'fields': form_fields(form, ('recipient_scope', 'recipient_user', 'recipient_office', 'send_now'))},
        ]

    def get_context_data(self, **kwargs):
        context = PortalContextMixin.get_context_data(self, **kwargs)
        form = context.get('form') or self.get_form()
        context.update({
            'form': form,
            'form_title': self.form_page_title_create,
            'form_groups': self.get_form_groups(form),
            'submit_label': self.submit_label,
            'cancel_url': self.get_cancel_url(),
            'edit_object': None,
        })
        return context

    def get_recipients(self, form):
        scope = form.cleaned_data['recipient_scope']
        if scope == PortalNotificationForm.SCOPE_USER:
            return User.objects.filter(pk=form.cleaned_data['recipient_user'].pk, is_active=True)
        if scope == PortalNotificationForm.SCOPE_OFFICE:
            return User.objects.filter(
                employee_profile__office=form.cleaned_data['recipient_office'],
                employee_profile__is_active=True,
                is_active=True,
            ).distinct()
        return User.objects.filter(employee_profile__is_active=True, is_active=True).distinct()

    def post(self, request, *args, **kwargs):
        form = self.get_form(data=request.POST)
        if form.is_valid():
            recipients = list(self.get_recipients(form).select_related('employee_profile__company', 'employee_profile__office'))
            if not recipients:
                messages.error(request, 'Под выбранные условия не найдено ни одного сотрудника.')
            else:
                kind = form.cleaned_data['notification_kind']
                employee, company, office = get_user_company_office(request.user)
                send_now = form.cleaned_data.get('send_now')
                batch = NotificationBatch.objects.create(
                    company=company,
                    office=office,
                    title=form.cleaned_data['title'],
                    message=form.cleaned_data['body'],
                    notification_type=kind,
                    sender=request.user,
                    target_type=form.cleaned_data['recipient_scope'],
                    target_user=form.cleaned_data.get('recipient_user') if form.cleaned_data['recipient_scope'] == PortalNotificationForm.SCOPE_USER else None,
                    target_office=form.cleaned_data.get('recipient_office') if form.cleaned_data['recipient_scope'] == PortalNotificationForm.SCOPE_OFFICE else None,
                    status=NotificationBatch.STATUS_SENT if send_now else NotificationBatch.STATUS_DRAFT,
                    sent_at=timezone.now() if send_now else None,
                )
                for recipient in recipients:
                    profile = get_employee_profile(recipient)
                    notification = Notification.objects.create(
                        company=profile.company if profile and profile.company_id else fallback_company(),
                        office=profile.office if profile and profile.office_id else None,
                        recipient=recipient,
                        sender=request.user,
                        notification_type=NotificationTemplate.TYPE_SYSTEM,
                        channel=NotificationTemplate.CHANNEL_IN_APP,
                        priority=form.get_priority(),
                        status=Notification.STATUS_NEW,
                        batch=batch,
                        title=form.cleaned_data['title'],
                        body=form.cleaned_data['body'],
                        data={'kind': kind, 'created_from': 'portal', 'batch_id': batch.pk},
                        target_url='/portal/notifications/',
                    )
                    if send_now:
                        notification.mark_sent()
                messages.success(request, f'Уведомление создано для {len(recipients)} сотрудник(ов).')
                return redirect('portal:notification_batch_detail', pk=batch.pk)
        context = self.get_context_data()
        context['form'] = form
        context['form_groups'] = self.get_form_groups(form)
        return self.render_to_response(context)


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
