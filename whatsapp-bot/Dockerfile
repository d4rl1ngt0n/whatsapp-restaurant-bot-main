FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8080

ENV LOG_LEVEL=INFO \
    APP_VERSION=1.0.0

CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:8080", "app.main:app"]
