# Dora X Classify — Sales Meeting Intelligence & Lead Analytics

Dora X Classify turns every sales video call into structured, actionable intelligence.
A sales person schedules a **Classify** meeting with a lead, the lead is invited by
email, and after the meeting the platform pulls attendance and the
recording from Classify. The backend downloads the recording, produces a transcript,
asks **Google Gemini** for a strictly validated sales analysis, and the dashboard shows
what happened, what the lead cares about, which objections came up, how much of the
pitch was covered and what to do next.

> **Meeting → Intelligence.** Not "meeting completed" — *what the lead said, what
> they care about, and the next action.*

Everything runs locally with **one command** in Docker, in **mock mode** (no
credentials needed) with seeded, clearly labelled demo data.

---

## Quick start (one command)

Prerequisite: Docker Desktop (or Docker Engine + Compose v2.24+).

```bash
docker compose up --build
```

| What | URL |
|---|---|
| App (Vite dev server, hot reload) | http://localhost:5173 |
| API + Swagger | http://localhost:8000/docs |
| MongoDB | `mongodb://localhost:27017/dora_x_classify` |

Code changes apply live: the backend runs `uvicorn --reload` and the frontend runs Vite HMR,
both from your working tree via bind mounts. MongoDB is seeded with demo data on first start.

With `make` (see `make help`):

| Command | Does |
|---|---|
| `make up` | Start MongoDB + backend + frontend (same as `docker compose up --build`, with fresh `node_modules`) |
| `make test` | Run **all** backend (pytest) and frontend (vitest) tests inside containers |
| `make seed` | Wipe and reseed demo data |
| `make logs` / `make ps` / `make down` | Follow logs / status / stop (keeps data) |
| `make prod-up` | Production-like images (nginx + non-root API) on http://localhost:8080 |
| `make clean` | Stop everything and delete volumes |

Without `make`:

```bash
docker compose --profile test run --rm backend-tests    # pytest  (81 tests)
docker compose --profile test run --rm frontend-tests   # vitest  (16 tests)
docker compose --profile tools up                       # + mongo-express on :8081
docker compose -f docker-compose.prod.yml up --build     # production-like on :8080
```

