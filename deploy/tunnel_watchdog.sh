#!/bin/bash
# Сторож туннеля «Агент-цех»: проверяет внешнюю ссылку, переподнимает при смерти.
# Запуск: каждые 5 мин через cron. Лог: ../ui/tunnel_watchdog.log
UI="/Users/aleksandr/Desktop/Методички/ИИ-направление/Прототип/ui"
export AGENT_CEH_PASSWORD='H8BgJlzfjESRDv4F'
USER_LOGIN='рцк'
ts() { date "+%Y-%m-%d %H:%M:%S"; }
# 1. Сервер жив?
if ! curl -s -o /dev/null --max-time 5 -u "$USER_LOGIN:$AGENT_CEH_PASSWORD" http://localhost:8000/; then
  echo "$(ts) сервер мёртв — поднимаю" >> "$UI/tunnel_watchdog.log"
  pkill -f "python3 app.py" 2>/dev/null; sleep 1
  (cd "$UI" && AGENT_CEH_PASSWORD="$AGENT_CEH_PASSWORD" nohup python3 app.py >> ui_server.log 2>&1 &)
  sleep 2
fi
# 2. Туннель жив? (берём последнюю ссылку из lhr.log)
URL=$(grep -o "https://[a-zA-Z0-9.-]*\.lhr\.life" "$UI/lhr.log" | tail -1)
CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 -u "$USER_LOGIN:$AGENT_CEH_PASSWORD" "$URL/" 2>/dev/null || echo 000)
if [ "$CODE" != "200" ]; then
  echo "$(ts) туннель мёртв ($CODE, $URL) — переподнимаю" >> "$UI/tunnel_watchdog.log"
  pkill -f "localhost.run" 2>/dev/null; sleep 2
  (cd "$UI" && nohup ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -R 80:localhost:8000 nokey@localhost.run > lhr.log 2>&1 &)
  sleep 15
  NEWURL=$(grep -o "https://[a-zA-Z0-9.-]*\.lhr\.life" "$UI/lhr.log" | head -1)
  echo "$(ts) новая ссылка: $NEWURL" >> "$UI/tunnel_watchdog.log"
fi
