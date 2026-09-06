#!/usr/bin/env bash
# ==========================================================================
# «Агент-цех» — ежедневный бэкап agent_ceh.db + файлы/ (docx прогонов).
# Данные лежат в docker-volume «agent-ceh_data»; снимаем копию из контейнера.
# Ротация: храним 14 дней, старше — удаляем.
#
# Установка (один раз, на VPS):
#   sudo crontab -e
#   23 3 * * *  /opt/agent-ceh/deploy/backup.sh >> /var/log/agent-ceh-backup.log 2>&1
#   (путь /opt/agent-ceh замените на реальный каталог проекта)
# ==========================================================================
set -euo pipefail
cd "$(dirname "$0")"

DEST="$(pwd)/backups/$(date +%Y-%m-%d)"
mkdir -p "$DEST"

log() { printf '[backup %s] %s\n' "$(date '+%F %T')" "$*"; }

# БД: горячая консистентная копия через sqlite3 .backup внутри контейнера
if docker compose exec -T app sh -c \
        'python - <<PY
import sqlite3
src = sqlite3.connect("/app/ui/agent_ceh.db")
dst = sqlite3.connect("/app/data/agent_ceh_backup.db")
src.backup(dst)
dst.close(); src.close()
PY' 2>/dev/null; then
    docker compose cp app:/app/data/agent_ceh_backup.db "$DEST/agent_ceh.db"
    docker compose exec -T app rm -f /app/data/agent_ceh_backup.db || true
else
    log "контейнер app недоступен — пробую холодную копию из volume"
    docker run --rm -v agent-ceh_data:/v -v "$DEST":/out alpine \
        cp /v/agent_ceh.db /out/agent_ceh.db
fi

# docx прогонов
docker run --rm -v agent-ceh_data:/v -v "$DEST":/out alpine \
    sh -c 'mkdir -p /out/файлы && cp -r /v/файлы/. /out/файлы/ 2>/dev/null || true'

# Ротация: 14 дней
find "$(pwd)/backups" -mindepth 1 -maxdepth 1 -type d -mtime +13 -exec rm -rf {} +

log "готово → $DEST (бэкапов хранится: $(ls "$(pwd)/backups" | wc -l | tr -d ' '))"
