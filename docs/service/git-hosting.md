# GitHub и синхронизация GitVerse

Основной репозиторий: https://github.com/krangras/FixRateAI. Второй хостинг: https://gitverse.ru/firewhite/FixRate_AI. Основная интеграционная ветка — dev.

## Состав веток и история

Эталон — 12 исходных веток GitVerse до переноса 04.11.2026, записанные в private manifest var/git-migration/20261104T104549Z/manifest.json. Исходных тегов в GitVerse не было. Сохраняются archive/legacy-ai-estimator, dev, docs/tests-p0, feat/ml-forecasting-photo-review, feature/frontend-kran, feature/frontend-next, front/mvidy, kran_dev, main, new_backend, qa/roles-contracts и qa/schedule-forecast-tests.

Локальные backend/QA/auth/Compose изменения из основного checkout объединены с актуальной dev обычным merge с сохранением обеих историй. Локальный Workspace-редизайн записан в существующую feature/frontend-next поверх её исходного tip. Локальные коммиты kran_dev сохранены в одноимённой ветке. Эти изменения дополняют исходный GitVerse, не переписывая опубликованные коммиты.

При первом переносе были избыточно опубликованы archive/frontend-kran, archive/gitverse-pr-1/2/3, migration/local-dev-20261104, migration/frontend-next-20261104 и три backup-тега. По уточнению владельца эти дополнительные ссылки удалены с обоих хостингов после включения локальных исходников в обычные ветки. Коммиты PR и прежние ссылки остаются в private bundle; оригинальные GitVerse-ветки сохраняются. Полный backup до очистки: var/git-migration/20261104T104549Z/before-cleanup-all.bundle.

.env, var, logs, кеши, зависимости, сгенерированные отчёты и reports.zip не публикуются как новые исходники. Файлы локальной среды и настоящая БД не удаляются.

## Работа и синхронизация

