# Установка и выпуск FixRate AI

Новый релизный путь находится в `deploy/`. Developer Compose и [локальный запуск](runtime.md) сохраняются. Локальные пакеты канала `test` не объявляются готовым публичным релизом: контейнерная и платформенная приёмка пока открыта.

## Аудит инфраструктуры 17.11.2026

| Узел | Факт | Решение |
|---|---|---|
| Git | origin=github.com/krangras/FixRateAI перенаправляется на Fir-White/FixRateAI; GitHub default_branch=main, локальный origin/HEAD=dev устарел | CI привязан к main реального GitHub |
| Source | main=892b23a от 07.11, kran_dev=1ef11e7 от 17.11; между ними 478 изменённых файлов | Перед переносом согласовать интеграционный срез, не выдавать старый main за текущий runtime |
| CI | Actions включён; до работы есть только GitVerse sync, Releases/environment нет, main без защиты | Новый release.yml; sync не меняется, GitVerse не объявлен исполнителем Actions |
| Auth | Сессии/CSRF, users/sites/memberships, объектные роли; регистрация сотрудника создаёт pending-заявку | Существующие роли/API переиспользованы; публичная выдача admin запрещена |
| Организации | Отдельной SaaS-модели нет | Одна компания, имя организации в singleton БД; здания/сотрудники не в env |
| Web | React/Vite SPA | Готовый Caddy/frontend image, `/setup` в общей auth-оболочке |
| Worker | OptimizationManager/CP-SAT и scheduler ранее работали внутри API | Отдельный worker использует существующий код; дублирование в API отключено |
| Оркестратор | Сохраняемые цели/request/resume; полный queue/lease recovery остаётся открытым | Установщик не объявляет новое промышленное recovery |
| PostgreSQL | Текущий maintenance не требует pgvector; он был в архивном сметном проекте | PostgreSQL 18; ненужное расширение не добавляется |
| Миграции | Ledger/checksum/advisory lock, seed отдельно | Oneshoot migrate + 024 bootstrap; исправлено возвращение autocommit после migrate/seed |
| Файлы | PHOTO_STORAGE_ROOT хранит фото и личные вложения чата | Постоянный общий API/worker volume; полный backup файлов |
| ML | RF — готовый артефакт, CLIP опционален | Core с RF/solver, без автоматической загрузки весов; неподготовленный CLIP unavailable |
| Telegram/Mini App | Рабочего транспорта в этом source baseline нет | Фиктивный сервис не создаётся; реализация у Артёма TEAM-ALG03 |
| Локальная машина | Docker Desktop/Compose и WSL установлены, engine недоступен; нативный PostgreSQL 18 есть | Docker/OS acceptance BLOCKED; рабочие БД/контейнеры/настройки не менялись |

Контракт предназначен для review Яне (серверная авторизация), Михаилу В (UI), Николаю (TEAM-N01/N03, миграция/выпуск) и QA. Полученное согласование команды не заявляется. По рабочему документу `docs/plans/2026-11-17-team-delivery-plan.md` до 26 ноября приоритетны Core/секреты/bootstrap/сохранность/CI; EXE, offline и новые платформы отложены. Этот ранее созданный файл плана не изменялся и не включён в infrastructure patch.

## Архитектура и платформы

Поставляются один `FixRateAI-Setup.ps1` и один `fixrate-install.sh`: каждый содержит проверяемый архив Compose, manifest и checksums. Библиотеки находятся в готовых образах, installer не вызывает pip/npm и не ставит Python/Node/PostgreSQL на машине заказчика.

Сервисы: PostgreSQL → отдельный migrate → API/worker → Caddy/frontend. API/worker работают под UID 10001, без capabilities. Стандартный PostgreSQL entrypoint подготавливает volume и переключается на postgres; Caddy оставлен с правом bind 80/443 для HTTPS, остальные capabilities сняты. Миграции не делают demo seed.

