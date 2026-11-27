# Профили запуска FixRate AI

| Профиль | Состав | Данные и внешние вызовы |
|---|---|---|
| **Development** | `compose.yaml`, сборка из исходников | Без автоматического seed при прямом `docker compose up`; по умолчанию профиль полномочий `legacy`. Только loopback. |
| **Demo** | `compose.yaml` + `compose.demo.yaml`, отдельный Compose project | Профиль `mvp`, v4, локальный режим. Учебное заполнение выполняется явно и только в новом проекте. |
| **Deployment / Core** | `deploy/compose.yaml` или Quick Start ZIP, образы по digest | Первый администратор через `/setup`, без seed, автоустановки моделей и платного AI. API, PostgreSQL и worker не имеют опубликованных портов. |
| **Ollama** | `compose.ollama.yaml` поверх исходного Compose или внешний локальный Ollama для Core | Укажите имя и SHA‑256 заранее загруженной модели. Для анализа фотографий требуется vision‑модель; доступность чата не гарантирует CV. |
| **Cloud (закрытый)** | `compose.cloud.yaml` из исходников либо `deploy/compose.cloud.yaml` поверх Core | Явный выбор AI Tunnel и локальный секрет. Только частный loopback‑стенд; публичный доступ требует проверенного учёта расходов и отдельного допуска. |

## Development и учебное демо

При использовании Docker подготовьте отдельный приватный env‑файл с `POSTGRES_PASSWORD` (случайная URL‑safe строка), `FIXRATE_DEMO_PASSWORD` (уникальный учебный пароль) и свободным `FIXRATE_PORT`. Не используйте конфигурацию или тома действующего стенда. `-p` задаёт имя нового проекта и должно оставаться одинаковым во всех командах.

```console
docker compose -p fixrate-demo-local --env-file <private-env> -f compose.yaml -f compose.demo.yaml config --quiet
docker compose -p fixrate-demo-local --env-file <private-env> -f compose.yaml -f compose.demo.yaml up -d --build --wait
docker compose -p fixrate-demo-local --env-file <private-env> -f compose.yaml -f compose.demo.yaml exec -T -e FIXRATE_DEMO_PASSWORD app python -m app.manage seed-demo --configure-accounts
```

Для последней команды безопасно передайте `FIXRATE_DEMO_PASSWORD` как переменную окружения оболочки: `exec -e NAME` наследует её от Compose CLI, а не из `--env-file`. Учебные логины: `fixrate-demo-chief_engineer@example.test` и `fixrate-demo-1@example.test`. Для проверки паритета добавьте `engineer` в `FIXRATE_DEMO_ROLES` до старта. Команда `python scripts/start_local.py` — прежний интерактивный путь из исходников с собственным проектом `fixrate-local` и локальным файлом учётных данных. [Первый запуск](first-run.md).

## Deployment / Core

[Quick Start](../../quick_start/README.md) использует `.env` и `images.env`. `config --quiet` проверяет структуру и обязательные переменные, но не наличие образов, доступность портов, совместимость миграций или работу контейнеров. `ps` должен показать здоровые сервисы; `migrate` завершится с кодом 0. При отказе сохраните данные, прочитайте локальные логи `migrate`, `api` и `web`, удалите секреты перед передачей логов.

Для обновления используйте проверенный установщик, совместимую версию и согласованный backup PostgreSQL и файлов. Проверяйте восстановление на отдельном проекте. Для отката верните прежний комплект и сохранённый backup, если миграции несовместимы; одного отката тега образа недостаточно. Не запускайте `down -v`. [Точные команды установки, диагностики, backup и restore](installation.md).

HTTPS: по умолчанию Core привязан к `127.0.0.1`. Для разрешённого внешнего размещения используйте Caddy или существующий шлюз, корректный DNS, защищённые cookies (`COOKIE_SECURE=true`) и доверенные прокси, ограниченные адресами фактического шлюза. Снаружи доступен только веб-вход; ключ первичной настройки не должен оставаться общедоступным. Проверка HTTPS на внешнем домене не входит в этот локальный прогон.

## Локальные модели и облако

Для Ollama задаются `OLLAMA_CHAT_MODEL`, `OLLAMA_CHAT_DIGEST` (`sha256:…` из `/api/tags`) и URL доступного **из контейнера** локального узла. В Deployment используются `OLLAMA_BASE_URL`, `OLLAMA_VISION_MODEL` и `OLLAMA_VISION_DIGEST` для vision; `PHOTO_REVIEW_PROVIDER=ollama` включает этот транспорт явно. Сервис с `--profile ollama` не публикует порт и не скачивает веса автоматически. [Подготовка и границы Ollama](installation.md#status-doctor-ollama).

Для закрытой облачной проверки указывайте override последним и передавайте `AITUNNEL_API_KEY` из приватного окружения. Для архива Core используйте `-f compose.yaml -f compose.cloud.yaml` (Compose ≥2.24.4 для `!override`). Оверрайд принудительно оставляет только веб-порт `127.0.0.1`, даже если базовый Core настроен на внешний HTTPS. Не подключайте внешний прокси. Не добавляйте секрет в Git, ZIP, скриншот, историю чата или командную строку. Проверка конфигурации не обращается к модели. Публичное облако вне допуска без подтверждённого ограничения расходов и частоты. [Настройки AI Tunnel](aitunnel.md).
