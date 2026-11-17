FROM node:24-bookworm-slim@sha256:dc26ae92c9fb15cf6b1d63e20f0944b2efe0f115b20e00be48fb23fceb061c54 AS web-build
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
COPY tests/web/ /build/tests/web/
COPY tests/fixtures/web/ /build/tests/fixtures/web/
ENV VITE_DEMO_MODE=false
RUN npm run build

FROM caddy:2@sha256:4851e54a46b206517c574821bb5cc67f170d2156041e9fbc4c9193b45e84a75b AS web
ARG SOURCE_REVISION
LABEL org.opencontainers.image.revision=${SOURCE_REVISION}
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=web-build /build/frontend/dist /srv

FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/backend:/app HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
WORKDIR /app
COPY deploy/requirements-core.lock ./requirements-core.lock
RUN apt-get update && apt-get install -y --no-install-recommends \
    libstdc++6=12.2.0-14+deb12u1 libgomp1=12.2.0-14+deb12u1 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --only-binary=:all: --no-cache-dir -r requirements-core.lock && pip check \
    && python -c "from ortools.sat.python import cp_model; import sklearn, PIL, psycopg"
COPY backend/ backend/
COPY ml_service/app/ ml_service/app/
COPY database/ database/
COPY data/models/ data/models/
COPY scripts/release_runtime.py scripts/release_runtime.py
RUN useradd --uid 10001 --create-home fixrate && mkdir -p /app/var/photos && chown -R fixrate:fixrate /app/var
ARG SOURCE_REVISION
LABEL org.opencontainers.image.revision=${SOURCE_REVISION}
ENV FIXRATE_SOURCE_REVISION=${SOURCE_REVISION}
USER 10001:10001
CMD ["python", "scripts/release_runtime.py", "api"]
