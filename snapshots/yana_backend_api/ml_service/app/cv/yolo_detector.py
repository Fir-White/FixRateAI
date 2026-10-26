"""Протокол детектора и реализация адаптера Ultralytics YOLO."""
import logging
from pathlib import Path
from typing import Protocol, runtime_checkable
from PIL import Image

from app.core.config import get_settings
from app.core.errors import ModelUnavailableError
from app.cv.schemas import BoundingBox, DetectionDTO

logger = logging.getLogger("app.cv.detector")


@runtime_checkable
class BaseDetectorProtocol(Protocol):
    """Интерфейс детектора строительных дефектов."""

    def is_available(self) -> bool:
        """Проверяет доступность весов и инициализации модели."""
        ...

    def detect(self, image: Image.Image) -> list[DetectionDTO]:
        """Выполняет инференс по изображению и возвращает список детекций."""
        ...


class UltralyticsYoloDetector:
    """Адаптер для библиотеки Ultralytics YOLO.
    
    Загружает модель один раз при старте. Если веса отсутствуют,
    корректно переходит в статус unavailable.
    """

    def __init__(self, model_path: str | Path | None = None) -> None:
        settings = get_settings()
        self.model_path = Path(model_path or settings.cv_model_path)
        self._model = None
        self._load_attempted = False

    def is_available(self) -> bool:
        """Проверяет физическое наличие файла весов."""
        return self.model_path.is_file()

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        if not self.is_available():
            raise ModelUnavailableError(
                f"Целевые веса YOLO строительных дефектов не найдены по пути: {self.model_path}. "
                "Инференс заблокирован до предоставления обученных весов."
            )

        try:
            from ultralytics import YOLO  # type: ignore
            logger.info("Загрузка весов YOLO из %s", self.model_path)
            self._model = YOLO(str(self.model_path))
        except ImportError as e:
            raise ModelUnavailableError(f"Пакет ultralytics не установлен в окружении: {e}") from e
        except Exception as e:
            raise ModelUnavailableError(f"Ошибка загрузки весов модели YOLO: {e}") from e

    def detect(self, image: Image.Image) -> list[DetectionDTO]:
        self._ensure_loaded()
        width, height = image.size

        # Запуск инференса
        results = self._model(image, verbose=False)
        detections: list[DetectionDTO] = []

        if not results:
            return detections

        first_res = results[0]
        names = first_res.names or {}

        for box in first_res.boxes:
            cls_id = int(box.cls.item())
            cls_name = names.get(cls_id, f"class_{cls_id}")
            conf = float(box.conf.item())

            # Координаты рамки в пикселях (xyxy)
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            bbox = BoundingBox.from_pixels(x1, y1, x2, y2, img_width=width, img_height=height)

            detections.append(
                DetectionDTO(
                    class_id=cls_id,
                    class_name=cls_name,
                    confidence=conf,
                    bbox=bbox,
                )
            )

        return detections