After changing `package.json` or `requirements*.txt`, rebuild with `make up`
(`--renew-anon-volumes` refreshes the container's `node_modules`). If file changes are not
picked up on your machine, set `WATCHFILES_FORCE_POLLING=true` / `VITE_USE_POLLING=true` in `.env`.

### Demo logins (seed data)

| Role | Email | Password |
|---|---|---|
| Admin | `admin@classify.demo` | `Admin@123` |
| Sales | `arjun@classify.demo` | `Sales@123` |
| Sales | `neha@classify.demo` | `Sales@123` |

Seed data (all flagged `is_demo`, shown with a **Demo** badge): 10 leads, 20 meetings —
completed meetings with AI analysis, scheduled meetings, no-shows, objections, follow-ups,
one meeting that processes on first start, and one failed recording.

---

## Architecture

```
Browser ── React (Vite) ──► FastAPI ──► MongoDB
                               │
                               ├── Classify   POST /createMS               (schedule)
                               ├── Classify   POST /send-attendance-details (attendance + recordings, pulled)
                               ├── faster-whisper  transcription (local, free — default)
                               ├── Gemini     sales analysis (transcription too, if TRANSCRIPTION_PROVIDER=gemini)
                               ├── Email      SMTP / SendGrid
                               └── S3         recording download (server-side only)

Meeting ends ─► worker pulls SendAttendanceDetails ─► attendance applied ─► recording → transcript (whisper) → analysis (Gemini)
Classify (optional push) ─► POST /api/webhooks/classify ─► same pipeline
```

- **Route → service → external API.** Route handlers never call Classify directly
  (`routes/meetings.py → services/meeting_service.py → services/classify_service.py`).
- **Durable, MongoDB-backed worker.** Attendance sync and each processing stage
  (`processing.recording|transcript|analysis`) are claimed atomically with
  `find_one_and_update`, so work survives restarts and several API replicas never
  double-process. Failures retry with backoff (max 3 per stage) and surface in the
  **Processing Monitor**.
- **Nothing heavy in the request path.** The UI polls every 5 s only while a meeting is
  active and stops once analysis completes.

### Meeting lifecycle

`DRAFT → SCHEDULED → INVITATION_SENT → WAITING_FOR_LEAD → LEAD_JOINED → IN_PROGRESS →
MEETING_COMPLETED → RECORDING_PROCESSING → TRANSCRIPT_PROCESSING → AI_ANALYSIS_PROCESSING →
ANALYSIS_COMPLETED → FOLLOW_UP_REQUIRED → CLOSED`, plus `NO_SHOW` and `FAILED`. Transitions are
validated (`constants/meeting_status.py`). The sales person sees a simplified journey:
*Scheduled ✓ → Lead Invited ✓ → Waiting for Lead… → Meeting Completed ✓ → Recording… →
Transcript ✓ → AI Analysis ✓ → Follow-up Required ⚠*. Every step writes a timeline event;
~40 flags (meeting / sales / lead / technical) are derived from stored facts, AI-derived ones marked.

## Classify integration (final API docs)

### 1. Create meeting — `POST {CLASSIFY_API_URL}/createMS`

- **Auth:** API key in a request header (`CLASSIFY_API_KEY_HEADER`, default `Authorization-Key`)
  **and** `authToken` + `product` in the body (admin session). Either failing → `401`.
- **Body** (`services/classify_service.py::build_create_payload`): `label`, `start_time`,
  `end_time` (Unix s), `thumbnail`, `minDuration`, `batch_data[{name,email}]`, `studentNotes`,
  `enable_chat`, `authToken`, `subject`, `message`, `footer`, `product`, `created_by`,
  `meetingType: "scheduled"`, `hosts[{name,email}]`, **`autoRecordingStart`**, `isEndTimeGiven`,
  `studentHMSRole`, `timezone`, `org_id`, `repeat: {type: "noRepeat"}`, `isPollEnabled: false`,
  `isQuizEnabled: false`, `guestConfig`. The legacy key `recording_autoStart` is sent with the same
  value for compatibility with the earlier docs (unknown keys are ignored).
- **Defaults:** `product=guvi`, `created_by=classify`, `autoRecordingStart=on` (Classify's own
  default is `off`; recordings feed the AI pipeline), `timezone=Asia/Kolkata`, `minDuration=1` —
  all configurable. `/createInstantMeet` is not used.
- **`authToken` prefix:** both createMS docs show the request example as `"auth:2a85b3a9aa..."`.
  Confirmed against a live call — a token without that prefix gets `401 Session Invalid` even
  though the API key header passed; a plain hex token with it succeeds. The backend adds `auth:`
  automatically if it's missing (`normalized_auth_token()`), so `CLASSIFY_AUTH_TOKEN` can be pasted
  either way.
- **`studentHMSRole`:** the docs' example *response* shows `"student"`, but it isn't in their
  documented list of accepted *request* values and a live call rejected it
  (`Invalid StudentHMSRole`). Default is `allow-video-audio` — documented and confirmed working,
  and the right fit for a sales video call.
- **Guest mode (off by default):** leads have no Classify account, so ideally meetings would use
  `guestConfig.IsGuestParticipantAllowed = true` (`CLASSIFY_GUEST_MODE_ENABLED`) so they can join by
  filling a short guest form instead of logging in — Classify always injects a required `Name`
  field itself; `CLASSIFY_GUEST_COLLECT_EMAIL` / `CLASSIFY_GUEST_COLLECT_PHONE` add more.
  **A live call rejected this**, combined with our scheduled + `batch_data` meeting:
  `"Guest access cannot be enabled for a private meeting"` — wording neither Classify doc defines,
  so what makes a meeting "private" (and how to make it not) is unknown; check with Classify. The
  payload/validation support is fully built (`guestConfig`'s inner fields use their literal Go
  struct names — `IsGuestParticipantAllowed`, `GuestInformationCollectionFields`, `FieldType`,
  `FieldName`, `Options` — unlike the rest of the camelCase createMS body) and tested; turning it
  back on once that's resolved is a single `.env` flag, no code change.
- **Pre-validation** mirrors every documented rule before any call (label ≥ 4, start ≥ 1 min
  ahead, 2 min ≤ duration ≤ 8 h, `0 < minDuration ≤ duration`, valid/unique emails,
  host ≠ lead, `on/off` flags, HMS role, timezone, poll/quiz IDs when enabled, guest field type/
  name/dropdown-option rules when guest mode is on).
  **`minDuration` is the lead's minimum attendance**, not the meeting length.
- **Response:** `{Access, Status, Message, Details{UniqueId, MeetProvider, …}}` in PascalCase —
  all parsing is case-insensitive. Success = `Access == true` **and** `Status` starts with `200`
  (poll/quiz errors arrive via *RespondWithSuccess* with HTTP 200). Every documented message maps
  to a friendly reason + hint, e.g. *"Unable to schedule meeting. Reason: Meeting start time must
  be in the future. Please select another time."* `401` → configuration error (no secrets
  exposed); `409` (jobs/recurrence/poll) → conflict; `500` (enqueue) → Classify unavailable.
