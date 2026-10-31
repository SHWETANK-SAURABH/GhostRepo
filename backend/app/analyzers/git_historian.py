"""Git Historian: read-only history observations.

A repository's own .git/config is hostile input. Settings such as core.fsmonitor can name a
program for Git to run, so every call disables them, ignores system and global config, and
uses only read commands. Age and activity are reported as observations, never as verdicts.
"""

import os
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any

from app.analyzers.base import AnalyzerResult, RawEvidence, ScanContext
from app.security.process_safety import ProcessError, run_command
from app.security.secret_redaction import redact

METHOD = "git-historian:git-log"
CATEGORY = "git"
MAX_COMMITS = 2000
_SEPARATOR = "\x1f"
_CONVENTIONAL = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\(.+\))?!?:"
)

_SAFE_CONFIG = [
    "-c", "core.fsmonitor=false",
    "-c", "core.hooksPath=/dev/null",
    "-c", "core.sshCommand=false",
    "-c", "core.pager=cat",
    "-c", "log.showSignature=false",
    "-c", "gpg.program=false",
    "-c", "core.attributesFile=/dev/null",
    "-c", "diff.external=",
    "-c", "protocol.allow=never",
]  # fmt: skip


def _git_env(root: Path) -> dict[str, str]:
    env = {
        key: os.environ[key]
        for key in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE")
        if key in os.environ
    }
    env.update(
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_TERMINAL_PROMPT="0",
        GIT_OPTIONAL_LOCKS="0",
        GIT_PAGER="cat",
        LC_ALL="C",
        # Without this, a folder with no .git would report its parent's history.
        GIT_CEILING_DIRECTORIES=str(root.parent),
    )
    return env


def run_git(ctx: ScanContext, *args: str, max_output_bytes: int = 2_000_000):
    return run_command(
        ["git", *_SAFE_CONFIG, *args],
        cwd=ctx.root,
        timeout=ctx.git_timeout,
        env=_git_env(ctx.root),
        max_output_bytes=max_output_bytes,
    )


def git_metadata_state(root: Path) -> str:
    """Return present, absent or unsafe. .git pointer files can aim outside the workspace."""
    git_path = root / ".git"
    if git_path.is_symlink():
        return "unsafe"
    if not git_path.exists():
        return "absent"
    if not git_path.is_dir() or (git_path / "commondir").exists():
        return "unsafe"
    return "present"


def tracked_paths(ctx: ScanContext, paths: list[str]) -> dict[str, bool] | None:
    """Which of these paths are committed? None means this could not be determined."""
    if git_metadata_state(ctx.root) != "present" or not paths:
        return None
    try:
        result = run_git(ctx, "ls-files", "-z", "--", *[f":(literal){path}" for path in paths])
    except ProcessError:
        return None
    if result.returncode != 0:
        return None
    tracked = set(filter(None, result.stdout.split("\x00")))
    return {path: path in tracked for path in paths}


def _clean(text: str, limit: int = 200) -> str:
    printable = "".join(char if char.isprintable() else " " for char in text)
    return redact(printable.strip())[:limit]


def _parse_date(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw).astimezone(UTC)
    except ValueError:
        return None


def parse_log(output: str) -> list[dict[str, Any]]:
    commits = []
    for line in output.splitlines():
        parts = line.split(_SEPARATOR)
        if len(parts) != 4:
            continue
        date = _parse_date(parts[2])
        if date is None:
            continue
        commits.append(
            {"hash": parts[0][:12], "author": _clean(parts[1], 80), "date": date,
             "subject": _clean(parts[3])}
        )  # fmt: skip
    return commits


