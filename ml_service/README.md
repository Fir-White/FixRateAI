# FixRate AI — ML Service

Интеллектуальный сервис детекции дефектов (CV/YOLO), семантического поиска нормативов (Hybrid RAG) и детерминированного расчёта сметной стоимости.

## Архитектура и документация
- [ML_PIPELINE.md](ML_PIPELINE.md) — подробная целевая архитектура и спецификация AI-пайплайна
- [PLAN.md](PLAN.md) — архитектурный план и дорожная карта разработки
- [PRODUCT.md](PRODUCT.md) — продуктовые сценарии и границы MVP
- [TASKS.md](TASKS.md) — полный реестр микрозадач со статусами
- [PROGRESS.md](PROGRESS.md) — оперативный журнал разработки

## Быстрый запуск

### 1. Локальный запуск через виртуальное окружение
```bash
# Создание окружения и установка зависимостей
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# Запуск тестов
pytest -v

# Запуск сервиса на порту 8001
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

Swagger документация доступна по адресу: `http://localhost:8001/docs`.

### 2. Запуск в Docker
```bash
docker build -t fixrate-ml-service .
docker run -p 8001:8001 fixrate-ml-service
```

### 3. Подключение GigaChat (Сбер) для анализа текста
Для перехода с эвристического mock-провайдера на боевую языковую модель GigaChat укажите в `.env`:
```env
ML_LLM_PROVIDER="gigachat"
ML_GIGACHAT_CREDENTIALS="<auth_key_из_личного_кабинета_Сбера>"
ML_GIGACHAT_SCOPE="GIGACHAT_API_PERS"   # или GIGACHAT_API_CORP
ML_GIGACHAT_MODEL="GigaChat-Pro"       # или GigaChat-Lite / GigaChat-Max
```
Проверка подключения:
```bash
python scripts/test_gigachat.py
```

## Ключевые эндпоинты API
- `GET /health` — проверка работоспособности сервиса и доступности моделей.
- `POST /api/v1/process` — сквозной запуск анализа дефектов и расчёта сметы.

## Поддерживаемые пилотные сценарии (MVP)
1. `facade_crack` — трещина наружной оштукатуренной/кирпичной стены фасада.
2. `tile_chip` — скол и разрушение керамической облицовочной плитки.
3. `parking_leak` — протечка и разрушение гидроизоляции подземного паркинга (с предупреждением о скрытых причинах).
