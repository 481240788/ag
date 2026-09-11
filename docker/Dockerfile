FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENVIRONMENT=production \
    ENABLE_LOCAL_PYTHON_EXECUTION=false

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home app

COPY . .
RUN mkdir -p /app/examples && chown app:app /app/examples

USER app
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main.web_app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
