"""Static analysis with Ruff, for Python only. Ruff parses files and runs nothing in them.

--isolated ignores the repository's own Ruff configuration, which is untrusted input. Results
keep rule codes and file names only, because messages can quote identifiers from the source.
"""

import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

from app.analyzers.base import AnalyzerResult, Inventory, RawEvidence, ScanContext
from app.security.process_safety import ProcessError, run_command

METHOD = "static-analysis:ruff"
CATEGORY = "static_analysis"
SYNTAX_ERROR = "syntax-error"
MAX_REPORTED_FILES = 15
_MAX_OUTPUT_BYTES = 5_000_000
_RULES = "E9,F"


def find_ruff() -> str | None:
    """Prefer the copy installed with GhostRepo, so the result does not depend on PATH."""
    name = "ruff.exe" if sys.platform == "win32" else "ruff"
    bundled = Path(sys.executable).parent / name
    return str(bundled) if bundled.is_file() else shutil.which("ruff")


def _not_run(reason: str, evidence: list[RawEvidence] | None = None) -> AnalyzerResult:
    return AnalyzerResult("static_analysis", {"ran": False, "reason": reason}, evidence or [])


def _could_not_finish(detail: str) -> AnalyzerResult:
    return _not_run(
        "ruff_failed",
        [
            RawEvidence(
                "static_analysis.incomplete",
                CATEGORY,
                f"Ruff did not produce a complete result: {detail}",
                METHOD,
            )
        ],
    )


def _relative(filename: str, root: Path) -> str | None:
    """A path Ruff reports outside the repository is dropped, not shown."""
    try:
        return Path(filename).resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return None


def analyze(ctx: ScanContext, inventory: Inventory) -> AnalyzerResult:
    if not any(item.suffix in {".py", ".pyi"} for item in inventory.files):
        return _not_run("no_python_files")
    ruff = find_ruff()
    if ruff is None:
        return _not_run("ruff_unavailable")

    args = [
        ruff,
        "check",
        "--isolated",
        "--no-cache",
        "--exit-zero",
        "--output-format=json",
        f"--select={_RULES}",
    ]
    args += [f"--extend-exclude={name}" for name in sorted(ctx.excluded_dirs)]
    env = {
        key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "TEMP", "TMP") if key in os.environ
    }
    try:
        result = run_command(
            [*args, "."],
            cwd=ctx.root,
            timeout=max(ctx.git_timeout, 60),
            env=env,
            max_output_bytes=_MAX_OUTPUT_BYTES,
        )
    except ProcessError as exc:
        return _could_not_finish(str(exc))
    if result.returncode != 0 or result.truncated:
        return _could_not_finish("it exited with an error or its output was too large.")
    try:
        diagnostics = json.loads(result.stdout)
    except ValueError:
        return _could_not_finish("its output could not be read.")

    codes: Counter[str] = Counter()
    per_file: Counter[str] = Counter()
    syntax_files: set[str] = set()
    for item in diagnostics:
        # The form depends on the Ruff version: invalid-syntax, no code at all, or E999.
        code = item.get("code")
        code = SYNTAX_ERROR if code in {None, "invalid-syntax", "E999"} else str(code)[:20]
        path = _relative(str(item.get("filename", "")), ctx.root)
        if path is None:
            continue
        codes[code] += 1
        per_file[path] += 1
        if code == SYNTAX_ERROR:
            syntax_files.add(path)

    total = sum(codes.values())
    facts = {
        "ran": True,
        "tool": "ruff",
        "rules": _RULES,
        "issue_count": total,
        "file_count": len(per_file),
        "codes": dict(codes.most_common(30)),
        "files": [path for path, _ in per_file.most_common(MAX_REPORTED_FILES)],
        "syntax_error_files": sorted(syntax_files)[:MAX_REPORTED_FILES],
    }

    evidence: list[RawEvidence] = []
    if syntax_files:
        evidence.append(
            RawEvidence(
                "static_analysis.syntax_errors",
                CATEGORY,
                f"Ruff could not parse {len(syntax_files)} Python file(s) with current syntax.",
                METHOD,
                data={"files": facts["syntax_error_files"], "count": len(syntax_files)},
            )
        )
    other = total - codes[SYNTAX_ERROR]
    if other:
        evidence.append(
            RawEvidence(
                "static_analysis.issues",
                CATEGORY,
                f"Ruff reported {other} issue(s) from its error and pyflakes rules.",
                METHOD,
                data={
                    "codes": {c: n for c, n in codes.most_common(30) if c != SYNTAX_ERROR},
                    "files": facts["files"],
                },
            )
        )
    if not total:
        evidence.append(
            RawEvidence(
                "static_analysis.clean",
                CATEGORY,
                "Ruff reported no issues from its error and pyflakes rules.",
                METHOD,
            )
        )
    return AnalyzerResult("static_analysis", facts, evidence)
