# AI Receptionist Prototype – Chat Booking Demo

This repository contains a working milestone of the project:

**Design and Development of a Single-Hotel AI Receptionist Prototype for Booking Inquiry and Request Handling**

The prototype demonstrates a full-stack conversational flow: a guest chats with an AI receptionist on the frontend, messages are handled by a FastAPI backend, booking details are extracted from the conversation, and every turn is stored in PostgreSQL.

```
Frontend (React chat UI) → FastAPI backend → PostgreSQL database
                              ↓
                    LLM extraction + replies (optional)
                    Rule-based fallback when LLM is off
```

The stack runs in Docker Compose with one command and supports GitHub Codespaces for easy testing.

---

## What this prototype does

- Displays a multilingual chat interface (English, German, French, Italian, Spanish)
- Collects the guest email before chat begins and persists the session in the browser
- Sends messages to `POST /api/chat` and shows assistant replies in real time
- Extracts structured booking fields (dates, guest count, request type, etc.) from conversation
- Uses a hosted LLM (Gemini or OpenAI) when configured, with rule-based replies as fallback
- Stores each message, extracted fields, and AI reply in PostgreSQL
- Restores chat history when the user returns in the same browser tab
- Runs through Docker Compose with one command
- Supports GitHub Codespaces for instructor testing

---

## System flow

1. The user opens the web page and selects a language.
2. The user enters their email and starts a session (`POST /api/session/start`).
3. The user sends chat messages (`POST /api/chat`).
4. The backend merges prior session fields, extracts new details (LLM or rules), and generates a reply.
5. The backend writes the message, extracted fields, and `ai_reply` into `booking_requests`.
6. The frontend displays the assistant reply and loads history on return visits.

For verification, use `GET /api/booking-requests` or `GET /api/chat-history/{session_id}`.

---

## Repository structure

```text
.
├─ backend/
│  ├─ app/
│  │  ├─ __init__.py
│  │  ├─ chat_rules.py          # Rule-based replies when LLM is disabled
│  │  ├─ database.py
│  │  ├─ date_normalization.py
│  │  ├─ extraction_service.py  # LLM + rule extraction orchestration
│  │  ├─ field_extraction.py
│  │  ├─ llm_service.py         # Gemini / OpenAI integration
│  │  ├─ main.py
│  │  ├─ models.py
│  │  ├─ routes.py
│  │  └─ schemas.py
│  ├─ Dockerfile
│  └─ requirements.txt
├─ frontend/
│  ├─ src/
│  │  ├─ App.jsx                # Chat UI, session, i18n
│  │  ├─ main.jsx
│  │  └─ styles.css
│  ├─ index.html
│  ├─ nginx.conf
│  ├─ package.json
│  ├─ vite.config.js
│  └─ Dockerfile
├─ .devcontainer/
│  └─ devcontainer.json
├─ .env.example
├─ docker-compose.yml
└─ README.md
```

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/session/start` | Create or update a chat session with guest email |
| `GET` | `/api/session/{session_id}` | Look up a session |
| `POST` | `/api/chat` | Send a message; extract fields and return assistant reply |
| `GET` | `/api/chat-history/{session_id}` | Return messages for a session |
| `POST` | `/api/booking-request` | Direct insert (legacy / testing) |
| `GET` | `/api/booking-requests` | List recent saved requests (JSON) |
| `GET` | `/health` | Health check including LLM configuration status |
| `GET` | `/docs` | FastAPI interactive API documentation |

---

## Run locally with Docker

### Prerequisites

- Docker Desktop or Docker Engine
- Docker Compose support

### Start the project

From the root of the repository:

```bash
docker compose up --build
```

### Open in browser

- Frontend: http://localhost:8080
- Backend docs: http://localhost:8000/docs
- Health (LLM status): http://localhost:8000/health

### Stop the project

```bash
docker compose down
```

To also remove the database volume:

```bash
docker compose down -v
```

---

## Run in GitHub Codespaces

1. Open the repository in GitHub Codespaces.
2. Wait until the dev container finishes loading.
3. In the Codespaces terminal, run:

```bash
docker compose up --build
```

4. Open the forwarded frontend port (8080).
5. Enter your email, start chatting, and send a booking-related message.
6. Verify stored data via `GET /api/booking-requests` or `GET /api/chat-history/{session_id}` in the API docs.

---

## Environment variables

Configuration is handled through environment variables. Copy `.env.example` to `.env` for local overrides.

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string for the backend |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Database container credentials |
| `FRONTEND_PORT`, `BACKEND_PORT`, `DB_PORT` | Host port mappings |
| `CORS_ALLOW_ORIGINS` | Allowed frontend origins (`*` by default) |
| `LOG_LEVEL` | Backend log level |
| `LLM_ENABLED` | `true` to use hosted LLM; `false` for rule-based replies only |
| `LLM_PROVIDER` | `gemini` or `openai` |
| `LLM_MODEL` | Model name (e.g. `gemini-2.5-flash`) |
| `API_KEY` | Provider API key (also accepts `LLM_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`) |
| `LLM_TIMEOUT_SECONDS` | Request timeout for LLM calls |
| `LLM_MAX_HISTORY_MESSAGES` | Max prior turns sent to the LLM |
| `LLM_CHAT_TEMPERATURE` | Reply creativity (default `0.6`; extraction stays low) |
| `LLM_CHAT_MAX_TOKENS` | Max length of assistant replies (default `450`) |
| `EMAIL_ENABLED` | `true` to send booking confirmation emails |
| `SMTP_HOST` | SMTP server (e.g. `smtp.gmail.com`) |
| `SMTP_PORT` | SMTP port (usually `587` for TLS) |
| `SMTP_USER` | SMTP login / sender mailbox |
| `SMTP_PASSWORD` | SMTP password or app password |
| `EMAIL_FROM` | From address (defaults to `SMTP_USER`) |
| `HOTEL_NAME` | Hotel name shown in the email subject and body |
| `BOOKING_NOTIFY_EMAIL` | Optional staff inbox that receives a copy of each completed booking |

**Never commit `.env` or API keys to the repository.**

When a guest provides complete booking details (dates, guest count, name, email), the backend sends:

1. **Guest confirmation** — to the email entered at session start
2. **Staff notification** — to `BOOKING_NOTIFY_EMAIL` if set (use your own address for testing)

With `LLM_ENABLED=false` (the default), the app still works using rule-based extraction and replies.

---

## Confirmation emails

When email is configured, the backend sends **one confirmation email per chat session** after the guest provides complete booking details:

- Request type: **booking**
- Check-in and check-out dates
- Guest count
- Guest email (collected at session start)

The email confirms the request was **received** — it is not a final reservation confirmation.

### Gmail example (local `.env`)

```env
EMAIL_ENABLED=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-16-char-app-password
EMAIL_FROM=you@gmail.com
HOTEL_NAME=SMART Hotel
BOOKING_NOTIFY_EMAIL=you@gmail.com
```

For Gmail, create an [App Password](https://myaccount.google.com/apppasswords) (requires 2-Step Verification). Use that value as `SMTP_PASSWORD`, not your normal Gmail password.

Restart after changing `.env`:

```bash
docker compose up --build
```

Check status at http://localhost:8000/health — look for `"llm": { "active": true, "reply_mode": "llm" }` and `"email": { "enabled": true, "configured": true }`.

### Test in chat

1. Open http://localhost:8080 and enter your real email.
2. Send a booking message with dates and guest count, for example:  
   `I'd like to book a room from 25 June 2026 to 27 June 2026 for 2 guests. My name is Alex.`
