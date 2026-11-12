# Запуск и эксплуатация

## Работы и реестр в kran_dev, 13.11.2026

Текущий образ на `http://127.0.0.1:8000` — `fixrate-ai:kran-dev-b286198`, код `b286198`. Добавлены реестр/детали/Excel и выбор здания; применена миграция 012. Имена рабочего приложения/БД остаются `fixrate-recovery-20261112-app` / `fixrate-recovery-20261112-db`; окружение, фото-volume, сеть, порт и restart policy сохранены. Health — ready/healthy.

До замены сохранены dump и приватная конфигурация в `var/deploy-b286198/`. Сверены все прежние значения строк и SHA-256 фотографий. При сравнении `engineering_systems` исключены только два новых столбца 012 (`system_group`, `revision`); прежние поля не менялись. Старый контейнер остановлен как `fixrate-recovery-20261112-app-before-b286198`. Проверка реального реестра и export→preview выполнена только чтением; бизнес-данные браузерными проверками не менялись. [Возможности и ограничения](registry.md), [результаты проверок](verification.md#13112026-работы-реестр-детали-и-excel).

## Обновление рабочего стенда из kran_dev, 12.11.2026

На `http://127.0.0.1:8000` развёрнут `fixrate-ai:kran-dev-8f2c102`, исходники приложения `8f2c10243f1e7c8c18f6dfe5ebaf01c4426006af`. Включены основы интеллектуального планирования и исправление scrollbar/геометрии Aurora. Применена миграция 011. Контейнер приложения — `fixrate-recovery-20261112-app`, PostgreSQL — `fixrate-recovery-20261112-db`; это существующий восстановленный стенд, а не Compose-проект `fixrate-local` из исторических инструкций ниже.

Настройки окружения, сеть, restart policy, порт и фото-volume сохранены. Зависимости взяты из прежнего проверенного образа, весь код backend/ML/миграций и production SPA скопирован из актуальных исходников в новый образ. До переключения сохранены dump БД, конфигурации, хеши прежних строк и файлов в приватный `var/deploy-8f2c102/` текущего worktree. После запуска все прежние строки и фотографии совпали; `/api/health` — ready, Docker health — healthy. Старый контейнер оставлен остановленным как `fixrate-recovery-20261112-app-before-8f2c102` для управляемого отката; dump не восстанавливается поверх новых пользовательских событий автоматически.

## Редизайн v2 в отдельном worktree, 07.11.2026

В worktree `.worktrees/frontend-redesign-v2` запустите из каталога `frontend`: `$env:VITE_DEMO_MODE='false'; npm.cmd run dev -- --host 127.0.0.1 --port 5174`. Новый интерфейс доступен на http://127.0.0.1:5174 и обращается через Vite proxy к существующему API :8000. Учётные данные остаются в приватном `var/compose-local/accounts.txt` исходного checkout. :8000 продолжает обслуживать собственную сборку; запуск Vite не является deploy. Для безопасной проверки изменений используйте отдельную QA-БД согласно [регрессии](../redesign-v2/REGRESSION.md).

Исходная ветка `frontend_polished` сохранена на `422eacf9`. Откат UI — остановить только Vite редизайна и открыть прежнюю сборку; не восстанавливать старый dump поверх новых бизнес-событий. Отдельно по разрешению владельца на локальном presentation-объекте восстановлены 117 связей оборудования; кодовый откат их не отменяет. [История, backup и границы](../redesign-v2/FINAL_REPORT.md).

## Актуальный локальный стенд, 06.11.2026

На `http://127.0.0.1:8000` работает образ `fixrate-ai:notice-copy` с UI из frontend_polished, миграциями 001–010 и четырьмя активными ролями на ЖК «Сосновый парк». Реквизиты находятся только в игнорируемом `var/compose-local/accounts.txt`. Остальные исторические сотрудники/учебный объект отключены, ссылки отчётов сохранены. Один активный исполнитель не покрывает операцию 1.4 с требованием двух работников; полный состав необходимо обеспечить отдельно, правило не ослабляется.

Повторный локальный запуск: `python scripts/start_local.py --bundled-image fixrate-ai:notice-copy --cloud-ai --presentation`. Этот tag существует на данном компьютере; на чистой машине после настройки зависимостей и `.env` используйте `python scripts/start_local.py --cloud-ai --presentation`. Обычный bootstrap создаёт исходный набор seed: сокращение активных аккаунтов текущего стенда является отдельным подтверждённым изменением данных, а не общим правилом production. `--presentation` обновляет список реквизитов четырёх основных ролей и сохраняет состояние существующих записей.

Backend запускается с проверкой миграций; применённые файлы неизменяемы. Сервер возвращает `director`, старый `/executive` перенаправляет на `/director`. Модели/ключи и происхождение данных описаны в [AI Tunnel](aitunnel.md), подтверждённые прогоны и ограничения — в [проверках](verification.md). Датированные запуски ниже описывают свои версии, а не текущий образ.

## Исторический прогон 06.11.2026 до frontend_polished

Повторно выполнена команда `python scripts/start_local.py --bundled-image fixrate-ai:analyst-conformance --cloud-ai`. Постоянные app/PostgreSQL healthy, UI `http://127.0.0.1:8000/login` отвечает 200, `/api/health` возвращает database=ready. Образ содержит код `961a1e30fd5fde015a3a67d96ba35c4c1b13027b`; последующие коммиты dev изменяют только документацию.

Оба рабочих ML-провайдера — aitunnel, модели forecast/vision — qwen3.7-flash. Ключ присутствует без вывода значения; авторизованный каталог AI Tunnel отвечает HTTP 200 и содержит выбранные модели. Локальный RF успешно загружается из image. Маршруты прогноза/фотоанализа присутствуют в OpenAPI. Это проверка готовности при повторном запуске; полный реальный прогон обоих инструментов 92/92 и фото AN06 9/9 выполнены 05.11 и заново не объявляются результатом этого запуска.

БД/фото volumes сохраняются. Вход обычный серверный, девять учёток — в приватном `var/compose-local/accounts.txt`. Источник шести исходных операций не изменялся: они остаются draft до утверждения методик, единиц и пределов; пункты 36–37 остаются частично BLOCKED. [Протокол запуска](../../reports/local_launch_20261106.json). Журналы helper — `logs/local/20261105T190307776508Z` (имя в UTC).


## Исторический стенд dev, 05.11.2026

На `http://127.0.0.1:8000` развёрнут `fixrate-ai:analyst-conformance`, код `961a1e30fd5fde015a3a67d96ba35c4c1b13027b`, image `sha256:ffc5bbb10054f2c255997b5f530443b1d7e4d861dc38c2cbd277e6c21114dc26`. App/DB healthy, применена 009. Это API-режим с PostgreSQL и настроенными облачными Qwen3.7 Flash для двух инструментов. Повторный запуск этого локального образа: `python scripts/start_local.py --bundled-image fixrate-ai:analyst-conformance --cloud-ai`. На чистой машине используется обычный `python scripts/start_local.py --cloud-ai`, который собирает исходники; локальный tag сам по себе не является опубликованным registry image.

Свежая копия `var/backups/before-analyst-20261105T175744Z` сравнена после обновления по каждому прежнему полю. Сохранены 624 задания, 377 отчётов, 249 приёмок, 801 календарная запись, 8 forecast_runs, 4 решения оркестратора и 4 фотоанализа. Все 11 записей evidence_files сохранены: 10 прежних файлов volume совпали по SHA-256, ещё один — исходный упакованный `data/demo/demo-photo.png`, его hash также проверен. История и фотографии не удалялись.

На существующей БД выполнены 17 браузерных чтений под шестью ролями, исполнитель — на 375px: ошибок JavaScript, ответов API 500 и горизонтального переполнения нет. Секреты в app logs отсутствуют. Девять локальных аккаунтов и пароли — в приватном `var/compose-local/accounts.txt`. Шесть исходных customer-операций подтверждены как draft; без утверждения норм их публикация и настоящий customer E2E остаются BLOCKED.

Обезличенная сводка: [analyst_deployment.json](../../reports/analyst_deployment.json). Полные локальные результаты и снимки — `reports/analyst-deployment`, журналы сборки — `logs/analyst-build`, запуска — `logs/local/20261105T182820789264Z`. Vite на 5173 из отдельной feature/frontend-next остаётся самостоятельным DEMO-просмотром и не подменяет этот стенд dev.


## Запуск с миграцией 009 и четырьмя бизнес-ролями

Для текущей версии применяйте всю цепочку 001–010. В новой схеме требуется maintenance_notifications; прежний образ с 001–008 не является сборкой текущего dev. Обычная чистая установка Compose по инструкции ниже получает данные, БД и фото в отдельных volumes; реальную БД не удалять и не запускать `down --volumes` для постоянного проекта. Изолированный QA runner создаёт собственный проект/БД и удаляет только его.

Базовый QA seed создаёт отдельные совместимые аккаунты для технических тестов. Текущий постоянный стенд владельца ограничен четырьмя активными аккаунтами director/chief_engineer/engineer/executor на ЖК «Сосновый парк»; остальные пользователи и учебный объект отключены с сохранением истории. Email новых ролей задаются `FIXRATE_DEMO_EXECUTIVE_EMAIL` / `FIXRATE_DEMO_CHIEF_EMAIL`, пароль — через существующие FIXRATE_DEMO_* в приватном `.env`. Файл `var/compose-local/accounts.txt` содержит фактические локальные реквизиты и не публикуется. Изменение настроек демо не сбрасывает задания, фотографии и прежние пароли без явной конфигурации.

Фоновое расписание управляется `MAINTENANCE_SCHEDULER`; в тестах внедрённый engine отключает автоматический цикл. Для cloud AI нужны AITUNNEL_API_KEY (поддерживается прежний AI_TUNNEL_API_KEY), модели и таймаут в `.env`; отсутствие ключа даёт явный unavailable. Включение реального облачного профиля передаёт фотографии и контекст выбранному провайдеру. Обычный проверщик не использует ключи и не тратит облачный баланс.

Исходные шесть операций остаются черновиками: владелец подтвердил отсутствие утверждённых методик/единиц/пределов. Для их публикации нужны реальные данные и решение главного инженера. Демонстрационные/изолированные TEST-прогоны не объявляются приёмкой этих операций. [Актуальный реестр 37 пунктов](../analysis/REMEDIATION.md).

Назначение: установить и проверить текущий модульный сервис. Команды выполняются из корня выбранного checkout dev. Текущий Compose использует PostgreSQL 18 и Python 3.12/CPU PyTorch. Полный native-прогон 04.11.2026 выполнен на Windows/Python 3.14.7/PostgreSQL 18.6; native-подготовка CLIP описана для Python 3.12. Прежние результаты PostgreSQL 16.13 относятся к датированным историческим протоколам.

## Готовый образ с RF и CLIP внутри

Для переносимого стенда используется Dockerfile.bundled поверх текущего приложения. Образ включает frontend, backend, RF и только восемь разрешённых файлов закреплённого CLIP. HF-токены, .env, БД и пользовательские фотографии в образ не копируются. Метаданные файла/размера/SHA-256 записываются в bundle-manifest.json; готовность обеих моделей проверяется в контейнере с отключённой сетью. RF обучен на synthetic_demo, CLIP оценивает видимые изменения; приёмка остаётся решением инженера.

Сборка на машине с уже подготовленным cache требует Docker/BuildKit и Python 3.11+; host Torch для самого упаковщика не нужен:

```powershell
python scripts/build_bundled_image.py --cache .venv/hf-cache --tag fixrate-ai:bundled
python scripts/start_local.py --bundled-image fixrate-ai:bundled
```

Упаковщик читает pin из ml_service/app/core/config.py, копирует только выбранный snapshot, строит отдельный runtime base и image с моделями. Дополнительный build context содержит только разрешённые файлы модели. Ничего не скачивается неявно. Внутри image устанавливаются HF_HOME=/app/model-cache и offline-флаги. Ревизия исходников записывается в OCI label и FIXRATE_SOURCE_REVISION; незакоммиченная сборка явно помечается -dirty. Отчёты — reports/bundled-image, логи — logs/bundled-image, подготовленный build context — var/bundled-image.

start_local.py сохраняет выбранный image/profile в приватном runtime.env. Последующие --status, --stop и обычный старт используют тот же профиль. compose.bundled.yaml запускает готовый image без build и без model bind mount, с теми же postgres_data/photos volumes и адресом/паролями постоянного fixrate-local. Приложение можно обновить без удаления БД и фото. Readiness и source_revision записываются в var/compose-local/state.json.

Проверка именно готового образа на отдельном одноразовом проекте:

```powershell
.\.venv\Scripts\python.exe scripts/verify_compose.py --bundled-image fixrate-ai:bundled
```

Она проверяет отсутствие host mount для моделей, реальные RF/CLIP-вызовы, повтор обоих вызовов после restart, неизменность сохранённого сравнения и историю принятой работы после следующего restart. Для обычного профиля --ml-cache сохраняется; параметры --bundled-image и --ml-cache взаимоисключающие.

Следующий экспорт относится к RF/CLIP-профилю. Он не включает Ollama и volume весов Qwen3.5; для подробного локального vision на новой машине дополнительно выполните prepare_local_vision.py по разделу ниже. Для переноса RF/CLIP на другую совместимую Docker-машину архивируйте оба образа — приложение и PostgreSQL, чтобы при запуске не требовалось скачивать postgres:18:

```powershell
docker image save --output var/bundled-image/fixrate-ai-bundled.tar fixrate-ai:bundled postgres:18
# На другой машине после клонирования dev:
docker image load --input fixrate-ai-bundled.tar
python scripts/start_local.py --bundled-image fixrate-ai:bundled
```

Для такого запуска host CLIP-cache и Python ML-зависимости не нужны; достаточно Docker и стандартного Python для launcher. PostgreSQL и пользовательские файлы остаются отдельными постоянными volumes. Перенос существующих пользовательских данных требует отдельного backup/restore, image их не содержит.

## Локальная vision-модель для фотоотчёта

Подробный разбор до/после использует отдельный Ollama-контейнер на локальном NVIDIA GPU и постоянный volume fixrate-local_vision_models. Существующие задания, приёмка, PostgreSQL/photos volumes и демо-реквизиты сохраняются. Полностью offline работает анализ; для первоначальной установки требуется интернет и около 3,33 GB весов плюс Docker image.

```powershell
# Один раз: явная загрузка закреплённых Ollama и Qwen3.5 4B.
python scripts/prepare_local_vision.py
# Собрать обновлённое приложение, если готовый image ещё не загружен.
python scripts/build_bundled_image.py --cache .venv/hf-cache --tag fixrate-ai:bundled
# Выбрать и сохранить локальный vision-профиль.
python scripts/start_local.py --bundled-image fixrate-ai:bundled --local-vision
```

Следующие python scripts/start_local.py / --status / --stop используют сохранённый профиль. prepare завершает свой временный bootstrap, оставляя веса в volume; --keep-bootstrap нужен только для явной диагностики и не используется обычным запуском. Перед запуском рабочего профиля такой диагностический контейнер нужно остановить и удалить без удаления volume, чтобы он не занимал GPU.

Профиль compose.vision.yaml добавляет vision с GPU и internal network без внешнего порта. Закреплённые image/model digest сохраняются в var/local-vision/model.json и private runtime.env. В измеренном холодном API-прогоне прогрев занял 247.48s, повторный после stop/start — 124.96s; это время установки/старта, не время каждого фотоанализа. Отдельный прогрев завершается до сообщения готовности launcher; сервис остаётся в памяти, поэтому пользовательский запрос не повторяет первоначальную загрузку. Конфигурация рассчитана на проверенную RTX 4050 6 ГБ; на другом GPU нужна собственная проверка скорости и памяти.

В интерфейсе инженер открывает отправленное задание, сверяет сопоставимость пары, запускает «Анализировать фото» и получает отдельные описания до/после, изменения, замечания, дальнейшие проверки и ограничения. Ошибка сервиса или неразличимый результат не считаются подтверждением выполнения. Прежние CLIP-заключения сохраняются и помечаются как результат прежней модели; для нового содержательного анализа требуется повторный запрос.

Для native backend предусмотрены PHOTO_REVIEW_PROVIDER=ollama, OLLAMA_BASE_URL (только локальный адрес), OLLAMA_VISION_MODEL, OLLAMA_VISION_DIGEST и PHOTO_REVIEW_TIMEOUT_SECONDS=120; пример находится в .env.example. В Docker эти параметры передаёт профиль, внешние AI API и API-ключи не нужны. [Контракт и ограничения](ml.md#подробный-локальный-разбор-фото).

Настоящий API/БД-прогон на отдельном Compose-проекте после подготовки весов:

```powershell
python scripts/verify_compose.py --bundled-image fixrate-ai:bundled --local-vision
```

Он использует отдельные БД/photos, проверяет сохранение структурированного ответа, restart и отказ модели без CLIP fallback. Подготовленный model volume — внешний, cleanup QA-проекта его и рабочие volumes не удаляет. Для дополнительного прогона на собственной паре добавьте --photo-before и --photo-after с локальными путями; фотографии не попадут в Git.

## Логин и пароль демо-стенда через .env

В корневом `.env` того checkout, из которого запускается scripts/start_local.py, можно задать:

```dotenv
FIXRATE_DEMO_LOGIN=dispatcher@example.test
FIXRATE_DEMO_PASSWORD="your-own-demo-password"
# Необязательно: email остальных ролей
FIXRATE_DEMO_ADMIN_EMAIL=fixrate-demo-admin@example.test
FIXRATE_DEMO_ENGINEER_EMAIL=fixrate-demo-engineer@example.test
FIXRATE_DEMO_EXECUTOR_EMAIL=fixrate-demo-1@example.test
```

FIXRATE_DEMO_LOGIN — email диспетчера, а не произвольное имя. Общий пароль минимум из 12 символов применяется к четырём основным ролям и трём работникам бригады. Пример пароля выше — только шаблон, задайте свой. Чтобы применить изменения к готовому образу с этой поддержкой:

```powershell
python scripts/start_local.py
```

Launcher читает только перечисленные демо-параметры из `.env`; DATABASE_URL и POSTGRES_PASSWORD из него не заменяют параметры постоянного Docker-стенда. Переменные процесса имеют приоритет. Существующие значения сохраняются в приватном var/compose-local/runtime.env, поэтому удаление строки из `.env` не откатывает логин/пароль. Без явного пароля на новом стенде генерируется случайный. Итоговые email с ролями и пароль находятся в var/compose-local/accounts.txt; секреты не печатаются в журнал.

Пароли с `$`, `#`, `=`, пробелами и кавычками передаются буквально, без shell expansion. В `.env` используйте одинарные кавычки или двойные в JSON-формате; для вложенной двойной кавычки внутри двойных нужна обратная косая черта. Перевод строки в пароле запрещён. Логины должны быть различными email и не занимать адрес другого пользователя.

Изменяются только семь демо-аккаунтов со стабильными UUID: назначения, отчёты, фото, приёмки и обычные пользователи сохраняются. При изменении email/пароля сессии этого аккаунта отзываются; повтор с теми же реквизитами сохраняет сессии. Конфликт email отклоняется до изменения аккаунтов. Параметры --status/--stop не применяют новые реквизиты.

Для native-запуска эквивалентная явная команда из настроенного Python-окружения: python -m app.manage seed-demo --configure-accounts, с PYTHONPATH=backend и корректным DATABASE_URL. Без --configure-accounts обычный seed-demo по-прежнему сохраняет существующие пароли. В Docker параметры передаются только при выполнении seed, в image они не включаются. Чтобы добавить поддержку к прежнему образу, пересоберите его по инструкции выше; переименование тега старого image код не обновляет.

## Первый запуск с чистого checkout

Выберите dev при клонировании:

```powershell
git clone --branch dev https://github.com/krangras/FixRateAI.git
Set-Location FixRateAI
```

Для постоянного стенда установите и запустите Docker Desktop/Engine с Compose. Native Node и PostgreSQL для этого варианта не нужны. Если закреплённый CLIP-cache уже подготовлен на этой машине, сразу используйте python scripts/start_local.py --cache "путь-к-cache". Для чистой машины сначала создайте Python 3.12 окружение и подготовьте веса:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:HF_HOME = Join-Path (Resolve-Path .venv).Path 'hf-cache'
.\.venv\Scripts\python.exe scripts/prepare_clip.py --download
.\.venv\Scripts\python.exe scripts/start_local.py --cache "$env:HF_HOME"
```

Скачивание выполняется явно один раз и требует сети. Команда без --download проверяет существующий cache offline. Веса не включены в Git; подготовка не требует проектной PostgreSQL или .env. Helper создаёт отдельный постоянный Docker-стенд, применяет миграции, выполняет demo seed, проверяет модели и печатает адрес/путь к учёткам. Без cache можно проверить API с контролируемым MODEL_NOT_READY через обычный [Compose](#чистая-postgresql-и-compose); start_local.py требует готовности обеих моделей.

## Постоянный локальный стенд для тестирования

Проверенная сборка dev запущена 04.11.2026 как Compose-проект fixrate-local: **http://127.0.0.1:8000**, Swagger — /docs, готовность — /api/health. Это один FastAPI со SPA, PostgreSQL 18 и реальные RF/CLIP. Текущий bundled-профиль содержит CLIP внутри image; прежний профиль compose.ml.yaml читает подготовленный read-only host cache. Адрес 5173 относится к отдельному Vite-процессу, для этого стенда используйте 8000. Созданные данные и фотографии сохраняются между запусками.

Из корня D:\FixRate AI\FixRate_AI:

```powershell
python scripts/start_local.py
# Последующие старты без изменения исходников:
python scripts/start_local.py --no-build
python scripts/start_local.py --status
# Остановка с сохранением БД и фото:
python scripts/start_local.py --stop
```

[start_local.py](../../scripts/start_local.py) использует только стандартную библиотеку Python и работающий Docker Desktop/Engine. При первом запуске нужен подготовленный cache .venv/hf-cache (другой путь: --cache); --port выбирает порт, по умолчанию первый свободный из 8000/8080/8090. Windows-путь Docker Desktop определяется автоматически, доступен --docker. Helper строит образ, применяет миграции через launcher, явно выполняет seed-demo, проверяет обе модели и health, оставляет контейнеры работать в фоне.

Приватная конфигурация находится в var/compose-local/runtime.env. Она генерируется один раз, сохраняет пароль PostgreSQL, отдельный пароль demo-аккаунтов, порт и путь к cache; существующий .env другого checkout не читается и не заменяется. Повторный seed не сбрасывает существующие пароли, задания, приёмку и фотографии. При наличии volumes без соответствующей приватной конфигурации helper отказывается генерировать новые пароли. --stop вызывает down без удаления volumes; автоматического удаления БД нет.

Учётки и общий локальный пароль записаны в **var/compose-local/accounts.txt** и исключены из Git. Сам пароль не помещается в документацию, исходники, журналы или build context.

| Роль | Email |
|---|---|
| Администратор | fixrate-demo-admin@example.test |
| Диспетчер | fixrate-demo-dispatcher@example.test |
| Контролёр/инженер | fixrate-demo-engineer@example.test |
| Исполнитель | fixrate-demo-1@example.test |
| Работники демонстрационной бригады | fixrate-assignment-1@example.test, fixrate-assignment-2@example.test, fixrate-assignment-3@example.test |

Роль определяется сервером после входа, переключение — через выход и вход другой учёткой. Для одновременной проверки разных ролей используйте отдельные браузерные профили. На момент проверки оставлены исходное назначенное задание, отдельное календарное задание для двух допущенных работников и принятый синтетический пример с парой PNG/JPEG. Можно выполнить назначенное задание, сдать отчёт и принять его из учётки инженера; real CLIP не принимает работу автоматически. Неподтверждённые нормативы заказчика по-прежнему требуют ввода данных, а не искусственного успешного расчёта.

Состояние/ID учебных заданий — var/compose-local/state.json, журналы — logs/local, протоколы — reports/local. [Фактическая проверка запуска](verification.md#04112026-постоянный-локальный-стенд), [общий контракт ML](ml.md#контракт-интеграции-backend-и-ml).

## Код и пространства имён

Расположение исходников, конфигов, данных и результатов определено в [единой карте репозитория](development.md#структура-репозитория). Backend импортируется как `app`, ML исключительно как `ml_service.app`; pytest использует `--import-mode=importlib`. Runtime и проверщик используют один канонический DTO из backend, документной Python-копии нет.

## Установка и запуск

Для native ML-профиля используйте Python 3.12, Node 24 и PostgreSQL 18. Создание роли и отдельной БД описано в [подготовке PostgreSQL](#чистая-postgresql-и-compose); выполните его до миграций в блоке ниже. Python-зависимости backend, RF, CLIP и тестов зафиксированы в `requirements.txt` (59 пакетов проверенного профиля). Frontend использует `package-lock.json` и `npm ci`.

PowerShell, из корня проекта:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Отредактируйте DATABASE_URL: новая проектная PostgreSQL, не рабочая БД с чужими данными.
$env:PYTHONPATH = "backend;."
.\.venv\Scripts\python.exe -m app.manage migrate
.\.venv\Scripts\python.exe -m app.manage seed-demo
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run build
.\.venv\Scripts\python.exe scripts/start_backend.py --host 127.0.0.1 --port 8000
```

CLI и scripts/start_backend.py загружают корневой `.env`, сохраняя приоритет переменных окружения. Launcher проверяет конфигурацию, запускает uvicorn без access log с query string; миграции запускает только с явным --migrate, seed никогда не запускает автоматически. Vite читает тот же корень через envDir и публикует в клиент только VITE_* переменные. Копируйте шаблон только при отсутствии .env в выбранном checkout; env другого worktree автоматически не используется. Команда seed явная и необязательная. Она запрашивает пароль минимум из 12 символов (или читает `FIXRATE_DEMO_PASSWORD`, который не нужно сохранять/публиковать). Без --configure-accounts повтор не сбрасывает пароли и выполненные работы; флаг явно применяет только демо-реквизиты из окружения. Исходный SQL seed из `kran_dev` сохранён отдельно и тестируется как исходный артефакт.

Демонстрационные аккаунты:

| Email | Роль |
|---|---|
| `fixrate-demo-1@example.test` | executor |
| `fixrate-demo-engineer@example.test` | engineer |
| `fixrate-demo-dispatcher@example.test` | dispatcher |
| `fixrate-demo-admin@example.test` | admin |
| `fixrate-assignment-1@example.test` … `fixrate-assignment-3@example.test` | executor; допущенные работники demo-бригады |

Учётные записи создаются только внутри demo объекта. Для создания обычного пользователя существующего объекта:

```powershell
.\.venv\Scripts\python.exe -m app.manage create-user --email user@example.test --name "Имя" --site "UUID-объекта" --role engineer
```

Замените UUID-объекта действительным идентификатором существующего объекта. Первый объект создаётся через SQL/bootstrap; оборудование и настройки обслуживания вводятся через /settings/equipment, работники и смены — /settings/workforce. Исходный импорт Excel хранится отдельно от новых операторских версий.

Linux/macOS: `python3.12 -m venv .venv`, `.venv/bin/python` вместо Windows python.exe, `export PYTHONPATH=backend:.`; используйте npm вместо npm.cmd; остальные команды аналогичны. Полный Windows-стенд и Linux-контейнер проверяются отдельно, журнал указан ниже.

Приложение: `http://127.0.0.1:8000`, OpenAPI: `/docs`, готовность: `/api/health`. Сначала примените миграции и соберите frontend, потом запускайте backend. Импорт модуля не соединяется с БД; lifespan откажет с понятной ошибкой, если схема не готова.

Для горячей разработки запускайте backend так же, а во второй консоли `npm --prefix frontend run dev`. Vite слушает 5173 и проксирует `/api` на 8000, сохраняя Host для same-origin проверки. Открывайте UI именно на адресе Vite и используйте его относительные /api URL; прямой запрос браузера с 5173 на 8000 останется межсайтовым. Остановка: Ctrl+C в обеих консолях; PostgreSQL управляется его штатным сервисом. Локальный скрипт проверки останавливает только созданные им процессы.

Переменные:

| Переменная | Назначение |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://…`; обязательно |
| `PHOTO_STORAGE_ROOT` | Каталог файлов, по умолчанию `var/photos`; не внутри публичной статики |
| `COOKIE_SECURE` | `false` для loopback HTTP; `true` для HTTPS |
| `HF_HOME` | Native cache моделей; для helper по умолчанию используйте .venv/hf-cache |
| `CORS_ORIGINS` | Настройка CORS middleware; не отменяет same-origin проверку API. Для Vite используется proxy |
| `VITE_DEMO_MODE` | По умолчанию false; true создаёт явно демонстрационную SPA с fixtures, без реальных изменений |
| `FORECAST_TIMEOUT_SECONDS` | Дедлайн одного RF-вызова в (0, 5], по умолчанию 2; календарный бюджет 8 секунд сохраняется |
| `PHOTO_REVIEW_MAX_FILES`, `PHOTO_REVIEW_MAX_BYTES` | Пакет анализа: 20 фото / 50 МиБ по умолчанию; общий upload-лимит одного файла не меняется |
| `CLIP_CACHE_ROOT` | Только compose.ml.yaml: существующий локальный HF cache, read-only |
| `PHOTO_REVIEW_TIMEOUT_SECONDS` | Ожидание CV: число в (0, 120], по умолчанию 20; неверное значение останавливает запуск |
| `POSTGRES_PASSWORD`, `FIXRATE_PORT` | Только Compose: hex-пароль отдельной БД и внешний loopback-порт (8000 по умолчанию) |
| `TEST_DATABASE_URL` | Только исходные ORM тесты; пустая база `fixrate_test_*` |
| `INTEGRATION_DATABASE_URL`, `FIXRATE_TEST_PASSWORD` | Только подготовленный временный HTTP тестовый стенд; задаёт runner |

## Чистая PostgreSQL и Compose

Для native-запуска установите PostgreSQL и создайте отдельные роль/базу (административный пароль вводится интерактивно). Не используйте существующую рабочую БД для проверки:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\createuser.exe" -h 127.0.0.1 -U postgres -P --no-superuser --no-createdb --no-createrole fixrate
& "C:\Program Files\PostgreSQL\18\bin\createdb.exe" -h 127.0.0.1 -U postgres -O fixrate fixrate
```

Укажите эту роль, пароль, адрес и базу в DATABASE_URL. Спецсимволы пароля должны быть URL-encoded. Мигратор применяет 001–008 под advisory lock, проверяет checksums и поддерживает повторный запуск; существующая схема без ledger требует отдельного проверенного --adopt-existing. Seed необязателен и сохраняет историю при повторе. Шесть исходных операций с неподтверждённой политикой/датами остаются needs_input до явной настройки, без выдуманных дат.

[compose.yaml](../../compose.yaml) и [Dockerfile](../../Dockerfile) создают PostgreSQL 18 и один FastAPI со SPA. Docker Desktop/Engine с Compose необходимы отдельно. В корневой .env добавьте POSTGRES_PASSWORD — уникальный случайный hex-пароль (например, 64 символа); сохраняйте его для повторного подключения к тому же volume. Compose не использует native DATABASE_URL: контейнер подключается к собственному db. COOKIE_SECURE=false подходит для локального HTTP.

```powershell
docker compose config --quiet
docker compose up --build -d
docker compose ps
docker compose exec app python -m app.manage seed-demo
```

Seed интерактивно запрашивает отдельный пароль demo-пользователей. Адрес http://127.0.0.1:8000, /docs и /api/health; FIXRATE_PORT позволяет выбрать другой локальный порт. PostgreSQL наружу не публикуется. Именованные volumes сохраняют БД и фото; docker compose down останавливает стенд с сохранением данных. Контейнер приложения работает пользователем uid 10001, использует CPU PyTorch, не получает .env/var/секреты в build context. Автомиграция выполняется до старта API; demo seed и скачивание весов не выполняются. Без локальных CLIP-весов фотоанализ честно unavailable; прогнозы используют регламентный fallback. Для реального CLIP подготовьте cache отдельно и подключите HF_HOME volume, как описано в разделе моделей.

Инфраструктура для публичного доступа, TLS, backup/restore и мониторинг требуют отдельной задачи. Состояние фактической сборки/прогона контейнера — в [аудите backend](verification.md#04112026-аудит-backend-и-устранение-блокеров).

## Запуск с двумя ML-инструментами

RF и manifest включены в data/models и образ; notebooks не нужны. Для CLIP подготовьте закреплённый Hugging Face cache заранее через scripts/prepare_clip.py --download из полного Python 3.12 окружения. Если cache уже есть, команда без --download проверяет его offline. HTTP никогда не скачивает веса.

Native PowerShell:

```powershell
$env:HF_HOME = "D:\models\fixrate-hf"
.\.venv\Scripts\python.exe scripts/prepare_clip.py --download
.\.venv\Scripts\python.exe scripts/start_backend.py
```

Укажите существующий подготовленный cache для Compose в корневой .env: CLIP_CACHE_ROOT — абсолютный путь на машине с Docker. Затем:

```powershell
docker compose -f compose.yaml -f compose.ml.yaml config --quiet
docker compose -f compose.yaml -f compose.ml.yaml up --build -d
# Только для нового demo-стенда:
docker compose -f compose.yaml -f compose.ml.yaml exec app python -m app.manage seed-demo
```

Профиль монтирует cache read-only и запрещает сеть для Hugging Face-клиента. Публичный доступ backend и остальных библиотек этим флагом не отключается. Веса не добавляются в образ и не копируются в Git. Для остановки используйте тот же набор -f; данные volumes сохраняются.

Повтор реальных сервисных end-to-end вызовов двух HTTP-маршрутов на уникальном временном стенде:

```powershell
python -B scripts/verify_compose.py --ml-cache "D:\models\fixrate-hf"
# Отдельно проверить контролируемую недоступность CLIP:
python -B scripts/verify_compose.py
```

--docker принимает путь к docker.exe, если CLI отсутствует в PATH. Скрипт не читает проектный .env, создаёт свой пароль/порт/проект, проверяет RF/CLIP и Pydantic-ответы в PostgreSQL, журналы/роли/фото, затем удаляет только собственные контейнеры и volumes. Без --ml-cache модель CLIP обязана вернуть MODEL_NOT_READY; с --ml-cache требуются реальный model_ref и непустые scores. Это отдельные профили, они не заменяют друг друга. [Контракт параметров, лимитов и версий](ml.md#контракт-интеграции-backend-и-ml); [протоколы](verification.md#04112026-два-ml-инструмента-в-backend).

## Что хранится в var

`var` содержит изменяемое локальное состояние приложения и полностью исключён из Git.

| Путь | Назначение |
|---|---|
| `var/compose-local/runtime.env`, `accounts.txt` | Приватные параметры постоянного Docker-стенда и demo-логины; не публикуются |
| `var/compose-local/state.json` | URL, имена volumes, версии моделей, ID учебных примеров и ссылки на журналы |
| `var/local-demo/postgres` | Действующий локальный кластер PostgreSQL с данными, пользователями, назначениями и историей; внутренними файлами управляет СУБД |
| `var/local-demo/*.pid` | Идентификаторы локальных процессов; PID сам по себе не доказывает, что процесс ещё работает |
| `var/local-demo/local-state.json`, `postgres-password.txt` | Сохранённые сведения подготовки локального стенда, включая секреты PostgreSQL/demo; это не env-файлы, они исключены из Git |
| `var/local-demo/photos` | Заданный текущим стендом PHOTO_STORAGE_ROOT для загруженных файлов; создаётся по мере необходимости. Общий default приложения — `var/photos` |
| `var/backups` | Частные дампы перед изменениями схемы; это резервные копии, а не заменяемые тестовые fixtures |
| `var/local-demo/postgres.start.*.log` | Два открытых потока работающей PostgreSQL; Windows не позволяет их переместить. Они остаются до штатного обслуживания СУБД |

Параметры подключения, путь к фотохранилищу и путь к cache весов задаются в корневом .env. Сами фотографии хранятся по PHOTO_STORAGE_ROOT, веса — в HF_HOME; содержимое файлов не переносится в .env. Новые журналы пишутся в logs, результаты проверок — в reports, сохраняемые входные материалы и модели — в data. Временные PostgreSQL-кластеры полного runner создаются в системном TEMP и удаляются самим runner; рабочий кластер из var он не использует. Полная карта размещения находится в [development](development.md#структура-репозитория).

## Проверки

### Полный Python-стек и локальные веса CLIP

`pip install -r requirements.txt` устанавливает библиотеки для backend, ML/CV и тестов одним списком. Веса CLIP устанавливаются отдельно: они не являются Python-пакетом, не включаются в Git и не скачиваются API во время запроса.

```powershell
$env:HF_HOME = Join-Path (Resolve-Path .venv).Path 'hf-cache'
.\.venv\Scripts\python.exe scripts/prepare_clip.py --download
$env:FIXRATE_REQUIRE_CLIP = '1'
.\.venv\Scripts\python.exe scripts/verify.py --browser --pg-bin "C:\Program Files\PostgreSQL\18\bin"
```

`--download` нужен для явной подготовки отсутствующих весов закреплённой ревизии. Если cache уже подготовлен, `scripts/prepare_clip.py` без флага проверяет готовность полностью локально. `FIXRATE_REQUIRE_CLIP=1` требует настоящий model_ref в HTTP-проверке; unavailable или подставной классификатор такой прогон не заменяют. Эти проверки подтверждают исполнение модели, но не её точность на заказчике.

При запуске приложения сохраняйте тот же HF_HOME, в котором подготовлены веса. Если backend уже работал без нужных пакетов/весов, после их подготовки перезапустите его командой scripts/start_backend.py из раздела установки.

Пути .venv/cv в старых протоколах относятся к окружению того запуска и не гарантируют его наличие в другом checkout. Для нового native-стенда создайте .venv на Python 3.12 по инструкции выше; проверенный контейнерный ML-профиль также использует Python 3.12. Каждый checkout использует собственный .env.

Основная команда из корня:

```powershell
.\.venv\Scripts\python.exe scripts/verify.py --browser --pg-bin "C:\Program Files\PostgreSQL\18\bin"
```

`--browser` требует установленный Chrome. Без этого флага выполняются все остальные проверки. Каждый запуск создаёт новые `reports/verification/<run-id>` и `logs/verification/<run-id>`; команда печатает оба пути. Playwright artifacts сохраняются в подкаталоге отчёта `playwright`; конфигурация frontend остаётся на месте. `--output reports/verification/<новое-имя>` задаёт каталог отчёта; внутри репозитория выход разрешён только в reports. Повтор с каталогом, уже содержащим результаты, отклоняется, чтобы не перезаписать доказательства. Для внешнего CI-каталога results.json сохраняет разрешимые ссылки на логи.

Runner не использует рабочий `DATABASE_URL`: создаёт новый кластер в TEMP, слушающий loopback на свободном порту, отдельные БД для ORM, runtime, upgrade и браузера; останавливает свои процессы и удаляет только проверенный собственный временный каталог.

Проверяются 001–004 и все SQL assertion исходников, повторный исходный seed, upgrade заполненной 004 до текущей схемы 010 с сохранением прежних полей восьми таблиц истории, повтор мигратора, новая 001–010, повтор runtime seed, все Python тесты с настоящей БД, 12 исполняемых сценариев оркестрации, архитектурный валидатор, compileall, TypeScript/Vite, UI тесты и npm audit. Browser E2E использует собранную SPA: 13 auth-сценариев работают с mock API, остальные 11 — с настоящим uvicorn/PostgreSQL: календарь → два прогноза → создание задания → подтверждение бригады → reload; также сохранены проверки четырёх ролей, фотоотчёта, доработки, приёмки и RF.

Изолированные команды:

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q
.\.venv\Scripts\python.exe -B scripts/validate_artifacts.py
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend run build
npm.cmd --prefix frontend test
npm.cmd --prefix frontend audit --audit-level=moderate
```

Все тесты находятся в корневом tests: Python — в tests/backend и tests/ml, UI — в tests/web/unit, browser E2E — в tests/web/e2e, общие fixtures и SQL — в tests/fixtures и tests/sql. Единая команда scripts/verify.py --browser запускает все эти группы. Команды npm выполняются из frontend либо через npm --prefix frontend; перенос тестов не требует новой установки Node-зависимостей. Обычный pytest без тестовых URL пропускает PostgreSQL/HTTP проверки: такой запуск не равен полному прогону. Vitest использует demo fixtures для проверки всех исходных маршрутов/доступности; production transport отдельно проверяется браузерным E2E. Фактические итоги, команды и ограничения — в [проверках](verification.md).

## Диагностика и ограничения

- `DATABASE_URL is required`: настройте `.env` и используйте scripts/start_backend.py; драйвер должен быть `postgresql+psycopg`.
- Ошибка startup о 004/008: примените SQL-цепочку. Сам API не создаёт таблицы через ORM; --migrate у launcher и Docker CMD явно запускают мигратор перед API.
- UI 404 при прямом открытии: сначала соберите `frontend/dist`, затем перезапустите backend; статика монтируется при создании приложения.
- 401: повторный вход или проверка активности пользователя/членства/объекта; клиентский выбор роли в production не даёт доступ.
- 403 при mutation: CSRF cookie/header, роль или запрет собственной приёмки. За reverse proxy сохраняйте корректный Host/origin.
- 409: перечитайте карточку; параллельный запрос мог уже увеличить revision. Повторная сдача/приёмка не создаёт дубликатов, но универсального Idempotency-Key store пока нет.
- `MISSING_CHECKLIST` / `MISSING_BINDING`: запись в БД не содержит согласованного входа; заполнение не подменяется fixtures.
- `UNCONFIRMED_RULE`: seed намеренно не утверждает неоднозначные правила заказчика. Нужно предметное подтверждение, а не снятие проверки.
- `MODEL_NOT_READY` / `CLIP_MODEL_UNAVAILABLE`: проверьте manifest, артефакт, установку корневого requirements.txt и локальный cache весов. Отсутствие ML не означает успешный прогноз.
- Нет `ui` payload в старом сравнении: нужны дополнительные достоверные поля и backfill. Старые записи не удалены.

Физическая модель и проектные DTO содержат ещё не покрытые отображением сценарии. Поддержка нескольких единиц оборудования в одном наряде остаётся в repository; нынешняя форма загрузки фото требует ровно одну единицу и возвращает 422 для неоднозначного наряда. Проекции SPA показывают основное оборудование наряда; расширение для нескольких единиц требует отдельного UI, а не потери исходных связей в БД.

## Границы поставки

В репозитории есть Dockerfile, compose.yaml/compose.ml.yaml, постоянный локальный launcher и GitHub Actions для синхронизации GitVerse. Автоматического CI-прогона полного набора тестов в GitHub Actions, nginx/TLS-конфигурации, мониторинга и проверенного backup/restore пока нет. Проектный ориентир 4 CPU / 8 ГБ RAM не является измеренным ресурсным бюджетом. Для внешней эксплуатации нужны отдельные замеры, резервирование БД/фото/моделей, ограничения запросов и политика регистрации.

Последовательность Compose: health PostgreSQL → launcher --migrate с остановкой при ошибке → API → app healthcheck. Volumes postgres_data и photos сохраняют данные; подготовленные веса подключаются отдельным read-only volume в ML-профиле. /api/health проверяет SELECT 1, а не качество или готовность AI; готовность обеих моделей проверяют start_local.py и отдельный контейнерный сценарий. Прогрев CLIP при startup API автоматически не вызывается; библиотечный warmup() доступен отдельно, см. [ML/CV](ml.md).

## Связи

[Данные и миграции](database.md) · [проверки и протоколы](verification.md) · [разработка и обновление источников](development.md).


### Изолированная проверка SQL без запуска рабочего приложения

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/verify_schema.ps1 -PgBin 'C:\Program Files\PostgreSQL\18\bin'
```

Runner проверяет базовые ограничения 001–004, upgrade заполненной истории до текущей схемы и отдельную чистую установку всех SQL-миграций. Добавлены тесты tests/sql/test_runtime_schema.sql и test_maintenance_history_upgrade.sql. Используется только собственный кластер в TEMP; Port=0 по умолчанию выбирает свободный loopback-порт. -Port задаёт явный свободный порт, -Database — имя тестовой БД, -LogPath — новый лог (существующий отклоняется). По умолчанию результаты находятся в logs/sql/<дата-PID>/run_schema_test.log. Сообщение ALL CHECKS PASSED появляется после остановки и удаления собственного кластера. Полный scripts/verify.py включает те же проверки; [актуальные результаты](verification.md#04112026-исправление-qa03-и-полный-успешный-прогон-dev).

## Фактический bundled-стенд 04.11.2026

На 127.0.0.1:8000 развёрнут fixrate-ai:bundled, image sha256:9229e1e5c8118379e2fecc225af70a031174e775dfadb8ac98d58a714adb6f2b. Исходники image — 6a86b66: Workspace, .env-демо-доступ и содержательный локальный фотоанализ; последующие изменения протокола в документации не меняют его backend/frontend. RF synthetic_demo:rf:985a24f18a997f38 и CLIP openai/clip-vit-base-patch32@3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268 находятся внутри image, model bind mount отсутствует. На 8000 теперь 68 OpenAPI paths и текущая JS-сборка index-BKTu07M2.js и Aurora favicon.

Первое обновление 3a8b243 сохранило прежние 6 work orders, 3 evidence records и 2 приёмки без изменений; backup — var/backups/before-bundled-20261104T130902Z. При последующем обновлении eab7f5d все исходные ID и метаданные прежних фото сохранены; backup — var/backups/before-demo-env-20261104T133931Z. Во время последующей проверки пользователь менял отчёт и добавлял фото (audit_events save_report/upload_photo), эти действия не откатывались. Первые 4 browser sessions: logs/bundled-image/live-roles.log; после обновления 7 HTTP login/logout прошли: reports/bundled-image/demo-env-deployment.json. Последующее обновление Workspace 6dc98a1 сохранило бизнес-таблицы полностью: 6 заданий, 5 фото и 2 приёмки; backup — var/backups/before-workspace-20261104T135428Z. Четыре роли, 14 маршрутов и 375px проверены на живом 8000: reports/frontend-integration/20261104/live-browser.json. Локальный VLM-профиль 6a86b66 дополнительно сохранил снимок всех восьми проверенных таблиц полностью: 6 заданий, 5 фото, 3 решения приёмки и 2 прежних AI-отзыва. Backup — var/backups/before-local-vision-20261104T151233Z; настоящий GPU/API/БД-прогон — 78/78. Runtime.env/accounts.txt сохраняют прежние реквизиты; mode bundled и source_revision записаны в state.json.

Исторический архив RF/CLIP-профиля до добавления локального VLM (код6dc98a1; Ollama/Qwen в нём отсутствуют): var/bundled-image/20261104T135150Z-f2b31f77/fixrate-ai-6dc98a1-bundled.tar, 979742720 bytes. SHA-256: 48540f9b4a71e36ff59c8c32122545b6a7d94f73854e3ffcf559d7450ad9265a. Проверен manifest Docker tar с двумя RepoTags. В архиве нет runtime-паролей, рабочей БД и загруженных пользователем фотографий. Для новой машины clone dev → docker image load → python scripts/start_local.py --bundled-image fixrate-ai:bundled.

## Исторические запуски frontend-next

Следующие записи относятся к отдельному worktree до объединения с dev. Текущий Docker-стенд использует API, VITE_DEMO_MODE=false и параметры постоянного fixrate-local, описанные выше.

## Локальный запуск после редизайна, 03.11.2026

В worktree frontend-next собрана production SPA из исходников новой поставки. FastAPI слушает **http://127.0.0.1:8000**, Vite — **http://127.0.0.1:5173**, его /api проксируется к тому же backend. VITE_DEMO_MODE=false: это серверные сессии и существующие данные, а не архивный dist-demo. Обновление интерфейса на 8000 требует `npm.cmd --prefix frontend run build`; на 5173 работает автоматическое обновление.

Для этого запуска повторно использованы существующие настройки БД fixrate_kran_demo на 127.0.0.1:5433 и каталог фотографий соседнего kran_dev; они не очищались и не пересоздавались. Локальный .env frontend-next создан с тем же подключением и абсолютным PHOTO_STORAGE_ROOT, секреты в Git не добавлены. Миграции 001–008 уже присутствовали: повторный seed и изменение схемы рабочей БД не выполнялись. Проектный PostgreSQL 18.6, FastAPI и Vite запущены в фоне без новых окон. Журналы — logs/frontend-redesign, PID — var/local-demo. Системный PostgreSQL на 5432 не изменялся.

Использовано уже установленное Python 3.11.9 окружение `../kran_dev/.venv/runtime311/Scripts/python.exe`, Node 24.21.0 и PostgreSQL 18.6. Это локальный профиль, отличный от основного проверенного Python 3.12/PostgreSQL 16.13; полный SQL gate на 18 не прошёл (см. verification). Random Forest загрузился; наличие и исполнение настоящих CLIP-весов этим запуском не подтверждено.

Повторный запуск из корня worktree (при остановленных серверах):

```powershell
$runtimePython = (Resolve-Path '../kran_dev/.venv/runtime311/Scripts/python.exe').Path
& $runtimePython -m uvicorn app.main:app --app-dir backend --env-file .env --host 127.0.0.1 --port 8000
# В другой консоли:
npm.cmd --prefix frontend run dev -- --host 127.0.0.1 --strictPort
```

На Windows с запретом npm.ps1 используется npm.cmd без изменения ExecutionPolicy. Основные инструкции установки чистого окружения находятся выше. Текущие фоновые процессы можно остановить по PID после проверки CommandLine; backend на Windows может иметь отдельный дочерний python.exe, поэтому один сохранённый PID не заменяет проверку дерева процесса.



## DEMO с выбором ролей, 04.11.2026

Для просмотра всех ролей в корневом локальном .env установлено `VITE_DEMO_MODE=true`. Vite запущен на **http://127.0.0.1:5173/login**. На первом входе выбирается роль без логина и пароля; в рабочей оболочке роль меняется через список «Демонстрационная роль» в верхней панели. Доступны диспетчер, инженер, исполнитель и администратор. Используются учебные fixtures; запись рабочих данных требует API-режима.

Запуск: `npm.cmd --prefix frontend run dev -- --host 127.0.0.1 --port 5173 --strictPort`. Журналы этого запуска находятся в logs/demo, PID — var/local-demo/vite.pid. Для возврата к API установите `VITE_DEMO_MODE=false` и перезапустите Vite. Сборка frontend/dist обновляется отдельной командой build и использует значение флага на момент сборки.

## Облачное демо без локальной vision-модели

`python scripts/start_local.py --cloud-ai` читает ключ AI Tunnel и qwen3.7-flash из .env. На чистой машине нужны Docker, Python и python-dotenv; локальный CLIP-cache/GPU не требуются. Для существующего готового образа можно добавить `--bundled-image fixrate-ai:aitunnel`. [Полная инструкция, env, модели и проверка](aitunnel.md). Локальные postgres_data/photos и подготовленный volume Ollama сохраняются; cloud-профиль не запускает GPU-контейнер. Учётки демо и API-токен AI Tunnel настраиваются независимо.

## Доступ с телефона в одной сети, 05.11.2026

Из текущей ветки `feature/frontend-next` запущен Vite с привязкой `0.0.0.0:5173`. На компьютере доступен `http://localhost:5173/login`. Текущий сетевой адрес после подключения ПК к роутеру по Ethernet — `http://192.168.0.19:5173/login`; прежние `10.153.0.161` и `10.77.43.140` больше не используются. Телефон должен быть подключён к Wi-Fi этого же роутера; при смене сети или адреса компьютера ссылку нужно обновить.

Повторный запуск из корня этой ветки, если порт свободен:

```powershell
npm.cmd --prefix frontend run dev -- --host 0.0.0.0 --port 5173 --strictPort
```

Текущий `.env` содержит `VITE_DEMO_MODE=true`: вход осуществляется выбором роли без пароля. Это просмотр интерфейса на учебных данных, без рабочего PostgreSQL и реальных вызовов AI. Изменения интеграционного стенда в `dev` этим запуском не развёртывались. Конфигурация `.env` не менялась.

Сервер запущен в фоне без отдельного окна; PID сохранён в `var/local-demo/vite.pid`, журналы — `logs/lan`. Существующее разрешающее правило Windows Firewall для Node.js соответствует активному профилю Wi-Fi; новые правила не добавлялись. Проверки и ограничения доступа приведены в [протоколе](verification.md#05112026-запуск-текущей-ветки-для-телефона).

При `ERR_ADDRESS_UNREACHABLE` проверьте VPN на обоих устройствах. В текущем окружении `Find-NetRoute -RemoteIPAddress 10.153.5.26` выбирал `xray_tun`; для диагностики нужно временно отключить TUN в v2rayN на ПК и VPN телефона, затем повторить HTTP-запрос. Если это помогает, дальнейшая настройка должна разрешать прямой доступ к локальной сети. Если не помогает, проверьте изоляцию клиентов Wi-Fi. Брандмауэр целиком отключать не требуется.

В hotspot проверено: `http://10.77.43.140:5173/login` возвращает HTTP 200 на ПК, а маршрут к шлюзу `10.77.43.30` проходит напрямую через Wi-Fi (`10.77.43.0/24`). Перезапуск Vite и изменение маршрутов не потребовались. Физический доступ с телефона требует отдельного подтверждения.

Повторное развёртывание для просмотра frontend-фикса `92581f6`: сервер PID 14224 слушает все интерфейсы на 5173 и использует текущую feature-ветку. Проверены HTTP 200 для localhost и `192.168.0.19`, прямой маршрут к шлюзу `192.168.0.1` через Ethernet и разрешение Node.js в активном профиле брандмауэра. Браузерный smoke по сетевому URL проверил выбор всех четырёх DEMO-ролей без ошибок JavaScript. Протокол — `reports/local-deploy-92581f6/results.json`; журналы процесса — `logs/frontend-review-92581f6`. Реальные backend/AI этим просмотром не запускаются; коммит ещё не включён в `dev`.

## Презентационный объект, 06.11.2026

Запуск полного API-стенда с отдельным объектом: `python scripts/start_local.py --cloud-ai --presentation`. Для локально собранного образа: `python scripts/start_local.py --bundled-image fixrate-ai:presentation --cloud-ai --presentation`. Нужны действующий AI Tunnel key и FIXRATE_DEMO_PASSWORD в приватном .env; пароль не помещается в образ или Git.

Создаётся отдельный ЖК «Сосновый парк»: пять единиц оборудования, шесть операций, 46 пунктов чек-листов, календарь текущего месяца, история и шесть обычных учёток четырёх бизнес-ролей. Новые логины стоят первыми в приватном var/compose-local/accounts.txt. Старые объекты/учётки не удаляются; повторный seed не сбрасывает состояния, пароль или ручные изменения. Генератор использует отдельное пространство UUID и метку synthetic_demo в хранилище; источник customer и исходные неизвестные нормы не заменяются.

Это вымышленные данные для презентации по запросу владельца. Нормы/методики/протокол отдельного объекта не являются утверждением нормативов заказчика. В рабочем интерфейсе нет отдельных плашек DEMO/происхождения. Backend, PostgreSQL, авторизация и AI остаются настоящими. ML-ответы не засеваются; сравнение прогноза и анализ фото выполняются через API. В карточку контрольного осмотра приложены копии пары CASE-05 и рабочий PDF-протокол; [происхождение](../../data/presentation/provenance.json). Протокол требует проверки инженером, не является свидетельством о поверке.