origin указывает на GitHub, gitverse — на GitVerse. Workflow [Sync GitHub and GitVerse](https://github.com/krangras/FixRateAI/actions/workflows/gitverse-sync.yml) синхронизирует все ветки и теги в обе стороны, сохраняя SHA коммитов. Обычный push в любой из репозиториев становится видимым на втором хостинге после успешного запуска синхронизации.

GitHub → GitVerse: запуск при push в ветку с workflow. GitVerse → GitHub: автоматическая проверка по расписанию `*/5 * * * *` на default branch `dev`, также доступна кнопка Run workflow. GitVerse webhook и внешний постоянно работающий сервер не требуются. Это плановый опрос, а не мгновенная доставка события: GitHub может задерживать или пропускать плановые запуски при нагрузке; после 60 дней отсутствия активности в публичном репозитории расписание может отключиться. Ограничения описаны в [GitHub Actions: schedule](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

Исполняемая логика — [scripts/sync_git_hosts.py](../../scripts/sync_git_hosts.py). Временный bare-репозиторий получает только Git-объекты и refs; содержимое импортируемых веток не исполняется. Управляющий скрипт всегда загружается из GitHub `dev`. Проверки истории определяют, какая сторона содержит более новый совместимый коммит. Новые ветки и теги копируются; совпадающие refs не обновляются. Повторный запуск не создаёт коммитов, поэтому взаимная отправка не образует бесконечного цикла.

Если одноимённую ветку независимо изменили на обоих хостингах, обе истории сохраняются, workflow получает статус failed и показывает имена/SHА конфликтующих refs в Summary. Независимые безопасные обновления при этом переносятся. Различающиеся одноимённые теги также считаются конфликтом. Для разрешения нужно объединить ветку обычным merge либо вручную определить корректное имя тега, затем повторить workflow. Автоматического merge, force push и удаления refs нет. Отправка на каждый хостинг атомарна; при конкурирующем несовместимом push Git отвергает обновление. Двухсторонняя транзакция между хостингами отсутствует: если один push прошёл, а второй не прошёл, следующий запуск повторяет сравнение без перезаписи истории.

Удаление ветки только на одном хостинге приводит к её восстановлению со второго. Намеренное удаление нужно делать на обоих хостингах при временно отключённом workflow. Автосинхронизация переносит историю репозитория, не Issues/PR/пользователей и не локальные незакоммиченные файлы. Рабочие папки разработчиков автоматически не обновляются; публикация сайта/перезапуск приложения в этот workflow не входят.

## Доступ

GitHub Actions сохраняет минимальные `contents: read`. Для GitVerse используются существующие repository secrets `GITVERSE_USERNAME` и `GITVERSE_TOKEN`. Для записи в GitHub добавлен отдельный write deploy key «GitVerse bidirectional mirror», ограниченный репозиторием `krangras/FixRateAI`; приватная часть хранится в Actions secret `GH_MIRROR_SSH_KEY`. Личный GitHub-токен в workflow не сохраняется. Такой ключ позволяет переносить также коммиты с изменениями workflow; встроенный read-only GITHUB_TOKEN используется только для чтения метаданных GitHub. Описание прав — [GitHub deploy keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys).

Оба хостинга и пользователи, имеющие право писать в их ветки, являются доверенными источниками кода. Добавление write-доступа на GitVerse означает возможность перенести эти коммиты на GitHub. Изменения GitHub `dev`, включая workflows, должны проверяться как изменения управляющего кода автоматизации.

Значения секретов не помещаются в URL, исходники и документацию. Временные key/askpass/known_hosts создаются с правами только для runner и удаляются при завершении. Host keys GitHub получаются через его HTTPS API; SSH StrictHostKeyChecking включён. Локальные приватные файлы подготовки находятся в игнорируемом `var/git-sync`; это не исходники.

Для ротации GitVerse-доступа обновить Secrets в Settings → Secrets and variables → Actions. Для GitHub-ключа создать новую пару, заменить deploy key в Settings → Deploy keys и `GH_MIRROR_SSH_KEY`, затем запустить workflow вручную. Для отзыва удалить deploy key и секрет. Не присылать ключи/токены в чат и не добавлять их в .env.example.

[GitVerse: токены](https://gitverse.ru/docs/collaborative/authentification/tokens/), [GitHub: секреты Actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets).

## Проверки

Первый перенос с 18 ветками/3 тегами подтверждён успешными Actions 41817344524, 41817427171, 41817744365 и 41817744640; эти числа описывают исторический промежуточный этап. Итоговая проверка очистки подтвердила ровно 12 исходных имён веток, отсутствие добавленных backup-тегов, сохранение ancestry исходных tips и локальных исходников, совпадение SHA на обоих хостингах и успешный следующий запуск Actions. Итоги: reports/git-migration; журналы: logs/git-migration. [Фактические результаты](verification.md).

## Подтверждённый результат очистки

GitHub, GitVerse и локальные heads содержат ровно 12 исходных имён веток; тегов 0. Шесть дополнительных веток и три backup-тега удалены на обоих сервисах атомарными push с проверкой ожидаемого SHA каждой удаляемой ссылки. Исходные branch tips остаются предками соответствующих веток; снимки локальных изменений включены в ancestry dev и feature/frontend-next. Локальная dev обновлена объединённой версией и больше не отстаёт; все три рабочие папки чистые. Вместо локальной archive/frontend-kran используется исходная feature/frontend-kran.

Полная проверка dev: verify-20261104-162000-c54b6633, 29/29, 576 Python / 196 UI / 24 E2E, npm audit 0. Compose с реальными RF/CLIP: compose-20261104-161727-39bd06b6, 58/58. Редизайн feature/frontend-next: build и 296 unit-тестов. Итоги удаления и сравнения: reports/git-migration/20261104-cleanup-results.json; логи cleanup-*.log — logs/git-migration. [Реестр исходных веток](../../data/provenance/GITVERSE_BASELINE.json).

На время атомарной очистки Sync GitVerse приостанавливался; затем включён повторно. Автоматическая отправка после очистки подтверждена [успешным push-run 41821292804](https://github.com/krangras/FixRateAI/actions/runs/41821292804) при окончательном составе 12 веток и 0 тегов. Итог сохранён в том же локальном JSON-протоколе.

## 05.11.2026: двусторонняя синхронизация

Односторонний workflow заменён на проверку fast-forward в обе стороны. До изменения GitVerse `feature/frontend-next` уже содержал `92581f6`, тогда как GitHub оставался на `8d6935c`; этот реальный коммит используется для проверки импорта без создания служебных веток.

Локальные проверки: `python -B -m pytest tests/automation/test_git_host_sync.py -q --override-ini addopts=''` — **9 PASS** на настоящих временных bare-репозиториях. Покрыты оба направления, повтор, новые ветки, annotated/lightweight tags, отказ перезаписи разных тегов, расхождение истории с переносом независимой ветки, dry-run, восстановление отсутствующей ветки и отказ при одновременном несовместимом push. YAML и Bash workflow прошли синтаксическую проверку. Протокол реального Actions и окончательное сравнение refs фиксируются в [проверках](verification.md).
