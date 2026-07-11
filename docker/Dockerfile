# ── Multi-stage build for 智能研报生成系统 ──────────────────────────

# ▸ Stage 1: Builder
FROM python:3.11-slim AS builder
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir --user hatchling && \
    python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies'])" > /tmp/deps.txt
RUN pip install --no-cache-dir --user -r /tmp/deps.txt

# ▸ Stage 2: Runtime
FROM python:3.11-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
COPY . .

ENV PYTHONPATH=/app
ENV ENVIRONMENT=prod

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
