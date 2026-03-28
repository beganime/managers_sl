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

CSRF_TRUSTED_ORIGINS = [
    'https://manager-sl.ru',
    'https://www.manager-sl.ru',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'http://localhost:8081',
    'http://127.0.0.1:8081',
    'http://localhost:19006',
    'http://127.0.0.1:19006',
]

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', not DEBUG)
SESSION_COOKIE_SECURE = env_bool('SESSION_COOKIE_SECURE', not DEBUG)
CSRF_COOKIE_SECURE = env_bool('CSRF_COOKIE_SECURE', not DEBUG)
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
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME', 'managers_sl'),
            'USER': os.environ.get('DB_USER', 'postgres'),
            'PASSWORD': os.environ.get('DB_PASSWORD', 'postgres'),
            'HOST': os.environ.get('DB_HOST', 'db'),
            'PORT': os.environ.get('DB_PORT', '5432'),
            'CONN_MAX_AGE': int(os.environ.get('DB_CONN_MAX_AGE', '60')),
            'OPTIONS': {
                'connect_timeout': int(os.environ.get('DB_CONNECT_TIMEOUT', '10')),
            },
        }
    }

AUTH_USER_MODEL = 'users.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LEADS_API_KEY = os.environ.get('LEADS_API_KEY', 'super_secret_key_manager_sl_2026')

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 50,
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

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'managers-sl-cache',
    }
}

PWA_APP_NAME = 'Managers SL'
PWA_APP_DESCRIPTION = 'Students Life ERP System'
PWA_APP_THEME_COLOR = '#D50000'
PWA_APP_BACKGROUND_COLOR = '#ffffff'
PWA_APP_DISPLAY = 'standalone'
PWA_APP_SCOPE = '/'
PWA_APP_ORIENTATION = 'any'
PWA_APP_START_URL = '/admin/'
PWA_APP_STATUS_BAR_COLOR = 'default'
PWA_APP_ICONS = [
    {'src': '/static/logo.ico', 'sizes': '160x160', 'type': 'image/png'},
    {'src': '/static/logo.ico', 'sizes': '512x512', 'type': 'image/png'},
]
PWA_APP_ICONS_APPLE = [
    {'src': '/static/logo.ico', 'sizes': '160x160', 'type': 'image/png'},
]
PWA_APP_SPLASH_SCREEN = [
    {'src': '/static/logo.ico', 'media': '(device-width: 320px) and (device-height: 568px)'}
]
PWA_APP_DIR = 'ltr'
PWA_APP_LANG = 'ru-ru'

UNFOLD = {
    "SITE_TITLE": "Managers SL",
    "SITE_HEADER": "Students Life ERP",
    "SITE_URL": "/admin/",
    "SITE_ICON": lambda request: static("logo.ico"),
    "DASHBOARD_CALLBACK": "students_life.dashboard.dashboard_callback",
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": "students_life.dashboard.get_navigation",
    },
    "COLORS": {
        "primary": {
            "50": "255 235 238", "100": "255 205 210", "200": "239 154 154",
            "300": "229 115 115", "400": "239 83 80", "500": "244 67 54",
            "600": "229 57 53", "700": "211 47 47", "800": "198 40 40", "900": "183 28 28",
        },
        "secondary": {
            "50": "248 250 252", "100": "241 245 249", "200": "226 232 240",
            "300": "203 213 225", "400": "148 163 184", "500": "100 116 139",
            "600": "71 85 105", "700": "51 65 85", "800": "30 41 59", "900": "15 23 42",
        },
        "success": {
            "50": "240 253 244", "100": "220 252 231", "200": "187 247 208",
            "300": "134 239 172", "400": "74 222 128", "500": "34 197 94",
            "600": "22 163 74", "700": "21 128 61", "800": "22 101 52", "900": "20 83 45",
        },
        "warning": {
            "50": "255 251 235", "100": "254 243 199", "200": "253 230 138",
            "300": "252 211 77", "400": "251 191 36", "500": "245 158 11",
            "600": "217 119 6", "700": "180 83 9", "800": "146 64 14", "900": "120 53 15",
        },
        "danger": {
            "50": "254 242 242", "100": "254 226 226", "200": "254 202 202",
            "300": "252 165 165", "400": "248 113 113", "500": "239 68 68",
            "600": "220 38 38", "700": "185 28 28", "800": "153 27 27", "900": "127 29 29",
        },
        "info": {
            "50": "239 246 255", "100": "219 234 254", "200": "191 219 254",
            "300": "147 197 253", "400": "96 165 250", "500": "59 130 246",
            "600": "37 99 235", "700": "29 78 216", "800": "30 64 175", "900": "30 58 138",
        },
        "default": {
            "50": "248 250 252", "100": "241 245 249", "200": "226 232 240",
            "300": "203 213 225", "400": "148 163 184", "500": "100 116 139",
            "600": "71 85 105", "700": "51 65 85", "800": "30 41 59", "900": "15 23 42",
        },
    },
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        },
        'simple': {
            'format': '%(levelname)s %(name)s: %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose' if not DEBUG else 'simple',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': os.environ.get('LOG_LEVEL', 'INFO'),
    },
}