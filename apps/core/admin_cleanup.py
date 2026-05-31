from types import MethodType

from django.apps import apps as django_apps


LEGACY_ADMIN_APP_LABELS = {
    'analytics',
    'catalog',
    'clients',
    'documents',
    'gamification',
    'leads',
    'mailing',
    'notifications',
    'reports',
    'services',
    'support',
    'tasks',
    'timetracking',
    'token_blacklist',
}

LEGACY_ARCHIVE_MODELS = {
    ('users', 'Office'),
}

APP_VERBOSE_NAMES = {
    'admin': 'Администрирование',
    'auth': 'Права доступа',
    'core': 'Настройки',
    'organizations': 'Организация',
    'users': 'Пользователи',
    'employees': 'Сотрудники',
    'crm': 'CRM',
    'education': 'ВУЗы и программы',
    'erp_services': 'Услуги',
    'finance': 'Финансы',
    'erp_documents': 'Документы',
    'attendance': 'Рабочий день',
    'projects_v2': 'Проекты и задачи',
    'knowledge': 'База знаний',
    'erp_notifications': 'Уведомления',
    'customfields': 'Настройки',
    'portal': 'Календарь',
    'client_api': 'API клиентского приложения',
}

LEGACY_APP_VERBOSE_NAME = 'Архив / Старые данные'

APP_ORDER = {
    'organizations': 10,
    'users': 20,
    'employees': 21,
    'crm': 30,
    'education': 40,
    'erp_services': 50,
    'finance': 60,
    'erp_documents': 70,
    'attendance': 80,
    'projects_v2': 90,
    'knowledge': 100,
    'portal': 110,
    'erp_notifications': 120,
    'customfields': 130,
    'auth': 900,
    'legacy_archive': 1000,
}

MODEL_ORDER = {
    ('organizations', 'Company'): 10,
    ('organizations', 'Office'): 20,
    ('organizations', 'Department'): 30,
    ('organizations', 'Position'): 40,
    ('users', 'User'): 10,
    ('employees', 'EmployeeProfile'): 20,
    ('employees', 'EmployeeRole'): 30,
    ('employees', 'EmployeeAccess'): 40,
    ('employees', 'EmployeeRating'): 50,
    ('crm', 'Lead'): 10,
    ('crm', 'LeadSource'): 20,
    ('crm', 'Client'): 30,
    ('crm', 'Application'): 40,
    ('crm', 'ClientActivity'): 50,
    ('crm', 'ClientNote'): 60,
    ('crm', 'ClientFile'): 70,
    ('education', 'Country'): 10,
    ('education', 'City'): 20,
    ('education', 'Currency'): 30,
    ('education', 'University'): 40,
    ('education', 'Program'): 50,
    ('education', 'ProgramFee'): 60,
    ('education', 'Intake'): 70,
    ('education', 'RequiredDocument'): 80,
    ('education', 'UniversityContact'): 90,
    ('erp_services', 'ServiceCategory'): 10,
    ('erp_services', 'Service'): 20,
    ('erp_services', 'ServicePrice'): 30,
    ('finance', 'Cashbox'): 10,
    ('finance', 'Deal'): 20,
    ('finance', 'Income'): 30,
    ('finance', 'Expense'): 40,
    ('finance', 'Payment'): 50,
    ('finance', 'Transaction'): 60,
    ('finance', 'EmployeeCommission'): 70,
    ('finance', 'FinancialPeriod'): 80,
    ('finance', 'ExpenseCategory'): 90,
    ('erp_documents', 'DocumentTemplate'): 10,
    ('erp_documents', 'DocumentTemplateField'): 20,
    ('erp_documents', 'GeneratedDocument'): 30,
    ('erp_documents', 'DocumentApproval'): 40,
    ('erp_documents', 'StampRule'): 50,
    ('erp_documents', 'DocumentDownloadLog'): 60,
    ('attendance', 'WorkDay'): 10,
    ('attendance', 'WorkSession'): 20,
    ('attendance', 'DailyReport'): 30,
    ('attendance', 'AttendanceReminder'): 40,
    ('attendance', 'AutoCloseLog'): 50,
    ('projects_v2', 'Project'): 10,
    ('projects_v2', 'ProjectSection'): 20,
    ('projects_v2', 'ProjectTask'): 30,
    ('projects_v2', 'TaskComment'): 40,
    ('projects_v2', 'TaskChecklist'): 50,
    ('projects_v2', 'TaskChecklistItem'): 60,
    ('projects_v2', 'TaskAttachment'): 70,
    ('projects_v2', 'ProjectNote'): 80,
    ('projects_v2', 'TaskWatcher'): 90,
    ('knowledge', 'KnowledgeCategory'): 10,
    ('knowledge', 'KnowledgeArticle'): 20,
    ('knowledge', 'KnowledgeAttachment'): 30,
    ('knowledge', 'KnowledgeTest'): 40,
    ('knowledge', 'KnowledgeQuestion'): 50,
    ('knowledge', 'KnowledgeTestAttempt'): 60,
    ('knowledge', 'ArticleReadLog'): 70,
    ('erp_notifications', 'Notification'): 10,
    ('erp_notifications', 'NotificationTemplate'): 20,
    ('erp_notifications', 'NotificationLog'): 30,
    ('erp_notifications', 'DeviceToken'): 40,
    ('customfields', 'CustomTable'): 10,
    ('customfields', 'CustomField'): 20,
    ('customfields', 'CustomFieldOption'): 30,
    ('customfields', 'CustomRecord'): 40,
    ('customfields', 'CustomFieldValue'): 50,
    ('portal', 'CalendarEvent'): 10,
}

