#!/bin/sh
set -e

# If PostgreSQL is configured, wait until database is ready
if [ -n "$POSTGRES_HOST" ] || [ -n "$DB_HOST" ]; then
  echo "==> Waiting for PostgreSQL database to be reachable..."
  python - << 'EOF'
import os, time, sys
import psycopg2

host = os.environ.get("POSTGRES_HOST") or os.environ.get("DB_HOST", "localhost")
port = int(os.environ.get("POSTGRES_PORT") or os.environ.get("DB_PORT", 5432))
user = os.environ.get("POSTGRES_USER") or os.environ.get("DB_USER", "postgres")
password = os.environ.get("POSTGRES_PASSWORD") or os.environ.get("DB_PASSWORD", "postgres")
dbname = os.environ.get("POSTGRES_DB") or os.environ.get("DB_NAME", "postgres")

max_retries = 30
for i in range(max_retries):
    try:
        conn = psycopg2.connect(host=host, port=port, user=user, password=password, dbname=dbname)
        conn.close()
        print("==> PostgreSQL database connection established successfully.")
        sys.exit(0)
    except Exception as e:
        time.sleep(1)

print("==> Warning: Could not connect to PostgreSQL within timeout; attempting migrations anyway.")
EOF
fi

echo "=================================================="
echo "🚀 Initializing Order-to-Audit Manufacturing System"
echo "=================================================="

# Ensure directory for SQLite database exists and is writable
if [ -n "$SQLITE_PATH" ]; then
    mkdir -p "$(dirname "$SQLITE_PATH")"
fi

# 1. Apply database migrations
echo "==> [1/3] Running database migrations..."
python manage.py migrate --noinput

# 2. Seed benchmark scenario data (safe to run repeatedly; skips duplicate movements)
echo "==> [2/3] Seeding Section 5 benchmark data and test logins..."
python manage.py seed_benchmark

# 3. Collect static files
echo "==> [3/3] Collecting static files..."
python manage.py collectstatic --noinput

# 4. Resolve port and configure server command
PORT="${PORT:-8000}"

echo "==> Starting web application on port ${PORT}..."
echo "=================================================="

if [ $# -eq 0 ]; then
    set -- gunicorn config.wsgi:application --bind "0.0.0.0:${PORT}" --workers 2 --threads 4
elif [ "$1" = "gunicorn" ]; then
    case "$*" in
        *--bind*) ;;
        *) set -- "$@" --bind "0.0.0.0:${PORT}" ;;
    esac
elif [ "$1" = "python" ] && [ "$2" = "manage.py" ] && [ "$3" = "runserver" ]; then
    set -- gunicorn config.wsgi:application --bind "0.0.0.0:${PORT}" --workers 2 --threads 4
fi

exec "$@"
