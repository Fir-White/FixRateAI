"""Пакет компьютерного зрения (CV) на базе YOLO."""
from app.cv.image_io import load_image
from app.cv.schemas import BoundingBox, DetectionDTO, CVInferenceResult
from app.cv.yolo_detector import BaseDetectorProtocol, UltralyticsYoloDetector
from app.cv.mock_detector import MockYoloDetector
from app.cv.service import CVService

__all__ = [
    "load_image",
    "BoundingBox",
    "DetectionDTO",
    "CVInferenceResult",
    "BaseDetectorProtocol",
    "UltralyticsYoloDetector",
    "MockYoloDetector",
    "CVService",
]