MODEL_VERBOSE_NAMES = {
    ('users', 'User'): ('Пользователь', 'Пользователи'),
    ('users', 'Office'): ('Архивный офис', 'Архивные офисы'),
    ('organizations', 'Company'): ('Компания', 'Компании'),
    ('organizations', 'Office'): ('Офис', 'Офисы'),
    ('organizations', 'Department'): ('Отдел', 'Отделы'),
    ('organizations', 'Position'): ('Должность', 'Должности'),
    ('employees', 'EmployeeRole'): ('Роль сотрудника', 'Роли сотрудников'),
    ('employees', 'EmployeeProfile'): ('Профиль сотрудника', 'Профили сотрудников'),
    ('employees', 'EmployeeAccess'): ('Доступ сотрудника', 'Доступы сотрудников'),
    ('employees', 'EmployeeRating'): ('Рейтинг сотрудника', 'Рейтинг сотрудников'),
    ('crm', 'LeadSource'): ('Источник лида', 'Источники лидов'),
    ('crm', 'Lead'): ('Лид', 'Лиды'),
    ('crm', 'Client'): ('Клиент', 'Клиенты'),
    ('crm', 'Application'): ('Заявка', 'Заявки'),
    ('crm', 'ClientActivity'): ('Активность клиента', 'Активности клиентов'),
    ('crm', 'ClientNote'): ('Заметка клиента', 'Заметки клиентов'),
    ('crm', 'ClientFile'): ('Файл клиента', 'Файлы клиентов'),
    ('education', 'Country'): ('Страна', 'Страны'),
    ('education', 'City'): ('Город', 'Города'),
    ('education', 'Currency'): ('Валюта', 'Валюты'),
    ('education', 'University'): ('ВУЗ', 'ВУЗы'),
    ('education', 'Program'): ('Программа', 'Программы'),
    ('education', 'ProgramFee'): ('Стоимость программы', 'Стоимость программ'),
    ('education', 'Intake'): ('Набор / intake', 'Наборы / intakes'),
    ('education', 'RequiredDocument'): ('Требуемый документ', 'Требуемые документы'),
    ('education', 'UniversityContact'): ('Контакт ВУЗа', 'Контакты ВУЗов'),
    ('erp_services', 'ServiceCategory'): ('Категория услуги', 'Категории услуг'),
    ('erp_services', 'Service'): ('Услуга', 'Услуги'),
    ('erp_services', 'ServicePrice'): ('Цена услуги', 'Цены услуг'),
    ('finance', 'Cashbox'): ('Касса', 'Кассы'),
    ('finance', 'Deal'): ('Сделка', 'Сделки'),
    ('finance', 'Payment'): ('Платёж', 'Платежи'),
    ('finance', 'ExpenseCategory'): ('Категория расхода', 'Категории расходов'),
    ('finance', 'Expense'): ('Расход', 'Расходы'),
    ('finance', 'Income'): ('Доход', 'Доходы'),
    ('finance', 'Transaction'): ('Транзакция', 'Транзакции'),
    ('finance', 'EmployeeCommission'): ('Комиссия сотрудника', 'Комиссии сотрудников'),
    ('finance', 'FinancialPeriod'): ('Финансовый период', 'Финансовые периоды'),
    ('erp_documents', 'DocumentTemplate'): ('Шаблон документа', 'Шаблоны документов'),
    ('erp_documents', 'DocumentTemplateField'): ('Поле шаблона', 'Поля шаблонов'),
    ('erp_documents', 'GeneratedDocument'): ('Сгенерированный документ', 'Сгенерированные документы'),
    ('erp_documents', 'DocumentApproval'): ('Подтверждение документа', 'Подтверждения документов'),
    ('erp_documents', 'StampRule'): ('Правило печати', 'Правила печати'),
    ('erp_documents', 'DocumentDownloadLog'): ('Лог скачивания', 'Логи скачиваний'),
    ('attendance', 'WorkDay'): ('Рабочий день', 'Рабочие дни'),
    ('attendance', 'WorkSession'): ('Рабочая сессия', 'Рабочие сессии'),
    ('attendance', 'DailyReport'): ('Ежедневный отчёт', 'Ежедневные отчёты'),
    ('attendance', 'AttendanceReminder'): ('Напоминание', 'Напоминания'),
    ('attendance', 'AutoCloseLog'): ('Лог автозакрытия', 'Логи автозакрытия'),
    ('projects_v2', 'Project'): ('Проект', 'Проекты'),
    ('projects_v2', 'ProjectSection'): ('Раздел проекта', 'Разделы проектов'),
    ('projects_v2', 'ProjectTask'): ('Задача', 'Задачи'),
    ('projects_v2', 'TaskComment'): ('Комментарий задачи', 'Комментарии задач'),
    ('projects_v2', 'TaskChecklist'): ('Чек-лист', 'Чек-листы'),
    ('projects_v2', 'TaskChecklistItem'): ('Пункт чек-листа', 'Пункты чек-листов'),
    ('projects_v2', 'TaskAttachment'): ('Файл задачи', 'Файлы задач'),
    ('projects_v2', 'ProjectNote'): ('Заметка проекта', 'Заметки проектов'),
    ('projects_v2', 'TaskWatcher'): ('Наблюдатель задачи', 'Наблюдатели задач'),
    ('knowledge', 'KnowledgeCategory'): ('Папка базы знаний', 'Папки базы знаний'),
    ('knowledge', 'KnowledgeArticle'): ('Статья', 'Статьи'),
    ('knowledge', 'KnowledgeAttachment'): ('Вложение', 'Вложения'),
    ('knowledge', 'KnowledgeTest'): ('Тест', 'Тесты'),
    ('knowledge', 'KnowledgeQuestion'): ('Вопрос теста', 'Вопросы тестов'),
    ('knowledge', 'KnowledgeTestAttempt'): ('Попытка теста', 'Попытки тестов'),
    ('knowledge', 'ArticleReadLog'): ('Прочтение статьи', 'Прочтения статей'),
    ('erp_notifications', 'DeviceToken'): ('Device token', 'Device tokens'),
    ('erp_notifications', 'Notification'): ('Уведомление', 'Уведомления'),
    ('erp_notifications', 'NotificationTemplate'): ('Шаблон уведомления', 'Шаблоны уведомлений'),
    ('erp_notifications', 'NotificationLog'): ('Лог уведомления', 'Логи уведомлений'),
    ('customfields', 'CustomTable'): ('Пользовательская таблица', 'Пользовательские таблицы'),
    ('customfields', 'CustomField'): ('Пользовательское поле', 'Пользовательские поля'),
    ('customfields', 'CustomFieldOption'): ('Вариант поля', 'Варианты полей'),
    ('customfields', 'CustomRecord'): ('Пользовательская запись', 'Пользовательские записи'),
    ('customfields', 'CustomFieldValue'): ('Значение поля', 'Значения полей'),
    ('portal', 'CalendarEvent'): ('Событие календаря', 'События календаря'),
}