3. The assistant reply should mention that a confirmation email was sent.
4. Check your inbox (and spam folder).

---

## Conversational design (examiner demo script)

After the initial milestone, replies were refined for more natural dialogue while keeping safe guardrails. Use these scenarios when demonstrating or evaluating the prototype:

### 1. Natural multi-turn booking

Guest messages across several turns:

1. `Hi, I'd like to stay with you next weekend.`
2. `Friday to Sunday, 2 guests.`
3. `My name is Alex.`

**Expected:** The assistant acknowledges each turn, remembers prior details, and only asks for what is still missing.

### 2. Correction across turns

1. `Book a room from 25 June to 27 June for 2 guests.`
2. `Sorry, checkout is Sunday the 28th, not the 27th.`

**Expected:** Check-out updates without re-asking for guest count or check-in.

### 3. Bounded openness (hotel-adjacent)

`Do you have parking? What time is breakfast?`

**Expected:** A short, helpful hospitality answer, then an offer to help with the stay or booking.

### 4. Guardrail (off-topic)

`Can you teach me Rust programming?`

**Expected:** A polite decline and redirect to hotel assistance — not a programming lesson.

### Verify LLM is active

Open http://localhost:8000/health and confirm:

```json
"llm": { "enabled": true, "configured": true, "active": true, "reply_mode": "llm" }
```

If `reply_mode` is `rule_based`, replies will feel more templated. Enable the LLM in `.env` and restart Docker.

---

## Team development workflow and AI tools

This project is developed using a mix of human work and support from AI tools.

### Human responsibilities

- Define project requirements and scope
- Decide the architecture and technology stack
- Review all generated code and configuration
- Run tests and verify that the full flow works
- Decide what is finally committed to the repository

### AI tool support

- Suggest project structure and boilerplate
- Propose backend and frontend implementations
- Help write and refine documentation
- Assist with debugging and troubleshooting
- Suggest simpler alternatives when something is too complex

