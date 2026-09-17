"""Isolated onboarding integration tests; never import production settings/.env."""
SECRET_KEY = 'synthetic-onboarding-tests-not-a-deployment-key'
DEBUG = True
ALLOWED_HOSTS = ['testserver']
INSTALLED_APPS = [
    'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
    'rest_framework', 'users', 'onboarding_test_settings.IsolatedCoreConfig', 'apps.organizations',
    'apps.employees', 'apps.education', 'apps.crm', 'apps.erp_notifications',
    'apps.client_onboarding', 'apps.sheets_sync',
]
AUTH_USER_MODEL = 'users.User'
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
ROOT_URLCONF = 'onboarding_test_urls'
USE_TZ = True
TIME_ZONE = 'Asia/Ashgabat'
STATIC_URL = '/static/'
MEDIA_ROOT = '/tmp/sl-onboarding-tests-media'
MIDDLEWARE = []
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'APP_DIRS': True,
              'OPTIONS': {'context_processors': []}}]
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
REST_FRAMEWORK = {'DEFAULT_AUTHENTICATION_CLASSES': [], 'DEFAULT_PERMISSION_CLASSES': []}
GOOGLE_SHEETS_SYNC_ENABLED = False
STUDENTS_LIFE_PROVISION_API_URL = ''
STUDENTS_LIFE_PROVISION_TOKEN = ''
TMMAIL_PROVISION_API_URL = ''
TMMAIL_PROVISION_TOKEN = ''
DISK_PROVISION_API_URL = ''
DISK_PROVISION_SERVICE_TOKEN = ''
ATTENDANCE_AUTO_CLOSE_MINUTE = 0
ATTENDANCE_AUTO_CLOSE_HOUR = 23
TASK_REMINDER_HOURS_AHEAD = 24
SERVICE_REQUEST_TIMEOUT = 1

from django.apps import AppConfig


class IsolatedCoreConfig(AppConfig):
    name = 'apps.core'
    default_auto_field = 'django.db.models.BigAutoField'
