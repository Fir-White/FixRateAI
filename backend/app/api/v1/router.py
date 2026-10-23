"""Корневой роутер бизнес-API версии 1."""
from fastapi import APIRouter

from app.api.v1 import requests

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(requests.router)
