import os

try:
    from .celery import app as celery_app
except ModuleNotFoundError as exc:
    if exc.name != 'celery':
        raise
    celery_app = None
except OSError:
    if os.environ.get('CELERY_STRICT_IMPORT') == '1':
        raise
    celery_app = None

__all__ = ('celery_app',)
