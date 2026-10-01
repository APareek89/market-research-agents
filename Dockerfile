FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HOME=/tmp XDG_CACHE_HOME=/tmp/cache
WORKDIR /app
COPY requirements-lock.txt ./
RUN pip install --no-cache-dir --requirement requirements-lock.txt \
 && groupadd --gid 1000 app \
 && useradd --uid 1000 --gid 1000 --no-create-home --home-dir /tmp app \
 && mkdir -p /app/uploads \
 && chown app:app /app/uploads
COPY app/ ./app/
COPY kb/frameworks/ ./kb/frameworks/
COPY --from=frontend /build/frontend/dist/ ./frontend/dist/
RUN chmod -R a=rX /app/app /app/kb /app/frontend
USER 1000:1000
EXPOSE 8600
HEALTHCHECK --interval=20s --timeout=5s --start-period=40s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8600/healthz', timeout=3)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8600", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "172.28.0.3", "--no-access-log"]
