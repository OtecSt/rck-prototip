#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WSGI-точка входа «Агент-цех» для gunicorn: `gunicorn wsgi:app`.

Важно: app.py не изменён — объект Flask `app` там уже на уровне модуля,
dev-сервер запускается только при `python3 app.py` (блок __main__).
Этот файл — лишь тонкая обёртка, чтобы команда запуска не зависела
от рабочего каталога: gunicorn стартует из каталога ui/ (см. Dockerfile
и gunicorn.conf.py).
"""
from app import app  # noqa: F401  (реэкспорт для gunicorn)
