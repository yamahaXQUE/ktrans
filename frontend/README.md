# Frontend — задачи из звонков

React + Vite + TypeScript интерфейс для потока **звонок → задача**. Приложение
встраивается в iframe Bitrix24, определяет пользователя и его роль и показывает
одну из двух витрин:

- **Оператор** — сетка кандидатов на задачи, извлечённых из **его** звонков.
  У каждого кандидата статус `pending` / `failed` («упавшая») / `confirmed` /
  `rejected`. Клик по карточке открывает **редактируемую модалку**: оператор
  правит поля и **создаёт задачу** (в Bitrix), **отклоняет** кандидата или
  **повторяет создание** упавшей задачи.
- **Супервайзер и выше** — общий дашборд всех операторов, **отсортированный по
  именам**, со счётчиками. Клик по оператору открывает его звонки, клик по
  звонку — модалку с расшифровкой и извлечённой задачей. Доступ и отрисовка
  отдельные от оператора.

UI построен на дизайн-системе `Kulikov UI Reference` (фиолетовый + лайм, тонкие
рамки, компактные панели, кот-маскот). Токены и layout-правила лежат в
[`src/styles.css`](src/styles.css); бизнес-логика Promo DB не переиспользуется.

## Запуск

```powershell
cd frontend
npm install
npm run dev
```

Dev-сервер: `http://localhost:5173`. Прод-сборка — `npm run build` (гоняет
`tsc` + `vite build`).

### Режим mock

Если backend недоступен, типизированный клиент
([`src/api/tasksApi.ts`](src/api/tasksApi.ts)) прозрачно переключается на
встроенный датасет ([`src/api/mockData.ts`](src/api/mockData.ts)) — так интерфейс
полностью кликабелен без сервера. В mock-режиме в шапке появляется переключатель
роли (Оператор / Супервайзер) для демонстрации обеих витрин. С живым backend
переключатель скрыт, роль приходит с сервера.

## Роль и сессия

Порядок определения пользователя ([`src/api/tasksApi.ts`](src/api/tasksApi.ts) →
`resolveSession`):

1. **iframe Bitrix24** — BX24 JS SDK отдаёт `user.current` + auth, фронт шлёт их
   в `POST /api/bitrix/session`, backend возвращает `SessionUser` с уже
   вычисленной ролью (руководитель подразделения / allowlist супервайзеров).
   Роль **не** решается на клиенте.
2. **dev-backend вне iframe** — `GET /api/session`.
3. **иначе** — mock-режим и локальный пользователь.

До получения пользователя экран пуст (boot), как и требовалось: «по умолчанию
пусто, при входе — фетч в БД».

## Контракт API (реализует backend)

Фронт ожидает следующие endpoints. Все DTO — в
[`src/types/domain.ts`](src/types/domain.ts). Backend **обязан** маскировать/
опускать сырые номера и URL записей: во фронт приходит только `phoneMasked`.

### Сессия и справочники

```text
POST /api/bitrix/session   -> { user: SessionUser }   # синхронизация BX24 + роль
GET  /api/session          -> { user: SessionUser }   # dev / не в iframe
GET  /api/emulation/users  -> SessionUser[]           # временный режим impersonation
POST /api/emulation/session -> { user: SessionUser }  # body: { operatorId: string }
GET  /api/dictionaries     -> { departments: Department[] }
```

### Кандидаты (роль: оператор — только свои; супервайзер — все / конкретного)

```text
GET   /api/candidates                 -> TaskCandidate[]   # супервайзер: все
GET   /api/candidates?operatorId={id} -> TaskCandidate[]   # оператор: свои
PATCH /api/candidates/{id}/confirm    -> TaskCandidate     # body: ConfirmCandidatePayload
PATCH /api/candidates/{id}/retry      -> TaskCandidate     # body: ConfirmCandidatePayload
PATCH /api/candidates/{id}/reject     -> TaskCandidate     # body: { reason: string }
```

- `confirm` — создать `ConfirmedTask` из (отредактированного) кандидата и
  записать обычную задачу в Bitrix (`task.item.add` на текущем портале).
  Ответственный —
  руководитель выбранного подразделения, подтвердивший оператор — наблюдатель.
  При успехе вернуть кандидата со статусом `confirmed` и `bitrixTaskId`.
- `retry` — повторить создание для `failed`-кандидата с учётом правок оператора.
- `reject` — записать `RejectedTaskCandidate`, статус `rejected`.
- Если создание в Bitrix упало — вернуть статус `failed` и `failureReason`.

Сервер **обязан** проверять, что оператор трогает только свои кандидаты, а
редактирование доступно только для `pending` / `failed`.

### Дашборд супервайзера (роль: супервайзер+)

```text
GET  /api/operators                 -> OperatorSummary[]   # агрегаты по операторам
GET  /api/operators/{id}/calls      -> SourceCall[]        # звонки оператора
GET  /api/analytics/complaints      -> ComplaintAnalytics  # созданные жалобы по отделам
GET  /api/analytics/complaints.xlsx -> application/xlsx    # Excel для супервайзера
GET  /api/calls/{id}                -> SourceCall          # звонок + расшифровка
POST /api/calls/{id}/analysis       -> SourceCall          # ручная очередь анализа
```

`SourceCall.transcript` — результат транскрибации (`AnalyzeCall`/whisper).

## Соответствие backend-модели

| Frontend (`domain.ts`)      | Backend (Python)                                   |
| --------------------------- | -------------------------------------------------- |
| `TaskCandidate`             | `backend/task_create.py :: TaskCandidate`          |
| `ConfirmCandidatePayload`   | поля `ConfirmedTask` (title/description/dep/prio)  |
| статус `rejected`           | `RejectedTaskCandidate`                            |
| `SourceCall`                | `bitrix/mirror.py :: BitrixCall` (маскированный)   |
| `Department`                | `bitrix/mirror.py :: BitrixDepartment`             |
| `SessionUser`               | `bitrix/mirror.py :: BitrixUser` + вычисленная роль |
| `priority: 1..5`            | `ConfirmedTask.priority` (1..5)                    |

## Структура

```text
src/
  api/            bitrixApi.ts (BX24), tasksApi.ts (клиент + mock), mockData.ts
  components/
    common/       PixelCat, EmptyState, LoadingState, Pills, CallPanel
    operator/     CandidateCard, CandidateFilters, TaskReviewModal
    supervisor/   OperatorList, OperatorCallsPanel, CallTranscriptModal
  constants/      task.ts (приоритеты, статусы, лимиты)
  types/          domain.ts
  utils/          date.ts, format.ts
  App.tsx         ролевой shell (topbar, sidebar, роутинг витрин)
  styles.css      дизайн-система Kulikov + добавления под звонки/задачи
```

## Принятые решения

- **Один build, две роли.** Витрины разделены по `role`; в mock-режиме доступен
  переключатель для демо. С backend роль фиксируется сервером.
- **Mock-fallback** повторяет подход reference (`fallbackUser`) — фронт живёт без
  сервера, пока backend (`main.py`/`router.py` сейчас пустые) не поднят.
- **Безопасность.** Сырые номера/записи/SIP не приходят на фронт; показывается
  только `phoneMasked`. Секреты Bitrix остаются на сервере.
- Контракт API согласуется с доменом `backend/` и `bitrix/`; endpoints выше —
  предложение для реализации серверной части.
