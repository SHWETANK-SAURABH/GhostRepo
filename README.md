# GhostRepo

*Every abandoned repository has a story. Let's bring it back to life.*

GhostRepo investigates a local repository and helps you prepare a safe recovery plan. Deterministic analyzers collect the facts. A model running on your own machine can then interpret them. Nothing is uploaded, and nothing in the scanned repository is executed or changed.

## What it does

- **Investigates** languages, frameworks, Git history, dependencies, configuration, documentation and tests, and runs Ruff on Python code.
- **Reports verified findings** with severity, evidence, source file, confidence and detection method.
- **Adds AI interpretation** from a local Ollama model, kept separate from verified findings and labeled.
- **Builds a resurrection plan** in priority order, with verification steps and rough effort estimates.
- **Drafts a README** from verified facts and marks anything it could not confirm.
- **Proposes patches** as diffs you review and approve before download. GhostRepo never applies them.
- **Exports reports** as Markdown or JSON, with secrets redacted.

It works without Ollama. Verified findings, the plan, README drafts, patches and exports need no model, and the interface always shows which source produced a result.

### Supported ecosystems

Manifest and test analysis covers Python, JavaScript, TypeScript, Java, Go and Rust. Other languages are counted by file size and get no deeper analysis. Static analysis covers Python only, using Ruff's error and pyflakes rules.

GhostRepo reads manifests offline, so it does **not** check whether dependencies are outdated or vulnerable. Reports say so. It discovers tests but does not run them, so it cannot tell you whether they pass.

## Quick start

You need Python 3.11+, Node.js 24, and Git. Ollama is optional.

### 1. Start the backend

```sh
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt      # Windows: .venv\Scripts\pip
.venv/bin/uvicorn app.main:app --port 8000     # Windows: .venv\Scripts\uvicorn
```

API documentation is at <http://127.0.0.1:8000/docs>.

### 2. Start the frontend

```sh
cd frontend
npm ci
npm run dev
```

Open <http://localhost:3000>.

### 3. Add local AI (optional)

Install [Ollama](https://ollama.com), then:

```sh
ollama pull gemma3:4b
```

See [docs/MODELS.md](docs/MODELS.md) for licenses, hardware and other models.

### 4. Investigate a repository

Only folders inside the workspace can be scanned. The default is `workspace/` in this project, and you can change it in Settings.

1. Copy or clone a repository into `workspace/`, or choose **Create demo repository** on the New investigation page. The demo's contents are synthetic and labeled as a demo.
2. Choose **Summon Ghost — Inspect Repository**, then select the repository.
3. Confirm the details and start the investigation.

## Run with Docker

```sh
docker compose up --build
```

Open <http://localhost:3000>. Ports are published on the loopback interface only.

- Repositories come from `./workspace`, mounted read-only. To use another folder, set `GHOSTREPO_WORKSPACE=/path/to/repositories`.
- The backend uses Ollama on the host by default. With Docker Desktop on Windows this worked with no changes to Ollama. Docker Engine on Linux may need Ollama to accept connections from containers, usually by setting `OLLAMA_HOST=0.0.0.0`. On a shared network, that also exposes Ollama to other machines, so prefer the container option below.
- To run Ollama in a container as well:

  ```sh
  GHOSTREPO_OLLAMA_ENDPOINT=http://ollama:11434 docker compose --profile ollama up --build
  docker compose exec ollama ollama pull gemma3:4b
  ```

Because the mount is read-only, the demo button cannot write there. Create the demo on the host first:

```sh
cd backend
.venv/bin/python -m app.demo_repo
```

## Configuration

Copy [.env.example](.env.example) to `backend/.env` to change defaults. Every setting is optional. The Settings page can change the Ollama endpoint, model, AI on or off, workspace root, maximum file size, excluded directories and analysis timeout. Values saved there override the environment.

## Testing

```sh
# Backend (the live model test is skipped when Ollama or the model is missing)
cd backend
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .

# Frontend
cd frontend
npm test
npm run lint
npm run typecheck

# Browser walkthrough of the whole workflow. Start both servers first.
# Uses an installed browser: E2E_BROWSER=msedge (default) or chrome.
npm run e2e
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Security](docs/SECURITY.md)
- [Models and hardware](docs/MODELS.md)
- [Verification report](docs/VERIFICATION_REPORT.md)
- [Implementation plan](docs/IMPLEMENTATION_PLAN.md)

## Limitations

- GhostRepo has no user accounts. It is built for one person on their own machine, and its API should not be exposed to a network.
- Secret detection uses patterns and file names. It can miss secrets and flag false positives, and it scans the current files, not Git history.
- Patch proposals cover missing project files and `.gitignore` entries. They do not change source code.
- A small local model can write inaccurate text. Code checks every citation and rejects known kinds of unsupported claim, but it cannot prove the rest is right, so AI output stays labeled for your review.
