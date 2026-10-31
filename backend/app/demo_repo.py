"""A deliberately neglected sample repository for trying GhostRepo. All contents are synthetic.

Create it with: python -m app.demo_repo
"""

import argparse
import os
import shutil
from pathlib import Path

from app.config import Settings
from app.security.process_safety import ProcessError, run_command

DEMO_NAME = "haunted-demo"
DEMO_MARKER = ".ghostrepo-demo"

_FILES = {
    DEMO_MARKER: "Synthetic sample created by GhostRepo. Safe to delete.\n",
    "README.md": "# Haunted Inventory\n\nInventory tracker.\n",
    "requirements.txt": "flask==1.1.2\nrequests\nsqlalchemy>=1.3\n",
    "inventory/__init__.py": "",
    "inventory/app.py": (
        "import os\n\nfrom flask import Flask\n\n"
        "app = Flask(__name__)\nDEBUG = True\n\n"
        'DATABASE_URL = os.environ["INVENTORY_DATABASE_URL"]\n'
        'LOG_LEVEL = os.getenv("INVENTORY_LOG_LEVEL", "info")\n\n\n'
        '@app.route("/health")\ndef health():\n    return {"status": "ok"}\n'
    ),
    "inventory/settings.py": (
        "# Demo fixture: a fake credential for GhostRepo to flag.\n"
        'admin_password = "demo-only-not-a-real-credential"\n'
    ),
    "main.py": "from inventory.app import app\n\napp.run()\n",
    ".env": "INVENTORY_DATABASE_URL=sqlite:///demo-only.db\n",
    "tests/test_health.py": (
        "from inventory.app import app\n\n\n"
        "def test_health():\n"
        '    assert app.test_client().get("/health").status_code == 200\n'
    ),
}

_HISTORY = [
    ("feat: initial inventory tracker", "2021-02-03T10:00:00+00:00", "Mara Vale"),
    ("add health route", "2021-03-14T09:30:00+00:00", "Mara Vale"),
    ("fix: read database url from environment", "2021-07-22T16:45:00+00:00", "Theo Marsh"),
]


class DemoRepoError(Exception):
    pass


def _git(root: Path, *args: str, author: str, date: str) -> None:
    email = f"{author.split()[0].lower()}@example.invalid"
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": author,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": author,
        "GIT_COMMITTER_EMAIL": email,
        "GIT_AUTHOR_DATE": date,
        "GIT_COMMITTER_DATE": date,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
    }
    try:
        result = run_command(["git", *args], root, 30, env=env)
    except ProcessError as exc:
        raise DemoRepoError(str(exc)) from exc
    if result.returncode != 0:
        raise DemoRepoError("Git could not create the demo repository.")


def create_demo_repo(target: Path) -> Path:
    """Create or rebuild the demo. Refuses to touch a directory it did not create."""
    if target.is_symlink():
        raise DemoRepoError("A symlink already uses the demo repository's name.")
    if target.exists():
        if not (target / DEMO_MARKER).is_file():
            raise DemoRepoError("A folder that is not the demo already uses that name.")
        shutil.rmtree(target, onerror=_retry_read_only)
    target.mkdir(parents=True)

    for relative, content in _FILES.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")

    first_author = _HISTORY[0][2]
    _git(target, "init", "-q", "-b", "main", author=first_author, date=_HISTORY[0][1])
    # The first commits are the code; the secret file arrives with the last one.
    secret_files = [".env"]
    for index, (message, date, author) in enumerate(_HISTORY):
        if index == len(_HISTORY) - 1:
            _git(target, "add", "-A", author=author, date=date)
        else:
            paths = [p for p in _FILES if p not in secret_files]
            _git(target, "add", "--", *paths, author=author, date=date)
        _git(target, "commit", "-q", "--allow-empty", "-m", message, author=author, date=date)
    return target


def _retry_read_only(function, path, _exc_info) -> None:
    """Git marks object files read-only, which blocks deletion on Windows."""
    os.chmod(path, 0o700)
    function(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=None)
    args = parser.parse_args()
    workspace = args.workspace or Settings().workspace_root
    path = create_demo_repo(Path(workspace) / DEMO_NAME)
    print(f"Created the demo repository at {path}")  # noqa: T201


if __name__ == "__main__":
    main()
