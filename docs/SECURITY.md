# Security

GhostRepo reads repositories that may be hostile. This document lists what it defends against, where each defense lives and what it does not protect.

## Threat model

Any file in a scanned repository may be crafted by an attacker, including its file names, manifests, Git configuration and any text a model will read.

GhostRepo is a single-user local tool. It has no login, so anyone who can reach its API can use it. Do not expose it to a network.

## Controls

| Risk | Defense | Where |
| --- | --- | --- |
| Reading outside the workspace | Paths are resolved through symlinks and must be strictly inside the workspace root, checked again when work starts | `security/path_validation.py` |
| Over-broad workspace | A drive root or home directory is refused as the workspace | `services/settings_service.py` |
| Browsing the server's files | Only direct children of the workspace are listed | `services/repository_service.py` |
| Symlinks and junctions in a repository | Never followed; special files are never opened | `analyzers/base.py` |
| Huge or deep repositories | Limits on file size, depth, file count and time | `analyzers/base.py`, orchestrator |
| Malicious file names | Names with control characters or invalid encoding are skipped and counted | `analyzers/base.py` |
| Malformed manifests | Parser errors become findings; deep nesting is caught | `analyzers/dependency_analyzer.py` |
| XML entity attacks in `pom.xml` | Parsed with defusedxml | `analyzers/dependency_analyzer.py` |
| Running repository code | No analyzer runs repository code. Tests are discovered only | `analyzers/test_discovery.py` |
| Command injection | Argument arrays only, never a shell, with an allowlist containing only `git`, plus timeouts and bounded output | `security/process_safety.py` |
| Hostile `.git/config` | See below | `analyzers/git_historian.py` |
| `.git` pointing elsewhere | Symlinks, pointer files and `commondir` are refused | `analyzers/git_historian.py` |
| Secrets in reports | Secret files are never read. Matches record only rule, file and line. Redaction runs on evidence, model input, model output, README drafts and exports | `security/secret_redaction.py` |
| Source sent to a model | Only normalized evidence is sent, within a size budget | `services/evidence_service.py` |
| Evidence sent off the machine | The Ollama endpoint host must be on a local allowlist, redirects are not followed and proxy settings are ignored | `services/settings_service.py`, `services/ollama_service.py` |
| Prompt injection | Evidence is delimited as untrusted data, and repository text cannot close the delimiter. Output is checked by code, and model output is never executed | `agents/ghost_analyst.py` |
| Model inventing facts | Citations are validated and unsupported claims rejected | `agents/ghost_analyst.py` |
| Repository HTML in the browser | Raw HTML is not rendered, unsafe links are dropped, and remote images are not loaded | `components/markdown-preview.tsx` |
| Patches escaping the repository | Refuses traversal, absolute paths, `.git` (with Windows name variants), secret files, reserved names and symlinked targets | `security/path_validation.py` |
| Patches applied without consent | GhostRepo has no code path that writes a patch to a repository. Download requires explicit approval | `api/reports.py` |
| SQL injection | All queries use SQLAlchemy parameter binding | `database/` |
| Other websites calling the API | Host header allowlist, strict CORS and an Origin check on every write | `main.py` |
| Leaking details in errors | Unexpected errors return a generic message. Validation errors omit submitted values | `errors.py` |
| Filesystem paths in responses | Reports and exports use workspace-relative paths | `services/investigation_service.py` |

The Settings page does show the workspace root, because it is an editable setting.

## Hostile Git configuration

A repository's `.git/config` can name programs for Git to run, through settings such as `core.fsmonitor`. Every Git call therefore:

- ignores system and global configuration
- overrides the settings known to start programs: `core.fsmonitor`, `core.hooksPath`, `core.sshCommand`, `core.pager`, `gpg.program`, `diff.external`
- blocks network transports and lazy fetches
- uses only read commands: `rev-parse`, `symbolic-ref`, `log`, `rev-list`, `ls-files`

`safe.directory=*` is set so mounted repositories owned by another user can be read. This turns off Git's own ownership check, so the overrides above are what protect you. A test plants a hostile config and confirms nothing runs. A future Git setting that starts a program would not be covered until it is added to this list, so scanning inside a disposable container or VM remains sensible for repositories you distrust.

## Known limits

- **Secret detection is pattern-based.** It can miss secrets, can flag harmless values, and does not scan Git history.
- **Settings can move the workspace.** Anyone who can reach the API can point it at another folder, though not a drive root or home directory. This is why the API must stay local.
- **Git author names are stored and shown** in reports. Email addresses are not collected.
- **The local database is not encrypted.** It holds redacted evidence and reports, in `backend/data/` by default.
- **Prompt injection cannot be fully prevented.** Injected text could skew what the model writes. Controls ensure it cannot run anything, cite invented evidence or change verified findings, and AI output is labeled accordingly.
- **Threads cannot be force-stopped.** A timeout takes effect at the next checkpoint in the scan.

## Security checks used

```sh
cd backend
.venv/bin/python -m ruff check .      # includes the flake8-bandit rules
.venv/bin/python -m bandit -r app
cd ../frontend
npm audit --omit=dev
```
