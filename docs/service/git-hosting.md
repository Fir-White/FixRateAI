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

## Фактический результат переноса

Перенесены 18 веток и 3 тега. Все 12 исходных веток GitVerse и три refs/pull/*/head остаются достижимы; отдельные PR heads опубликованы архивными ветками. Сравнение git ls-remote --heads --tags подтвердило точное совпадение всех 21 ссылок GitHub и GitVerse. Git LFS объектов не обнаружено.

Проверены реальные GitHub Actions:

- [Автоматический запуск после push, 41817344524](https://github.com/krangras/FixRateAI/actions/runs/41817344524) — success, ветки и теги отправлены в GitVerse.
- [Повторный ручной запуск из dev, 41817427171](https://github.com/krangras/FixRateAI/actions/runs/41817427171) — success, состояние уже синхронизировано.

В скачанных Actions logs значение GitVerse-доступа отсутствует. YAML/Bash syntax и минимальные contents: read проверены отдельно. Фактические результаты: reports/git-migration/20261104-results.json; журналы push и Actions — logs/git-migration. Перенос авторизован владельцем, включая публичные снимки локальной работы и хранение доступа в GitHub Secrets; значения секретов в этих файлах не записываются.

Снимок local-dev содержит 108 новых/изменённых исходных файлов, снимок frontend-next — 63. Архив reports.zip и приватные runtime-данные остаются локально. Начальные snapshot-коммиты: c01a7ca (local-dev), 0ecb70d (frontend-next). Документация снимка может обновляться следующими коммитами; исходники сохранены в его ancestry.

Рабочие папки и их исходный staging сохранены. Локальная dev до переноса отставала от GitVerse на 17 коммитов; её незакоммиченная работа теперь дополнительно находится в migration/local-dev-20261104. Перед прямым push из этой старой dev требуется обычная интеграция новой origin/dev с локальной работой. Автоматическая синхронизация хостингов этого объединения не делает и чужую историю не переписывает. Для нового checkout использовать git clone https://github.com/krangras/FixRateAI.git.
