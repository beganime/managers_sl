#!/bin/sh
set -e

echo "⏳ Waiting for PostgreSQL TCP port at ${DB_HOST}:${DB_PORT} ..."
until nc -z "${DB_HOST}" "${DB_PORT}"; do
  sleep 1
done

echo "✅ PostgreSQL TCP port is open"

# nc checks only that the TCP port is open. A remote PostgreSQL server can still
# accept the socket and then close it while it is starting/restarting.
# Run a real Django DB check before migrations and retry migrations too.
echo "⏳ Waiting for Django database connection..."
DB_READY_ATTEMPTS=${DB_READY_ATTEMPTS:-30}
DB_READY_SLEEP=${DB_READY_SLEEP:-3}
DB_READY_COUNT=1

until python manage.py check --database default >/dev/null 2>&1; do
  if [ "$DB_READY_COUNT" -ge "$DB_READY_ATTEMPTS" ]; then
    echo "❌ Database is not ready after ${DB_READY_ATTEMPTS} attempts"
    python manage.py check --database default
    exit 1
  fi
  echo "Database is not ready yet (${DB_READY_COUNT}/${DB_READY_ATTEMPTS}), retrying in ${DB_READY_SLEEP}s..."
  DB_READY_COUNT=$((DB_READY_COUNT + 1))
  sleep "$DB_READY_SLEEP"
done

echo "✅ Django database connection is ready"

echo "⏳ Running migrations..."
MIGRATE_ATTEMPTS=${MIGRATE_ATTEMPTS:-5}
MIGRATE_SLEEP=${MIGRATE_SLEEP:-5}
MIGRATE_COUNT=1

until python manage.py migrate --noinput; do
  if [ "$MIGRATE_COUNT" -ge "$MIGRATE_ATTEMPTS" ]; then
    echo "❌ Migrations failed after ${MIGRATE_ATTEMPTS} attempts"
    exit 1
  fi
  echo "Migrations failed (${MIGRATE_COUNT}/${MIGRATE_ATTEMPTS}), retrying in ${MIGRATE_SLEEP}s..."
  MIGRATE_COUNT=$((MIGRATE_COUNT + 1))
  sleep "$MIGRATE_SLEEP"
done

echo "📦 Collecting static..."
python manage.py collectstatic --noinput --clear

echo "🚀 Starting Gunicorn..."
exec gunicorn students_life.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 3 \
  --worker-class sync \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -
