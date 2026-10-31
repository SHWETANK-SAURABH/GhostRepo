"""Patch proposals: unified diffs a person can review and download.

Nothing here writes to a scanned repository. Every path goes through validate_patch_path,
and proposals only add missing project files or append to .gitignore.
"""

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.analyzers.base import ScanContext, read_text
from app.security.path_validation import PathValidationError, validate_patch_path
from app.security.secret_redaction import find_secrets

_NO_NEWLINE = "\\ No newline at end of file\n"

_ECOSYSTEM_IGNORES = {
    "pypi": ["__pycache__/", "*.py[cod]", ".venv/", "venv/", "*.egg-info/"],
    "npm": ["node_modules/", "dist/", "coverage/"],
    "cargo": ["target/"],
    "maven": ["target/"],
}
_SECRET_IGNORES = [".env", ".env.*", "!.env.example"]


@dataclass
class ProposedFile:
    path: str
    change_type: str  # create | modify
    explanation: str
    before: str | None
    after: str


def _diff_lines(lines: list[str]) -> str:
    """Mark lines without a line ending the way Git expects, or the patch will not apply."""
    output = []
    for line in lines:
        if line.endswith("\n"):
            output.append(line)
        else:
            output.append(line + "\n")
            output.append(_NO_NEWLINE)
    return "".join(output)


def unified_diff(path: str, before: str | None, after: str) -> str:
    old = (before or "").splitlines(keepends=True)
    new = after.splitlines(keepends=True)
    header = [f"diff --git a/{path} b/{path}\n"]
    if before is None:
        header.append("new file mode 100644\n")
    body = list(
        difflib.unified_diff(
            old,
            new,
            fromfile="/dev/null" if before is None else f"a/{path}",
            tofile=f"b/{path}",
        )
    )
    # The ---/+++ lines from difflib end with a newline regardless of the content's endings.
    return "".join(header) + _diff_lines(body)


def _gitignore_change(ctx: ScanContext, profile: dict[str, Any]) -> ProposedFile | None:
    config = profile.get("configuration", {})
    ecosystems = profile.get("dependencies", {}).get("ecosystems", [])
    wanted = [entry for eco in ecosystems for entry in _ECOSYSTEM_IGNORES.get(eco, [])]

    if not config.get("has_gitignore"):
        lines = ["# Proposed by GhostRepo. Review before adding.", *dict.fromkeys(wanted)]
        lines += _SECRET_IGNORES
        return ProposedFile(
            ".gitignore",
            "create",
            "Adds a .gitignore covering local secret files and the dependency and build "
            "folders of the ecosystems detected here.",
            None,
            "\n".join(lines) + "\n",
        )

    before = read_text(ctx, ".gitignore")
    if before is None or find_secrets(before):
        return None
    existing = {line.strip() for line in before.splitlines()}
    if ".env" in existing or ".env*" in existing or ".env.*" in existing:
        return None

    newline = "\r\n" if "\r\n" in before else "\n"
    prefix = before if before.endswith(("\n", "\r")) or not before else before + newline
    addition = newline.join(["# Added by a GhostRepo proposal", *_SECRET_IGNORES]) + newline
    return ProposedFile(
        ".gitignore",
        "modify",
        "Adds local secret files to .gitignore so they cannot be committed by accident.",
        before,
        prefix + addition,
    )


def _env_example(profile: dict[str, Any]) -> ProposedFile | None:
    config = profile.get("configuration", {})
    variables = config.get("env_variables", [])
    if config.get("env_templates") or not variables:
        return None
    lines = ["# Variables read by the code. Proposed by GhostRepo: fill in and describe each."]
    lines += [f"{name}=" for name in variables]
    return ProposedFile(
        ".env.example",
        "create",
        "Documents the environment variables the code reads. Names only, with no values.",
        None,
        "\n".join(lines) + "\n",
    )


def _readme(profile: dict[str, Any], readme_draft: str | None) -> ProposedFile | None:
    if profile.get("documentation", {}).get("readme_files") or not readme_draft:
        return None
    return ProposedFile(
        "README.md",
        "create",
        "Adds the README draft, since the repository has none. An existing README is never "
        "replaced.",
        None,
        readme_draft,
    )


def _contributing(profile: dict[str, Any]) -> ProposedFile | None:
    if profile.get("documentation", {}).get("contributing_files"):
        return None
    commands = profile.get("tests", {}).get("commands", [])
    lines = [
        "# Contributing",
        "",
        "> Starter guide proposed by GhostRepo. Replace the placeholders before relying on it.",
        "",
        "## Getting set up",
        "",
        "TODO: describe how to set up a development environment.",
        "",
        "## Tests",
        "",
    ]
    if commands:
        lines += ["```sh", *[item["command"] for item in commands], "```"]
    else:
        lines.append("TODO: describe how to run the tests.")
    lines += ["", "## Submitting changes", "", "TODO: describe the review process.", ""]
    return ProposedFile(
        "CONTRIBUTING.md",
        "create",
        "Adds a starter contributing guide with placeholders for what could not be verified.",
        None,
        "\n".join(lines),
    )


def propose(
    ctx: ScanContext, profile: dict[str, Any], readme_draft: str | None = None
) -> tuple[list[ProposedFile], list[str]]:
    """Return accepted proposals and the paths refused by validation."""
    candidates = [
        _gitignore_change(ctx, profile),
        _env_example(profile),
        _readme(profile, readme_draft),
        _contributing(profile),
    ]
    accepted: list[ProposedFile] = []
    refused: list[str] = []
    for item in filter(None, candidates):
        if check_proposal(ctx.root, item):
            accepted.append(item)
        else:
            refused.append(item.path)
    return accepted, refused


def check_proposal(root: Path, item: ProposedFile) -> bool:
    try:
        validate_patch_path(root, item.path)
    except PathValidationError:
        return False
    target = root / item.path
    if target.is_symlink():
        return False
    # A proposal to create must not replace something that appeared since the scan.
    return not (item.change_type == "create" and target.exists())


def render_patch(files: list[ProposedFile]) -> str:
    return "".join(unified_diff(item.path, item.before, item.after) for item in files)


def describe(files: list[ProposedFile]) -> list[dict[str, Any]]:
    described = []
    for item in files:
        diff = unified_diff(item.path, item.before, item.after).splitlines()
        described.append(
            {
                "path": item.path,
                "change_type": item.change_type,
                "explanation": item.explanation,
                "additions": sum(
                    1 for line in diff if line.startswith("+") and not line.startswith("+++")
                ),
                "deletions": sum(
                    1 for line in diff if line.startswith("-") and not line.startswith("---")
                ),
            }
        )
    return described
