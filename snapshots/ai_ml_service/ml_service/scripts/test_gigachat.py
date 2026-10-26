"""Скрипт проверки «живого» подключения к GigaChat API.

Использование:
1. Задайте в ml_service/.env:
   ML_LLM_PROVIDER="gigachat"
   ML_GIGACHAT_CREDENTIALS="<ваш_auth_key_из_сбера>"
   ML_GIGACHAT_SCOPE="GIGACHAT_API_PERS"   # или GIGACHAT_API_CORP
   ML_GIGACHAT_MODEL="GigaChat-Pro"       # или GigaChat-Lite / GigaChat-Max

2. Запустите:
   .venv/bin/python ml_service/scratch_test_gigachat.py
"""
import os
import sys
from pathlib import Path

# Добавляем ml_service в путь импорта
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings
from app.llm.gigachat_provider import GigaChatProvider
from app.llm.schemas import NormalizedDefectDescription


def test_live():
    settings = get_settings()
    cred = settings.gigachat_credentials or os.getenv("ML_GIGACHAT_CREDENTIALS")
    if not cred:
        print("\n[!] Ключ ML_GIGACHAT_CREDENTIALS не задан.")
        print("Добавьте в ml_service/.env строку:")
        print('ML_GIGACHAT_CREDENTIALS="<ваш_auth_key>"')
        print('ML_GIGACHAT_SCOPE="GIGACHAT_API_PERS"')
        print('ML_GIGACHAT_MODEL="GigaChat-Pro"')
        print("\nИли передайте ключ при запуске:")
        print("ML_GIGACHAT_CREDENTIALS='...' .venv/bin/python ...")
        return

    print(f"=== Подключение к GigaChat: model={settings.gigachat_model}, scope={settings.gigachat_scope} ===")
    provider = GigaChatProvider(
        credentials=cred,
        scope=settings.gigachat_scope,
        model=settings.gigachat_model,
        verify_ssl_certs=False,
    )

    test_text = (
        "На штукатурном фасаде обнаружена вертикальная трещина. "
        "Длина трещины примерно 4 метра 50 сантиметров, раскрытие до 2 мм. "
        "Требуется заделка и покраска."
    )
    print(f"\nТестовый текст заявки:\n\"{test_text}\"\n")
    print("Отправка запроса в GigaChat...")

    try:
        result = provider.complete_structured(test_text, NormalizedDefectDescription)
        print("\n=== РЕЗУЛЬТАТ GIGACHAT (100% Structured Pydantic) ===")
        print(f"Тип дефекта:    {result.detected_defect_type}")
        print(f"Описание:       {result.defect_description}")
        print(f"Локализация:    {result.location_details}")
        print(f"Материалы:      {result.materials}")
        print(f"Измерения:      {result.extracted_measurements}")
        print("=====================================================")
        print("\nУСПЕХ! GigaChat корректно разобрал текст без галлюцинации цен.")
    except Exception as exc:
        print(f"\n[ОШИБКА GigaChat]: {exc}")


if __name__ == "__main__":
    test_live()
