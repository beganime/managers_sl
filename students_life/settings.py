# students_life/settings.py
import os
from pathlib import Path
from datetime import timedelta

from corsheaders.defaults import default_headers
from django.templatetags.static import static


BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ('1', 'true', 'yes', 'on')


def env_list(name: str, default: str = '') -> list[str]:
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(',') if item.strip()]


DEBUG = env_bool('DEBUG', False)
SECRET_KEY = os.environ.get('SECRET_KEY', 'change-me-in-production-only-for-local-dev')

if not DEBUG and SECRET_KEY == 'change-me-in-production-only-for-local-dev':
    raise RuntimeError('SECRET_KEY must be set in production.')

ALLOWED_HOSTS = env_list(
    'ALLOWED_HOSTS',
    '127.0.0.1,localhost,manager-sl.ru,www.manager-sl.ru,91.229.10.83'
)

CORS_ALLOW_CREDENTIALS = True

from corsheaders.defaults import default_headers, default_methods

CORS_ALLOW_ALL_ORIGINS = env_bool('CORS_ALLOW_ALL_ORIGINS', False)

CORS_ALLOWED_ORIGINS = [
    'https://manager-sl.ru',
    'https://www.manager-sl.ru',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'http://localhost:8081',
    'http://127.0.0.1:8081',
    'http://localhost:19006',
    'http://127.0.0.1:19006',
]
DOCUMENT_WATERMARK_IMAGE = "/app/branding/watermark.png"

CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https?://localhost(:\d+)?$",
    r"^https?://127\.0\.0\.1(:\d+)?$",
]

CORS_ALLOW_HEADERS = list(default_headers) + [
    'authorization',
    'content-type',
    'accept',
    'origin',
    'x-requested-with',
]
CORS_ALLOW_METHODS = list(default_methods)

DEFAULT_CSRF_TRUSTED_ORIGINS = [
    'https://manager-sl.ru',
    'https://www.manager-sl.ru',
    'http://manager-sl.ru',
    'http://www.manager-sl.ru',
    'https://91.229.10.83',
    'http://91.229.10.83',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'http://localhost:8081',
    'http://127.0.0.1:8081',
    'http://localhost:19006',
    'http://127.0.0.1:19006',
]
CSRF_TRUSTED_ORIGINS = sorted(set(
    DEFAULT_CSRF_TRUSTED_ORIGINS + env_list('CSRF_TRUSTED_ORIGINS', '')
))
CSRF_FAILURE_VIEW = 'students_life.csrf.csrf_failure'

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', not DEBUG)
SESSION_COOKIE_SECURE = env_bool('SESSION_COOKIE_SECURE', not DEBUG)
CSRF_COOKIE_SECURE = env_bool('CSRF_COOKIE_SECURE', not DEBUG)
SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
CSRF_COOKIE_SAMESITE = os.environ.get('CSRF_COOKIE_SAMESITE', 'Lax')
SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '31536000' if not DEBUG else '0'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', not DEBUG)
SECURE_HSTS_PRELOAD = env_bool('SECURE_HSTS_PRELOAD', not DEBUG)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'same-origin'

INSTALLED_APPS = [
    'unfold',
    'unfold.contrib.filters',
    'unfold.contrib.forms',
    'unfold.contrib.import_export',
    'pwa',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'django_cleanup',
    'import_export',
    'smart_selects',
    'corsheaders',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'users',
    'catalog',
    'clients',
    'services',
    'analytics',
    'gamification',
    'tasks',
    'documents',
    'leads',
    'timetracking',
    'reports',
    'mailing',
    'notifications',
    'support',
    'apps.core.apps.CoreConfig',
    'apps.organizations',
    'apps.employees',
    'apps.crm',
    'apps.education.apps.EducationConfig',
    'apps.erp_services.apps.ErpServicesConfig',
    'apps.finance.apps.FinanceConfig',
    'apps.erp_documents.apps.ErpDocumentsConfig',
    'apps.attendance.apps.AttendanceConfig',
    'apps.projects_v2.apps.ProjectsV2Config',
    'apps.knowledge.apps.KnowledgeConfig',
    'apps.customfields.apps.CustomFieldsConfig',
    'apps.erp_notifications.apps.ErpNotificationsConfig',
    'apps.portal.apps.PortalConfig',
    'apps.client_api.apps.ClientApiConfig',
    'apps.client_onboarding.apps.ClientOnboardingConfig',
    'apps.sheets_sync.apps.SheetsSyncConfig',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'students_life.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'students_life.wsgi.application'

USE_SQLITE = env_bool('USE_SQLITE', False)

if USE_SQLITE:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    database_options = {
        'connect_timeout': int(os.environ.get('DB_CONNECT_TIMEOUT', '10')),
    }
    database_sslmode = os.environ.get('DB_SSLMODE', '').strip()
    database_sslrootcert = os.environ.get('DB_SSLROOTCERT', '').strip()
    if database_sslmode:
        database_options['sslmode'] = database_sslmode
    if database_sslrootcert:
        database_options['sslrootcert'] = database_sslrootcert

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME', 'managers_sl'),
            'USER': os.environ.get('DB_USER', 'postgres'),
            'PASSWORD': os.environ.get('DB_PASSWORD', 'postgres'),
            'HOST': os.environ.get('DB_HOST', 'db'),
            'PORT': os.environ.get('DB_PORT', '5432'),
            'CONN_MAX_AGE': int(os.environ.get('DB_CONN_MAX_AGE', '60')),
            'OPTIONS': database_options,
        }
    }

