FROM python:3.12-slim

ENV DATA_DIR=/data \
    OAUTH_BIND_ADDR=0.0.0.0 \
    PORT=5000 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first so this layer is cached across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/
COPY frontend/ frontend/

RUN useradd --uid 1000 --create-home app \
    && mkdir /data \
    && chown app:app /data
USER app

VOLUME /data
EXPOSE 5000

# Exactly one worker: the login lockout and sync lock are in-process.
# Long timeout: POST /api/sync runs Gmail ingestion inside a single request.
# Shell form so ${PORT} expands; exec makes gunicorn PID 1 so `docker stop` reaches it.
CMD exec gunicorn backend.server:app --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 300
