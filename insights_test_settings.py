"""Local isolated schema tests; no production DB or delivery integrations."""
import os
ATTENDANCE_AUTO_CLOSE_MINUTE = 0
ATTENDANCE_AUTO_CLOSE_HOUR = 20
TASK_REMINDER_HOURS_AHEAD = 24
os.environ['DEBUG'] = 'true'
os.environ['USE_SQLITE'] = 'true'
from students_life.settings import *
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
CELERY_BROKER_URL = 'memory://'
CELERY_RESULT_BACKEND = 'cache+memory://'
GOOGLE_SHEETS_SYNC_ENABLED = False
class NoMigrations(dict):
    def __contains__(self, item):
        return True
    def __getitem__(self, item):
        return None
MIGRATION_MODULES = NoMigrations()
