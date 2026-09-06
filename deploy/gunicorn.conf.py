# -*- coding: utf-8 -*-
"""Gunicorn-конфиг «Агент-цех».

bind: в Docker — 0.0.0.0:8000 (nginx ходит по внутренней сети compose);
локально можно переопределить: GUNICORN_BIND=127.0.0.1:8000 gunicorn ...
"""
import os

bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")
workers = int(os.environ.get("GUNICORN_WORKERS", "3"))  # 2–4; SQLite — пишем редко
timeout = 120          # расчёты ядер длинные
graceful_timeout = 30
keepalive = 5
max_requests = 500     # плавная ротация воркеров против утечек памяти
max_requests_jitter = 50
accesslog = "-"
errorlog = "-"
loglevel = "info"
proc_name = "agent-ceh"
