# ---- base: runtime dependencies (shared) -------------------------------------
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
# FFmpeg extracts audio from recordings before transcription; curl for healthchecks.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg curl \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# ---- dev: hot reload + test tooling (source is bind-mounted by compose) -------
FROM base AS dev
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "app"]

# ---- prod: code baked in, non-root ---------------------------------------------
FROM base AS prod
COPY app ./app
RUN useradd --create-home --uid 10001 dxc \
 && mkdir -p /app/storage/recordings /home/dxc/.cache/huggingface \
 && chown -R dxc:dxc /app /home/dxc/.cache
USER dxc
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD curl -fsS http://localhost:8000/api/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
