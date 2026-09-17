#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/sl-system/manager}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-rebuild-erp-core}"
BACKUP_ROOT="${BACKUP_ROOT:-/opt/sl-system/backups/github-deploy}"
HEALTH_URL="${HEALTH_URL:-https://manager-sl.ru/api/health/}"
PG_DUMP_IMAGE="${PG_DUMP_IMAGE:-postgres:18-alpine}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="$BACKUP_ROOT/$timestamp"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

[ "$(id -u)" -eq 0 ] || fail "Run this script as root."
[ -d "$APP_DIR/.git" ] || fail "$APP_DIR is not a Git checkout."
cd "$APP_DIR"

[ -f .env ] || fail ".env is missing."
[ -f docker-compose.yml ] || fail "docker-compose.yml is missing."
command -v git >/dev/null || fail "git is not installed."
command -v docker >/dev/null || fail "docker is not installed."
docker compose version >/dev/null || fail "Docker Compose plugin is unavailable."

# Never overwrite manual production edits. The one-time baseline procedure must
# be completed before this updater is used for the first time.
if [ -n "$(git status --porcelain --untracked-files=all)" ]; then
  git status --short
  fail "Working tree is not clean. Reconcile production changes before updating."
fi

mkdir -p "$backup_dir"
git rev-parse HEAD > "$backup_dir/source-head.txt"
cp -a .env "$backup_dir/.env"
docker compose config > "$backup_dir/compose.resolved.yml"

echo "Creating PostgreSQL backup in $backup_dir ..."
docker run --rm \
  --env-file "$APP_DIR/.env" \
  -v "$APP_DIR/secrets:/app/secrets:ro" \
  --entrypoint sh \
  "$PG_DUMP_IMAGE" \
  -lc 'PGPASSWORD="$DB_PASSWORD" exec pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -Fc' \
  > "$backup_dir/database.dump"
test -s "$backup_dir/database.dump" || fail "PostgreSQL backup is empty."

echo "Fetching origin/$DEPLOY_BRANCH ..."
git fetch --prune origin "$DEPLOY_BRANCH"
git merge-base --is-ancestor HEAD "origin/$DEPLOY_BRANCH" \
  || fail "origin/$DEPLOY_BRANCH is not a fast-forward from the installed revision."
git merge --ff-only "origin/$DEPLOY_BRANCH"

echo "Building ManagerSL images ..."
docker compose build web celery celery-beat
docker compose up -d --no-deps --force-recreate web celery celery-beat

for _ in $(seq 1 36); do
  state="$(docker inspect -f '{{.State.Health.Status}}' managers_sl_web 2>/dev/null || true)"
  [ "$state" = "healthy" ] && break
  sleep 5
done

if [ "$(docker inspect -f '{{.State.Health.Status}}' managers_sl_web 2>/dev/null || true)" != "healthy" ]; then
  docker compose logs --tail 150 web
  fail "ManagerSL web container did not become healthy. Backup: $backup_dir"
fi

# Nginx resolves the Docker service IP when it starts.
docker compose restart nginx
curl --fail --silent --show-error --max-time 20 "$HEALTH_URL" >/dev/null \
  || fail "External health check failed: $HEALTH_URL"

git rev-parse HEAD > "$backup_dir/deployed-head.txt"
docker compose ps
echo "Deployment completed. Backup: $backup_dir"
