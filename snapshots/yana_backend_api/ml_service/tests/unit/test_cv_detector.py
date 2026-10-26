"""Unit-тесты детектора и фасада CV-сервиса."""
import io
import pytest
from PIL import Image
from app.cv.image_io import load_image
from app.cv.mock_detector import MockYoloDetector
from app.cv.service import CVService
from app.cv.yolo_detector import UltralyticsYoloDetector
from app.core.errors import ModelUnavailableError


def make_dummy_image_bytes(width: int = 640, height: int = 480) -> bytes:
    img = Image.new("RGB", (width, height), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_mock_detector_default_crack():
    raw = make_dummy_image_bytes()
    service = CVService(detector=MockYoloDetector(), confidence_threshold=0.25)
    res = service.detect_image(raw)

    assert res.status == "completed"
    assert res.image_width == 640
    assert res.image_height == 480
    assert len(res.detections) == 1
    assert res.detections[0].class_name == "facade_crack"
    assert res.detections[0].confidence == 0.88


def test_mock_detector_scenarios():
    mock = MockYoloDetector()
    service = CVService(detector=mock)
    raw = make_dummy_image_bytes()

    mock.set_scenario("tile_chip")
    res = service.detect_image(raw)
    assert len(res.detections) == 1
    assert res.detections[0].class_name == "tile_chip"

    mock.set_scenario("parking_leak")
    res = service.detect_image(raw)
    assert len(res.detections) == 1
    assert res.detections[0].class_name == "parking_leak"

    mock.set_scenario("empty")
    res = service.detect_image(raw)
    assert len(res.detections) == 0


def test_cv_service_confidence_filter():
    mock = MockYoloDetector()
    mock.set_scenario("facade_crack")  # confidence = 0.88
    # Если порог 0.90, детекция должна отфильтроваться
    service = CVService(detector=mock, confidence_threshold=0.90)
    raw = make_dummy_image_bytes()
    res = service.detect_image(raw)
    assert len(res.detections) == 0


def test_ultralytics_detector_unavailable_when_weights_missing(tmp_path):
    missing_weights = tmp_path / "non_existent_weights.pt"
    detector = UltralyticsYoloDetector(model_path=missing_weights)
    assert not detector.is_available()

    service = CVService(detector=detector)
    raw = make_dummy_image_bytes()
    res = service.detect_image(raw)

    assert res.status == "unavailable"
    assert len(res.warnings) == 1
    assert "не найдены" in res.warnings[0]