AUTH_USER_MODEL = 'users.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LEADS_API_KEY = os.environ.get('LEADS_API_KEY', '')
STUDENTS_LIFE_DEFAULT_API_BASE_URL = 'https://students-life.ru/api2/api/v1/'
STUDENTS_LIFE_ORIGINAL_API_BASE_URL = 'https://stud-life.com/api/v1/'
STUDENTS_LIFE_API_BASE_URL = os.environ.get('STUDENTS_LIFE_API_BASE_URL', STUDENTS_LIFE_DEFAULT_API_BASE_URL)
STUDENTS_LIFE_API_KEY = os.environ.get('STUDENTS_LIFE_API_KEY', LEADS_API_KEY)
STUDENTS_LIFE_PROVISION_API_URL = os.environ.get(
    'STUDENTS_LIFE_PROVISION_API_URL',
    '',
)
STUDENTS_LIFE_PROVISION_TOKEN = os.environ.get('STUDENTS_LIFE_PROVISION_TOKEN', '')
SMTP_SL_API_BASE_URL = os.environ.get('SMTP_SL_API_BASE_URL', '').rstrip('/')
SMTP_SL_SERVICE_TOKEN = os.environ.get('SMTP_SL_SERVICE_TOKEN', '')
SERVICE_REQUEST_TIMEOUT = int(os.environ.get('SERVICE_REQUEST_TIMEOUT', '20'))
AKYLCHAT_API_BASE_URL = os.environ.get('AKYLCHAT_API_BASE_URL', '').rstrip('/')
AKYLCHAT_SERVICE_TOKEN = os.environ.get('AKYLCHAT_SERVICE_TOKEN', '')
DISK_AUTH_SERVICE_TOKEN = os.environ.get('DISK_AUTH_SERVICE_TOKEN', '')
DISK_WEB_URL = os.environ.get('DISK_WEB_URL', 'https://disk.manager-sl.ru/web/client/login')
DISK_PROVISION_API_URL = os.environ.get(
    'DISK_PROVISION_API_URL',
    'https://disk.manager-sl.ru/api/internal/disk/folders',
)
DISK_PROVISION_SERVICE_TOKEN = os.environ.get('DISK_PROVISION_SERVICE_TOKEN', '')

GOOGLE_SHEETS_ENABLED = env_bool('GOOGLE_SHEETS_ENABLED', False)
GOOGLE_SHEETS_SPREADSHEET_ID = os.environ.get('GOOGLE_SHEETS_SPREADSHEET_ID', '')
GOOGLE_SHEETS_CREDENTIALS_FILE = os.environ.get('GOOGLE_SHEETS_CREDENTIALS_FILE', '')
GOOGLE_SHEETS_GENERAL_SHEET = os.environ.get('GOOGLE_SHEETS_GENERAL_SHEET', 'Общее')
GOOGLE_SHEETS_ONBOARDING_SHEET = os.environ.get(
    'GOOGLE_SHEETS_ONBOARDING_SHEET',
    'Заявки из анкеты',
)
GOOGLE_SHEETS_FINANCE_SHEET = os.environ.get('GOOGLE_SHEETS_FINANCE_SHEET', 'Финансы')
GOOGLE_SHEETS_REFERENCE_SHEET = os.environ.get('GOOGLE_SHEETS_REFERENCE_SHEET', 'Справочники')
GOOGLE_SHEETS_EXAMS_SHEET = os.environ.get('GOOGLE_SHEETS_EXAMS_SHEET', 'Экзамены')

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated',),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 50,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '30/min',
        'user': '60/min',
        'leads_create': '3/min',
    }
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.yandex.ru')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '465'))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_SSL = env_bool('EMAIL_USE_SSL', True)
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', False)
EMAIL_TIMEOUT = int(os.environ.get('EMAIL_TIMEOUT', '20'))
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER)
SERVER_EMAIL = EMAIL_HOST_USER

