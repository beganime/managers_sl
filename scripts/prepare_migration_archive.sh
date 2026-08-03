#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_ROOT="${BACKUP_ROOT:-$PROJECT_DIR/backups}"
PACKAGE_NAME="${PACKAGE_NAME:-managers_sl_migration_$TIMESTAMP}"
WORK_DIR="$BACKUP_ROOT/$PACKAGE_NAME"
ARCHIVE_PATH="$BACKUP_ROOT/$PACKAGE_NAME.tar.gz"

COMPOSE="${COMPOSE:-docker compose}"
WEB_SERVICE="${WEB_SERVICE:-web}"
DB_SERVICE="${DB_SERVICE:-db}"

mkdir -p "$WORK_DIR"/{code,data,db,env,logs,media}

echo "== ManagerSL migration archive =="
echo "Project: $PROJECT_DIR"
echo "Output : $WORK_DIR"

cd "$PROJECT_DIR"

echo "== Saving git metadata =="
{
  git rev-parse --abbrev-ref HEAD || true
  git rev-parse HEAD || true
  git status --short || true
} > "$WORK_DIR/logs/git_state.txt"

echo "== Copying source code =="
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git archive --format=tar HEAD | tar -x -C "$WORK_DIR/code"
else
  rsync -a \
    --exclude '.git' \
    --exclude 'venv' \
    --exclude '__pycache__' \
    --exclude 'staticfiles' \
    --exclude 'backups' \
    --exclude 'media' \
    "$PROJECT_DIR/" "$WORK_DIR/code/"
fi

echo "== Copying environment files =="
for env_file in .env .env.production .env.example; do
  if [ -f "$PROJECT_DIR/$env_file" ]; then
    cp "$PROJECT_DIR/$env_file" "$WORK_DIR/env/$env_file"
  fi
done

echo "== Copying media files =="
if [ -d "$PROJECT_DIR/media" ]; then
  tar -C "$PROJECT_DIR" -cf "$WORK_DIR/media/media.tar" media
fi

echo "== Capturing docker compose config and container list =="
($COMPOSE ps || true) > "$WORK_DIR/logs/docker_compose_ps.txt"
($COMPOSE config || true) > "$WORK_DIR/logs/docker_compose_config.yml"

echo "== Building web image with current code =="
$COMPOSE build "$WEB_SERVICE"

echo "== Exporting business data to XLSX/CSV/JSON =="
$COMPOSE run --rm \
  -v "$WORK_DIR/data:/backup" \
  "$WEB_SERVICE" \
  python manage.py export_migration_data --output /backup/business_export

echo "== Exporting Django fixture =="
$COMPOSE run --rm \
  -v "$WORK_DIR/db:/backup_db" \
  "$WEB_SERVICE" \
  sh -c 'python manage.py dumpdata --natural-foreign --natural-primary --exclude contenttypes --exclude auth.permission --exclude sessions --exclude admin.logentry > /backup_db/django_dumpdata.json'

echo "== Trying PostgreSQL pg_dump from db container =="
set +e
DB_NAME_VALUE="$($COMPOSE exec -T "$WEB_SERVICE" python - <<'PY'
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'students_life.settings')
try:
    import django
    django.setup()
    from django.conf import settings
    db = settings.DATABASES['default']
    print(db.get('NAME') or '')
except Exception:
    print(os.environ.get('DB_NAME', 'managers_sl'))
PY
)"
DB_USER_VALUE="$($COMPOSE exec -T "$WEB_SERVICE" python - <<'PY'
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'students_life.settings')
try:
    import django
    django.setup()
    from django.conf import settings
    db = settings.DATABASES['default']
    print(db.get('USER') or '')
except Exception:
    print(os.environ.get('DB_USER', 'postgres'))
PY
)"
$COMPOSE exec -T "$DB_SERVICE" pg_dump -U "${DB_USER_VALUE:-postgres}" -d "${DB_NAME_VALUE:-managers_sl}" \
  > "$WORK_DIR/db/postgres_dump.sql"