def _is_legacy_model(app_label, object_name):
    return app_label in LEGACY_ADMIN_APP_LABELS or (app_label, object_name) in LEGACY_ARCHIVE_MODELS


def _configure_site_titles(admin_site):
    admin_site.site_header = 'ManagerSL — Администрирование'
    admin_site.site_title = 'ManagerSL'
    admin_site.index_title = 'Панель управления'


def _localize_app_configs():
    for app_label in LEGACY_ADMIN_APP_LABELS:
        try:
            django_apps.get_app_config(app_label).verbose_name = LEGACY_APP_VERBOSE_NAME
        except LookupError:
            continue

    for app_label, verbose_name in APP_VERBOSE_NAMES.items():
        try:
            django_apps.get_app_config(app_label).verbose_name = verbose_name
        except LookupError:
            continue


def _localize_model_meta():
    for model_key, (verbose_name, verbose_name_plural) in MODEL_VERBOSE_NAMES.items():
        try:
            model = django_apps.get_model(*model_key)
        except LookupError:
            continue
        model._meta.verbose_name = verbose_name
        model._meta.verbose_name_plural = verbose_name_plural


def _deny_legacy_admin_for_staff(model_admin):
    if getattr(model_admin, '_managers_sl_legacy_hidden', False):
        return

    permission_methods = (
        'get_model_perms',
        'has_module_permission',
        'has_view_permission',
        'has_add_permission',
        'has_change_permission',
        'has_delete_permission',
    )

    for method_name in permission_methods:
        original = getattr(model_admin, method_name)

        def guarded(self, request, *args, _original=original, _method_name=method_name, **kwargs):
            if not request.user.is_superuser:
                return {} if _method_name == 'get_model_perms' else False
            return _original(request, *args, **kwargs)

        setattr(model_admin, method_name, MethodType(guarded, model_admin))

    model_admin._managers_sl_legacy_hidden = True


