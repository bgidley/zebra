# ============================================================================
# Stage 1: Builder — install dependencies with UV
# ============================================================================
FROM python:3.14-slim AS builder

RUN pip install uv

WORKDIR /app

# Copy workspace definition and lockfile first (cache-friendly)
COPY pyproject.toml uv.lock ./

# Copy each package's pyproject.toml for dependency resolution
COPY zebra-py/pyproject.toml zebra-py/pyproject.toml
COPY zebra-tasks/pyproject.toml zebra-tasks/pyproject.toml
COPY zebra-agent/pyproject.toml zebra-agent/pyproject.toml
COPY zebra-agent-web/pyproject.toml zebra-agent-web/pyproject.toml

# Copy source code (needed for editable installs)
COPY zebra-py/ zebra-py/
COPY zebra-tasks/ zebra-tasks/
COPY zebra-agent/ zebra-agent/
COPY zebra-agent-web/ zebra-agent-web/

# Install all packages without dev dependencies
RUN uv sync --all-packages --no-dev --frozen

# Collect static files (needs Django settings, use dummy secret)
ENV DJANGO_SETTINGS_MODULE=zebra_agent_web.settings \
    DJANGO_SECRET_KEY=build-only-dummy-key \
    ORACLE_DSN="" \
    ORACLE_USERNAME="" \
    ORACLE_PASSWORD=""
RUN uv run python zebra-agent-web/manage.py collectstatic --noinput

# ============================================================================
# Stage 2: Runtime — slim image with only what's needed
# ============================================================================
FROM python:3.14-slim

WORKDIR /app

# Copy the entire venv from builder
COPY --from=builder /app/.venv /app/.venv

# Copy source code and collected static files
COPY --from=builder /app/zebra-py zebra-py/
COPY --from=builder /app/zebra-tasks zebra-tasks/
COPY --from=builder /app/zebra-agent zebra-agent/
COPY --from=builder /app/zebra-agent-web zebra-agent-web/
COPY --from=builder /app/pyproject.toml pyproject.toml

# Copy entrypoint
COPY docker/entrypoint.sh /app/docker/entrypoint.sh

# Ensure venv is on PATH
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=zebra_agent_web.settings

# Create log directory
RUN mkdir -p /app/zebra-agent-web/tmp

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
