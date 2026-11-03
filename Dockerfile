# syntax=docker/dockerfile:1.7

FROM node:24-bookworm-slim AS frontend-build

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend ./
COPY tests/web /tests/web
RUN npm run build

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --index-url https://download.pytorch.org/whl/cpu torch==2.5.1 && \
    pip install -r requirements.txt

COPY backend ./backend
COPY database ./database
COPY data ./data
COPY ml_service ./ml_service
COPY --from=frontend-build /frontend/dist ./frontend/dist
COPY .env.example ./.env.example

ENV PYTHONPATH=/app/backend:/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
