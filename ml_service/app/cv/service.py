"""Фасад подсистемы компьютерного зрения (CVService)."""
import logging
import time
from pathlib import Path
from typing import BinaryIO

from app.core.config import get_settings
from app.core.errors import ModelUnavailableError
from app.cv.image_io import load_image
from app.cv.mock_detector import MockYoloDetector
from app.cv.schemas import CVInferenceResult
from app.cv.yolo_detector import BaseDetectorProtocol, UltralyticsYoloDetector

logger = logging.getLogger("app.cv.service")


class CVService:
    """Сервис инференса компьютерного зрения FixRate AI."""

    def __init__(
        self,
        detector: BaseDetectorProtocol | None = None,
        confidence_threshold: float | None = None,
    ) -> None:
        settings = get_settings()
        self.confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else settings.cv_confidence_threshold
        )

        if detector is not None:
            self.detector = detector
        elif settings.cv_provider == "yolo":
            self.detector = UltralyticsYoloDetector()
        else:
            self.detector = MockYoloDetector()

    def detect_image(self, image_input: str | Path | bytes | BinaryIO) -> CVInferenceResult:
        """Безопасно декодирует изображение, запускает детектор и фильтрует результат."""
        rgb_image, width, height = load_image(image_input)

        start_time = time.perf_counter()
        try:
            raw_detections = self.detector.detect(rgb_image)
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)

            # Фильтрация по порогу уверенности
            valid_detections = [
                d for d in raw_detections if d.confidence >= self.confidence_threshold
            ]

            return CVInferenceResult(
                status="completed",
                model_name=type(self.detector).__name__,
                model_version="v2.0",
                image_width=width,
                image_height=height,
                inference_time_ms=elapsed_ms,
                detections=valid_detections,
                warnings=[],
            )

        except ModelUnavailableError as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            logger.warning("Модель CV недоступна: %s", e)
            return CVInferenceResult(
                status="unavailable",
                model_name=type(self.detector).__name__,
                model_version="v2.0",
                image_width=width,
                image_height=height,
                inference_time_ms=elapsed_ms,
                detections=[],
                warnings=[str(e)],
            )
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            logger.error("Ошибка при выполнении CV инференса: %s", e, exc_info=True)
            return CVInferenceResult(
                status="failed",
                model_name=type(self.detector).__name__,
                model_version="v2.0",
                image_width=width,
                image_height=height,
                inference_time_ms=elapsed_ms,
                detections=[],
                warnings=[f"Ошибка CV: {e}"],
            )
