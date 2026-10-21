"""Юнит-тесты для GigaChatProvider и интеграции с LLMGateway."""
from decimal import Decimal
from unittest.mock import MagicMock, patch
import pytest

from app.llm.gigachat_provider import GigaChatProvider
from app.llm.gateway import LLMGateway
from app.llm.schemas import NormalizedDefectDescription


def test_gigachat_provider_init():
    provider = GigaChatProvider(
        credentials="test_cred",
        scope="GIGACHAT_API_PERS",
        model="GigaChat-Pro",
        verify_ssl_certs=False,
    )
    assert provider.credentials == "test_cred"
    assert provider.scope == "GIGACHAT_API_PERS"
    assert provider.model == "GigaChat-Pro"
    assert provider.verify_ssl_certs is False


def test_gigachat_provider_missing_credentials_raises():
    provider = GigaChatProvider(credentials="")
    with pytest.raises(ValueError, match="credentials не настроены"):
        provider.complete_structured("тест", NormalizedDefectDescription)


def test_gigachat_provider_chat_parse_success():
    expected_defect = NormalizedDefectDescription(
        detected_defect_type="facade_crack",
        defect_description="Трещина фасада",
        location_details="наружная стена",
        materials=["штукатурка"],
        extracted_measurements={"length_m": Decimal("4.5")},
    )

    mock_client = MagicMock()
    mock_client.chat_parse.return_value = (MagicMock(), expected_defect)

    provider = GigaChatProvider(credentials="test_cred")
    provider._client = mock_client

    result = provider.complete_structured("Трещина фасада 4.5м", NormalizedDefectDescription)
    assert result == expected_defect
    mock_client.chat_parse.assert_called_once()


def test_gigachat_provider_fallback_to_json_chat():
    mock_client = MagicMock()
    # chat_parse падает
    mock_client.chat_parse.side_effect = Exception("Not supported")

    # chat.create возвращает JSON
    raw_json = """{
        "detected_defect_type": "tile_chip",
        "defect_description": "Скол плитки на крыльце",
        "location_details": "крыльцо",
        "materials": ["керамогранит"],
        "extracted_measurements": {"count": 2},
        "unclear_aspects": []
    }"""
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = raw_json
    mock_response.choices = [mock_choice]
    mock_client.chat.return_value = mock_response

    provider = GigaChatProvider(credentials="test_cred")
    provider._client = mock_client

    result = provider.complete_structured("Скол двух плиток", NormalizedDefectDescription)
    assert result.detected_defect_type == "tile_chip"
    assert result.extracted_measurements["count"] == Decimal("2")
    assert "керамогранит" in result.materials


def test_gigachat_provider_handles_markdown_codeblock():
    mock_client = MagicMock()
    mock_client.chat_parse.side_effect = Exception("Not supported")

    content_with_markdown = """Вот структурированный ответ:
```json
{
    "detected_defect_type": "parking_leak",
    "defect_description": "Протечка в паркинге",
    "location_details": "подземный паркинг",
    "materials": ["бетон"],
    "extracted_measurements": {"area_m2": 15.0},
    "unclear_aspects": []
}
```
Спасибо за обращение!"""
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = content_with_markdown
    mock_response.choices = [mock_choice]
    mock_client.chat.return_value = mock_response

    provider = GigaChatProvider(credentials="test_cred")
    provider._client = mock_client

    result = provider.complete_structured("Протечка 15 м2", NormalizedDefectDescription)
    assert result.detected_defect_type == "parking_leak"
    assert result.extracted_measurements["area_m2"] == Decimal("15.0")


def test_gateway_with_gigachat_fallback_on_network_error():
    mock_failing_provider = MagicMock()
    mock_failing_provider.complete_structured.side_effect = ConnectionError("GigaChat timeout")

    gateway = LLMGateway(provider=mock_failing_provider)
    # При сбое GigaChat шлюз должен безопасно переключиться на эвристический MockLLMProvider
    result = gateway.normalize_user_text("Обнаружена трещина на фасаде длиной 3.5 метра")
    assert result.detected_defect_type == "facade_crack"
    assert result.extracted_measurements.get("length_m") == Decimal("3.5")
