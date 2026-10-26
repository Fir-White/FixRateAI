"""Детерминированный Mock-детектор для модульного и интеграционного тестирования."""
from PIL import Image
from app.cv.schemas import BoundingBox, DetectionDTO


class MockYoloDetector:
    """Mock-детектор с предсказуемыми детекциями для пилотных сценариев."""

    def __init__(self, predefined_detections: list[DetectionDTO] | None = None) -> None:
        self.predefined_detections = predefined_detections
        self.call_count = 0

    def is_available(self) -> bool:
        return True

    def set_scenario(self, scenario_name: str) -> None:
        """Настраивает детекции под конкретный пилотный сценарий."""
        if scenario_name == "facade_crack":
            self.predefined_detections = [
                DetectionDTO(
                    class_id=1,
                    class_name="facade_crack",
                    confidence=0.88,
                    bbox=BoundingBox(x_min=0.35, y_min=0.1, x_max=0.45, y_max=0.9),
                )
            ]
        elif scenario_name == "tile_chip":
            self.predefined_detections = [
                DetectionDTO(
                    class_id=2,
                    class_name="tile_chip",
                    confidence=0.91,
                    bbox=BoundingBox(x_min=0.4, y_min=0.4, x_max=0.6, y_max=0.6),
                )
            ]
        elif scenario_name == "parking_leak":
            self.predefined_detections = [
                DetectionDTO(
                    class_id=3,
                    class_name="parking_leak",
                    confidence=0.85,
                    bbox=BoundingBox(x_min=0.2, y_min=0.2, x_max=0.8, y_max=0.7),
                )
            ]
        elif scenario_name == "empty":
            self.predefined_detections = []
        else:
            self.predefined_detections = []

    def detect(self, image: Image.Image) -> list[DetectionDTO]:
        self.call_count += 1
        if self.predefined_detections is not None:
            return list(self.predefined_detections)

        # Дефолтная детекция пилотной трещины фасада
        return [
            DetectionDTO(
                class_id=1,
                class_name="facade_crack",
                confidence=0.88,
                bbox=BoundingBox(x_min=0.3, y_min=0.1, x_max=0.5, y_max=0.8),
            )
        ]
