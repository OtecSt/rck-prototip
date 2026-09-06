#!/usr/bin/env bash
# ==========================================================================
# «Агент-цех» — путь Б: доступ снаружи через cloudflared quick tunnel
# к ЛОКАЛЬНОМУ серверу на Mac владельца (без Docker, без VPS).
#
# Запуск:  bash tunnel.sh
# Скрипт:
#   1. проверяет cloudflared (подскажет brew install, если нет);
#   2. находит/поднимает локальный сервер (уже запущенный python3 app.py
#      на порту 8000+ используется как есть; иначе поднимаем gunicorn);
#   3. стартует туннель и печатает временную https-ссылку.
# Остановка: Ctrl+C (туннель закроется; gunicorn, если поднимали мы, тоже
# будет остановлен — если сервер был ваш, он продолжит работать).
# ==========================================================================
set -euo pipefail
cd "$(dirname "$0")/../ui"   # каталог ui/ с app.py

log() { printf '\033[1;32m[tunnel]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[tunnel] ОШИБКА:\033[0m %s\n' "$*" >&2; exit 1; }

# --- 1. cloudflared ---
command -v cloudflared >/dev/null 2>&1 || die \
"cloudflared не установлен. Установите:
    brew install cloudflared
и запустите скрипт снова."

# --- 2. Локальный сервер ---
find_port() {  # первый слушающий порт 8000–8099 или пусто
    for p in $(seq 8000 8099); do
        if lsof -nP -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then echo "$p"; return; fi
    done
}

WE_STARTED=""
PORT="$(find_port || true)"

if [ -z "$PORT" ]; then
    # Защита от зомби: неподвисших процессов нет (find_port пуст),
    # но добиваем «хвосты» старых gunicorn этого проекта на всякий случай.
    pkill -f "gunicorn.*wsgi:app" 2>/dev/null || true
    sleep 1
    PORT=8000
    log "локальный сервер не найден — поднимаю gunicorn на 127.0.0.1:$PORT"
    command -v gunicorn >/dev/null 2>&1 || die \
"gunicorn не установлен в текущем python. Варианты:
    python3 -m pip install gunicorn
или просто запустите сервер как обычно:  python3 app.py  (в другом окне)
и затем снова  bash tunnel.sh"
    cp ../deploy/gunicorn.conf.py ./.gunicorn.tunnel.conf.py
    PYTHONPATH="../deploy" GUNICORN_BIND=127.0.0.1:$PORT GUNICORN_WORKERS=2 \
        gunicorn -c ./.gunicorn.tunnel.conf.py wsgi:app &
    WE_STARTED=$!
    for _ in $(seq 1 20); do
        curl -fsS -o /dev/null "http://127.0.0.1:$PORT/" 2>/dev/null && break
        sleep 1
    done
    curl -fsS -o /dev/null "http://127.0.0.1:$PORT/" \
        || die "gunicorn не поднялся на порту $PORT — смотрите вывод выше"
    log "gunicorn поднят (pid $WE_STARTED)"
else
    log "найден работающий локальный сервер на порту $PORT — использую его"
fi

cleanup() {
    [ -n "$WE_STARTED" ] && { kill "$WE_STARTED" 2>/dev/null || true; }
    rm -f ./.gunicorn.tunnel.conf.py
}
trap cleanup EXIT

# --- 3. Туннель ---
log "поднимаю cloudflared quick tunnel → http://127.0.0.1:$PORT"
log "через несколько секунд ниже появится строка вида  https://<случайное>.trycloudflare.com"
echo
cloudflared tunnel --url "http://127.0.0.1:$PORT" --no-autoupdate
