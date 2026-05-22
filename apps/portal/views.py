from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q, Sum
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.attendance.models import DailyReport, WorkDay
from apps.core.permissions import get_employee_profile, is_erp_admin
from apps.crm.models import Application, Client, Lead
from apps.erp_documents.models import GeneratedDocument
from apps.erp_notifications.models import Notification
from apps.finance.models import Deal, Expense, FinancialPeriod, Payment
from apps.knowledge.models import KnowledgeArticle, KnowledgeTestAttempt
from apps.projects_v2.models import Project, ProjectTask


PAGE_SIZE = 25


NAV_ITEMS = (
    {'name': 'dashboard', 'label': 'Dashboard', 'icon': 'layout-dashboard'},
    {'name': 'leads', 'label': 'Leads', 'icon': 'radar'},
    {'name': 'clients', 'label': 'Clients', 'icon': 'users'},
    {'name': 'applications', 'label': 'Applications', 'icon': 'file-check-2'},
    {'name': 'tasks', 'label': 'Tasks', 'icon': 'check-square'},
    {'name': 'projects', 'label': 'Projects', 'icon': 'folder-kanban'},
    {'name': 'finance', 'label': 'Finance', 'icon': 'wallet-cards'},
    {'name': 'documents', 'label': 'Documents', 'icon': 'file-text'},
    {'name': 'knowledge', 'label': 'Knowledge', 'icon': 'book-open-check'},
    {'name': 'workday', 'label': 'Workday', 'icon': 'timer'},
    {'name': 'reports', 'label': 'Reports', 'icon': 'bar-chart-3'},
)


def full_name(user):
    return user.get_full_name() or getattr(user, 'email', '') or str(user)


def bool_param(value):
    if value in ('1', 'true', 'True', 'yes', 'on'):
        return True
    if value in ('0', 'false', 'False', 'no', 'off'):
        return False
    return None


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
    active_page = ''
    page_title = ''

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = get_employee_profile(self.request.user)
        nav_items = [{**item, 'url': reverse(f'portal:{item["name"]}')} for item in NAV_ITEMS]
        context.update({
            'active_page': self.active_page,
            'page_title': self.page_title,
            'nav_items': nav_items,
            'employee_profile': employee,
            'display_name': full_name(self.request.user),
            'unread_notifications_count': notification_queryset(self.request.user).filter(read_at__isnull=True).exclude(status=Notification.STATUS_READ).count(),
            'is_htmx': self.request.headers.get('HX-Request') == 'true',
        })
        return context


class PortalIndexView(LoginRequiredMixin, View):
    def get(self, request):
        return redirect('portal:dashboard')


class DashboardView(PortalContextMixin, TemplateView):
    template_name = 'portal/dashboard.html'
    active_page = 'dashboard'
    page_title = 'Dashboard'

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
        documents = document_queryset(user)
        notifications = notification_queryset(user)

        context.update({
            'metrics': [
                {'label': 'Leads', 'value': leads.exclude(status__in=['converted', 'lost', 'spam']).count(), 'icon': 'radar', 'url': reverse('portal:leads')},
                {'label': 'Clients', 'value': clients.exclude(status__in=['archive', 'rejected']).count(), 'icon': 'users', 'url': reverse('portal:clients')},
                {'label': 'Applications', 'value': applications.exclude(status__in=['cancelled', 'rejected', 'enrolled']).count(), 'icon': 'file-check-2', 'url': reverse('portal:applications')},
                {'label': 'Tasks', 'value': tasks.filter(Q(assigned_to=user) | Q(watchers__user=user)).exclude(status__in=[ProjectTask.STATUS_DONE, ProjectTask.STATUS_CANCELLED]).distinct().count(), 'icon': 'check-square', 'url': reverse('portal:tasks')},
                {'label': 'Payments', 'value': payments.filter(is_confirmed=True, created_at__gte=week_ago).count(), 'icon': 'wallet-cards', 'url': reverse('portal:finance')},
                {'label': 'Documents', 'value': documents.filter(status__in=[GeneratedDocument.STATUS_PENDING, GeneratedDocument.STATUS_GENERATED]).count(), 'icon': 'file-text', 'url': reverse('portal:documents')},
                {'label': 'Notifications', 'value': notifications.filter(read_at__isnull=True).exclude(status=Notification.STATUS_READ).count(), 'icon': 'bell', 'url': reverse('portal:dashboard')},
            ],
            'my_leads': limit(leads.exclude(status__in=['converted', 'lost', 'spam']).order_by('-created_at'), 6),
            'my_clients': limit(clients.order_by('-updated_at'), 6),
            'my_applications': limit(applications.order_by('-updated_at'), 6),
            'my_tasks': limit(tasks.filter(Q(assigned_to=user) | Q(watchers__user=user)).exclude(status__in=[ProjectTask.STATUS_DONE, ProjectTask.STATUS_CANCELLED]).distinct().order_by('deadline', '-updated_at'), 6),
            'workday': get_today_workday(user),
            'recent_payments': limit(payments.order_by('-payment_date', '-created_at'), 6),
            'recent_documents': limit(documents.order_by('-created_at'), 6),
            'notifications': limit(notifications.order_by('-created_at'), 8),
            'today': today,
        })
        return context


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
        if context['is_htmx']:
            self.template_name = self.table_template
        return context


