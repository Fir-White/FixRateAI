# Кандидат локальной установки и выпуска — 17.11.2026

Результат: реализован отдельный релизный контур, который упаковывает существующий FixRate AI в заранее собранные образы и single-file Windows/Linux installers. Статус **LOCAL CANDIDATE / RELEASE BLOCKED**. Готовый официальный installer из Releases пока отсутствует. [Единая инструкция](../service/installation.md) содержит аудит, команды, требования и восстановление; [протокол TEST-01…15](../service/verification.md#17112026--кандидат-установки-и-выпуска) различает выполненные и открытые испытания.

## Предлагаемый PR

Название: `Add Docker release packaging, one-time installation bootstrap and protected CI releases`.

Чистая установка раньше требовала подготовки developer runtime и не имела безопасного первого admin или проверяемого release pipeline. Кандидат добавляет отдельный Compose с API/worker/migrator/PostgreSQL/Caddy, digest-пины и Core lock, single-file PS1/bash, bootstrap и команды install/status/doctor/backup/restore/upgrade. Core не требует Ollama; существующая внешняя или profile-local Ollama подключается явно без скачивания моделей.

Bootstrap использует текущие users/sites/memberships/session и выдаёт admin один раз по установочному коду. Миграция **024** добавочная; старые пользователи закрывают первоначальную регистрацию. При проверке конкурентного bootstrap устранён дефект autocommit в существующем migrator/seed. Новые маршруты `/api/setup` документированы как инфраструктура до появления principal; публичная регистрация сотрудников/их роли не заменены.

Workflow проверяет точный SHA, тесты/миграции/сборку, generated installer smoke и Windows payload. Main создаёт CI-кандидаты; строгий semver tag допускается к публичному release только через независимый reviewer, owner enable flag, SHA из main и успешные gates. Рабочая production-инфраструктура автоматически не обновляется. Backup включает БД, всё файловое хранилище и прежний bundle; restore требует явного подтверждения, несовместимый downgrade образа не считается откатом данных.

## Проверки

- Native PostgreSQL 18: **68 passed**, реальный HTTP bootstrap/enrollment, race, populated migration, recovery, pg_dump/pg_restore в другую БД и файловый roundtrip.
- SetupPage **2 passed**; полный frontend **657 passed / 6 failed** — выпуск блокируется. Typecheck/build успешны, initial JS 123,76 KiB gzip.
- Четыре production Chrome профиля, ошибки/успех/Back/Forward/reload; scoped fixtures, без заявления backend browser E2E. Ввод в установившемся состоянии и нативная wheel-прокрутка уложились в ориентиры; начальный desktop outlier записан в протоколе.
- Два реальных embedded payload проверены PowerShell/Git Bash; Compose config/actionlint/ruff/contracts/artifacts проходят. 38 точных Linux Python 3.12 wheels разрешены.
- Docker build/install/restart/upgrade/fault migration, Windows 11 чистая установка, настоящие main CI/repeat/tag/public download **не выполнены**. Цель целиком ещё не достигнута.

## Граница интеграции

Работа подготовлена поверх локального **kran_dev `1ef11e7d34579686a07236bba25a0095ad9c6db3`**. Во время аудита фактическая default branch GitHub — **main `892b23addb66a523acfe1920ff52eaaca66fd923`**; `origin/HEAD → dev` локально устарел. Между baseline main и текущим HEAD **478 файлов / 101176 добавлений / 416 удалений**. Маленький infrastructure patch нельзя считать самодостаточным PR к старому main: он использует текущие users/roles/assistant/worker и схемы до 023. Требуется согласованное включение runtime baseline либо rebase этого patch на уже включённый baseline. Непроверенный перенос всех 478 файлов в main не выполнен.

Подготовлен локальный review patch/файловый manifest/PR description в ignored `var/release-installation-20261117/handoff/`. Существующие пользовательские dossier HTML и командный план исключены; общий Git index не изменялся. Это материалы для PR, **PR на хостинге не открыт**, commit/push/merge не выполнены.

## Открытые условия передачи

1. Николай TEAM-N01/N03: независимый review инфраструктуры и порядок интеграции текущего runtime в main. Яна: auth/bootstrap/migration/recovery. Михаил В: setup UI. QA: независимая платформа/матрица. Согласование не получено и сообщения команде не отправлялись.
2. Поднять разрешённый отдельный Docker Engine/runner с тестовыми volumes. На этой машине запуск Docker Desktop может автоматически поднять прежние контейнеры; engine не включался ради теста без отдельного разрешения на этот эффект.
3. Разобрать шесть frontend отказов и выполнить весь backend/ML gate на Linux/Python 3.12. Ограниченный native PASS не заменяет этот gate.
4. Выполнить TEST-01/02/06/07/09/10/11 реальным installer; TEST-08 — только с предоставленной существующей Ollama/моделями. Проверить Windows 11 отдельно от Server runner.
5. Владелец настраивает main/tag protections, release reviewer без self-review/admin bypass, публичное чтение согласованного GHCR и `FIXRATE_RELEASES_ENABLED`. Внешние настройки не менялись. Затем разрешить CI в согласованной ветке и отдельный пробный tag release, проверить rerun/download/checksums.

EXE/signing, полноценный offline bundle, ARM/другие ОС, encrypted remote backup и промышленный multiworker recovery оркестратора остаются следующим объёмом; этот кандидат не закрывает их и не меняет сроки приёмки 28 ноября/защиты 5 декабря.
