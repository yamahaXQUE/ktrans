# Call → task flow

The backend keeps the neural-network prediction separate from a task that may
be written to Bitrix:

1. `AnalyzeText.analyze()` returns an immutable `TaskCandidate`.
2. The operator either creates a separate `ConfirmedTask` (with edits) or a
   `RejectedTaskCandidate`.
3. The selected department is resolved against the synchronized Bitrix
   structure; its head (or the nearest parent head) becomes responsible.
4. `BitrixClient.task_add()` creates a native Bitrix task through the method
   exposed by the portal. The operator who confirmed it becomes an observer.

```python
from bitrix import BitrixClient

result = BitrixClient(BITRIX_WEBHOOK_URL).task_add(
    fields={
        "TITLE": "Разобрать обращение клиента",
        "DESCRIPTION": "Контекст звонка и выбранное подразделение",
        "RESPONSIBLE_ID": 9,
        "AUDITORS": [10],
        "PRIORITY": "2",
    },
    method="task.item.add",
)
```

The incoming webhook needs the legacy Bitrix task scope `task` in addition to
the read scopes used by directory, telephony, and Disk synchronization.

The task-extraction model is configured through `OPENAI_TASK_MODEL`; the
default is `gpt-5.6-luna`. Recorded calls are transcribed with
`OPENAI_TRANSCRIPTION_MODEL` (`gpt-4o-mini-transcribe` by default). The
raw ASR result is preserved, while `OPENAI_TRANSCRIPT_ENHANCEMENT_MODEL`
restores punctuation, paragraphs, natural phrasing, and confidently identified
speakers. Readability is preferred over verbatim fidelity; the raw ASR text is
retained for audit. If that optional pass fails, analysis continues with the
raw transcript. The production `analysis` service downloads one recent
Bitrix Disk recording, transcribes it, creates the immutable prediction, and
stores the result atomically.

Task creation uses a strict concrete-complaint gate. The customer must state a
specific complaint subject and a specific defect, failure, incorrect action,
or negative incident. Vague negative feedback, questions, requests, and facts
inferred only from the operator's words are stored with `should_create=false`,
are omitted from the task queue, and are rejected by the delivery API.
It automatically selects only users listed in
`ANALYSIS_AUTO_BITRIX_USER_IDS`; every other call enters the queue only after a
user presses the frontend analysis button. It is rate-limited by
`ANALYSIS_POLL_INTERVAL_SECONDS`. The OpenAI key, Bitrix webhook URL, and their
secrets stay in Docker secrets and must never be returned to the frontend.

## Read-only Bitrix mirror

`BitrixMirror` provides paginated, typed reads for the data needed by the
backend:

```python
from datetime import datetime, timezone

from bitrix import BitrixClient, BitrixMirror

mirror = BitrixMirror(BitrixClient.from_env())
users = mirror.iter_users(active_only=True)
departments = mirror.iter_departments()
calls = mirror.iter_calls(
    since=datetime(2026, 7, 1, tzinfo=timezone.utc),
    max_records=500,
)
```

Configure `BITRIX_WEBHOOK_URL` only in the server environment or a secret
manager. `BITRIX_TLS_COMPATIBILITY=true` is currently required for the
`bitrix.kulikov.com` certificate chain under Python 3.14. This mode still
validates the CA chain and hostname; it only disables OpenSSL's stricter
Authority Key Identifier requirement.

Phone numbers and recording URLs returned by the telephony API stay inside
`BitrixCall`; a future frontend DTO must mask or omit them. The facade does not
wrap `voximplant.user.get` because that method may return SIP credentials,
including a password, and those values must not be mirrored.

Run the local checks with:

```powershell
python -m compileall -q backend bitrix tests
python -m unittest discover -v
```

## PostgreSQL and frontend API

Install dependencies, apply migrations, and synchronize the live Bitrix
directory:

```powershell
python -m pip install -r requirements.txt
$env:DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/call_tasks"
python -m backend.migrate
python -m backend.sync_bitrix directory
python -m backend.sync_bitrix calls --days 7
uvicorn backend.main:app --host 127.0.0.1 --port 8080
```

The operator scope defaults to Bitrix department `82` (`Contact Centre`).
The discovery snapshot is documented in
[`docs/bitrix_contact_centre.md`](docs/bitrix_contact_centre.md); employees are
always synchronized from Bitrix rather than hard-coded in migrations.

The stored flow is:

```text
Bitrix operator + call
        ↓
backend transcript
        ↓
immutable task candidate
        ↓ operator confirms/edits or rejects
confirmed task
        ↓ department head routing
task.item.add / tasks.task.add + attempt audit
```

`backend.analysis_store.persist_call_analysis()` is the worker boundary that
atomically stores call text and the immutable model prediction. The FastAPI
routes in `backend/router.py` match `frontend/src/api/tasksApi.ts`, including
server-enforced own-record access for operators and the all-operator dashboard
for supervisors.

