# Architecture

GhostRepo is a Next.js frontend and a FastAPI backend, with SQLite for storage and an optional local Ollama server. One orchestrator coordinates deterministic tools. The only model calls are the Ghost Analyst and the optional README overview.

```text
Browser
  │  same-origin /api requests
  ▼
Next.js (rewrites /api/* to the backend)
  ▼
FastAPI ── SQLite
  │
  ▼ background thread pool
Investigation orchestrator
  ├─ Repository Scout
  ├─ Git Historian
  ├─ Dependency Detective
  ├─ Configuration Inspector
  ├─ Documentation Inspector
  └─ Test Investigator
  │
  ▼
Evidence normalization and redaction ──► saved
  │
  ├─► Findings engine and Resurrection Planner (deterministic) ──► saved
  │
  ▼ only if AI is enabled and available
Ghost Analyst ──► Ollama ──► open-weight model
  │
  ▼
Schema check ► citation check ► claim policy ► redaction ──► saved, labeled as AI
```

## An investigation, step by step

1. `POST /api/investigations` validates the path, creates a record and returns 202. The work runs in a bounded thread pool, so the request does not wait for it.
2. The orchestrator validates the path again, because it may have become a symlink since the request.
3. Each analyzer runs as its own stage, with progress saved to SQLite. If one fails, the stage is marked failed, the others still run and the report says it is incomplete. A timeout stops the investigation with a clear message.
4. Evidence, findings and the plan are **saved before any model is called**, so an AI failure cannot lose them.
5. The Ghost Analyst runs if AI is enabled and the model is installed. Otherwise the AI stage records why not.
6. Retrying AI (`/reanalyze`) reads stored evidence and does not rescan.

If the server restarts mid-run, startup marks those investigations `interrupted` instead of leaving them running forever.

## Evidence

Analyzers produce evidence, not conclusions. Each item gets a key such as `ev-dep-003`, and passes through redaction and size limits before it is stored.

Findings cite evidence keys. Deterministic findings come from rules in `services/findings_engine.py`. AI findings must cite keys that exist.

## Two kinds of result

| | Verified findings | AI findings |
| --- | --- | --- |
| Produced by | Rules over analyzer evidence | Local model |
| `origin` | `deterministic` | `ai` |
| Counted in the health indicator | Yes | No |
| Survives AI failure | Yes | Not applicable |
| Labeled in the UI and exports | Verified | AI-generated, and hypothesis where the model marked it |

## How model output is checked

The model's reply is untrusted. It passes through these steps in `agents/ghost_analyst.py`:

1. **Parse.** Tolerates reasoning tags and code fences. Invalid JSON gets one retry.
2. **Schema.** Validated by Pydantic in `models/analysis.py`.
3. **Redaction.** Removes any secret the model echoes.
4. **Citations.** Items citing unknown or no evidence are rejected.
5. **Claim policy.** Items claiming abandonment, vulnerable or outdated software, or test results are rejected, and such sentences are removed from prose. A finding citing only Git history is capped at low severity.

Rejected items are listed in the report. The policy exists because testing with a real small model showed it ignoring those same rules in the prompt.

Ollama compiles a requested schema into a sampling grammar, and references or length limits can make that fail. So the request carries a simplified schema (`grammar_schema` in `services/ollama_service.py`), and Pydantic enforces the full limits on the reply. If a model still refuses, the client falls back to plain JSON mode, and validation is the same either way.

## Health indicator

The score is 100 minus a penalty for each verified finding: critical 25, high 12, medium 6, low 2, informational 0, with a floor of 0. It measures how ready a repository is to pick up, not the quality of its code.

## Source layout

```text
backend/app/
  analyzers/    Six deterministic analyzers and the bounded file walker
  agents/       Orchestrator, Ghost Analyst, Resurrection Planner, README generator
  services/     Evidence, findings, reports, patches, Ollama client, settings
  security/     Path validation, secret redaction, process safety
  api/          REST routes
  schemas/      API models
  models/       Contract for model output
  database/     SQLAlchemy models and sessions
frontend/src/
  app/          Routes
  components/   Views and shared UI (components/ui is shadcn/ui)
  lib/          API client and types
```

## Decisions

- **Thread pool, not a task queue.** There is nothing extra to install. Jobs do not survive a restart, which `recover_interrupted` reports honestly.
- **Schema created at startup with `create_all`.** There are no migrations yet, so a future change to existing tables would need one, or a fresh database.
- **Same-origin API through rewrites.** The browser only talks to Next.js. CORS remains a strict second layer.
- **Polling, not Server-Sent Events.** Progress is already saved to SQLite, so polling is simple and survives reloads.
