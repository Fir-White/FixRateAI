"""Сквозные интеграционные тесты трёх пилотных демонстрационных сценариев FixRate AI:
1. facade_crack (Трещина фасада)
2. tile_chip (Скол плитки)
3. parking_leak (Протечка парковки)
"""
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.cv.mock_detector import MockYoloDetector
from app.cv.service import CVService
from app.main import create_app
from app.pipeline.orchestrator import PipelineOrchestrator
from app.api.v1.process import get_orchestrator


@pytest.fixture
def app_with_mock_cv():
    app = create_app()
    mock_cv = MockYoloDetector()
    cv_service = CVService(detector=mock_cv)
    orchestrator = PipelineOrchestrator(cv_service=cv_service)

    # Переопределяем зависимость оркестратора для тестов
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator
    return app, mock_cv


def test_scenario_1_facade_crack(app_with_mock_cv):
    """Сценарий 1: facade_crack.
    
    1. Пользователь загружает фото трещины без указания длины.
       -> Сервис возвращает status="needs_clarification" с вопросом о длине.
    2. Пользователь присылает уточнение с длиной 4.5 метра.
       -> Сервис возвращает статус "completed", сметную позицию DEMO-FACADE-CRACK-01
          и точный расчёт: S = 4.5 * 0.1 = 0.45 м2, стоимость = 0.45 * 850 = 382.50 RUB.
    """
    app, mock_cv = app_with_mock_cv
    mock_cv.set_scenario("facade_crack")

    with TestClient(app) as client:
        # Шаг 1: Загрузка без измерений
        res1 = client.post(
            "/api/v1/process",
            json={
                "description_text": "Обнаружена вертикальная трещина на фасаде дома",
                "files": [{"file_id": "photo-crack-1", "file_type": "image"}],
            },
        )
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["status"] == "needs_clarification"
        assert len(data1["clarification_questions"]) == 1
        assert data1["clarification_questions"][0]["field_name"] == "length_m"

        # Шаг 2: Повторный запуск с уточнением длины
        res2 = client.post(
            "/api/v1/process",
            json={
                "description_text": "Обнаружена вертикальная трещина на фасаде дома",
                "files": [{"file_id": "photo-crack-1", "file_type": "image"}],
                "known_measurements": [
                    {"parameter_name": "length_m", "numeric_value": "4.5", "unit_code": "m"}
                ],
            },
        )
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["status"] == "completed"
        assert len(data2["estimate_items"]) == 1
        item = data2["estimate_items"][0]
        assert item["rate_code"] == "DEMO-FACADE-CRACK-01"
        assert Decimal(str(item["quantity"])) == Decimal("0.4500")
        assert Decimal(str(item["line_total"])) == Decimal("382.50")
        assert Decimal(str(data2["total_cost"])) == Decimal("382.50")


def test_scenario_2_tile_chip(app_with_mock_cv):
    """Сценарий 2: tile_chip.
    
    Пользователь загружает фото скола плитки и указывает 'откололось 4 плитки'.
    -> Модель CV детектирует tile_chip, RAG подбирает DEMO-TILE-CHIP-01 (1200 руб/м2),
       расчётный модуль вычисляет площадь 4 * 0.09 = 0.36 м2,
       стоимость = 0.36 * 1200 = 432.00 RUB.
    """
    app, mock_cv = app_with_mock_cv
    mock_cv.set_scenario("tile_chip")

    with TestClient(app) as client:
        res = client.post(
            "/api/v1/process",
            json={
                "description_text": "На крыльце откололось 4 плитки облицовки",
                "files": [{"file_id": "photo-tile-1", "file_type": "image"}],
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "completed"
        assert len(data["estimate_items"]) == 1
        item = data["estimate_items"][0]
        assert item["rate_code"] == "DEMO-TILE-CHIP-01"
        assert Decimal(str(item["quantity"])) == Decimal("0.3600")
        assert Decimal(str(item["line_total"])) == Decimal("432.00")
        assert Decimal(str(data["total_cost"])) == Decimal("432.00")


def test_scenario_3_parking_leak(app_with_mock_cv):
    """Сценарий 3: parking_leak.
    
    Пользователь загружает фото протечки на парковке площадью 10 м2.
    -> CV классифицирует parking_leak, RAG подбирает DEMO-PARKING-LEAK-01 (1500 руб/м2).
       Так как протечка требует обязательной инструментальной верификации причины,
       сервис возвращает статус 'needs_review' и предупреждение для сметчика,
       но смета рассчитывается детерминированно:
       10 м2 * 1.15 = 11.5 м2 * 1500 = 17250.00 RUB.
    """
    app, mock_cv = app_with_mock_cv
    mock_cv.set_scenario("parking_leak")

    with TestClient(app) as client:
        res = client.post(
            "/api/v1/process",
            json={
                "description_text": "В подземном паркинге протечка, мокрое пятно площадью 10 м2",
                "files": [{"file_id": "photo-leak-1", "file_type": "image"}],
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "needs_review"
        assert len(data["warnings"]) > 0
        assert any("скрытых причин" in w for w in data["warnings"])
        assert len(data["estimate_items"]) == 1
        item = data["estimate_items"][0]
        assert item["rate_code"] == "DEMO-PARKING-LEAK-01"
        assert Decimal(str(item["quantity"])) == Decimal("11.5000")
        assert Decimal(str(item["line_total"])) == Decimal("17250.00")
        assert Decimal(str(data["total_cost"])) == Decimal("17250.00")
