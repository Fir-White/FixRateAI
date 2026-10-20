"""Unit-тесты доменных схем детекций и нормализации координат BoundingBox."""
import pytest
from pydantic import ValidationError
from app.cv.schemas import BoundingBox, DetectionDTO, CVInferenceResult


def test_bounding_box_valid():
    bbox = BoundingBox(x_min=0.1, y_min=0.2, x_max=0.5, y_max=0.8)
    assert pytest.approx(bbox.width) == 0.4
    assert pytest.approx(bbox.height) == 0.6


def test_bounding_box_inverted_coords_raises():
    with pytest.raises(ValidationError):
        BoundingBox(x_min=0.7, y_min=0.2, x_max=0.3, y_max=0.8)


def test_bounding_box_out_of_range_raises():
    with pytest.raises(ValidationError):
        BoundingBox(x_min=-0.1, y_min=0.0, x_max=0.5, y_max=0.5)
    with pytest.raises(ValidationError):
        BoundingBox(x_min=0.0, y_min=0.0, x_max=1.5, y_max=0.5)


def test_bounding_box_to_pixels():
    bbox = BoundingBox(x_min=0.25, y_min=0.5, x_max=0.75, y_max=1.0)
    # На картинке 800x600:
    # x1 = 0.25 * 800 = 200, x2 = 0.75 * 800 = 600
    # y1 = 0.5 * 600 = 300, y2 = 1.0 * 600 = 600
    pixels = bbox.to_pixel_box(img_width=800, img_height=600)
    assert pixels == (200, 300, 600, 600)


def test_bounding_box_from_pixels():
    bbox = BoundingBox.from_pixels(
        x1=100, y1=200, x2=500, y2=800, img_width=1000, img_height=1000
    )
    assert pytest.approx(bbox.x_min) == 0.1
    assert pytest.approx(bbox.y_min) == 0.2
    assert pytest.approx(bbox.x_max) == 0.5
    assert pytest.approx(bbox.y_max) == 0.8


def test_cv_inference_result_structure():
    bbox = BoundingBox(x_min=0.1, y_min=0.1, x_max=0.4, y_max=0.4)
    det = DetectionDTO(
        class_id=1,
        class_name="facade_crack",
        confidence=0.89,
        bbox=bbox,
    )
    res = CVInferenceResult(
        status="completed",
        model_name="YOLOv8",
        model_version="v2.0",
        image_width=1920,
        image_height=1080,
        inference_time_ms=45,
        detections=[det],
    )
    data = res.model_dump()
    assert data["status"] == "completed"
    assert len(data["detections"]) == 1
    assert data["detections"][0]["class_name"] == "facade_crack"