def summarize_commits(commits: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    subjects = [commit["subject"] for commit in commits]
    conventional = sum(1 for subject in subjects if _CONVENTIONAL.match(subject))
    merges = sum(1 for subject in subjects if subject.lower().startswith("merge "))
    authors = Counter(commit["author"] for commit in commits)

    def within(days: int) -> int:
        cutoff = now - timedelta(days=days)
        return sum(1 for commit in commits if commit["date"] >= cutoff)

    total = len(commits) or 1
    return {
        "activity": {
            "last_30_days": within(30),
            "last_90_days": within(90),
            "last_365_days": within(365),
        },
        "contributor_count": len(authors),
        "top_contributors": [
            {"name": name, "commits": count} for name, count in authors.most_common(5)
        ],
        "message_patterns": {
            "conventional_commit_share": round(conventional / total * 100, 1),
            "merge_commit_share": round(merges / total * 100, 1),
            "median_subject_length": int(median(len(s) for s in subjects)) if subjects else 0,
        },
    }


def _unavailable(reason: str, kind: str, description: str) -> AnalyzerResult:
    return AnalyzerResult(
        "git_historian",
        {"available": False, "reason": reason},
        [RawEvidence(kind, CATEGORY, description, METHOD, data={"reason": reason})],
    )


def analyze(ctx: ScanContext, now: datetime | None = None) -> AnalyzerResult:
    now = now or datetime.now(UTC)
    state = git_metadata_state(ctx.root)
    if state == "absent":
        return _unavailable(
            "no_git_metadata", "git.absent", "No .git directory was found, so history is unknown."
        )
    if state == "unsafe":
        return _unavailable(
            "unsafe_git_metadata",
            "git.unsafe",
            "The .git entry is a symlink or pointer file. It was not followed.",
        )

    log_format = _SEPARATOR.join(["%H", "%an", "%aI", "%s"])
    try:
        probe = run_git(ctx, "rev-parse", "--is-inside-work-tree")
        if probe.returncode != 0:
            return _unavailable(
                "git_refused",
                "git.unreadable",
                "Git could not read this repository's metadata. It may be corrupt or "
                "owned by another user.",
            )
        branch = run_git(ctx, "symbolic-ref", "--short", "-q", "HEAD")
        log = run_git(ctx, "log", f"--max-count={MAX_COMMITS}", f"--format={log_format}")
        count = run_git(ctx, "rev-list", "--count", "HEAD")
        roots = run_git(ctx, "log", "--max-parents=0", "--format=%aI", "-n", "20", "HEAD")
        shallow = run_git(ctx, "rev-parse", "--is-shallow-repository")
    except ProcessError as exc:
        return _unavailable("git_failed", "git.unreadable", f"Git could not be used: {exc}")

    branch_name = _clean(branch.stdout) if branch.returncode == 0 else None
    commits = parse_log(log.stdout) if log.returncode == 0 else []
    is_shallow = shallow.stdout.strip() == "true"

    if not commits:
        facts = {"available": True, "branch": branch_name, "commit_count": 0}
        return AnalyzerResult(
            "git_historian",
            facts,
            [
                RawEvidence(
                    "git.no_commits",
                    CATEGORY,
                    "The Git repository has no readable commits.",
                    METHOD,
                    data=facts,
                )
            ],
        )

    latest = commits[0]
    root_dates = [d for d in map(_parse_date, roots.stdout.split()) if d]
    first_date = min(root_dates) if root_dates else commits[-1]["date"]
    days_since = max(0, (now - latest["date"]).days)
    summary = summarize_commits(commits, now)
    commit_count = int(count.stdout.strip()) if count.stdout.strip().isdigit() else len(commits)

    facts = {
        "available": True,
        "branch": branch_name,
        "detached_head": branch_name is None,
        "commit_count": commit_count,
        "sampled_commits": len(commits),
        "shallow_clone": is_shallow,
        "latest_commit": {
            "hash": latest["hash"],
            "author": latest["author"],
            "date": latest["date"].isoformat(),
            "subject": latest["subject"],
        },
        "first_commit_date": first_date.isoformat(),
        "days_since_last_commit": days_since,
        **summary,
    }

    evidence = [
        RawEvidence(
            "git.history",
            CATEGORY,
            f"{commit_count} commit(s) on {branch_name or 'a detached HEAD'}. "
            f"Latest commit is {days_since} day(s) old. "
            f"{summary['contributor_count']} contributor name(s) in the sampled history.",
            METHOD,
            data={
                "branch": branch_name,
                "commit_count": commit_count,
                "latest_commit_date": latest["date"].isoformat(),
                "first_commit_date": first_date.isoformat(),
                "days_since_last_commit": days_since,
                "contributor_count": summary["contributor_count"],
                "activity": summary["activity"],
            },
        ),
        RawEvidence(
            "git.message_patterns",
            CATEGORY,
            f"{summary['message_patterns']['conventional_commit_share']}% of sampled commit "
            "subjects follow the conventional commit format.",
            METHOD,
            data=summary["message_patterns"],
        ),
    ]
    if days_since >= 365:
        evidence.append(
            RawEvidence(
                "git.no_recent_commits",
                CATEGORY,
                f"No commits in the last {days_since} day(s). This is an observation: "
                "a quiet repository may be finished or stable, not abandoned.",
                METHOD,
                data={"days_since_last_commit": days_since},
            )
        )
    if is_shallow:
        evidence.append(
            RawEvidence(
                "git.shallow",
                CATEGORY,
                "This is a shallow clone, so history figures cover only part of the project.",
                METHOD,
            )
        )
    return AnalyzerResult("git_historian", facts, evidence)