- **Timeout:** `CLASSIFY_TIMEOUT_SECONDS` (default 45s, under the frontend's 60s request timeout
  for scheduling). A real createMS call was observed to occasionally take longer than the original
  20s default and fail client-side with *"Classify did not respond in time."* — retrying (from the
  UI, or via the same `Idempotency-Key`) is the only real remedy, since a timeout doesn't tell us
  whether Classify's side actually finished; we don't auto-retry, to avoid risking a duplicate
  meeting on their end. Timeouts and successes both log the elapsed wait time.
- **Storage:** the complete response is kept as `raw_classify_response` (echoed `AuthToken`
  masked); normalised fields go to `meeting.classify` (`unique_id`, `room_id`, codes,
  `meet_provider`, join URLs).
- **Join link:** built from the createMS `uniqueId` as Classify's documented meeting-dashboard
  URL, `{CLASSIFY_MEETING_LINK_BASE}?session={uniqueId}` (default
  `https://classify.zenclass.in/meet-dashboard-new?session={uniqueId}`) — the same link is used
  for both the host and the lead; Classify resolves the role from the signed-in session. A direct
  URL in the response (if Classify ever sends one) or an admin-configured
  `CLASSIFY_STUDENT_JOIN_URL_TEMPLATE` / `CLASSIFY_HOST_JOIN_URL_TEMPLATE` override take
  precedence. In mock mode the link instead points at the app's own demo room.
- **Idempotency:** `Idempotency-Key` header (UI sends one per dialog), unique-indexed; without it
  a key is derived from user + lead + start + duration. Double clicks and retries never duplicate.

### 2. Attendance — SendAttendanceDetails (`POST {CLASSIFY_API_URL}/send-attendance-details`)

- **Body:** `{"for": "meet", "uniqueId": "<createMS UniqueId>", "product": "guvi", "creator_email": "<Classify admin>"}`
  — `CLASSIFY_CREATOR_EMAIL` **must be a Classify admin account** (else `401 Not an Admin`).
- **Always HTTP 200** — the real result is the body `Status`/`Message`.
- **Automatic sync** (`services/attendance_service.py`): the worker calls it
  `CLASSIFY_ATTENDANCE_SYNC_DELAY_MINUTES` (5) after the scheduled end. While Classify answers
  `409 Class in progress…` it retries every `CLASSIFY_ATTENDANCE_RETRY_MINUTES` (10) up to
  `CLASSIFY_ATTENDANCE_MAX_ATTEMPTS` (12). Configuration errors (`Not an Admin`, `No such meetings`,
  `Wrong product`, …) stop immediately and raise `ATTENDANCE_SYNC_FAILED`. Sales people can also
  press **Sync attendance** on the meeting page (`POST /api/meetings/{id}/sync-attendance`).
- **Response used:** `SessionDetailsToSend` (`StartTime`/`EndTime` as `"January 02, 2006 3:04 PM"`
  in IST → duration, `TotalPresent`, `MinimumAttendanceTime`, `AssetDetails[{type, url}]` →
  recording / transcript / chat URLs) and `AttendanceDetails[]` (`AttendanceStatus "P"` = present,
  `Attendedtime` minutes, `Role host|student`). The lead is matched by email, the sales person by
  email or `Role: host`. **No-show is only recorded when this data says the lead was absent.**
- Each successful pull is stored verbatim in `webhook_events` (source `classify_attendance_api`)
  and applied through the same code path as a webhook, so pull and push are idempotent together.
- **Mock-created meetings are never queried for real.** A meeting scheduled while
  `CLASSIFY_MOCK_MODE=true` has a fake `uniqueId` that only ever existed locally; if mock mode is
  later switched off, both the background worker and the manual **Sync attendance** button skip
  meetings with `classify.is_mock: true` instead of sending Classify a lookup it can never satisfy.

### 3. Optional push webhook — `POST /api/webhooks/classify`

