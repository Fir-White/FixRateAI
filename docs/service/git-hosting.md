# GitHub и синхронизация GitVerse

Основной репозиторий: https://github.com/krangras/FixRateAI. Второй хостинг: https://gitverse.ru/firewhite/FixRate_AI. Основная интеграционная ветка — dev.

## Как работать

После настройки origin указывает на GitHub, gitverse — на исходный GitVerse. Обычный git push отправляет коммиты в GitHub. Workflow Sync GitVerse переносит все GitHub-ветки и теги в GitVerse; оба сайта сохраняют одни и те же SHA. Проверка запускается при push в ветку с workflow, вручную и по расписанию */5 минут на default branch dev. Для старых веток без workflow используется расписание; GitHub может задерживать плановые запуски. Статус: https://github.com/krangras/FixRateAI/actions/workflows/gitverse-sync.yml.

Синхронизация односторонняя. Изменения, отправленные напрямую в GitVerse, нужно получить через git fetch gitverse и объединить с GitHub перед следующей отправкой. Workflow использует обычный atomic push, не выполняет force и не удаляет ветки/теги. Расхождение истории приводит к красному запуску вместо перезаписи чужих коммитов. Удаление веток на GitHub намеренно не удаляет копии в GitVerse.

## Доступ

GitHub Actions имеет contents: read. Для отправки в GitVerse используются repository secrets GITVERSE_USERNAME и GITVERSE_TOKEN; токену требуется доступ к репозиториям. Значения не помещаются в URL, исходники или документацию. Askpass-файл на временном runner содержит только обращения к переменным и удаляется после выполнения. При ротации токена обновить секрет в Settings → Secrets and variables → Actions, затем запустить Sync GitVerse вручную. Не присылать токен в чат и не добавлять его в .env.example.

[GitVerse: токены](https://gitverse.ru/docs/collaborative/authentification/tokens/), [GitHub: секреты Actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets), [запуск workflow](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows).

## Сохранение истории при переносе 04.11.2026

Перед переносом сохранены полный mirror GitVerse, локальный bundle --all и manifest в var/git-migration/20261104T104549Z. Исходные удалённые ветки и теги не переписываются. Коммиты refs/pull/*/head сохранены как archive/gitverse-pr-N, поскольку GitHub управляет собственным пространством refs/pull. Это сохраняет Git-коммиты, но не переносит обсуждения и настройки pull requests между сервисами.

Локальные ветки, отсутствующие в GitVerse, также публикуются. Локальные незакоммиченные исходники сохранены снимками migration/local-dev-20261104 и migration/frontend-next-20261104. Их parent — HEAD соответствующей рабочей папки; запись через отдельный Git index сохраняет исходные рабочие файлы и staging без изменений. Эти ветки не объявляются автоматически объединёнными с dev. В dev публикуется актуальный GitVerse tip с отдельным коммитом настройки синхронизации.

.env, var, logs, кеши, зависимости, сгенерированные отчёты и reports.zip не добавляются в снимки. Уже существующая опубликованная история переносится без фильтрации и изменения SHA. Проверки backend/UI относятся к явно указанным срезам; сам перенос истории не является новым прогоном приложения. Итоговые сравнения refs и запуск Actions фиксируются в журнале переноса, logs/git-migration и reports/git-migration.
