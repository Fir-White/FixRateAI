"""Эндпоинт здоровья сервиса."""

from fastapi import APIRouter

router = APIRouter(tags=["Служебные"])


@router.get(
    "/health",
    summary="Проверка живости сервиса",
    description=(
        "Возвращает статус процесса API. "
        "Не проверяет БД (для этого позже будет GET /ready)."
    ),
    response_description="Сервис запущен",
)
def health() -> dict[str, str]:
    return {"status": "ok"}
