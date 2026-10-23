"""Корневой роутер бизнес-API версии 1."""
from fastapi import APIRouter

from app.api.v1 import requests
from app.api.v1 import photos

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(requests.router)
api_v1_router.include_router(photos.router)