def _sort_model_dicts(model_dicts):
    return sorted(
        model_dicts,
        key=lambda item: (
            MODEL_ORDER.get((item.get('app_label'), item.get('object_name')), 500),
            item.get('name', ''),
        ),
    )


def _patch_admin_app_list(admin_site):
    if getattr(admin_site, '_managers_sl_app_list_patched', False):
        return

    original_get_app_list = admin_site.get_app_list

    def get_app_list(self, request, app_label=None, _original=original_get_app_list):
        app_list = _original(request, app_label)
        visible_apps = []
        archived_models = []

        for app in app_list:
            current_app_label = app.get('app_label')
            kept_models = []

            for model_info in app.get('models', []):
                model_app_label = model_info.get('app_label') or current_app_label
                object_name = model_info.get('object_name')

                if _is_legacy_model(model_app_label, object_name):
                    if request.user.is_superuser:
                        archived = dict(model_info)
                        archived['app_label'] = model_app_label
                        archived['name'] = f'{APP_VERBOSE_NAMES.get(model_app_label, model_app_label)}: {model_info.get("name")}'
                        archived_models.append(archived)
                    continue

                model_info['app_label'] = model_app_label
                kept_models.append(model_info)

            if not kept_models:
                continue

            normalized = dict(app)
            normalized['name'] = APP_VERBOSE_NAMES.get(current_app_label, app.get('name', current_app_label))
            normalized['models'] = _sort_model_dicts(kept_models)
            visible_apps.append(normalized)

        if request.user.is_superuser and archived_models:
            visible_apps.append(
                {
                    'name': LEGACY_APP_VERBOSE_NAME,
                    'app_label': 'legacy_archive',
                    'app_url': '',
                    'has_module_perms': True,
                    'models': _sort_model_dicts(archived_models),
                }
            )

        return sorted(
            visible_apps,
            key=lambda item: (
                APP_ORDER.get(item.get('app_label'), 500),
                item.get('name', ''),
            ),
        )

    admin_site.get_app_list = MethodType(get_app_list, admin_site)
    admin_site._managers_sl_app_list_patched = True


def apply_admin_cleanup():
    """Keep legacy apps installed but remove their clutter from the working admin."""
    try:
        from django.contrib import admin
    except Exception:
        return

    _configure_site_titles(admin.site)
    _localize_app_configs()
    _localize_model_meta()

    for model, model_admin in list(admin.site._registry.items()):
        if _is_legacy_model(model._meta.app_label, model.__name__):
            _deny_legacy_admin_for_staff(model_admin)

    _patch_admin_app_list(admin.site)
