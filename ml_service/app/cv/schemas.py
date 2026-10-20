"""Схемы данных компьютерного зрения (YOLO) и нормализация координат."""
from typing import Any
from pydantic import BaseModel, Field, model_validator


class BoundingBox(BaseModel):
    """Нормализованный прямоугольник детекции (координаты от 0.0 до 1.0)."""
    x_min: float = Field(ge=0.0, le=1.0, description="Левая граница (относительно ширины)")
    y_min: float = Field(ge=0.0, le=1.0, description="Верхняя граница (относительно высоты)")
    x_max: float = Field(ge=0.0, le=1.0, description="Правая граница (относительно ширины)")
    y_max: float = Field(ge=0.0, le=1.0, description="Нижняя граница (относительно высоты)")

    @model_validator(mode="after")
    def validate_box_order(self) -> "BoundingBox":
        if self.x_max < self.x_min:
            raise ValueError(f"x_max ({self.x_max}) не может быть меньше x_min ({self.x_min})")
        if self.y_max < self.y_min:
            raise ValueError(f"y_max ({self.y_max}) не может быть меньше y_min ({self.y_min})")
        return self

    @property
    def width(self) -> float:
        return self.x_max - self.x_min

    @property
    def height(self) -> float:
        return self.y_max - self.y_min

    def to_pixel_box(self, img_width: int, img_height: int) -> tuple[int, int, int, int]:
        """Преобразует нормализованные координаты в целочисленные пиксели (x1, y1, x2, y2)."""
        x1 = int(round(self.x_min * img_width))
        y1 = int(round(self.y_min * img_height))
        x2 = int(round(self.x_max * img_width))
        y2 = int(round(self.y_max * img_height))
        # Ограничиваем рамки физическими размерами кадра
        x1 = max(0, min(x1, img_width))
        x2 = max(0, min(x2, img_width))
        y1 = max(0, min(y1, img_height))
        y2 = max(0, min(y2, img_height))
        return (x1, y1, x2, y2)

    @classmethod
    def from_pixels(
        cls,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        img_width: int,
        img_height: int,
    ) -> "BoundingBox":
        """Создаёт нормализованный BoundingBox из пиксельных координат с безопасным клиппингом."""
        if img_width <= 0 or img_height <= 0:
            raise ValueError(f"Недопустимые размеры изображения: {img_width}x{img_height}")

        norm_x1 = max(0.0, min(float(x1) / img_width, 1.0))
        norm_y1 = max(0.0, min(float(y1) / img_height, 1.0))
        norm_x2 = max(0.0, min(float(x2) / img_width, 1.0))
        norm_y2 = max(0.0, min(float(y2) / img_height, 1.0))

        # Гарантируем правильный порядок
        real_x_min = min(norm_x1, norm_x2)
        real_x_max = max(norm_x1, norm_x2)
        real_y_min = min(norm_y1, norm_y2)
        real_y_max = max(norm_y1, norm_y2)

        return cls(x_min=real_x_min, y_min=real_y_min, x_max=real_x_max, y_max=real_y_max)


class DetectionDTO(BaseModel):
    """Единичная детекция видимого строительного дефекта."""
    class_id: int
    class_name: str
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: BoundingBox
    polygon: list[tuple[float, float]] | None = None


class CVInferenceResult(BaseModel):
    """Полный результат инференса компьютерного зрения по изображению."""
    status: str = "completed"  # "completed" | "unavailable" | "failed"
    model_name: str = "YOLO"
    model_version: str = "v1.0"
    image_width: int
    image_height: int
    inference_time_ms: int = 0
    detections: list[DetectionDTO] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
