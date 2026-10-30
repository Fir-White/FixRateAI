# Протокол прогона: контракты ролей, маршрутов и авторизации

Дата: **30.10.2026**. База: `origin/new_backend` @ `16b79af` (FX26-BE01 + reusable role authorization helpers). Зависимости: **QA01, BE01**.

## 1. Назначение и границы

Файл [`test_roles_contracts.py`](test_roles_contracts.py) фиксирует клиент-серверный контракт **до появления реального API**:

- строгие Pydantic-схемы запросов и ответов;
- матрицу «роль × маршрут» из [API-контрактов](../../docs/architecture/api_contracts.md);
- запрет чужих задач и собственной приёмки;
- отказ недействительному пользователю.

**Это не интеграционные тесты.** В прогоне не участвуют PostgreSQL, реальное хранилище сессий, AI-runtime и HTTP-сервер. Используются только in-memory фикстуры и реальные модули `app.schemas` и `app.security.authorization`.

Причина: FX26-BE01 поставил строгие DTO **без фиктивных endpoints и success-заглушек** ([fx26-be01-implementation.md](../../docs/architecture/fx26-be01-implementation.md)). Поэтому таблица `ROUTES` в тесте — исполняемая спецификация маршрутов, а не заявление о работающем сервере. Зелёный прогон не доказывает работоспособность API.

## 2. Что проверяется

| Слой | Проверка | Тестов |
|---|---|---|
| Схемы | Запрет неизвестных полей и клиентских `executor_id`/`assigned_by`/`submitted_by`/`site_id`; закрытые enum статусов; обязательное основание решения; состав бригады; форма `ErrorResponse` | 6 |
| Матрица прав | Реальные `ROLE_PERMISSIONS`: приёмка только у `engineer`, назначение только у `dispatcher`, запись операции не у контролёра | 1 |
| Маршруты | 14 маршрутов × 4 роли = 56 комбинаций allow/deny; негативные пары для исполнителя, контролёра, диспетчера и admin; уникальность и версионирование путей | 65 |
| Аутентификация | Нет сессии, неизвестный пользователь, отключённый пользователь → отказ; известный пользователь → доступ | 4 |
| HTTP-коды отказов | 401 — нет/неизвестный пользователь, 403 — нет роли, 404 — чужая задача | 1 |
| Видимость | Исполнитель видит только назначенные задания; чужой Site и чужая задача недоступны; инженер видит Site, но не чужой Site | 5 |
| Самоприёмка | Инженер-исполнитель не может принять собственную работу; чужую — может; исполнитель не принимает ни одну | 3 |

Итого: **85 тестов**.

## 3. Запуск

Из каталога `backend`:

```powershell
..\.venv\Scripts\python.exe -B -m pytest -q tests/test_roles_contracts.py
```

Полный backend-набор:

```powershell
..\.venv\Scripts\python.exe -B -m pytest -q
```

Дополнительные пакеты не требуются: используются `pydantic` и `pytest`. `fastapi`, `httpx`, БД и переменные окружения не нужны.

## 4. Фактический результат

Среда: Windows, Python **3.12.8**, Pydantic **2.14.2**, pytest **9.2.0**.

| Прогон | Результат |
|---|---|
| `tests/test_roles_contracts.py` | **85 passed** |
| Весь `backend/tests` | **97 passed** (12 существующих + 85 новых) |
| Пропуски, падения, предупреждения | Нет |

## 5. Матрица сценариев

### 5.1. Негативные сценарии (запрещённые действия)

| ID | Роль | Действие | Ожидаемый результат | Тест |
|---|---|---|---|---|
| N-01 | `executor` | Открыть чужое задание | Задача не видна; 404 без раскрытия ID | `test_executor_cannot_open_foreign_task` |
| N-02 | `executor` | Список заданий | Только назначенные ему | `test_executor_sees_only_own_tasks` |
| N-03 | `executor` | Принять/отклонить работу | `AuthorizationError` → 403 | `test_executor_cannot_review_any_task`, `test_executor_is_denied_supervisory_routes` |
| N-04 | `executor` | Утвердить операцию, назначить бригаду, изменить регламент | 403 | `test_executor_is_denied_supervisory_routes` |
| N-05 | `engineer` (контролёр) | Изменить регламент | 403 | `test_engineer_cannot_change_regulation` |
| N-06 | `engineer` | Назначить или отменить задание | 403 | `test_engineer_cannot_assign_or_cancel_tasks` |
| N-07 | `dispatcher` | Принять работу, утвердить операцию | 403 | `test_dispatcher_cannot_review_or_approve_operations` |
| N-08 | `admin` без роли `engineer` | Принять работу, назначить бригаду | 403; admin не заменяет контролёра | `test_admin_alone_does_not_replace_engineer_or_dispatcher` |
| N-09 | `engineer` + `executor` | Принять собственную работу | 403 `own execution` | `test_engineer_cannot_review_own_execution` |
| N-10 | Нет сессии | Любой защищённый маршрут | `AuthenticationError` → 401 | `test_missing_session_is_rejected` |
| N-11 | Неизвестный `user_id` | Любой защищённый маршрут | 401 | `test_unknown_user_is_rejected` |
| N-12 | Отключённый пользователь | Любой защищённый маршрут | 401 | `test_disabled_user_is_rejected` |
| N-13 | Пользователь Site B | Задания Site A | Не видны; 404 | `test_outsider_does_not_see_foreign_site_tasks`, `test_engineer_sees_site_tasks_but_not_other_site` |
| N-14 | Клиент | Передать `executor_id`, `assigned_by`, `submitted_by`, `site_id` в Task | `ValidationError` (extra=forbid) | `test_task_response_rejects_client_supplied_identity_fields` |
| N-15 | Клиент | Решение без основания, с чужим `verdict`, `revision=0` | `ValidationError` | `test_review_command_requires_reason_and_known_verdict` |
| N-16 | Клиент | Назначение без исполнителей или с naive временем | `ValidationError` | `test_assignment_command_requires_crew_and_positive_revision` |
| N-17 | Клиент | Неизвестный статус задания (`approved`) | `ValidationError` | `test_task_state_enum_is_closed` |

### 5.2. Разрешённые действия (контроль ложных запретов)

| ID | Роль | Действие | Ожидаемый результат | Тест |
|---|---|---|---|---|
| P-01 | `dispatcher` | Создать задание, назначить, отменить, сгенерировать план | Разрешено | `test_route_matrix_allows_or_denies_role` |
| P-02 | `engineer` | Утвердить операцию, план, принять чужую работу | Разрешено | то же, `test_engineer_can_review_foreign_execution` |
| P-03 | `executor` | Взять назначенное задание, сдать отчёт, загрузить фото | Разрешено | `test_route_matrix_allows_or_denies_role` |
| P-04 | `admin`, `dispatcher` | Изменить регламент | Разрешено | то же |
| P-05 | `dispatcher`, `engineer` | Создать привязку | Разрешено | то же |
| P-06 | Любая известная роль | Читать задания в своём Site | Разрешено | `test_authenticated_user_can_list_tasks` |

## 6. Матрица маршрутов

| Метод | Путь (после `/api/v1/maintenance`) | Роли |
|---|---|---|
| GET | `/tasks`, `/tasks/{task_id}` | все; для `executor` — только свои |
| POST | `/tasks` | `dispatcher` |
| POST | `/tasks/{task_id}/assign` | `dispatcher` |
| POST | `/tasks/{task_id}/start` | `executor` |
| POST | `/tasks/{task_id}/review` | `engineer` |
| POST | `/tasks/{task_id}/cancel` | `dispatcher` |
| POST | `/operations` | `dispatcher`, `admin` |
| POST | `/operations/{operation_id}/approve` | `engineer` |
| PATCH | `/regulations/{regulation_id}` | `dispatcher`, `admin` |
| POST | `/bindings` | `dispatcher`, `engineer` |
| POST | `/plans/generate` | `dispatcher` |
| POST | `/plans/{plan_id}/approve` | `engineer` |
| POST | `/executions/{execution_id}/submit` | `executor` |

## 7. Ограничения

1. **Нет реального router.** Таблица `ROUTES` — спецификация; тесты не вызывают HTTP и не проверяют коды ответов через `TestClient`. Проверяются типы отказов и их отображение в 401/403/404.
2. **Нет хранилища сессий.** `PrincipalDirectory` — фикстура. Хеши токенов, cookie, CSRF и срок действия не проверяются.
3. **Нет БД и AI.** Site scope и принадлежность задачи проверяются на in-memory проекции, а не SQL-запросами.
4. **`ROLE_PERMISSIONS` — черновой.** Тест фиксирует текущее разделение обязанностей; при изменении матрицы тест должен меняться одновременно с контрактом.
5. **Idempotency, revision-конфликты, `STALE_SNAPSHOT`** не покрыты — это следующий слой после появления сервисов.

## 8. Следующий шаг

Когда появится реальный FastAPI router:

1. Заменить `ROUTES`/`PrincipalDirectory` на импорт приложения и dependency override сессии.
2. Проверить те же сценарии через `TestClient` с кодами 401/403/404/409/422.
3. Сверить OpenAPI приложения с таблицей маршрутов из раздела 6.
4. Добавить проверки CSRF, `Idempotency-Key`, `expected_revision` и site scope на SQL-уровне.

До этого момента формулировка «API проверен интеграционно» запрещена: проверен только контракт.
