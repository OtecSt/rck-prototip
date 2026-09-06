# «Агент-цех» — серверный запуск (прод-пакет)

Два пути:

- **Путь А (основной)** — свой VPS на Ubuntu 22.04: Docker + nginx + HTTPS.
- **Путь Б (запасной)** — сервер остаётся на вашем Mac, наружу выходим
  через временный туннель cloudflared (бесплатно, без регистрации).

Локальный запуск `python3 app.py` в каталоге `ui/` **не изменился** —
прод-пакет ничего в приложении не ломает.

---

## Путь А. Развёртывание на VPS (Ubuntu 22.04), шаг за шагом

### 1. Подключитесь к серверу

```bash
ssh root@<IP-вашего-VPS>
```

### 2. Заберите код на сервер

Либо git:

```bash
apt-get update && apt-get install -y git
git clone <ссылка-на-репозиторий> /opt/agent-ceh
```

либо с локальной машины через scp (выполняется на Mac, не на сервере):

```bash
scp -r "/Users/aleksandr/Desktop/Методички/ИИ-направление/Прототип" \
    root@<IP-вашего-VPS>:/opt/agent-ceh
```

Дальше все команды — на сервере.

### 3. Запустите установщик

```bash
cd /opt/agent-ceh/deploy
sudo bash deploy.sh
```

Скрипт сам: поставит Docker и compose-плагин, освободит порты 80/443
от «зомби», сгенерирует пароль базовой авторизации, соберёт образ,
поднимет сервисы и проверит, что сервис отвечает 200.
В конце он напечатает **адрес, логин и пароль — сохраните их**.

### 4. Проверьте в браузере

Откройте `http://<IP-вашего-VPS>/` — браузер спросит логин/пароль
из шага 3, дальше — привычный интерфейс «Агент-цех».

### 5. Включение HTTPS (нужен домен)

1. В панели регистратора создайте A-запись: `agent.ваш-домен.ru` → IP VPS.
2. Откройте `deploy/nginx/nginx.conf` и действуйте по инструкции
   в комментариях внизу файла (заменить `server_name`, раскомментировать
   ACME-блок и TLS-блок, выполнить 4 команды certbot — всё расписано).
3. В `deploy/docker-compose.yml` раскомментируйте `- "443:443"` и
   два volume certbot.
4. `docker compose restart nginx` — готово, адрес `https://agent.ваш-домен.ru/`.

---

## Путь Б. Туннель с Mac (запасной вариант)

Ничего ставить на сервер не нужно.

```bash
# один раз:
brew install cloudflared

# затем:
bash "/Users/aleksandr/Desktop/Методички/ИИ-направление/Прототип/deploy/tunnel.sh"
```

- Если локальный сервер уже запущен (`python3 app.py`) — скрипт найдёт его сам.
- Если нет — поднимет gunicorn на 127.0.0.1:8000.
- В терминале появится строка `https://....trycloudflare.com` — это внешняя
  ссылка на ваш локальный «Агент-цех». Действует, пока окно открыто.
- Остановка: `Ctrl+C`.

Внимание: ссылка без пароля — не публикуйте её и закрывайте туннель после работы.

---

## Бэкапы

```bash
sudo bash /opt/agent-ceh/deploy/backup.sh
```

Копии складываются в `deploy/backups/<дата>/` (БД + docx прогонов),
хранятся 14 последних дней. Автоматизация (cron, один раз):

```bash
sudo crontab -e
# добавить строку:
23 3 * * *  /opt/agent-ceh/deploy/backup.sh >> /var/log/agent-ceh-backup.log 2>&1
```

---

## Откат

```bash
cd /opt/agent-ceh/deploy
docker compose down            # остановить сервисы (данные в volume целы)
# восстановить БД из бэкапа:
docker run --rm -v agent-ceh_data:/v -v $(pwd)/backups/2025-01-01:/b alpine \
    cp /b/agent_ceh.db /v/agent_ceh.db
docker compose up -d           # поднять снова
```

Полный откат версии кода: заменить каталог проекта старой копией и повторить
`sudo bash deploy.sh`.

## Смена пароля базовой авторизации

