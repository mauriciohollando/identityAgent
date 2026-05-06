FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    PYTHONPATH=/app/src \
    DISPUTES_DB_PATH=/app/data/disputes.db \
    PAYMENT_LEDGER_DB_PATH=/app/data/payment_ledger.db

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /app/data

COPY .well-known ./.well-known
COPY src ./src
COPY legal ./legal

EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn auditor:a2a_app --host 0.0.0.0 --port ${PORT:-8080}"]
