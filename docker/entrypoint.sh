#!/bin/sh
set -eu

wait_for_tcp() {
  host="$1"
  port="$2"
  label="$3"

  python - "$host" "$port" "$label" <<'PY'
import socket
import sys
import time

host, port, label = sys.argv[1], int(sys.argv[2]), sys.argv[3]
deadline = time.time() + 120
while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=3):
            print(f"{label} is ready")
            sys.exit(0)
    except OSError:
        time.sleep(2)

raise SystemExit(f"Timed out waiting for {label} at {host}:{port}")
PY
}

if [ "${SXDEVOPS_WAIT_FOR_DB:-1}" = "1" ]; then
  wait_for_tcp "${MYSQL_HOST:-mysql}" "${MYSQL_PORT:-3306}" "MySQL"
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
