# GhostRepo implementation plan

## Starting point (Phase 0 inspection)

The repository was empty: no application code, dependencies or conventions to preserve.

Tooling verified on the development machine:

| Tool | Version | Note |
| --- | --- | --- |
| Python | 3.11 | Meets the 3.11+ requirement |
| Node.js / npm | 24 / 11 | Frontend toolchain |
| Git | 2.55 | Used through safe argument-array wrappers only |
| Docker | 29 | Optional deployment |
| Ollama | 0.32 | Local runtime, with `gemma3:4b` installed |

## Decisions

| Decision | Choice | Reason |
| --- | --- | --- |
| Default model | `gemma3:4b`, configurable | It is the model that can be tested here. `qwen3:*` works through the same setting. |
| Orchestration | One orchestrator, six deterministic analyzers | No independent LLM agents. Only the Ghost Analyst and optional README drafting call a model. |
| Background work | Bounded thread pool, progress persisted in SQLite | No broker or other service to install |
| Frontend/backend link | Next.js rewrites `/api/*` to FastAPI | Same origin in the browser, with CORS as a strict second layer |
| Evidence identifiers | Per-investigation keys such as `ev-dep-003` | Short enough for a model to echo, easy to validate |
| Patches | Proposed diffs, approval gate, download only | GhostRepo never writes into a scanned repository |
| Scanned Git repositories | Read-only commands with config overrides | Repository config can otherwise run programs through `core.fsmonitor` and similar settings |

## Phases

| Phase | Scope |
| --- | --- |
| 1. Foundation | Backend and frontend scaffolds, configuration, health endpoints, connectivity, dashboard, design system |
| 2. Repository intelligence | Workspace validation, the six analyzers, evidence normalization |
| 3. Local AI | Ollama client, health checks, model configuration, Ghost Analyst, output validation, fallback |
| 4. Autopsy engine | Orchestration, persistence, progress, deterministic findings, reports |
| 5. Resurrection tools | Recovery plans, README drafts, patches, diff previews, approvals |
| 6. Frontend integration | All pages connected to the API |
| 7. Quality and release | Full test runs, security checks, offline check, Docker, documentation, verification report |

Each phase ends with its tests passing, a commit and a push.

## Risks

| Risk | Mitigation |
| --- | --- |
| Hostile repository content (symlinks, huge files, malformed manifests, Git config) | Path validation, no symlink following, size, depth and file-count limits, safe parsers, Git overrides |
| Prompt injection from repository files | Evidence is sent as delimited data, model output is schema-validated and every evidence reference is checked |
| The model invents facts | Findings citing unknown evidence are rejected, and AI output stays separate from verified findings |
| Secret leakage | Secret files are never read into model context. Redaction runs on evidence, model input and exports. |
| Slow or missing model | Deterministic results are saved first, AI failure is reported honestly and AI analysis can be retried alone |
| Ollama endpoint pointed at a remote host | The endpoint host must be on a local allowlist |
