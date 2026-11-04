FROM node:24-bookworm-slim AS web
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
COPY tests/web/ /build/tests/web/
COPY tests/fixtures/web/ /build/tests/fixtures/web/
ENV VITE_DEMO_MODE=false
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/backend:/app
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt
COPY backend/ backend/
COPY ml_service/ ml_service/
COPY database/ database/
COPY data/customer/ data/customer/
COPY data/demo/ data/demo/
COPY data/models/ data/models/
COPY scripts/start_backend.py scripts/start_backend.py
COPY --from=web /build/frontend/dist frontend/dist
RUN useradd --create-home --uid 10001 fixrate && mkdir -p /app/var/photos && chown -R fixrate:fixrate /app/var
USER fixrate
EXPOSE 8000
CMD ["python", "scripts/start_backend.py", "--migrate", "--host", "0.0.0.0"]