class LeadsView(ListPageMixin):
    active_page = 'leads'
    page_title = 'Leads'
    table_template = 'portal/partials/leads_table.html'
    search_fields = ('full_name', 'phone', 'email', 'interested_country', 'interested_program', 'comment')
    status_choices = Lead.STATUS_CHOICES

    def get_queryset(self):
        return lead_queryset(self.request.user).select_related('manager', 'source')


class ClientsView(ListPageMixin):
    active_page = 'clients'
    page_title = 'Clients'
    table_template = 'portal/partials/clients_table.html'
    search_fields = ('full_name', 'phone', 'email', 'city', 'citizenship', 'comments')
    status_choices = Client.STATUS_CHOICES

    def get_queryset(self):
        return client_queryset(self.request.user).select_related('manager')


class ApplicationsView(ListPageMixin):
    active_page = 'applications'
    page_title = 'Applications'
    table_template = 'portal/partials/applications_table.html'
    search_fields = ('client__full_name', 'university_name', 'program_name', 'country', 'comment')
    status_choices = Application.STATUS_CHOICES

    def get_queryset(self):
        return application_queryset(self.request.user).select_related('client', 'manager')


class TasksView(ListPageMixin):
    active_page = 'tasks'
    page_title = 'Tasks'
    table_template = 'portal/partials/tasks_table.html'
    search_fields = ('title', 'description', 'project__title', 'assigned_to__email')
    status_choices = ProjectTask.STATUS_CHOICES
    default_ordering = 'deadline'

    def get_queryset(self):
        return task_queryset(self.request.user)


class ProjectsView(ListPageMixin):
    active_page = 'projects'
    page_title = 'Projects'
    table_template = 'portal/partials/projects_table.html'
    search_fields = ('title', 'code', 'description', 'owner__email')
    status_choices = Project.STATUS_CHOICES
    default_ordering = '-updated_at'

    def get_queryset(self):
        return project_queryset(self.request.user)


class FinanceView(PortalContextMixin, TemplateView):
    template_name = 'portal/finance.html'
    active_page = 'finance'
    page_title = 'Finance'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        payments = payment_queryset(user)
        deals = deal_queryset(user)
        expenses = expense_queryset(user)
        current_month = timezone.localdate().replace(day=1)
        context.update({
            'payment_total_usd': payments.filter(is_confirmed=True, payment_date__gte=current_month).aggregate(total=Sum('amount_usd'))['total'] or 0,
            'expense_total_usd': expenses.filter(is_confirmed=True, date__gte=current_month).aggregate(total=Sum('amount_usd'))['total'] or 0,
            'open_deals_count': deals.exclude(payment_status__in=[Deal.PAYMENT_STATUS_FULL, Deal.PAYMENT_STATUS_CANCELLED, Deal.PAYMENT_STATUS_REFUNDED]).count(),
            'recent_payments': limit(payments.order_by('-payment_date', '-created_at')),
            'recent_deals': limit(deals.order_by('-created_at')),
            'recent_expenses': limit(expenses.order_by('-date', '-created_at')),
        })
        return context


class DocumentsView(ListPageMixin):
    active_page = 'documents'
    page_title = 'Documents'
    table_template = 'portal/partials/documents_table.html'
    search_fields = ('title', 'template__name', 'client__full_name', 'deal__title')
    status_choices = GeneratedDocument.STATUS_CHOICES

    def get_queryset(self):
        return document_queryset(self.request.user)


class KnowledgeView(ListPageMixin):
    active_page = 'knowledge'
    page_title = 'Knowledge'
    table_template = 'portal/partials/knowledge_table.html'
    search_fields = ('title', 'summary', 'content', 'category__name')
    status_choices = KnowledgeArticle.STATUS_CHOICES

    def get_queryset(self):
        return knowledge_queryset(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['attempts'] = KnowledgeTestAttempt.objects.filter(user=self.request.user).select_related('test').order_by('-created_at')[:8]
        return context


class WorkdayView(PortalContextMixin, TemplateView):
    template_name = 'portal/workday.html'
    active_page = 'workday'
    page_title = 'Workday'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'workday': get_today_workday(self.request.user),
            'reports': DailyReport.objects.filter(employee=self.request.user).select_related('workday').order_by('-date')[:10],
            'history': workday_queryset(self.request.user).order_by('-date')[:10],
        })
        return context


class WorkdayActionMixin(LoginRequiredMixin, View):
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


class ReportsView(PortalContextMixin, TemplateView):
    template_name = 'portal/reports.html'
    active_page = 'reports'
    page_title = 'Reports'

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