```bash
cd /opt/agent-ceh/deploy
printf 'agentceh:%s\n' "$(openssl passwd -apr1 'НОВЫЙ-ПАРОЛЬ')" > nginx/.htpasswd
docker compose restart nginx
```

## Где логи

```bash
cd /opt/agent-ceh/deploy
docker compose logs -f app      # приложение (расчёты, ошибки ядер)
docker compose logs -f nginx    # доступ и авторизация
docker compose ps               # статус (healthy/unhealthy)
```

## Частые ошибки

| Симптом | Причина и лечение |
|---|---|
| `port 80 is already allocated` | Порт занят другим сервисом. `sudo bash deploy.sh` убивает «зомби» сам; если повторяется — `sudo lsof -i :80`, остановите мешающий процесс. |
| Браузер: `ERR_CONNECTION_REFUSED` | Сервис не поднялся: `docker compose ps`, затем `docker compose logs app`. |
| 401 / постоянный запрос пароля | Неверный логин/пароль — смените пароль (раздел выше). |
| 502 Bad Gateway | Контейнер app упал или ещё стартует: `docker compose logs app`; обычно проходит за 15–30 с. |
| 413 при загрузке Excel | Файл > 25 МБ (лимит nginx) или > 20 МБ (лимит приложения) — уменьшите файл. |
| «файл базы данных не найден» | Volume очищен. Восстановите из `deploy/backups/` (раздел «Откат»). |
| certbot: `connection refused` на 80 | Домен не указывает на VPS или порт 80 закрыт файрволом облака — откройте 80/443 в панели хостера. |

## Состав пакета

```
deploy/
├── Dockerfile            # прод-образ (python:3.12-slim, non-root, healthcheck)
├── docker-compose.yml    # app (gunicorn) + nginx, volume для данных
├── entrypoint.sh         # симлинки volume → БД/файлы, первичная заливка БД
├── wsgi.py               # точка входа gunicorn (app.py не изменён)
├── gunicorn.conf.py      # 3 воркера, timeout 120 с, ротация max_requests
├── requirements.txt      # flask 3.1.3, openpyxl 3.1.5, python-docx 1.2.0, gunicorn 23.0.0
├── nginx/nginx.conf      # proxy + basic auth + лимит 25M + security-заголовки + TLS-шаблон
├── deploy.sh             # установка на чистом Ubuntu 22.04 (идемпотентен)
├── backup.sh             # ежедневный бэкап БД + файлы/, ротация 14 дней
├── tunnel.sh             # путь Б: cloudflared quick tunnel с Mac
└── README.md             # этот файл
```

---

## LLM-слой (Спека № 4, ломтик Л4.1) — переменные окружения

Модуль `llm_sloy.py` — инфраструктура вызова LLM для «глубокого» режима
генератора мероприятий. Без ключа сервис работает как раньше
(детерминированный генератор, откат с пометкой `rezhim="bystriy_otkat"`).
Реальные значения задаются только на сервере (в `docker-compose.yml` →
`environment` сервиса app), в репозиторий ключи не вбиваются.

| Переменная | Назначение | Дефолт-заглушка |
|---|---|---|
| `LLM_API_KEY` | Ключ chat-completions-совместимого API. Без него — режим «недоступно», вызовов нет | не задан |
| `LLM_BASE_URL` | База API (выбор российского API — отдельным протоколом, спека 2.1) | `https://api.openai.com/v1` |
| `LLM_MODEL` | Модель | `gpt-4o-mini` |
| `LLM_MONTH_LIMIT_RUB` | Месячный лимит расхода, руб.; превышение → `LLMError` «лимит» | `1000` |
| `LLM_PRICE_1K_TOK_RUB` | Оценка цены за 1000 токенов для учёта расхода (консервативно) | `0.5` |
| `LLM_DB_PATH` | Переопределение пути БД кэша/расхода (тесты); в бою не задавать | `ui/agent_ceh.db` |

Кэш ответов (`llm_kesh`, sha256 входа + версия промпта; попадание = бесплатно)
и учёт расхода (`llm_rashod`) живут в той же `agent_ceh.db` — таблицы
создаются миграцией при старте (`CREATE TABLE IF NOT EXISTS` в `СХЕМА_SQL`
app.py и `llm_sloy.init_llm_db()`), локальная БД на прод не копируется.