### How AI is used in practice

AI tools are used to draft code and documentation while the developer focuses on planning and testing. Once a draft is generated, it is reviewed, simplified if needed, and only then added to the project.

### Keeping the project aligned

To keep the project aligned with the proposal and the course requirements:

- The project proposal is used as the main reference for scope and goals
- Milestones are kept testable end-to-end in Docker
- All important changes are reviewed by a human
- Only verified code is included in the submission

### Quality and traceability

Content suggested by AI tools is treated as a draft until it is verified by:

- Running Docker Compose
- Testing the chat flow (email → message → reply)
- Checking saved records in the database
- Reviewing logs and API behavior (`/health`, `/docs`)

Traceability is maintained through repository structure, documented endpoints, version control, and this README.

---

## Prototype and evaluation dimensions

| Dimension | Notes |
|-----------|-------|
| **Performance** | Chat requests involve DB reads/writes; LLM calls are optional and timeout-bounded |
| **Development time** | Modular backend services and a single-page React frontend |
| **Cost** | Open-source stack; LLM usage is optional and provider-billed |
| **Accuracy** | Structured field extraction with session merge; multi-turn corrections; LLM does not confirm bookings |
| **Usability** | Multilingual chat UI with natural LLM replies and tiered hospitality guardrails |
| **Security** | Secrets via environment variables; DB accessed only through the backend |
| **Scalability** | Frontend, backend, and database are separate services |
| **Extensibility** | Clear split between routes, extraction, LLM, and rule-based fallback |
| **Traceability** | Full message history and extracted fields stored per session |

---

## Future roadmap

Next iterations can extend this base by adding:

- Room availability and pricing checks against real inventory
- Staff/admin dashboard for reviewing conversations and requests
- Additional channels such as WhatsApp or voice
- Stronger authentication and guest identity verification

---

## Purpose of this milestone

This repository demonstrates a working prototype that is:

- Frontend based (React chat UI)
- Backend connected (FastAPI with session and chat APIs)
- Database integrated (PostgreSQL with sessions and booking requests)
- AI-ready (optional LLM with safe rule-based fallback)
- Containerized (Docker Compose)
- Cloud-deployable and GitHub Codespaces compatible

It serves as the technical foundation for the long-term goal of building a single-hotel AI receptionist system.

---

## Development checklist (professor evaluation criteria) — **Excellent (1.0–2.0)**

| # | Criterion | Excellent implementation |
|---|-----------|------------------------|
| 1 | **Dev environment** | `flake.nix` reproducible shell, `package-lock.json`, `make bootstrap`, pre-commit, CI with dependency caching |
| 2 | **Testing** | 34+ tests: unit, integration, **Hypothesis property-based**, chaos/resilience; **60%+ coverage gate** in CI |
| 3 | **Config management** | `pydantic-settings`, prod fail-fast validation, **dual-key rotation** (`scripts/rotate_admin_key.py`) |
| 4 | **Logging** | JSON logs, **PII redaction** (`logging_filters.py`), **audit trail** (`audit_logs`), **anomaly detection** + webhook alerts |
| 5 | **Deployment** | HA-ready nginx upstream, `restart: unless-stopped`, **Prometheus/Grafana** (`docker-compose.monitoring.yml`), `/ready` probe |
| 6 | **Security** | **`docs/THREAT_MODEL.md`**, Dependabot, CI **bandit + pip-audit**, rate limiting, session HMAC tokens |
| 7 | **Error handling** | **DLQ** (`failed_operations` + background worker), idempotent chat (`client_message_id`), structured errors |
| 8 | **Auth & encryption** | **MFA (TOTP)** + JWT (`/api/admin/mfa/verify`), **Fernet PII encryption at rest**, granular audit log |
| 9 | **Fault tolerance** | Circuit breaker + retry, **autoheal** sidecar, `make scale` (2× backend), DLQ self-healing |

### Quick commands

```bash
make bootstrap       # Install all deps + hooks
make up              # Start stack
make test            # Run tests with coverage gate
make monitoring      # Prometheus + Grafana + autoheal
make scale           # Run 2 backend replicas (load balanced)
make rotate-key      # Generate new admin API key
nix develop          # Reproducible dev shell (optional)
```

### Admin access (MFA + API key)

```bash
# Option A: API key
curl -H "X-API-Key: your-key" http://localhost:8000/api/booking-requests

# Option B: MFA → JWT
curl -X POST http://localhost:8000/api/admin/mfa/verify -H "Content-Type: application/json" -d '{"code":"123456"}'
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/booking-requests
```

### Production secrets (generate once)

```bash
python scripts/rotate_admin_key.py
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
python -c "import pyotp; print(pyotp.random_base32())"
```

See `docs/THREAT_MODEL.md` for the full security analysis.
