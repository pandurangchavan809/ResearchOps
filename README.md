# ResearchOps

**ResearchOps — Evidence-Grounded Technical Research Agent** finds, checks, and explains technical research with source-backed evidence. The web UI returns a cited answer by default; a polished PDF is generated only when the user asks for one.

## Product flow

```text
Register / log in → question → scope guard → research planner → LangGraph workflow
                  → Tavily search → source ranking → HTTPX fetch → Trafilatura extraction
                  → evidence extraction → claim verification → (follow-up searches if needed)
                  → cited answer → (on request) ReportLab PDF
```

LangGraph owns state, routing, and limits. Search and fetching are service functions. Pydantic validates everything crossing a boundary. Progress in the UI comes from real workflow events.

## Stack

| Area | Technology |
|---|---|
| Frontend | React, TypeScript, Tailwind CSS, Zustand |
| API | FastAPI, Pydantic |
| Auth | SQLite (`auth.db`), Argon2, JWT access and refresh tokens |
| Models | OpenAI, Gemini, Nebius |
| Workflow | LangGraph, LangChain |
| Search | Tavily |
| Web extraction | HTTPX, Trafilatura |
| Tracing | LangSmith |
| PDF and charts | ReportLab Platypus, Matplotlib |

## Repository layout

```text
ResearchOps/
├── .env.example            All settings, documented
├── backend/
│   ├── app/
│   │   ├── main.py         App setup and system routes
│   │   ├── config.py       Validated settings from .env
│   │   ├── db.py           SQLite connections and schema
│   │   ├── security.py     Password hashing and JWT
│   │   ├── guardrails.py   Deterministic safety and quality checks
│   │   ├── schemas.py      API request and response models
│   │   ├── dependencies.py Current-user and settings injection
│   │   ├── routers/        auth, research
│   │   ├── services/       users and credits, runs, llm routing, web
│   │   ├── workflow/       LangGraph graph, prompts, models, runner
│   │   └── report/         compose (content), charts, render (PDF)
│   └── tests/
├── frontend/src/
│   ├── api.ts              HTTP client with silent token refresh
│   ├── hooks/              useAuth, useApp stores
│   └── components/         auth, chat, sidebar, ui
└── data/                   Created at runtime: auth.db, research.db, reports/ (gitignored)
```

## Setup

Python 3.11+ and Node 20+ are required.

1. Copy `.env.example` to `.env`.
2. Set `RESEARCHOPS_JWT_SECRET`, `TAVILY_API_KEY`, and at least one of `OPENAI_API_KEY` or `GEMINI_API_KEY`.

**Backend**, from `backend/`:

```bash
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

**Frontend**, from `frontend/`:

```bash
npm install
npm run dev
```

Open http://localhost:5173. Vite forwards `/api` to the backend.

**Production:** run `npm run build`. The API then serves `frontend/dist` itself, keeping the auth cookie same-origin. Set `RESEARCHOPS_ENVIRONMENT=production` and `RESEARCHOPS_COOKIE_SECURE=true`, and serve over HTTPS. Run one worker per data directory, because SQLite and the startup recovery step assume a single host.

**Tests**, from `backend/`:

```bash
pip install -r requirements-dev.txt
python -m pytest
```

Tests stub the models and the web, so they need no API keys and spend nothing.

## Configuration

`.env` is the single place to change behaviour; `.env.example` documents every setting. Common changes:

| Goal | Setting |
|---|---|
| Give every user more credits, including existing users | `RESEARCHOPS_USER_CREDITS` |
| Change what a research run costs | `RESEARCHOPS_RESEARCH_CREDIT_COST` |
| Change the Auto model and its fallbacks | `RESEARCHOPS_PRIMARY_MODEL`, `RESEARCHOPS_FALLBACK_MODELS` |
| Offer more models in the picker | `RESEARCHOPS_EXTRA_MODELS` |
| Keep users logged in longer | `RESEARCHOPS_REFRESH_TOKEN_DAYS` |
| Limit research cost and depth | `RESEARCHOPS_MAX_SEARCHES`, `_MAX_PAGES`, `_MAX_SOURCES`, `_MAX_ITERATIONS`, `_MAX_TOKEN_BUDGET`, `_MAX_RUNTIME_SECONDS` |

Model IDs change often. If a model is retired, update the ID in `.env`; no code changes are needed. Only models whose provider has an API key are offered.

Process environment variables override `.env`.

## Behaviour worth knowing

**Sessions.** A short-lived access token is kept in memory, and a long-lived refresh token is kept in an HttpOnly cookie. The token rotates on every refresh, and replaying an old one revokes that login everywhere.

**Credits.** A run reserves its credits when it starts. They are returned if the run is refused as out of scope, finds no evidence, fails, or is stopped. Reports use no credits but are capped per run, because each one calls a model. Registration has no email verification yet, so one person can create several accounts to get more credits.

**Model routing.** Auto tries the primary model, then each fallback in order. A model chosen in the picker runs first with the same fallbacks behind it. The models that actually answered are shown under each answer.

**Guardrails.** These run in code, whatever a model returns:

- Evidence excerpts must really appear in the page they cite; invented quotes are discarded.
- Citations that don't resolve to a source are removed, and a claim with no real evidence becomes `unsupported`.
- An answer with no valid citations is never shown.
- Chart values must appear in the cited evidence; otherwise the chart is left out.
- Web text is sanitized and marked as untrusted data for the model. This reduces prompt injection risk but cannot rule it out.
- Page fetching allows only public addresses, re-checked on every redirect, with size and time limits.
- Each run is bounded by searches, pages, sources, iterations, tokens, and runtime.

**Reports.** A report is written from the full text of the pages the research read, not just the short answer. Choose the length with the **Pages** selector, or ask in the question, such as "Generate a 3 page PDF comparing X and Y", which creates it automatically. Page counts are measured from the rendered PDF: long drafts are trimmed, and short ones are extended in further model calls and then with verbatim source excerpts. If the sources run out, the UI says how many pages they supported instead of padding. Report text drawn from page text is cited but does not go through the claim-verification step.

The model supplies content only. Platypus handles layout: tables repeat their header row and split between rows, and text is capped so that no block can outgrow a page. The title is cleaned and validated, with a fallback derived from the question. **Regenerate** produces a new title and content, and a failed attempt keeps the previous PDF.

See [project.md](./project.md) for scope and [uireaserchop.md](./uireaserchop.md) for the interface handoff.
