#!/bin/bash
# Все регрессии одной командой — «Ведение проектов · РЦК»
# Стандарт бережливой работы §6. Запуск: ./run_all_regress.sh
# Ожидание: 108/108 (sim_s1 8, sim_s2 25, preza_p2 20, preza_p3 14, ee_e1 26, fck64 15)
set -u
cd "$(dirname "$0")"
PY=".venv/bin/python"
PORT=8012
LOG=/tmp/rck_regress_server.log

if [ ! -x "$PY" ]; then echo "ОШИБКА: нет .venv — создайте: python3.13 -m venv .venv && .venv/bin/pip install -r deploy/requirements.txt pypdfium2"; exit 2; fi

# Уборка за собой (5С): гасим сервер при любом выходе
SERVER_PID=""
cleanup() { [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null; rm -f "$LOG"; }
trap cleanup EXIT

PASS=0; FAIL=0; FAILED_LIST=""
run() { # $1 — имя, $2 — команда
  local name="$1"; shift
  local out; out=$("$@" 2>&1 | grep -E "ИТОГО|Итого" | tail -1)
  echo "$name: $out"
  if echo "$out" | grep -qE "FAIL"; then FAIL=$((FAIL+1)); FAILED_LIST="$FAILED_LIST $name"; else PASS=$((PASS+1)); fi
}

run "sim_s1  (8)  "  $PY _test_sim_s1.py
run "sim_s2  (25) "  $PY _test_sim_s2.py
run "preza_p2 (20)"  $PY _test_preza_p2.py
run "preza_p3 (14)"  $PY _test_preza_p3.py
run "ee_e1   (26) "  $PY _test_ee_e1.py

# fck64 — нужен живой сервер на своём порту (8000 не трогаем)
(cd ui && exec "../$PY" -c "import app; app.app.run(host='127.0.0.1', port=$PORT, debug=False, use_reloader=False)" >"$LOG" 2>&1) &
SERVER_PID=$!
for i in $(seq 1 25); do sleep 1; curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$PORT/" && break; done
run "fck64   (15) " env AGENT_CEH_BASE="http://127.0.0.1:$PORT" $PY ui/_qa_regress_fck64.py

echo "----------------------------------------"
if [ "$FAIL" -eq 0 ]; then echo "ИТОГ: ВСЕ НАБОРЫ ЗЕЛЁНЫЕ (6/6, ожидается 108/108 тестов)"; else echo "ИТОГ: ПАДЕНИЕ в:$FAILED_LIST"; exit 1; fi
