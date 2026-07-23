# syntax=docker/dockerfile:1.7

FROM node:20-alpine AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=secret,id=corp_ca,required=false \
    if grep -q "BEGIN CERTIFICATE" /run/secrets/corp_ca 2>/dev/null; then \
        export NODE_EXTRA_CA_CERTS=/run/secrets/corp_ca; \
    fi \
    && npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim AS application

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8080

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --disable-pip-version-check \
    -r requirements.txt

COPY backend/ ./backend/
COPY bitrix/ ./bitrix/
COPY migrations/ ./migrations/
COPY deploy/entrypoint.py ./deploy/entrypoint.py
COPY --from=frontend-build /build/frontend/dist/ ./frontend/dist/

RUN addgroup --system app \
    && adduser --system --ingroup app --home /app app \
    && chown -R app:app /app

USER app

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "from urllib.request import urlopen; urlopen('http://127.0.0.1:8080/health', timeout=2).read()"]

CMD ["python", "-m", "deploy.entrypoint"]