Core запускается без Ollama: доступы, реестр, детерминированное планирование и workflow не требуют генерации. Необязательная AI-функция при недоступной модели возвращает unavailable, без облачного fallback. Полная готовность MVP/оркестратора этим не подтверждается.

Базовые Python/Node/PostgreSQL/Caddy/Ollama images закреплены проверенными registry digest (`images.lock.json`), Python-библиотеки — `requirements-core.lock`, web — package-lock. Архитектура linux/amd64. Побитовая повторяемость OCI ещё требует Docker-испытания; повторяемость установочных файлов из одних входов проверяется отдельно.

В app image явно устанавливаются закреплённые системные runtime [libstdc++6](https://packages.debian.org/bookworm/libstdc%2B%2B6) и [libgomp1](https://packages.debian.org/bookworm/libgomp1) версии `12.2.0-14+deb12u1`; pip разрешены только binary wheels. Обязательный build import проверяет OR-Tools/sklearn/Pillow/psycopg. Разрешение wheels без Docker выполнено, наличие системных библиотек в итоговом образе подтверждается только успешной контейнерной сборкой.

Целевые платформы: **Windows 11 x64, Docker Desktop/WSL2** и **Ubuntu 24.04 LTS amd64, Docker Engine**. Windows Server CI проверяет PowerShell package, не заменяет чистую Windows 11 install. ARM и произвольные ОС не заявляются.

Нужны Compose >=2.24, готовый Linux Docker engine, свободный порт и минимум 10 GiB свободного диска до pull. Docker рекомендуется выделить 8 GiB RAM; растущие данные и backup требуют дополнительного места. GPU для Core не нужен. Это требования подготовки, не доказанный SLA.

По умолчанию доступ только loopback. Для удалённого режима нужен DNS, открытые 80/443 и возможность выпуска TLS-сертификата; включаются HTTPS/Secure cookies. DB/API/worker/Ollama host-портов не имеют. В локальном режиме неиспользуемые TLS-порты получают случайные loopback host-порты, чтобы установки не конфликтовали.

## Скачать и проверить

Скачайте installer и SHA256SUMS одной версии из доверенной страницы Releases. Сравните SHA-256 файла:

```powershell
Get-FileHash .\FixRateAI-Setup.ps1 -Algorithm SHA256
powershell -NoProfile -ExecutionPolicy Bypass -File .\FixRateAI-Setup.ps1 -Action verify
```

```bash
sha256sum fixrate-install.sh
bash fixrate-install.sh verify
```

`verify` проверяет встроенный архив и каждый файл, не запускает Docker. Проверка хеша не равна испытанию установки и опирается на доверенный источник checksums.

## Windows и Ubuntu

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\FixRateAI-Setup.ps1 -Action doctor
powershell -NoProfile -ExecutionPolicy Bypass -File .\FixRateAI-Setup.ps1 -Action install -OpenBrowser
```

Windows default: `%LOCALAPPDATA%\FixRateAI`; параметры `-InstallDir`, `-Port`, `-PublicHost fixrate.example.org`. Если Docker отсутствует, `-InstallPrerequisites` предлагает официальный winget-пакет с отдельным подтверждением INSTALL. Неготовая WSL2/виртуализация/необходимость перезагрузки прекращают установку с инструкцией повторного запуска. Глобальная execution policy не меняется.

```bash
bash fixrate-install.sh doctor
bash fixrate-install.sh install
```

Ubuntu default: `${XDG_DATA_HOME:-$HOME/.local/share}/fixrateai`; параметры `--install-dir /absolute/path`, `--port`, `--public-host`. `--install-prerequisites` после явного INSTALL ставит подписанные apt-пакеты docker.io/docker-compose-v2. Скрипт не делает curl|bash, chmod 666 Docker socket или скрытое добавление в привилегированную группу. Условия лицензии Docker Desktop не обходятся.

Повтор той же версии сохраняет secrets/project/volumes и пользователей, не выполняет seed. Параллельные install/backup/restore/upgrade сериализованы локальным lock. `-UseLocalImages` / `--local-images` проверяет заранее загруженные образы и применяется CI; это не полноценный offline bundle.

EXE не собирается: подписанный/проверенный wrapper относится к следующей итерации. Основной Windows-интерфейс — PS1, без обещания GUI-установки двойным щелчком.

## Конфигурация и первый запуск

| Файл | Содержимое |
|---|---|
| infrastructure.env | Порты, отдельное случайное имя проекта, HTTPS, явное подключение Ollama |
| secrets.env | Криптографически случайный пароль БД и SHA-256 одноразового кода |
| bootstrap-token.txt | Исходный одноразовый код, не печатаемый в общий лог |
| release.json/images.env | Версия/source и immutable references образов |

Каталог закрыт Windows ACL или Linux 0700/0600. Compose читает секреты при запуске; секретов нет в образах/bundle. Организация, здания, люди и роли сохраняются в БД.

Откройте `/setup`: введите код из файла, организацию, первое здание, имя/email/пароль администратора. После успеха войдите через `/login`. Администратор выдаёт приглашение и принимает сотрудников существующим экраном доступов. Бизнес-роли не подменяются техническим admin.

GET `/api/setup` возвращает только required. POST принимает бизнес-поля и защищённый header `X-FixRate-Setup-Token`. Эти маршруты — документированная инфраструктура до первого principal, исключённая из model tools; они не передают код/пароль в assistant/history.

Одна транзакция с SELECT FOR UPDATE создаёт site/user/admin membership, закрывает singleton и пишет audit. При гонке один запрос успешен, другой получает 409. Hash кода после успеха удаляется. Миграция на населённой базе закрывает bootstrap. Повтор installer не открывает регистрацию и не сбрасывает пользователей.

Для восстановления существующего активного admin оператор с доступом Docker запускает интерактивно, с теми же env/compose:

```text
docker compose ... run --rm api python scripts/release_runtime.py recover-admin --email admin@example.org --confirm-data-replacement
```

Пароль запрашивается getpass дважды, не передаётся аргументом shell. Сессии отзываются, audit сохраняется. Это OS-защищённая процедура, не публичный reset endpoint и не способ выдать admin произвольному сотруднику.

## Status, doctor, Ollama

Для существующей установки используйте тот же InstallDir и action `status`/`doctor`. Status показывает сервисы; doctor проверяет Docker/платформу/диск/Compose, затем БД и временное чтение-запись в файловом хранилище. Бизнес-данные и inference не затрагиваются.

Чтобы подключить **уже установленную** Ollama, задайте infrastructure-параметры и повторите install той же версии:

```dotenv
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_CHAT_MODEL=<фактически установленный tag>
OLLAMA_CHAT_DIGEST=sha256:<фактический digest>
```

Команда `release_runtime.py ollama-status` внутри API делает только GET `/api/tags`. Доступность не равна положительной генеративной приёмке. Личные настройки developer-версии не меняются.

Service `ollama` включается только явно через `--profile ollama`; URL внутри сети — `http://ollama:11434`. Volume изначально пуст, host API закрыт, автоматических model pull нет. Наполнение весов — отдельная согласованная операция. По последнему решению владельца участники могут тестировать на доступных локальных моделях либо через бесплатные/платные API, фиксируя фактические provider/model и профиль прогона. Текущий Compose сохраняет свой Ollama-профиль; API-прогоны выполняются в подходящей отдельной тестовой конфигурации. Пользовательские настройки работающей версии ради тестов не меняются.

## Backup и обновление

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\FixRateAI-Setup.ps1 -Action backup -InstallDir C:\FixRateAI
powershell -NoProfile -ExecutionPolicy Bypass -File .\FixRateAI-Setup.ps1 -Action upgrade -InstallDir C:\FixRateAI
```

```bash
bash fixrate-install.sh backup --install-dir /srv/fixrateai
bash fixrate-install.sh upgrade --install-dir /srv/fixrateai
```

Для upgrade скачивается installer **целевой** версии. `compatible_from` содержит точные проверенные версии. Пока предыдущего официального релиза нет, список пуст. Major PostgreSQL автоматически не меняется.

До миграции останавливаются web/API/worker, сохраняются pg_dump custom-format, всё файловое хранилище, конфигурация и manifest прежнего пакета. Проверяются SHA-256, pg_restore --list, состав tar. На Windows используются BaseStream, не текстовый `>` PowerShell 5.1.

После backup применяются образы/миграции и health. При ошибке миграции новая API не запускается. Один откат image не восстанавливает несовместимую схему; используется прежний проверенный backup. Молчаливого отката данных нет.

## Восстановление

Сначала проверяйте restore в **отдельном InstallDir/project**, не в рабочей установке:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\FixRateAI-Setup.ps1 -Action restore -InstallDir C:\FixRateAI-Test -BackupPath C:\SafeBackup\<id> -ConfirmDataReplacement
```

```bash
bash fixrate-install.sh restore --install-dir /srv/fixrate-test --backup-path /safe/backup --confirm-data-replacement
```

Целевая установка должна быть предварительно создана. Restore сохраняет её инфраструктурные порты/новый пароль роли БД, выбирает образы/Compose из backup, проверяет файлы, останавливает потребителей и восстанавливает БД одной транзакцией, затем хранилище. При ошибке файлов сервисы остаются остановленными; backup сохраняется для повторного восстановления. Единой атомарной транзакции PostgreSQL+filesystem не обещается.

Backup содержит инфраструктурные секреты: нужны закрытые права и принятая политика шифрования/переноса. Автоматическое удалённое encrypted хранилище и RPO/RTO не реализованы. Пользовательские команды не делают down --volumes; это есть только в очистке доказанно отдельных TEST-проектов CI.

## CI и Releases

`release.yml`: push main, PR main, workflow_dispatch и тег vX.Y.Z. Checkout SHA события, Actions закреплены commit SHA. До публикации должны пройти backend lint/dependencies/migrations/tests, frontend typecheck/tests/build, Windows verification и Linux installer acceptance. Проверенные app/web images передаются publisher через CI artifact, без поздней пересборки.

Обычные push, PR и автоматический запуск на теге создают тестовые артефакты Actions, но не пишут в GHCR, не создают Releases и не деплоят. Publisher доступен только через `workflow_dispatch` на теге версии. Он проверяет source label/amd64, получает digest, проверяет анонимное чтение и формирует установщики, Quick Start ZIP, manifest, checksums и notes. GHCR package должен быть публично читаем для публичного installer; логин CI не подменяет проверку доступа клиента. Новый private GHCR package может блокировать первый выпуск до настройки владельцем.

Официальный тег дополнительно требует SHA из main, repository variable `FIXRATE_RELEASES_ENABLED=true`, environment `release` с reviewer, prevent self-review и без admin bypass. Пустой автоматически созданный environment не проходит gate. Concurrency сериализует одну версию. Повтор опубликованной версии проверяет скачанные checksums/source SHA и не создаёт дубль; незавершённый чужой draft не перезаписывается.

Файлы сначала загружаются в draft и скачиваются/проверяются до публикации. Минимальные права обычных jobs — contents:read; publisher — contents/packages/actions. Настройка environment/reviewer, защиты main/тегов, публичного чтения GHCR и первый публичный тег требуют отдельного действия владельца. Эта работа не меняла внешние настройки, не выполняла push/merge main и не публиковала релиз.

## Проверки и остаток

Факты TEST-01…15 и исходный красный прогон сохраняются в [verification](verification.md). Нативные тесты и проверка двух payload не заменяют чистую установку. Контейнерные upgrade/restore, Windows 11 install, повтор CI и тестовый тег остаются открытыми до доступной среды. Локальный test-пакет в var содержит candidate image refs, не является готовым Releases installer.

Основания решений: [Compose startup conditions](https://docs.docker.com/compose/how-tos/startup-order/), [GitHub Packages workflow](https://docs.github.com/en/packages/managing-github-packages-using-github-actions-workflows/publishing-and-installing-a-package-with-github-actions), [защита environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments).