PG_DUMP_STATUS=$?
set -e
if [ "$PG_DUMP_STATUS" -ne 0 ] || [ ! -s "$WORK_DIR/db/postgres_dump.sql" ]; then
  echo "pg_dump through db container failed. Django dumpdata and XLSX/CSV exports are still available." \
    > "$WORK_DIR/db/postgres_dump_failed.txt"
  rm -f "$WORK_DIR/db/postgres_dump.sql"
fi

if [ ! -f "$WORK_DIR/db/postgres_dump.sql" ]; then
  echo "== Trying PostgreSQL pg_dump from web container settings =="
  set +e
  $COMPOSE run --rm \
    -v "$WORK_DIR/db:/backup_db" \
    "$WEB_SERVICE" \
    python - <<'PY'
import os
import subprocess
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'students_life.settings')

try:
    import django
    django.setup()
    from django.conf import settings
    db = settings.DATABASES['default']
except Exception as exc:
    print(f'Cannot read Django database settings: {exc}', file=sys.stderr)
    sys.exit(2)

if db.get('ENGINE') != 'django.db.backends.postgresql':
    print('Database engine is not PostgreSQL; SQL dump skipped.', file=sys.stderr)
    sys.exit(3)

env = os.environ.copy()
env['PGPASSWORD'] = str(db.get('PASSWORD') or '')
command = [
    'pg_dump',
    '-h', str(db.get('HOST') or 'localhost'),
    '-p', str(db.get('PORT') or '5432'),
    '-U', str(db.get('USER') or 'postgres'),
    '-d', str(db.get('NAME') or 'managers_sl'),
    '-f', '/backup_db/postgres_dump.sql',
]
result = subprocess.run(command, env=env, text=True, capture_output=True)
if result.returncode != 0:
    print(result.stderr or result.stdout or 'pg_dump failed', file=sys.stderr)
sys.exit(result.returncode)
PY
  WEB_PG_DUMP_STATUS=$?
  set -e
  if [ "$WEB_PG_DUMP_STATUS" -ne 0 ] || [ ! -s "$WORK_DIR/db/postgres_dump.sql" ]; then
    echo "pg_dump through web container failed too. Use db/django_dumpdata.json and data/business_export as fallback." \
      >> "$WORK_DIR/db/postgres_dump_failed.txt"
    rm -f "$WORK_DIR/db/postgres_dump.sql"
  else
    rm -f "$WORK_DIR/db/postgres_dump_failed.txt"
  fi
fi

echo "== Writing restore notes =="
cat > "$WORK_DIR/README_RESTORE.md" <<'EOF'
# ManagerSL migration package

Содержимое архива:

- `code/` — исходный код текущего коммита.
- `env/` — `.env` файлы со старого сервера. Храните их как секреты.
- `media/media.tar` — пользовательские файлы, если папка `media/` существовала.
- `db/postgres_dump.sql` — SQL dump PostgreSQL, если `pg_dump` был доступен.
- `db/django_dumpdata.json` — Django fixture как резервный вариант.
- `data/business_export/` — XLSX/CSV/JSON выгрузки по бизнес-моделям.
- `logs/` — состояние git/docker на момент архивации.

## Быстрое восстановление на новом сервере

1. Распаковать архив.
2. Скопировать `code/` в новый каталог проекта.
3. Скопировать нужный `.env` из `env/` в корень проекта как `.env`.
4. Восстановить `media`:

```bash
tar -C /var/www/project/managers_sl -xf media/media.tar
```

5. Собрать контейнеры:

```bash
docker compose build --no-cache
docker compose up -d db redis
docker compose run --rm web python manage.py migrate --noinput
```

6. Если есть `db/postgres_dump.sql`, предпочтительно восстановить SQL dump в пустую базу.

7. Если SQL dump недоступен, использовать Django fixture:

```bash
docker compose run --rm web python manage.py loaddata db/django_dumpdata.json
```

8. Проверить проект:

```bash
docker compose exec web python manage.py check
docker compose exec web python manage.py collectstatic --noinput
docker compose up -d
docker compose logs web --tail=100
```
EOF

echo "== Creating final archive =="
tar -C "$BACKUP_ROOT" -czf "$ARCHIVE_PATH" "$PACKAGE_NAME"

echo "== Done =="
echo "Archive: $ARCHIVE_PATH"
echo "Size:"
du -h "$ARCHIVE_PATH" || true
