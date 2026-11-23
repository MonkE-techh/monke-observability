# Monk-E admin: build the React page, then serve it and the API from one FastAPI process.
# Build context is the repository root (the image needs apps.yaml):
#   docker build -f admin/Dockerfile -t monke-admin .

FROM node:22-slim AS web
WORKDIR /src/admin/frontend
COPY admin/frontend/package.json admin/frontend/package-lock.json ./
RUN npm ci
COPY admin/frontend/ ./
# vite writes the bundle to ../backend/static
RUN npm run build

FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv
WORKDIR /app/admin/backend
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY admin/backend/pyproject.toml admin/backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY admin/backend/ ./
RUN uv sync --frozen --no-dev
COPY --from=web /src/admin/backend/static ./static
COPY apps.yaml /app/apps.yaml

ENV APPS_FILE=/app/apps.yaml PATH="/app/admin/backend/.venv/bin:$PATH" PORT=8000
RUN useradd --create-home admin && chown -R admin /app
USER admin
EXPOSE 8000
CMD ["sh", "-c", "uvicorn monke_admin.main:create_app --factory --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