If Classify also pushes attendance, register `{BACKEND_URL}/api/webhooks/classify` with the
`api-key: {WEBHOOK_SECRET}` header (or `X-Classify-Signature: sha256=<HMAC of raw body>`). Both the
SendAttendanceDetails shape and the older `sessionDetails/attendanceDetails` shape are accepted.
Payloads are stored verbatim, deduplicated, answered with 200 immediately and processed in the
background. Unsigned webhooks are rejected when `APP_ENV=production`.

## Processing pipeline

```
Attendance (pull or push) → recording URL(s) → download (S3 creds / HTTPS) → FFmpeg audio
    → transcript (Classify transcript asset, else Gemini) → Gemini analysis → validated JSON → MongoDB
```

1. **Recording** — `AssetDetails[type=recording]` URLs. `s3://` and S3 HTTPS URLs are downloaded
   with boto3 using `S3_ACCESS_KEY/SECRET`; other URLs (e.g. pre-signed) via HTTPS. Files stay on
   the server; the browser streams them via `/api/meetings/{id}/recording/stream` with a
   15-minute meeting-scoped token. No recording → `RECORDING_MISSING` (nothing fabricated).
2. **Transcript** — a Classify transcript asset (VTT/SRT/JSON/text) is used first; otherwise FFmpeg
   extracts mono 16 kHz audio and Gemini transcribes it. Speaker labels and timestamps are stored
   only when the source provides them; AI transcripts are labelled.
3. **Analysis** — Gemini JSON is validated against `models/analysis.py::SalesAnalysis`; invalid
   output gets one repair attempt, then retries. Each run is a new versioned `meeting_analytics`
   document (`model`, `prompt_version`, `analysis_version`); **Re-analyze** reuses the transcript.

Talk ratio / interruptions / silence are computed **only** when the transcript has speaker labels
*and* timestamps; otherwise the UI shows *Speaker talk-time data unavailable*.

## Environment variables

All configuration comes from `.env` (see the commented [`.env.example`](.env.example)); compose
loads it automatically and the React app never receives a secret.

| Group | Key variables |
|---|---|
| App | `APP_ENV`, `FRONTEND_URL`, `BACKEND_URL`, `CORS_ORIGINS`, `SEED_DEMO_DATA`, `JWT_SECRET`, `BOOTSTRAP_ADMIN_*` |
| MongoDB | `MONGO_URI`, `MONGO_DATABASE` (default `dora_x_classify`) |
| Classify | `CLASSIFY_MOCK_MODE`, `CLASSIFY_API_URL`, `CLASSIFY_CREATE_MEETING_PATH` (`/createMS`), `CLASSIFY_ATTENDANCE_PATH`, `CLASSIFY_API_KEY_HEADER`, `CLASSIFY_API_KEY`, `CLASSIFY_AUTH_TOKEN`, `CLASSIFY_ORG_ID`, `CLASSIFY_PRODUCT`, `CLASSIFY_CREATOR_EMAIL`, `CLASSIFY_ATTENDANCE_*`, `CLASSIFY_*` defaults |
| Webhook | `WEBHOOK_SECRET` |
| Gemini | `GEMINI_MOCK_MODE`, `GEMINI_API_KEY`, `GEMINI_MODEL` |
| Transcription | `TRANSCRIPTION_PROVIDER` (whisper/gemini), `WHISPER_MODEL_SIZE`, `WHISPER_DEVICE`, `WHISPER_COMPUTE_TYPE` |
| Email | `EMAIL_MOCK_MODE`, `EMAIL_PROVIDER` (smtp/sendgrid), `EMAIL_API_KEY`, `EMAIL_FROM`, `SMTP_*` |
| Recordings | `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION`, `S3_BUCKET`, `RECORDING_STORAGE_DIR` |
| Docker | `FRONTEND_PORT`, `BACKEND_PORT`, `MONGO_PORT`, `WATCHFILES_FORCE_POLLING`, `VITE_USE_POLLING` |

### Going from mock to real Classify

```env
CLASSIFY_MOCK_MODE=false
CLASSIFY_API_KEY=...            # partner key (header)
CLASSIFY_AUTH_TOKEN=auth:...    # admin session token (body)
CLASSIFY_ORG_ID=...
CLASSIFY_CREATOR_EMAIL=admin@yourorg.com   # a Classify ADMIN, for SendAttendanceDetails
```

## Transcription, Gemini and email

