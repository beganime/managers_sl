import os
from pathlib import Path
from django.templatetags.static import static

# --- BASE DIR ---
BASE_DIR = Path(__file__).resolve().parent.parent

# --- SECURITY ---
SECRET_KEY = 'django-insecure-!rqdvi^b78eoq6ya$ltzt0a5ohyiz5n*az!cdoc5wcnmv3s621'
DEBUG = False
ALLOWED_HOSTS = ['91.229.10.83', 'manager-sl.ru', 'www.manager-sl.ru', 'localhost']

# --- APPS ---
INSTALLED_APPS = [
    # 1. UI & PWA
    'unfold',
    'unfold.contrib.filters',
    'unfold.contrib.forms',
    'unfold.contrib.import_export',
    'pwa', # <--- APK Генератор

    # 2. Django
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',

    # 3. Utils
    'django_cleanup',
    'import_export',
    'smart_selects',
    'corsheaders',      
    'rest_framework',   

    # 4. My Apps
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
]

CORS_ALLOW_ALL_ORIGINS = True

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

# --- TEMPLATES ---
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

# --- DATABASE ---
# Проверяем, есть ли переменная окружения DB_NAME (она будет только на сервере)
if os.environ.get('DB_NAME'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME'),
            'USER': os.environ.get('DB_USER'),
            'PASSWORD': os.environ.get('DB_PASSWORD'),
            'HOST': os.environ.get('DB_HOST'),
            'PORT': os.environ.get('DB_PORT')
        }
    }
else:
    # Локальная разработка
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# --- AUTH ---
AUTH_USER_MODEL = 'users.User'

LEADS_API_KEY = "super_secret_key_manager_sl_2026"

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- INTERNATIONALIZATION ---
LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Asia/Ashgabat'
USE_I18N = True
USE_TZ = True

# --- STATIC & MEDIA ---
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- PWA SETTINGS (Для APK) ---
PWA_APP_NAME = 'Managers SL'
PWA_APP_DESCRIPTION = "Students Life ERP System"
PWA_APP_THEME_COLOR = '#D50000' # Алый
PWA_APP_BACKGROUND_COLOR = '#ffffff'
PWA_APP_DISPLAY = 'standalone'
PWA_APP_SCOPE = '/'
PWA_APP_ORIENTATION = 'any'
PWA_APP_START_URL = '/admin/'
PWA_APP_STATUS_BAR_COLOR = 'default'
PWA_APP_ICONS = [
    {
        'src': '/static/logo.ico', # Убедись, что логотип есть
        'sizes': '160x160',
        'type': 'image/png' # Или image/x-icon
    },
    {
        'src': '/static/logo.ico',
        'sizes': '512x512',
        'type': 'image/png'
    }
]
PWA_APP_ICONS_APPLE = [
    {
        'src': '/static/logo.ico',
        'sizes': '160x160',
        'type': 'image/png'
    }
]
PWA_APP_SPLASH_SCREEN = [
    {
        'src': '/static/logo.ico',
        'media': '(device-width: 320px) and (device-height: 568px) and (-webkit-device-pixel-ratio: 2)'
    }
]
PWA_APP_DIR = 'ltr'
PWA_APP_LANG = 'ru-ru'


CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'erp-snowflake',
    }
}

# --- UNFOLD SETTINGS ---
from django.templatetags.static import static

# settings.py

UNFOLD = {
    "SITE_TITLE": "Managers SL",
    "SITE_HEADER": "Students Life ERP",
    "SITE_URL": "/admin/",
    "SITE_ICON": lambda request: static("logo.ico"),
    "DASHBOARD_CALLBACK": "students_life.dashboard.dashboard_callback",
    
    # ЦВЕТА (Полная палитра)
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

    "SIDEBAR": {
        "show_search": True,
        # ОТКЛЮЧАЕМ стандартное нижнее меню приложений
        "show_all_applications": False, 
        # ПОДКЛЮЧАЕМ нашу новую функцию
        "navigation": "students_life.dashboard.get_navigation",
    },
}