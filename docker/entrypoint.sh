#!/bin/sh
set -eu

if [ "${SXDEVOPS_WAIT_FOR_DB:-1}" = "1" ]; then
  python - <<'PY'
import os
import socket
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sxdevops.settings')
from django.conf import settings

database = settings.DATABASES['default']
engine = database['ENGINE'].rsplit('.', 1)[-1]
if engine != 'sqlite3':
    host = database.get('HOST') or 'localhost'
    port = int(database.get('PORT') or (5432 if engine == 'postgresql' else 3306))
    deadline = time.monotonic() + 120
    while True:
        try:
            with socket.create_connection((host, port), timeout=3):
                print(f'{engine} is ready')
                break
        except OSError:
            if time.monotonic() >= deadline:
                raise SystemExit(f'Timed out waiting for {engine} at {host}:{port}')
            time.sleep(2)
PY
fi

if [ "${SXDEVOPS_MIGRATE:-1}" = "1" ]; then
  python manage.py migrate --noinput
fi

if [ "${SXDEVOPS_WAIT_FOR_SCHEMA:-0}" = "1" ]; then
  python manage.py wait_for_schema --timeout 600
fi

if [ "${SXDEVOPS_SEED_DATA:-0}" = "1" ]; then
  python manage.py seed_data
fi

if [ "${SXDEVOPS_SEED_TEMPLATES:-1}" = "1" ]; then
  python manage.py seed_templates
fi

exec "$@"
