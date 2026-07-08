# Backend container for Koyeb (free tier, no card).
# Postgres is external (Neon) via DATABASE_URL; frontend deploys to Vercel.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
WORKDIR /app/backend

# Collect static at build time (no DB needed). Whitenoise serves them.
RUN python manage.py collectstatic --no-input

EXPOSE 8000

# Migrate on boot (idempotent), then serve. $PORT is provided by Koyeb.
CMD ["sh", "-c", "python manage.py migrate --no-input && gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000}"]
