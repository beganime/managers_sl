# Обновление ManagerSL через GitHub

Основной репозиторий: `https://github.com/beganime/managers_sl`  
Production-ветка: `rebuild-erp-core`  
Production-каталог: `/opt/sl-system/manager`

## Локальная работа

Один раз клонировать актуальный репозиторий:

```powershell
cd C:\Users\ThinkPad\Desktop\projects
git clone --branch rebuild-erp-core https://github.com/beganime/managers_sl.git ManagersSL-GitHub
cd ManagersSL-GitHub
```

Перед началом каждой задачи:

```powershell
git switch rebuild-erp-core
git pull --ff-only origin rebuild-erp-core
git switch -c codex/kratkoe-nazvanie-zadachi
```

После изменений:

```powershell
git status --short
git diff --check
git add <список-изменённых-файлов>
git commit -m "Краткое описание изменения"
git push -u origin HEAD
```

После проверки изменения объединяются в `rebuild-erp-core`. Не хранить в Git:
`.env`, ключи Firebase/Google/S3/SSH, базы, `media`, `staticfiles`, архивы,
дампы, `.venv`, `node_modules` и пароли.

Старая папка `C:\Users\ThinkPad\Desktop\projects\Managers SL` не является
актуальной production-копией. Не выкладывать её целиком на сервер.

## Ручное обновление production

После объединения проверенного PR в `rebuild-erp-core`:

```bash
ssh root@5.129.248.183
cd /opt/sl-system/manager
bash deploy.sh
```

Скрипт перед обновлением:

1. останавливается, если на сервере есть незакоммиченные файлы;
2. сохраняет текущий Git HEAD, `.env` и итоговую Compose-конфигурацию;
3. создаёт PostgreSQL dump;
4. допускает только fast-forward обновление production-ветки;
5. пересобирает `web`, `celery`, `celery-beat`;
6. проверяет Docker healthcheck и внешний `/api/health/`;
7. не удаляет Docker volumes, `media`, `secrets`, сертификаты и базу.

Резервные копии создаются в:

```text
/opt/sl-system/backups/github-deploy/<UTC-дата-время>/
```

## Проверка после обновления

```bash
cd /opt/sl-system/manager
docker compose ps
docker compose logs --tail 100 web
curl -fsS https://manager-sl.ru/api/health/
git status --short --branch
git rev-parse HEAD
```

## Важное ограничение первого запуска

До первой команды `bash deploy.sh` текущие незакоммиченные production-изменения
должны быть один раз сверены с GitHub и закреплены в `rebuild-erp-core`.
Скрипт намеренно не делает `reset --hard`, не прячет изменения через stash и
не выполняет слепой `git pull`.
