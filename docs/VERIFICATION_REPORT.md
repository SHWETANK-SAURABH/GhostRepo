# Verification report

Results from the final verification on Windows 11, with Python 3.11, Node.js 24, Git 2.55, Docker Desktop 29.5 and Ollama 0.32.4 running `gemma3:4b`.

## Summary

The MVP works end to end with a real local model, both running directly on Windows and in Docker containers.

| Check | Result |
| --- | --- |
| Backend tests on Windows | 252 passed, 3 skipped |
| Backend tests on Linux, in the `test` Docker target | 251 passed, 4 skipped |
| Backend lint (`ruff`, including security rules) | Passed |
| Frontend tests | 29 passed |
| Frontend typecheck, lint and production build | Passed |
| Browser walkthrough with the real model, run directly | Passed on its final run |
| Browser walkthrough with the real model, in Docker Compose | Passed |
| `bandit` | 3 low severity, reviewed below |
| `npm audit --omit=dev` | 0 vulnerabilities |

**What was skipped.** On Windows, 3 tests need symlink creation, which this account cannot do. They passed on Linux. On Linux, 3 Windows junction tests do not apply, and they passed on Windows. The live model test also skips on Linux because the test container has no Ollama, and it passed on Windows.

## Docker

Tested with `docker compose up --build`, using the default setup with Ollama on the host.

| Check | Result |
| --- | --- |
| Both images build, and the backend health check reports healthy | Passed |
| Backend runs as a non-root user | Passed (uid 1000) |
| Workspace mount refuses writes | Passed |
| Backend reaches Ollama on the host | Passed |
| Git history reads from a mount owned by another user | Passed |
| Browser walkthrough through the containers | Passed |
| Downloaded patch passes `git apply --check` | Passed |
| Cross-site write through the proxy | Refused with 403 |
| Demo button on the read-only mount | Clear 409 message |
| Errors in the backend log | None |

**Not tested:** the optional `ollama` Compose profile, and Docker Engine on Linux.

## Acceptance criteria

| Criterion | Status | How it was checked |
| --- | --- | --- |
| Frontend starts | Met | `next start`, `npm run dev` and Docker |
| Backend starts | Met | `uvicorn` and Docker |
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
| Installation documentation is complete | Met | The local and default Docker steps were used for the checks above |

## Real-model results

| Repository | Files | AI status | AI findings kept | AI items rejected | Time for AI |
| --- | --- | --- | --- | --- | --- |
| Synthetic demo | 9 | Completed | 6 to 7 per run | 0 to 3 | About 20 seconds |
| Clone of this project | About 147 | Completed | 6 to 8 per run | 1 to 3 | About 25 seconds |

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

Ruff itself is covered by tests that plant a repository config trying to hide issues, and that confirm no source text is kept and nothing is written to the repository.

Tests cover traversal, symlink and junction escapes, hostile Git configuration, XML entity attacks, secret redaction, prompt delimiter escape, cross-site writes and unsafe patch paths. No secret value or absolute path appeared in any exported file.

## Local-only operation

- The app's backend and frontend processes were sampled 240 times during a full walkthrough with the real model. No connection to a non-loopback address was seen.
- Sampling can miss very short connections, so this is strong evidence rather than proof.
- The machine was **not** physically disconnected from the network, so fully offline operation was not tested directly. The design supports it: fonts are bundled, the Ollama client only contacts the configured local endpoint, and telemetry is off in Docker. For local runs, set `NEXT_TELEMETRY_DISABLED=1` to turn off Next.js telemetry.
- An earlier sampling run listed external addresses, but its process list was incomplete because the frontend had not started yet, so it could not be attributed. The rerun above used checked process IDs.

## Known gaps

- **Static analysis is limited.** Only Python is covered, and only with Ruff's `E9` and `F` rules. The other ecosystems have no static analyzer.
- **Patches do not change source code.** They only add missing project files and `.gitignore` entries, so GhostRepo does not suggest code fixes.
- **No license file.** This was the project owner's decision, so GhostRepo's own scan reports it as a finding.
- **Qwen3 is untested.** Only `gemma3:4b` was run.
- **The browser walkthrough failed in three of eight runs.** Two failures had known causes that are fixed: a stale server left over from an earlier check, and the script treating its own deliberate 422 as an error. The third is unconfirmed. The frontend port was not yet listening when checked, and the walkthrough passed on rerun after waiting for the servers to respond. The script has no readiness wait of its own, so start both servers and confirm they respond first.
- **AI text can still be wrong.** Citations and known claim types are enforced, but a citation shows only that the evidence exists, not that the model interpreted it correctly.
- **The AI README overview is labeled but has no claim policy.** In one test, it described the project's "original purpose" with more confidence than the facts supported.
- **Only some of the frontend is covered by component tests.** The dashboard, forms, progress, findings, plan, README and patch approval have them. Other pages are covered by the walkthrough.
- **No database migrations.** A future schema change would need them.
