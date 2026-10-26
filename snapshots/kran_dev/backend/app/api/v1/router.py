"""Корневой роутер бизнес-API версии 1 (префикс /api/v1).

Сейчас пустой — это зарезервированное место. Следующие карточки подключают сюда:
auth (3), requests (3), photos (5), estimates (6). Версию в пути не меняем без согласования:
фронтенд будет жить на стабильных путях.
"""
from fastapi import APIRouter

api_v1_router = APIRouter(prefix="/api/v1")

# Пример подключения в будущем:
# from app.api.v1 import requests
# api_v1_router.include_router(requests.router)
