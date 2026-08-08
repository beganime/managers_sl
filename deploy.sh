#!/usr/bin/env bash
set -euo pipefail

branch="${DEPLOY_BRANCH:-$(git branch --show-current)}"
if [ -z "$branch" ]; then
  echo "Cannot determine deployment branch." >&2
  exit 1
fi

git pull --ff-only origin "$branch"
docker compose build web celery celery-beat
docker compose up -d --no-deps --force-recreate web celery celery-beat

for _ in $(seq 1 24); do
  state=$(docker inspect -f '{{.State.Health.Status}}' managers_sl_web 2>/dev/null || true)
  [ "$state" = "healthy" ] && break
  sleep 5
done

if [ "$(docker inspect -f '{{.State.Health.Status}}' managers_sl_web)" != "healthy" ]; then
  docker compose logs --tail 100 web
  echo "ManagerSL web container did not become healthy." >&2
  exit 1
fi

# Nginx resolves the Docker service IP when it starts. Restart it after a web
# container replacement so it cannot keep the previous upstream address.
docker compose restart nginx
docker compose ps
