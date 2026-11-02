# Журнал фактической проверки backend

Дата проверки: 2026-11-02  
Среда: Windows, Python 3.12, зависимости из `requirements.txt`

| Команда | Результат | Факт |
|---|---|---|
| `$env:PYTHONPATH='backend;.'; .\venv\Scripts\python.exe -m pytest -q tests/backend` (до изменений) | Пройдено | 287 passed, 129 skipped, 1 warning |
| `$env:PYTHONPATH='backend;.'; .\venv\Scripts\python.exe -m pytest -q tests/backend/test_api_hardening.py tests/backend` | Пройдено | 289 passed, 129 skipped, 1 warning |
| `docker compose config` | Пройдено | Compose-файл разобран успешно |
| `docker compose build backend` | Заблокировано | Docker Desktop Linux daemon недоступен (`dockerDesktopLinuxEngine` не найден) |
| `scripts/verify.py` | Не запускалось | PostgreSQL 16 binaries отсутствуют в `C:\Program Files\PostgreSQL\16\bin` |

Пропущенные тесты backend требуют отдельного PostgreSQL стенда и не считаются
подтверждением HTTP/API сценариев. Для чистой машины такой стенд создаётся
командами из [`backend/README.md`](../../backend/README.md). После запуска
Compose и PostgreSQL следует повторно записать сюда фактический результат
`scripts/verify.py`.
