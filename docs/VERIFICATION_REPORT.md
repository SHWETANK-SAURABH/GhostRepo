# Verification report

Results from the final verification on Windows 11, with Python 3.11, Node.js 24, Git 2.55 and Ollama 0.32.4 running `gemma3:4b`.

## Summary

The MVP works end to end with a real local model, with one exception: **the Docker setup has not been run**, because the Docker daemon was not running on the test machine.

| Check | Result |
| --- | --- |
| Backend tests | 245 passed, 3 skipped |
| Backend lint (`ruff`, including security rules) | Passed |
| Frontend tests | 29 passed |
| Frontend typecheck, lint and production build | Passed |
| Browser walkthrough with the real model (`npm run e2e`) | Passed |
| `bandit` | 0 high, 0 medium, 3 low (reviewed below) |
| `npm audit --omit=dev` | 0 vulnerabilities |
| `docker compose config` | Valid |
| Docker image build and run | **Not run** |

The live model test is one of the 245 and runs only when Ollama and the model are available.

The 3 skipped tests need symlink creation, which this Windows account cannot do. Equivalent tests using Windows junctions passed. The `test` target in `backend/Dockerfile` runs the suite on Linux, where the symlink tests would run.

## Acceptance criteria

| Criterion | Status | How it was checked |
| --- | --- | --- |
| Frontend starts | Met | `next start` and `npm run dev` |
| Backend starts | Met | `uvicorn` |
| Frontend communicates with backend | Met | Browser walkthrough through the proxy |
| User can select an allowed repository | Met | Browser walkthrough |
| Invalid paths are rejected | Met | Browser walkthrough and tests |
| Repository scanning works | Met | Demo and a clone of this project |
| Git history is analyzed when available | Met | Tests and both repositories |
| Dependency manifests are detected | Met | Tests for all six formats |
| Documentation is inspected | Met | Tests and both repositories |
| Tests are discovered without execution | Met | Tests plant files that would leave a marker if run |
| Evidence is persisted | Met | Lifecycle tests |
| Deterministic findings appear without Ollama | Met | Lifecycle tests against an unreachable endpoint |
| Ollama connectivity is checked | Met | Tests and the live Settings page |
| Open-weight model analysis works | Met | `gemma3:4b` through the real pipeline |
| AI findings reference valid evidence | Met | Tests, and live results |
| Hypotheses are clearly labeled | Met | Component tests and screenshots |
| Recovery plan generation works | Met | Tests and walkthrough |
| README draft generation works | Met | Tests and walkthrough, plus a live AI overview |
| Patch previews are generated safely | Met | Path tests, and `git apply --check` on the downloaded patch |
| No changes are applied without approval | Met | Tests hash the repository throughout. The demo's `git status` stayed clean |
| Reports can be exported | Met | Markdown and JSON downloads in the walkthrough |
| Works without cloud AI APIs | Met | No cloud API is used |
| Automated tests pass | Met | See above |
| Installation documentation is complete | Met, except Docker is unproven | README; the local steps were followed for the checks above, but the Docker steps were not run |

## Real-model results

| Repository | Files | AI status | AI findings kept | AI items rejected | Time for AI |
| --- | --- | --- | --- | --- | --- |
| Synthetic demo | 9 | Completed | 6 to 7 per run | 0 to 2 | About 20 seconds |
| Clone of this project | 146 | Completed | 6 to 8 per run | 1 to 3 | About 25 seconds |

Output varies between runs. In a direct test, the model succeeded on the first attempt in four of four runs. Timing is from this machine only.

## Problems found by testing against real conditions

Mocks passed in all of these cases. Each was found only with the real model or a real repository, and each is fixed.

| Problem | Effect | Fix |
| --- | --- | --- |
| Ollama rejected the JSON schema with `failed to parse grammar` | Structured output never ran. The JSON-mode fallback hid this, and sometimes returned `{}`, so AI failed on the larger repository | Send a simplified schema. The live test now calls it directly, with no fallback |
| The model ignored prompt rules | It rated commit age as critical and claimed abandonment and vulnerabilities | Code now rejects those claims. Live runs rejected findings such as "Long Inactivity" and "Outdated Dependencies" |
| Fake credentials in test files | Reported as a critical leak | Matches in test and example paths rank low |
| `.env` listed in the draft README's file tree | Advertised a secret file's name | Secret file names are left out |
| Investigation could read as completed with a stage still running | A brief inconsistent state | Both now change in one transaction |

## Security checks

The `bandit` findings are all expected:

- **B405:** imports `ParseError` for exception handling. Parsing itself uses defusedxml.
- **B404 and B603:** the single subprocess wrapper, which uses argument arrays, an allowlist and timeouts.

Tests cover traversal, symlink and junction escapes, hostile Git configuration, XML entity attacks, secret redaction, prompt delimiter escape, cross-site writes and unsafe patch paths. No secret value or absolute path appeared in any exported file.

## Local-only operation

- The app's backend and frontend processes were sampled 240 times during a full walkthrough with the real model. No connection to a non-loopback address was seen.
- Sampling can miss very short connections, so this is strong evidence rather than proof.
- The machine was **not** physically disconnected from the network, so fully offline operation was not tested directly. The design supports it: fonts are bundled, the Ollama client only contacts the configured local endpoint, and telemetry is off in Docker. For local runs, set `NEXT_TELEMETRY_DISABLED=1` to turn off Next.js telemetry.
- An earlier sampling run listed external addresses, but its process list was incomplete because the frontend had not started yet, so it could not be attributed. The rerun above used checked process IDs.

## Known gaps

- **Docker is unverified.** The configuration is valid, but no image has been built or run. The cases to watch are the proxy's Host header and reading mounted repositories owned by another user.
- **Qwen3 is untested.** Only `gemma3:4b` was run.
- **The browser walkthrough had one failed run** out of five full runs, when the frontend server had not finished starting. It has no readiness wait of its own, so start the servers first.
- **AI text can still be wrong.** Citations and known claim types are enforced, but a citation shows only that the evidence exists, not that the model interpreted it correctly.
- **The AI README overview is labeled but has no claim policy.** In one test, it described the project's "original purpose" with more confidence than the facts supported.
- **Only some of the frontend is covered by component tests.** The dashboard, forms, progress, findings, plan, README and patch approval have them. Other pages are covered by the walkthrough.
- **No database migrations.** A future schema change would need them.