- **Transcription:** `TRANSCRIPTION_PROVIDER=whisper` (default) runs a local `faster-whisper`
  model (`WHISPER_MODEL_SIZE`, default `small`) over the downloaded recording — free, real, no
  API key, so even with `GEMINI_MOCK_MODE=true` a meeting with a real recording gets a genuine
  transcript instead of scripted text. It gives real timestamped text but does **not** do speaker
  diarization (every segment is `speaker: unknown`) — a Classify-supplied transcript or
  `TRANSCRIPTION_PROVIDER=gemini` can attribute speakers, faster-whisper can't. A meeting with no
  real recording at all (fully-mock Classify data) always falls back to a scripted example
  transcript, flagged `is_mock: true` and surfaced as a toast on the meeting page.
- **Gemini:** `GEMINI_API_KEY`, `GEMINI_MODEL` (default `gemini-2.5-flash`). Sales analysis
  (objections, pitch coverage, follow-up) calls the real API whenever a key is configured,
  independent of the transcription provider above — `GEMINI_MOCK_MODE` now only affects analysis
  (and transcription too, if `TRANSCRIPTION_PROVIDER=gemini`). The prompt
  (`prompts/sales_analysis.py`, v1.0) returns strict JSON, keeps `explicit_statements` (quotes)
  separate from `ai_interpretations`, scores each configurable pitch-checklist topic, and must not
  invent facts.
- **Email:** `EMAIL_MOCK_MODE=false` plus SMTP (`SMTP_*`) or SendGrid (`EMAIL_API_KEY`). A failed
  delivery never fails the meeting; failed deliveries retry (max 3) and can be resent.

## Security

JWT auth with roles **admin** (everything) and **sales** (own leads, meetings, analytics,
follow-ups); secrets only in `.env`; structured logs redact tokens/keys/passwords; recording
source URLs never reach the browser; login rate limiting; bcrypt; CSV formula-injection guard;
audit log (`activity_logs`) of schedules, lead edits, meeting views, resends, follow-up changes,
exports, retries and attendance syncs. The production image runs as a non-root user.

## Project structure

```
backend/   FastAPI app (app/), tests/ (81), Dockerfile (dev + prod targets)
frontend/  React + Vite app (src/), tests in src/test (16), Dockerfile (dev + prod/nginx targets)
docker-compose.yml       local development (hot reload) + test runners
docker-compose.prod.yml  production-like stack
Makefile                 one-command workflows
.env.example             every setting, commented
```

Local (non-Docker) development still works: `cd backend && pip install -r requirements-dev.txt &&
uvicorn app.main:app --reload` and `cd frontend && npm install && npm run dev` (needs a MongoDB on
`localhost:27017`).

## Production deployment

1. `APP_ENV=production`, a long random `JWT_SECRET`, `WEBHOOK_SECRET`, `SEED_DEMO_DATA=false`,
   `BOOTSTRAP_ADMIN_EMAIL/PASSWORD` for the first admin.
2. Disable mock modes and set Classify (incl. `CLASSIFY_CREATOR_EMAIL`), Gemini, email, S3.
3. Managed MongoDB (replica set, backups) and persistent storage for `RECORDING_STORAGE_DIR`.
4. Build the `prod` targets (see `docker-compose.prod.yml`) and serve behind HTTPS.
5. The worker runs inside each API process; claims are atomic, so scaling out is safe.

## Assumptions and known limits

- **SendAttendanceDetails path** is not in the final doc; `/send-attendance-details` comes from
  the Zen integration notes and is configurable (`CLASSIFY_ATTENDANCE_PATH`).
- **API key header name** is not named in the final createMS doc ("a request header"); the earlier
  doc's `Authorization-Key` is used and configurable (`CLASSIFY_API_KEY_HEADER`) — **confirmed
  correct** against a real call (it passed the API-key check; the `authToken` check failed
  separately, see below).
- **`StartTime`/`EndTime`** strings carry no timezone; they are read as Asia/Kolkata (the zone the
  API loads). Minute precision only.
- **Live join events** are not documented, so "Lead Joined" is confirmed from attendance after the
  meeting; during the meeting the UI shows *Waiting for Lead…*.
- **Confirmed against a real createMS call** (org/product from this deployment's credentials):
  the `Authorization-Key` header name, the `auth:`-prefixed `authToken` format, and
  `studentHMSRole=allow-video-audio` all work; `studentHMSRole=student` and `guestConfig` combined
  with a scheduled + `batch_data` meeting do not (see the createMS section above for both). These
  may be specific to this org/product rather than universal — worth re-checking if scheduling fails
  against a different Classify account.
