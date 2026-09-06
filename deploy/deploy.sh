#!/usr/bin/env bash
# ==========================================================================
# «Агент-цех» — развёртывание на чистом Ubuntu 22.04 VPS.
# Идемпотентен: можно запускать повторно.
# Запуск:  sudo bash deploy.sh
# ==========================================================================
set -euo pipefail
cd "$(dirname "$0")"

log()  { printf '\033[1;32m[deploy]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[deploy]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[deploy] ОШИБКА:\033[0m %s\n' "$*" >&2
         echo "  Что делать: смотрите раздел «Частые ошибки» в deploy/README.md" >&2
         exit 1; }

# --- 0. Защита от зомби: освобождаем порты 80/443, если их держат чужие ---
kill_port_holders() {
    local port="$1"
    # старые контейнеры с теми же именами
    if command -v docker >/dev/null 2>&1; then
        docker ps -q --filter "publish=${port}" | xargs -r docker stop >/dev/null 2>&1 || true
    fi
    # локальные процессы на порту (не docker-proxy — те уйдут вместе с контейнером)
    if command -v lsof >/dev/null 2>&1; then
        { lsof -ti "tcp:${port}" 2>/dev/null || true; } | while read -r pid; do
            comm="$(ps -p "$pid" -o comm= 2>/dev/null || echo '')"
            case "$comm" in
                docker*|com.docker*) ;;
                *) warn "порт ${port} занят процессом «${comm:-?}» (pid $pid) — останавливаю"
                   kill "$pid" 2>/dev/null || true ;;
            esac
        done
    fi
}

# --- 1. Docker + compose-плагин ---
if ! command -v docker >/dev/null 2>&1; then
    log "Docker не найден — устанавливаю (официальный репозиторий Docker)"
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl gnupg lsof openssl
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    . /etc/os-release
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
else
    log "Docker уже установлен: $(docker --version)"
fi

if ! docker compose version >/dev/null 2>&1; then
    log "Ставлю compose-плагин"
    apt-get update -qq && apt-get install -y -qq docker-compose-plugin \
        || die "docker compose недоступен и не установился"
fi
command -v openssl >/dev/null 2>&1 || apt-get install -y -qq openssl

systemctl enable --now docker >/dev/null 2>&1 || true

# --- 2. Освобождаем порты перед поднятием (двойной запуск — наша боль) ---
kill_port_holders 80
kill_port_holders 443
docker rm -f agent-ceh-app-1 agent-ceh-nginx-1 >/dev/null 2>&1 || true

# --- 3. htpasswd: базовая авторизация nginx ---
BASIC_AUTH_USER="${BASIC_AUTH_USER:-agentceh}"
if [ ! -s nginx/.htpasswd ]; then
    BASIC_AUTH_PASSWORD="${BASIC_AUTH_PASSWORD:-$(openssl rand -base64 12 | tr -d '/+=')}"
    printf '%s:%s\n' "$BASIC_AUTH_USER" \
        "$(openssl passwd -apr1 "$BASIC_AUTH_PASSWORD")" > nginx/.htpasswd
    chmod 600 nginx/.htpasswd
    warn "Создан пароль базовой авторизации. СОХРАНИТЕ ЕГО:"
    warn "  логин:  $BASIC_AUTH_USER"
    warn "  пароль: $BASIC_AUTH_PASSWORD"
    warn "Смена пароля позже: см. deploy/README.md → «Смена пароля»"
else
    log "nginx/.htpasswd уже есть — пароль не трогаю"
fi

# --- 4. Сборка и запуск ---
log "Собираю образ и поднимаю сервисы…"
docker compose up -d --build || die "docker compose up завершился с ошибкой"

# --- 5. Проверка: ждём healthcheck приложения и ответ через nginx ---
log "Жду готовности приложения (до 90 с)…"
ok=""
for _ in $(seq 1 30); do
    if curl -fsS -u "$BASIC_AUTH_USER:${BASIC_AUTH_PASSWORD:-}" \
            -o /dev/null -w '%{http_code}' http://127.0.0.1/ 2>/dev/null | grep -q 200; then
        ok=1; break
    fi
    sleep 3
done
[ -n "$ok" ] || die "сервис не отвечает 200 через nginx. Диагностика:
  docker compose ps
  docker compose logs app
  docker compose logs nginx"

IP="$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}')"
log "ГОТОВО. Сервис поднят и отвечает 200."
echo
echo "  Адрес:  http://${IP:-<IP-вашего-VPS>}/"
echo "  Логин:  $BASIC_AUTH_USER    пароль: ${BASIC_AUTH_PASSWORD:-см. nginx/.htpasswd}"
echo
echo "  Дальше:"
echo "   - HTTPS: deploy/README.md → «Включение HTTPS» (нужен домен)"
echo "   - Бэкапы: sudo bash backup.sh + cron-строка из README"
echo "   - Логи:  docker compose logs -f app   (или nginx)"
