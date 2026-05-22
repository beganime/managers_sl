from django.urls import path

from .views import (
    ApplicationsView,
    ClientsView,
    DashboardView,
    DocumentsView,
    FinanceView,
    KnowledgeView,
    LeadsView,
    PortalIndexView,
    ProjectsView,
    ReportsView,
    TasksView,
    WorkdayCloseView,
    WorkdayReportView,
    WorkdayStartView,
    WorkdayView,
)

app_name = 'portal'

urlpatterns = [
    path('', PortalIndexView.as_view(), name='index'),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('leads/', LeadsView.as_view(), name='leads'),
    path('clients/', ClientsView.as_view(), name='clients'),
    path('applications/', ApplicationsView.as_view(), name='applications'),
    path('tasks/', TasksView.as_view(), name='tasks'),
    path('projects/', ProjectsView.as_view(), name='projects'),
    path('finance/', FinanceView.as_view(), name='finance'),
    path('documents/', DocumentsView.as_view(), name='documents'),
    path('knowledge/', KnowledgeView.as_view(), name='knowledge'),
    path('workday/', WorkdayView.as_view(), name='workday'),
    path('workday/start/', WorkdayStartView.as_view(), name='workday_start'),
    path('workday/report/', WorkdayReportView.as_view(), name='workday_report'),
    path('workday/close/', WorkdayCloseView.as_view(), name='workday_close'),
    path('reports/', ReportsView.as_view(), name='reports'),
]