USE_X_FORWARDED_HOST = True

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = os.environ.get('TIME_ZONE', 'Asia/Ashgabat')
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/1')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = USE_TZ
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = int(os.environ.get('CELERY_TASK_TIME_LIMIT', '1800'))
CELERY_TASK_SOFT_TIME_LIMIT = int(os.environ.get('CELERY_TASK_SOFT_TIME_LIMIT', '1500'))
CELERY_TASK_ALWAYS_EAGER = env_bool('CELERY_TASK_ALWAYS_EAGER', False)

ATTENDANCE_AUTO_CLOSE_HOUR = int(os.environ.get('ATTENDANCE_AUTO_CLOSE_HOUR', '23'))
ATTENDANCE_AUTO_CLOSE_MINUTE = int(os.environ.get('ATTENDANCE_AUTO_CLOSE_MINUTE', '0'))
TASK_REMINDER_HOURS_AHEAD = int(os.environ.get('TASK_REMINDER_HOURS_AHEAD', '24'))

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'managers-sl-cache',
    }
}

UNFOLD = {
    'SITE_TITLE': 'ManagerSL',
    'SITE_HEADER': 'ManagerSL — Администрирование',
    'SITE_SUBHEADER': 'ERP / CRM / HRM',
    'SITE_URL': '/portal/dashboard/',
    'SHOW_HISTORY': True,
    'SHOW_VIEW_ON_SITE': True,
    'SIDEBAR': {
        'show_search': True,
        'command_search': True,
        'show_all_applications': False,
        'navigation': [
            {
                'title': 'Организация',
                'separator': True,
                'items': [
                    {'title': 'Компании', 'icon': 'business', 'link': '/admin/organizations/company/'},
                    {'title': 'Офисы', 'icon': 'location_city', 'link': '/admin/organizations/office/'},
                    {'title': 'Отделы', 'icon': 'account_tree', 'link': '/admin/organizations/department/'},
                    {'title': 'Должности', 'icon': 'badge', 'link': '/admin/organizations/position/'},
                ],
            },
            {
                'title': 'Сотрудники',
                'separator': True,
                'items': [
                    {'title': 'Пользователи', 'icon': 'person', 'link': '/admin/users/user/'},
                    {'title': 'Профили сотрудников', 'icon': 'groups', 'link': '/admin/employees/employeeprofile/'},
                    {'title': 'Роли сотрудников', 'icon': 'admin_panel_settings', 'link': '/admin/employees/employeerole/'},
                    {'title': 'Доступы сотрудников', 'icon': 'lock_open', 'link': '/admin/employees/employeeaccess/'},
                    {'title': 'Рейтинг сотрудников', 'icon': 'leaderboard', 'link': '/admin/employees/employeerating/'},
                ],
            },
            {
                'title': 'CRM',
                'separator': True,
                'items': [
                    {'title': 'Потенциальные клиенты и лиды', 'icon': 'person_add', 'link': '/admin/crm/lead/'},
                    {'title': 'Источники лидов', 'icon': 'campaign', 'link': '/admin/crm/leadsource/'},
                    {'title': 'Клиенты', 'icon': 'contacts', 'link': '/admin/crm/client/'},
                    {'title': 'Заявки', 'icon': 'assignment', 'link': '/admin/crm/application/'},
                    {'title': 'Активности', 'icon': 'timeline', 'link': '/admin/crm/clientactivity/'},
                    {'title': 'Заметки', 'icon': 'sticky_note_2', 'link': '/admin/crm/clientnote/'},
                    {'title': 'Файлы клиентов', 'icon': 'folder', 'link': '/admin/crm/clientfile/'},
                ],
            },
            {
                'title': 'ВУЗы и услуги',
                'separator': True,
                'items': [
                    {'title': 'Страны', 'icon': 'public', 'link': '/admin/education/country/'},
                    {'title': 'Города', 'icon': 'location_on', 'link': '/admin/education/city/'},
                    {'title': 'Валюты', 'icon': 'attach_money', 'link': '/admin/education/currency/'},
                    {'title': 'ВУЗы', 'icon': 'school', 'link': '/admin/education/university/'},
                    {'title': 'Программы', 'icon': 'menu_book', 'link': '/admin/education/program/'},
                    {'title': 'Наборы / intakes', 'icon': 'event_available', 'link': '/admin/education/intake/'},
                    {'title': 'Требуемые документы', 'icon': 'description', 'link': '/admin/education/requireddocument/'},
                    {'title': 'Категории услуг', 'icon': 'category', 'link': '/admin/erp_services/servicecategory/'},
                    {'title': 'Услуги', 'icon': 'handshake', 'link': '/admin/erp_services/service/'},
                    {'title': 'Цены услуг', 'icon': 'price_change', 'link': '/admin/erp_services/serviceprice/'},
                ],
            },
            {
                'title': 'Финансы и документы',
                'separator': True,
                'items': [
                    {'title': 'Кассы', 'icon': 'account_balance_wallet', 'link': '/admin/finance/cashbox/'},
                    {'title': 'Сделки', 'icon': 'request_quote', 'link': '/admin/finance/deal/'},
                    {'title': 'Доходы', 'icon': 'trending_up', 'link': '/admin/finance/income/'},
                    {'title': 'Расходы', 'icon': 'trending_down', 'link': '/admin/finance/expense/'},
                    {'title': 'Платежи', 'icon': 'credit_card', 'link': '/admin/finance/payment/'},
                    {'title': 'Транзакции', 'icon': 'receipt_long', 'link': '/admin/finance/transaction/'},
                    {'title': 'Комиссии сотрудников', 'icon': 'percent', 'link': '/admin/finance/employeecommission/'},
                    {'title': 'Шаблоны документов', 'icon': 'article', 'link': '/admin/erp_documents/documenttemplate/'},
                    {'title': 'Сгенерированные документы', 'icon': 'task', 'link': '/admin/erp_documents/generateddocument/'},
                    {'title': 'Подтверждения документов', 'icon': 'verified', 'link': '/admin/erp_documents/documentapproval/'},
                    {'title': 'Правила печати', 'icon': 'approval', 'link': '/admin/erp_documents/stamprule/'},
                ],
            },
            {
                'title': 'Операционная работа',
                'separator': True,
                'items': [
                    {'title': 'Рабочие дни', 'icon': 'schedule', 'link': '/admin/attendance/workday/'},
                    {'title': 'Ежедневные отчёты', 'icon': 'fact_check', 'link': '/admin/attendance/dailyreport/'},
                    {'title': 'Проекты', 'icon': 'view_kanban', 'link': '/admin/projects_v2/project/'},
                    {'title': 'Задачи', 'icon': 'checklist', 'link': '/admin/projects_v2/projecttask/'},
                    {'title': 'Календарь', 'icon': 'calendar_month', 'link': '/admin/portal/calendarevent/'},
                    {'title': 'База знаний', 'icon': 'library_books', 'link': '/admin/knowledge/knowledgearticle/'},
                    {'title': 'Папки базы знаний', 'icon': 'folder_open', 'link': '/admin/knowledge/knowledgecategory/'},
                    {'title': 'Уведомления', 'icon': 'notifications', 'link': '/admin/erp_notifications/notification/'},
                    {'title': 'Рассылки уведомлений', 'icon': 'send', 'link': '/admin/erp_notifications/notificationbatch/'},
                    {'title': 'Шаблоны уведомлений', 'icon': 'notification_important', 'link': '/admin/erp_notifications/notificationtemplate/'},
                ],
            },
            {
                'title': 'Настройки',
                'separator': True,
                'items': [
                    {'title': 'Пользовательские поля', 'icon': 'dynamic_form', 'link': '/admin/customfields/customfield/'},
                    {'title': 'Варианты полей', 'icon': 'list_alt', 'link': '/admin/customfields/customfieldoption/'},
                    {'title': 'Значения полей', 'icon': 'table_chart', 'link': '/admin/customfields/customfieldvalue/'},
                    {'title': 'Группы прав', 'icon': 'group_work', 'link': '/admin/auth/group/'},
                ],
            },
        ],
    },
}
