#!/bin/sh
# Entrypoint «Агент-цех»: данные живут в volume /app/data (переживают
# пересоздание контейнера). Приложение ждёт БД и файлы/ рядом с app.py —
# выдаём их симлинками. При первом запуске подкладываем эталонную БД из образа.
set -eu

DATA=/app/data
UI=/app/ui

mkdir -p "$DATA/файлы"

if [ ! -s "$DATA/agent_ceh.db" ]; then
    echo "[entrypoint] БД в volume отсутствует — копирую эталон из /app/seed"
    cp /app/seed/agent_ceh.db "$DATA/agent_ceh.db"
fi

# Если в образе/контейнере уже есть реальные файлы (не ссылки) — не трогаем;
# иначе связываем с volume.
if [ ! -e "$UI/agent_ceh.db" ] || [ -L "$UI/agent_ceh.db" ]; then
    ln -sfn "$DATA/agent_ceh.db" "$UI/agent_ceh.db"
fi
if [ ! -e "$UI/файлы" ] || [ -L "$UI/файлы" ]; then
    ln -sfn "$DATA/файлы" "$UI/файлы"
fi

cd "$UI"
exec "$@"
