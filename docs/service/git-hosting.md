# GitHub и синхронизация GitVerse

Основной репозиторий: https://github.com/krangras/FixRateAI. Второй хостинг: https://gitverse.ru/firewhite/FixRate_AI. Основная интеграционная ветка — dev.

## Состав веток и история

Эталон — 12 исходных веток GitVerse до переноса 04.11.2026, записанные в private manifest var/git-migration/20261104T104549Z/manifest.json. Исходных тегов в GitVerse не было. Сохраняются archive/legacy-ai-estimator, dev, docs/tests-p0, feat/ml-forecasting-photo-review, feature/frontend-kran, feature/frontend-next, front/mvidy, kran_dev, main, new_backend, qa/roles-contracts и qa/schedule-forecast-tests.

Локальные backend/QA/auth/Compose изменения из основного checkout объединены с актуальной dev обычным merge с сохранением обеих историй. Локальный Workspace-редизайн записан в существующую feature/frontend-next поверх её исходного tip. Локальные коммиты kran_dev сохранены в одноимённой ветке. Эти изменения дополняют исходный GitVerse, не переписывая опубликованные коммиты.

При первом переносе были избыточно опубликованы archive/frontend-kran, archive/gitverse-pr-1/2/3, migration/local-dev-20261104, migration/frontend-next-20261104 и три backup-тега. По уточнению владельца эти дополнительные ссылки удалены с обоих хостингов после включения локальных исходников в обычные ветки. Коммиты PR и прежние ссылки остаются в private bundle; оригинальные GitVerse-ветки сохраняются. Полный backup до очистки: var/git-migration/20261104T104549Z/before-cleanup-all.bundle.

.env, var, logs, кеши, зависимости, сгенерированные отчёты и reports.zip не публикуются как новые исходники. Файлы локальной среды и настоящая БД не удаляются.

## Работа и синхронизация

origin указывает на GitHub, gitverse — на GitVerse. Обычный git push отправляет коммиты в GitHub. Workflow Sync GitVerse переносит все GitHub-ветки и теги в GitVerse с сохранением SHA. Проверка запускается при push в ветку с workflow, вручную и по расписанию */5 минут на default branch dev. Для исторических веток без workflow используется расписание; GitHub может задерживать плановые запуски. Статус: https://github.com/krangras/FixRateAI/actions/workflows/gitverse-sync.yml.

Синхронизация односторонняя. Новые изменения, отправленные напрямую в GitVerse, нужно получить через git fetch gitverse и объединить с GitHub. Workflow использует atomic push без force и не удаляет ветки/теги автоматически. Расхождение истории приводит к ошибке вместо перезаписи чужих коммитов. Однократная очистка дополнительных ссылок выполнена отдельно по явному запросу владельца; это не разрешение автоматически удалять будущую работу команды на GitVerse.

## Доступ

GitHub Actions имеет contents: read. Для отправки используются repository secrets GITVERSE_USERNAME и GITVERSE_TOKEN с доступом к GitVerse-репозиторию. Значения не помещаются в URL, исходники и документацию. Временный askpass-файл runner содержит обращения к переменным и удаляется после выполнения. При ротации обновить секрет в Settings → Secrets and variables → Actions, затем запустить Sync GitVerse вручную. Не присылать токен в чат и не добавлять его в .env.example.

[GitVerse: токены](https://gitverse.ru/docs/collaborative/authentification/tokens/), [GitHub: секреты Actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets).

## Проверки

Первый перенос с 18 ветками/3 тегами подтверждён успешными Actions 41817344524, 41817427171, 41817744365 и 41817744640; эти числа описывают исторический промежуточный этап. Новая проверка очистки должна подтвердить ровно 12 исходных имён веток, отсутствие добавленных backup-тегов, сохранение ancestry исходных tips и локальных исходников, совпадение SHA на обоих хостингах и успешный следующий запуск Actions. Итоги: reports/git-migration; журналы: logs/git-migration. [Фактические результаты](verification.md).

## Подтверждённый результат очистки

GitHub, GitVerse и локальные heads содержат ровно 12 исходных имён веток; тегов 0. Шесть дополнительных веток и три backup-тега удалены на обоих сервисах атомарными push с проверкой ожидаемого SHA каждой удаляемой ссылки. Исходные branch tips остаются предками соответствующих веток; снимки локальных изменений включены в ancestry dev и feature/frontend-next. Локальная dev обновлена объединённой версией и больше не отстаёт; все три рабочие папки чистые. Вместо локальной archive/frontend-kran используется исходная feature/frontend-kran.

Полная проверка dev: verify-20261104-162000-c54b6633, 29/29, 576 Python / 196 UI / 24 E2E, npm audit 0. Compose с реальными RF/CLIP: compose-20261104-161727-39bd06b6, 58/58. Редизайн feature/frontend-next: build и 296 unit-тестов. Итоги удаления и сравнения: reports/git-migration/20261104-cleanup-results.json; логи cleanup-*.log — logs/git-migration. [Реестр исходных веток](../../data/provenance/GITVERSE_BASELINE.json).

На время атомарной очистки Sync GitVerse приостанавливался; затем включён повторно. Следующий push этого протокола проверяет автоматическую отправку при окончательном составе 12 веток и 0 тегов. Состояние запуска доступно в Actions, его итог сохраняется в том же локальном JSON-протоколе.
