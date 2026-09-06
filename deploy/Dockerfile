# syntax=docker/dockerfile:1
# «Агент-цех» — прод-образ. Контекст сборки: каталог Прототип/ (родитель deploy/),
# см. docker-compose.yml → build.context: ..
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    GUNICORN_BIND=0.0.0.0:8000

WORKDIR /app

# Зависимости — отдельным слоем для кеша
COPY deploy/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Ядра расчётов (импортируются app.py как ../<ядро>.py — структура сохранена)
COPY узкие_места.py ээ_калькулятор.py protokol_zakrytiya.py ord_smart.py vsm_karta.py ээ_экспорт_фцк.py otbor.py otbor_potok.py dokumenty_fck.py meropriyatiya.py biblioteka_instrumentov.py pokazateli_potoka.py ekstraktor_pa.py cifrovoy_zamer.py oee_kalkulator.py vr_export.py llm_sloy.py /app/
# Эталонный шаблон «Вскрытие резервов» V4.7.2 (актив vr_export.py)
COPY assets/vr_shablon_v472.xlsx /app/assets/vr_shablon_v472.xlsx
COPY данные_окз_слепой.json данные_ээ_новохром.json данные_ээ_оренбив.json данные_ээ_пример_v523.json /app/
# Шаблон справки ФЦК 1.4 (фикс Д3.1-Б2: без него «Скачать справку ФЦК» → 500)
COPY разведка_ээ/*.xlsm /app/разведка_ээ/

# UI: приложение, шаблоны, статика (БД и файлы/ НЕ копируем в образ —
# приезжают через volume, см. compose; эталонная пустая БД — в seed)
COPY ui/app.py ui/simulyator.py ui/preza_data.py ui/preza_pptx.py /app/ui/
COPY ui/templates /app/ui/templates
COPY ui/static /app/ui/static
COPY ui/agent_ceh.db /app/seed/agent_ceh.db
COPY deploy/wsgi.py deploy/gunicorn.conf.py /app/ui/
COPY deploy/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh \
    && mkdir -p /app/ui/файлы \
    && useradd -r -u 10001 agentceh \
    && chown -R agentceh:agentceh /app

USER agentceh
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; r=urllib.request.urlopen('http://127.0.0.1:8000/'); sys.exit(0 if r.status==200 else 1)"

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]
