#!/bin/bash
set -e

# Load .env file if mounted (handles quoted values correctly via shell)
if [ -f /app/.env ]; then
    set -a
    . /app/.env
    set +a
fi

cd /app/zebra-agent-web

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting Daphne on 0.0.0.0:8000..."
exec daphne -b 0.0.0.0 -p 8000 zebra_agent_web.asgi:application
