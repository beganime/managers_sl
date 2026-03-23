#!/bin/bash
set -e

echo "⏳ Применяем миграции..."
python manage.py migrate --noinput

echo "📦 Собираем статику..."
python manage.py collectstatic --noinput --clear

echo "🚀 Запускаем Gunicorn..."
exec gunicorn students_life.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --worker-class sync \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -