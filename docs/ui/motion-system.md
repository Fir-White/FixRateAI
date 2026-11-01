# FixRate AI — Motion System 1.0

Единая система появления, переходов и обратной связи существующего React-интерфейса. Основные средства — CSS custom properties и конечные Web Animations API-анимации. Маршруты, серверная авторизация, роли, API и исходные SVG не заменяются. Поведение форм и самостоятельная система Aurora описаны в [web](../service/web.md#вход-и-фон-aurora).

Текущая Aurora не содержит большого центрального знака и затемняющих слоёв. Сохранён небольшой неподвижный бренд над формой. Изображения и видео первоначальной проверки Motion System ниже фиксируют прежнюю композицию; актуальная геометрия и её отдельные проверки связаны из раздела web.

## Токены

Источник — [motion.css](../../frontend/src/shared/motion/motion.css), подключённый из [index.css](../../frontend/src/index.css). Значения считываются перед запуском, а не каждый кадр. Компактная компоновка: ширина до 820 px либо до 1000 px при высоте до 500 px.

| Переменная | Desktop | Компактный экран | Назначение |
|---|---|---|---|
| `--motion-fast` | 160 ms | 140 ms | Поля, кнопки, ссылки и feedback |
| `--motion-normal` | 220 ms | 220 ms | Повторно используемый обычный переход |
| `--motion-slow` | 360 ms | 160 ms внутри auth | Элемент первого reveal |
| `--motion-reveal` | 600 ms | 300 ms | Панель и заголовок при входе в auth |
| `--motion-stagger` | 55 ms | 20 ms | Последовательность полей |
| `--motion-auth-exit` | 140 ms | 90 ms | Исчезновение старой auth-формы |
| `--motion-auth-enter` | 160 ms | 110 ms | Появление новой auth-формы |
| `--motion-success-exit` | 160 ms | 100 ms | Подтверждённый успешный вход |
| `--motion-app-enter` | 200 ms | 180 ms | Появление рабочего контента |
| `--ease-standard` | `cubic-bezier(0.2, 0.8, 0.2, 1)` | то же | Появление и взаимодействие |
| `--ease-exit` | `cubic-bezier(0.4, 0, 1, 1)` | то же | Исчезновение |

При reduced-motion CSS-эффекты отключаются, длительности WAAPI и stagger обнуляются. Значения — часть текущей реализации, а не обязательство сохранять одинаковое число для разных по смыслу эффектов.

## Компоненты и изменённые файлы

| Слой | Файлы и назначение |
|---|---|
| Токены и общие стили | [motion.css](../../frontend/src/shared/motion/motion.css), [index.css](../../frontend/src/index.css): переменные, microinteractions и default transition-токены Tailwind |
| Конечные эффекты | [animate.ts](../../frontend/src/shared/motion/animate.ts): WAAPI, feature detection, отмена, hidden/reduced-motion |
| Feedback | [useFeedbackMotion.ts](../../frontend/src/shared/motion/useFeedbackMotion.ts), [feedbackMotion.ts](../../frontend/src/shared/motion/feedbackMotion.ts): измерение блока по событию и управление только собственными эффектами |
| Общая auth-оболочка | [AuthLayout.tsx](../../frontend/src/pages/AuthLayout.tsx), [useAuthTransition.ts](../../frontend/src/features/auth/useAuthTransition.ts), [AuthMotionContext.ts](../../frontend/src/features/auth/AuthMotionContext.ts): один отображаемый Outlet, exit/enter и подтверждённый success |
| Первое появление | [useInitialReveal.ts](../../frontend/src/features/auth/useInitialReveal.ts), [LoginPage.css](../../frontend/src/pages/LoginPage.css): последовательность появления и сохранение координат нажатия |
| Auth-состояния | [LoginPage.tsx](../../frontend/src/pages/LoginPage.tsx), [RegistrationPage.tsx](../../frontend/src/pages/RegistrationPage.tsx), [AuthFormError.tsx](../../frontend/src/features/auth/AuthFormError.tsx), [useAuthValidation.ts](../../frontend/src/features/auth/useAuthValidation.ts), [authGesture.ts](../../frontend/src/features/auth/authGesture.ts): фокус, pending, ошибки и защита допустимого жеста |
| UI-kit | [Button.tsx](../../frontend/src/shared/ui/Button.tsx), [Form.tsx](../../frontend/src/shared/ui/Form.tsx): общие профили взаимодействия и доступный feedback |
| Контент приложения | [usePageEntry.ts](../../frontend/src/shared/motion/usePageEntry.ts), [authEntry.ts](../../frontend/src/shared/motion/authEntry.ts), [AppShell.tsx](../../frontend/src/layouts/AppShell.tsx), [ExecutorLayout.tsx](../../frontend/src/layouts/ExecutorLayout.tsx), [HomeRedirect.tsx](../../frontend/src/pages/HomeRedirect.tsx): opacity на `location.key`, фокус подтверждённого входа и сохранение маркера при домашнем redirect без размонтирования layout/header |
| Регрессии | [AuthMotion.test.tsx](../../frontend/src/features/auth/AuthMotion.test.tsx), [LoginPage.test.tsx](../../frontend/src/pages/LoginPage.test.tsx), [login.spec.ts](../../frontend/e2e/login.spec.ts): отмена, история, profile race, redirect и реальные жесты |

## Первое появление авторизации

[AuthLayout](../../frontend/src/pages/AuthLayout.tsx) сохраняет Aurora и бренд отдельно от изменяемой области формы. Панель появляется через opacity. Заголовок, подзаголовок и поля используют opacity и небольшое вертикальное смещение, кнопка — появление после полей; вторичные ссылки не получают длинной задержки. Desktop-последовательность укладывается примерно в 745 ms, мобильная — примерно в 320 ms.

Reveal выполняется при монтировании auth-оболочки, а не заново при каждом переходе между её страницами. Первый ввод доступен сразу. Взаимодействие пользователя завершает или приостанавливает принадлежащие системе эффекты так, чтобы цель нажатия не смещалась посреди жеста. Вся панель, родительские элементы логотипов и страницы не масштабируются и не перемещаются.

## Переход вход ↔ регистрация

[useAuthTransition](../../frontend/src/features/auth/useAuthTransition.ts) удерживает один отображаемый Outlet. Последовательность: исчезновение → замена содержимого при невидимой старой форме → появление. На desktop это 140 + 160 ms, на компактном экране 90 + 110 ms. Изменение естественной высоты происходит при замене содержимого; непрерывного tween высоты всей панели нет.

Во время exit старая область формы и её footer получают `inert` и `aria-hidden`; новая форма ещё не смонтирована. Одновременных активных форм нет. Класс регистрации, подписи и `aria-labelledby` относятся к отображаемой форме до момента замены. При PUSH/REPLACE положение новой auth-формы устанавливается в начало страницы, пока содержимое скрыто. POP сохраняет контекст прокрутки, кроме минимальной мгновенной коррекции для видимости заголовка. Фокус новой страницы получает её `h1` с `tabIndex=-1` и `preventScroll` после снятия `inert` в момент замены, а не после анимации, чтобы не отнимать уже начатый ввод.

Обычная история React Router сохраняется. Устаревшие completion отбрасываются по поколению перехода, а последний маршрут становится целью. Отмена, unmount и смена reduced-motion освобождают принадлежащие переходу эффекты. Aurora остаётся тем же DOM-узлом с прежними фазой и настройкой паузы.

## Подтверждённый вход и рабочие экраны

Во время запроса остаётся существующая форма с `aria-busy`, заблокированными полями и кнопкой стабильной ширины. Успех не показывается до ответа API. После подтверждения выполняется короткий exit, затем прежний безопасный redirect либо домашний маршрут роли. Дополнительного ожидания «успешной» кнопки нет.

[LoginPage](../../frontend/src/pages/LoginPage.tsx) учитывает, что session provider обновляет profile до возврата `signIn`: текущий pending-вход завершает свой переход, а уже существующая сессия перенаправляется штатно. Завершение устаревшего запроса не должно уводить пользователя с другого auth-маршрута. Ошибка оставляет форму и введённые значения, снимает pending и показывает существующие сообщения.

Рабочий контент появляется отдельно от sidebar/header с брендом: [AppShell](../../frontend/src/layouts/AppShell.tsx) и [ExecutorLayout](../../frontend/src/layouts/ExecutorLayout.tsx) используют `usePageEntry` по `location.key`. Это opacity-переход существующего main-контента, без размонтирования shell или header. Подтверждённый вход передаёт внутренний frontend-маркер в state навигации: для этого PUSH/REPLACE main получает фокус и начало прокрутки перед появлением. При POP или перезагрузке сохранённый маркер не сбрасывает контекст; обычные app-переходы не получают глобальную политику reset. На эти контейнеры нельзя переносить эффекты, затрагивающие логотипы или всю страницу.

## Микровзаимодействия

- `Button`/`IconButton` используют общий быстрый профиль изменения цвета, яркости и мягкой тени. Active даёт краткую обратную связь без bounce и масштабирования страницы. Loading сохраняет ширину и доступное описание.
- Поля плавно меняют цвет границы и фона. Сохраняется одна рамка: нейтральная до проверки, красная при ошибке, зелёная после успешной локальной проверки. Внешнее мятное кольцо не добавляется; клавиатурный фокус утолщает ту же рамку.
- Ссылки меняют цвет/underline с теми же токенами и сохраняют keyboard focus.
- `FormField` выводит ошибки с прежними `role="alert"`, `aria-invalid` и `aria-describedby`. [useFeedbackMotion](../../frontend/src/shared/motion/useFeedbackMotion.ts) сглаживает изменение высоты небольшого блока hint/error только при изменении сообщения. Высота измеряется перед переходом; текст ограничен этим блоком. Это конечная layout-анимация, а не постоянный кадровый цикл.
- Во время жеста собственные feedback/reveal/enter-эффекты не должны сдвигать цель нажатия. Ранее исправленный переход с первого клика сохраняется; система не имитирует навигацию на `pointerdown`. Заблокированные элементы, включая наследование `disabled` от fieldset, не удерживают жест и не приостанавливают последующую ошибку; release/cancel освобождают собственные эффекты.

## Reduced-motion и клавиатура

CSS отключает перемещения, stagger и декоративные анимации. [animateMotion](../../frontend/src/shared/motion/animate.ts) проверяет preference до запуска WAAPI и завершает текущий эффект при смене настройки или скрытии вкладки. При отсутствии WAAPI переход получает мгновенный fallback. Конечное состояние остаётся видимым и доступным.

Tab/Shift+Tab, Enter, Space и Escape сохраняют нативный смысл. Space не управляет фоном. Пользовательская настройка паузы Aurora удалена вместе с окном помощи; внизу auth-панели находится обычный информационный текст. Системное reduced-motion останавливает Aurora по её собственному lifecycle, как и скрытая вкладка или невидимая сцена.

Непрерывный мобильный Canvas и начальное восстановление auth-scroll описаны отдельно в [web](../service/web.md#геометрия-пауза-и-производительность). Они используют существующую фазу и не создают дополнительный motion loop. Исторические снимки и performance-пробы ниже относятся к первоначальному внедрению Motion System; для текущего mobile renderer применяется [новый протокол](../service/verification.md#02112026-мобильная-aurora-viewport-и-производительность).

## Повторное использование

Для нового control используйте токены, а не ещё одну фиксированную длительность:

```css
.status-control {
  transition: color var(--motion-fast) var(--ease-standard),
              background-color var(--motion-fast) var(--ease-standard);
}
```

Для конечного эффекта content-узла доступен driver с явной очисткой:

```tsx
useEffect(() => {
  const element = contentRef.current;
  if (!element) return;
  const run = animateMotion(
    element,
    [{ opacity: 0 }, { opacity: 1 }],
    "--motion-normal",
  );
  void run.finished.then(() => run.cancel());
  return () => run.cancel();
}, []);
```

`finished` сообщает, завершён эффект или отменён; переход маршрута должен дополнительно проверять актуальность своего поколения. Пример применяется к содержимому, а не к родителю бренда. Не используйте driver, чтобы задерживать API, подменять серверный успех или самостоятельно менять права.

## Производительность и границы

Основные эффекты используют opacity/transform, не blur/filter, вращение или spring. Высота допускается только для небольшого feedback-блока на изменение сообщения. Не добавляются JS-циклы rAF, setState каждый кадр или измерения layout в цикле Aurora. Её геометрия, renderer, частоты и кэширование остаются самостоятельными.

WAAPI-эффекты отменяются при замене/unmount; обработчики освобождаются, временные fill/inert состояния снимаются. После завершения конечного перехода новые постоянные анимации не должны оставаться. Физическая клавиатура телефона и Safari требуют отдельной проверки; эмуляция viewport не заменяет устройство.

## Проверки

Проверена текущая `feature/frontend-kran` с сохранёнными незакоммиченными исправлениями навигации и рамок. Новые проверки выполнены 01.11.2026; более ранние результаты не подменяют этот прогон.

| Проверка | Результат |
|---|---|
| `npm.cmd run typecheck` | PASS |
| `npm.cmd test` | PASS, 179 тестов в 15 файлах |
| `npm.cmd run test:e2e -- e2e/login.spec.ts` с локальным `FIXRATE_BASE_URL` | PASS, 9 сценариев с mock API |
| `npm.cmd run build` | PASS |
| `git diff --check` | PASS для текущих изменений |

Контролируемые unit-тесты проверяют StrictMode, один inert Outlet, фокус после снятия inert, отмену устаревшего перехода, profile-first race, trailing slash, сохранение маркера подтверждённого входа и поведение POP/reload. Browser-регрессии используют физические координаты: первый клик, повторное нажатие заблокированного submit и кнопки внутри disabled fieldset, видимая ошибка без последующей клавиши, короткий scrolled-экран и успешный вход с сохранением query/hash.

Артефакты находятся в датированном каталоге (`reports/verification/2026-11-01-motion-system`). Итоговый протокол (`reports/verification/2026-11-01-motion-system/results.json`) связывает первоначальные проверки, исправленные предположения QA, фокусированные повторы и проверку сборки через порт 8000 (`reports/verification/2026-11-01-motion-system/built-review.json`). Каждый прогон сохраняет собственные дату и объём; итог агрегирует фактически выполненные проверки. Baseline (`reports/verification/2026-11-01-motion-system/baseline.json`) содержит исходные снимки и хеши. Проверены все четыре роли, Back/Forward, ввод во время первого reveal, reduced-motion во время exit, клавиатура и мобильные 320×568, 375×812, 390×844, 430×932. Для низких desktop-экранов проверены также 1366×768 и 1024×768 с общей неподвижной точкой бренда.

Во время browser review найдены и исправлены фокус до снятия inert, зависший feedback после нажатия disabled-кнопки, заголовок за пределами короткого экрана, а также потеря entry-маркера из-за повторного profile-redirect. Сценарии сохранены как регрессии вместе с исходными доказательствами и положительными повторами.

Снимки: первое появление (`reports/verification/2026-11-01-motion-system/initial-reveal-1440x900.png`), вход на телефоне (`reports/verification/2026-11-01-motion-system/login-390x844.png`), регистрация на телефоне (`reports/verification/2026-11-01-motion-system/register-390x844.png`), раздел после входа (`reports/verification/2026-11-01-motion-system/authorized-entry-1440x900.png`). Короткая WebM-запись (`reports/verification/2026-11-01-motion-system/auth-transitions.webm`) показывает reveal, оба auth-перехода, pending и подтверждённый вход. Метод записи (`reports/verification/2026-11-01-motion-system/video.json`): CDP JPEG-кадры с ограничением до 15 Hz, отдельный canvas и Chrome MediaRecorder; запись выполнена отдельно от замеров. Её 54 захваченных кадра за 5,37 s не являются измерением FPS интерфейса.

## Сравнение производительности

Измерения (`reports/verification/2026-11-01-motion-system/performance.json`): Chrome 156 headless, 1440×900, DPR 1, одинаковый probe rAF/CDP, 1,5 s прогрева и примерно 10 s steady-state без записи видео и параллельной сборки. Шесть защищённых исходников — оба SVG, AuroraScene, геометрия, renderer и lifecycle Aurora — совпали с baseline по SHA-256.

| Метрика | До | Контрольный замер после |
|---|---|---|
| Main-thread TaskDuration | 0,636 s | 0,471 s |
| ScriptDuration | 0,165 s | 0,128 s |
| Число rAF-интервалов | 745 | 1306 |
| p95 интервала rAF | 15,7 ms | 8,1 ms |
| Интервалы >25 ms | 0 | 0 |

У headless-браузера изменился cadence callbacks; из этих одиночных сэмплов нельзя выводить процент ускорения, физический FPS или суммарную нагрузку CPU/GPU. В контрольном steady-state ухудшения не наблюдалось, новых постоянных JS-циклов нет. Временные height-эффекты feedback проверяются отдельно как конечные переходы; этот замер не является измерением GPU/compositor каждого перехода.

## Ограничения проверки

Проверки интерфейса используют API fixtures: реальная серверная авторизация, PostgreSQL и ML в этой frontend-задаче не проверялись. Firefox локально не установлен, поэтому фактический browser review выполнен в Chrome; fallback без WAAPI проверяется отдельно. Физические телефоны, iOS Safari и настоящая экранная клавиатура не проверялись. Смена viewport и эмуляция touch не заменяют эти устройства.
