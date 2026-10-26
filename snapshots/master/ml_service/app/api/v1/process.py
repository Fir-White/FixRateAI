"""API эндпоинт запуска обработки AI-пайплайна."""
from fastapi import APIRouter, Depends
from app.pipeline.orchestrator import PipelineOrchestrator
from app.schemas.request import JobRequestDTO
from app.schemas.response import JobResponseDTO

router = APIRouter(tags=["Pipeline Processing"])

# Глобальный экземпляр оркестратора (инициализируется один раз на процесс)
_orchestrator_instance: PipelineOrchestrator | None = None


def get_orchestrator() -> PipelineOrchestrator:
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = PipelineOrchestrator()
    return _orchestrator_instance


@router.post(
    "/process",
    response_model=JobResponseDTO,
    summary="Запуск сквозной обработки дефекта и расчёта сметы",
    description=(
        "Принимает фотографии, текст описания и характеристики объекта. "
        "Выполняет детекцию дефекта (YOLO), семантическую нормализацию (LLM), "
        "поиск расценок (RAG) и детерминированный расчёт сметы. "
        "При нехватке физических измерений возвращает статус needs_clarification."
    ),
)
def process_job(
    request: JobRequestDTO,
    orchestrator: PipelineOrchestrator = Depends(get_orchestrator),
) -> JobResponseDTO:
    """Обрабатывает задачу и возвращает смету либо запрос на уточнение параметров."""
    return orchestrator.process_job(request)
