FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/app/data/reminders.db \
    PORT=8000

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scanremind ./scanremind
COPY wsgi.py gunicorn.conf.py ./

RUN useradd --create-home appuser && mkdir -p /app/data && chown appuser /app/data
USER appuser

VOLUME ["/app/data"]
EXPOSE 8000

CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]