The supervisor analytics tab counts only complaint-backed tasks whose Bitrix
delivery status is `created`, grouped by the department selected during
confirmation. `GET /api/analytics/complaints` returns the dashboard aggregate;
`GET /api/analytics/complaints.xlsx` exports both complaint rows and a summary
sheet with a chart.

Every analyzed call also stores a short `conversationTitle`, even when the
model does not recommend a task. Operators can browse all of their synchronized
calls, request or retry transcription, and decide themselves whether to create
a Bitrix task. Deleting a call removes its transcript, prediction, review, and
local delivery history; a minimal statistic-ID tombstone prevents the Bitrix
sync worker from importing that call again. An already-created Bitrix task is
not deleted from Bitrix.

When no department is selected, tasks route to the head of the configured
default department:

```powershell
$env:BITRIX_TASK_DEFAULT_DEPARTMENT_ID = "82"
$env:BITRIX_TASK_ADD_METHOD = "task.item.add"
```

The current on-premise portal exposes `task.item.add`; installations exposing
the newer method can set `BITRIX_TASK_ADD_METHOD=tasks.task.add`.

The complete webhook URL is a backend-only secret and must not be committed or
sent to the browser.

## Docker: one origin for frontend and backend

No nginx is used. The multi-stage [`Dockerfile`](Dockerfile) builds React and
copies only `frontend/dist` into the Python runtime image. FastAPI serves the
static application and `/api/*` from the same container and origin.

```powershell
Copy-Item .env.example .env
# Set BITRIX_WEBHOOK_URL, POSTGRES_PASSWORD and portal-specific values in .env
docker compose up -d --build
```

The public address is `http://host:${APP_PORT}`; the default port is `8080`.
PostgreSQL has no published host port. On startup the app waits for PostgreSQL,
applies migrations, and only then starts Uvicorn.

Runtime routes that the corporate proxy must preserve:

| Route | Purpose |
| --- | --- |
| `/` and browser paths such as `/operators/...` | React SPA / static files |
| `/assets/*` | versioned frontend assets |
| `/api/*` | backend API; preserve path, method, body, cookies, and status |
| `/api/analytics/complaints.xlsx` | supervisor-only Excel download |
| `/health` | container/proxy health check |

The proxy should forward the complete path without rewriting `/api` and pass
`X-Forwarded-Proto` and `X-Forwarded-Host`. It must not convert API 401/404/409
responses into the SPA HTML. Unknown browser navigation routes fall back to
`index.html`; unknown `/api/*` routes remain JSON 404 responses.

Useful commands:

```powershell
docker compose ps
docker compose logs -f app
docker compose exec app python -m backend.sync_bitrix directory
docker compose exec app python -m backend.sync_bitrix calls --days 7
docker compose down
```

For a reverse proxy running on the same host, `APP_BIND_ADDRESS=127.0.0.1`
keeps port 8080 private to that host. Leave `0.0.0.0` when the proxy reaches
the container host over the network.

If the corporate network replaces npm registry certificates, export its root
certificate as PEM and set `NPM_CA_FILE=/absolute/path/corporate-root.pem`.
Compose passes it as a BuildKit secret only to the disposable Node build
stage; it is not copied into the Python runtime image. Do not disable npm TLS
verification.

For production, add `compose.production.yaml` and provide
`BITRIX_WEBHOOK_URL`, `POSTGRES_PASSWORD`, `KULIKOV_DATABASE_URL`, and
`OPENAI_API_KEY` through the deployment environment/secret manager. In a
network with TLS inspection, also provide its root certificate PEM as
`CORPORATE_CA_PEM`:

```powershell
docker compose -f compose.yaml -f compose.production.yaml up -d --build
```

The production overlay mounts those values as Docker secrets. They are not
stored in the image or exposed by `docker inspect` as container environment
variables.

### Temporary direct-browser Bitrix emulation

To open the live frontend outside a Bitrix iframe, add the emulation overlay:

```powershell
$env:DEV_BITRIX_USER_ID = "10"
docker compose -f compose.yaml -f compose.production.yaml `
  -f compose.emulation.yaml up -d
```

This bypasses the BX24 iframe handshake and resolves every unauthenticated
request as that existing Bitrix user. Omit `compose.emulation.yaml` to restore
normal Bitrix authentication. The temporary overlay also permits its session
cookie over direct HTTP; set `EMULATION_COOKIE_SECURE=true` when testing only
through an HTTPS proxy.

The same overlay starts non-public `sync` and `analysis` services. `sync`
upserts a 48-hour call window every five minutes and refreshes the operator
directory hourly. `analysis` processes recent recordings one at a time and
stores transcripts and task candidates. The unique statistic ID and unique
candidate-per-call constraint keep repeated cycles idempotent.
