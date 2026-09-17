"""Isolated synthetic tests only; deliberately never imports production settings/.env."""
SECRET_KEY = 'synthetic-identity-tests-not-a-deployment-key'
INSTALLED_APPS = [
    'django.contrib.auth', 'django.contrib.contenttypes', 'rest_framework',
    'identity_test_settings.IsolatedCoreConfig', 'apps.organizations', 'apps.employees', 'apps.education',
    'apps.crm', 'apps.client_onboarding',
]
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
USE_TZ = True
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
ROOT_URLCONF = 'identity_test_urls'
REST_FRAMEWORK = {'DEFAULT_AUTHENTICATION_CLASSES': [], 'DEFAULT_PERMISSION_CLASSES': []}

from django.apps import AppConfig


class IsolatedCoreConfig(AppConfig):
    name = 'apps.core'
    default_auto_field = 'django.db.models.BigAutoField'
