"""Deterministic rules that turn evidence into verified findings. No model is involved."""

from dataclasses import dataclass, field
from typing import Any

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
_PENALTY = {"critical": 25, "high": 12, "medium": 6, "low": 2, "info": 0}

HEALTH_NOTE = (
    "An indicator from verified findings: 100 minus a penalty per finding by severity. It "
    "measures how ready a repository is to pick up, not the quality of its code."
)


@dataclass
class DraftFinding:
    rule_id: str
    title: str
    description: str
    severity: str
    category: str
    confidence: float
    recommendation: str
    detection_method: str
    evidence_references: list[str] = field(default_factory=list)
    source_file: str | None = None
    files: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Rule:
    rule_id: str
    title: str
    severity: str
    category: str
    confidence: float
    recommendation: str


RULES: dict[str, Rule] = {
    "documentation.readme_missing": Rule(
        "docs-no-readme", "No README", "high", "documentation", 1.0,
        "Add a README that explains the project and how to run it. GhostRepo can draft one.",
    ),
    "documentation.readme_unreadable": Rule(
        "docs-readme-unreadable", "README could not be read", "medium", "documentation", 0.9,
        "Check the README's encoding and size.",
    ),
    "documentation.readme_gaps": Rule(
        "docs-readme-gaps", "README is missing setup information", "medium", "documentation", 0.8,
        "Add sections explaining how to install and use the project.",
    ),
    "documentation.contributing_missing": Rule(
        "docs-no-contributing", "No contributing guide", "low", "documentation", 1.0,
        "Add a CONTRIBUTING file describing how to set up and submit changes.",
    ),
    "configuration.license_missing": Rule(
        "config-no-license", "No license file", "high", "configuration", 0.95,
        "Ask the rights holder to add a license. Without one, reuse rights are unclear.",
    ),
    "configuration.env_template_missing": Rule(
        "config-no-env-template", "Environment variables are undocumented", "medium",
        "configuration", 0.85,
        "Add a .env.example listing each variable the code reads, with no real values.",
    ),
    "configuration.gitignore_missing": Rule(
        "config-no-gitignore", "No .gitignore", "medium", "configuration", 1.0,
        "Add a .gitignore covering build output, dependencies and local secret files.",
    ),
    "configuration.ci_missing": Rule(
        "config-no-ci", "No continuous integration", "low", "maintenance", 0.9,
        "Add a CI workflow that runs the project's tests on each change.",
    ),
    "static_analysis.syntax_errors": Rule(
        "static-syntax-errors", "Python files do not parse", "medium", "maintenance", 0.9,
        "Check which Python version these files target. Older code may need porting.",
    ),
    "static_analysis.issues": Rule(
        "static-issues", "Static analysis reported issues", "low", "maintenance", 0.9,
        "Run ruff check with the rules E9 and F, then review what it reports.",
    ),
    "static_analysis.incomplete": Rule(
        "static-incomplete", "Static analysis did not finish", "info", "maintenance", 1.0,
        "Run ruff check by hand if this repository's Python code matters to you.",
    ),
    "testing.no_tests": Rule(
        "tests-none", "No tests found", "high", "testing", 0.85,
        "Add a small smoke test first, so later changes have a safety net.",
    ),
    "testing.no_runner": Rule(
        "tests-no-runner", "Test files have no identified runner", "medium", "testing", 0.7,
        "Document the test command and declare the test framework as a dependency.",
    ),
    "testing.placeholder_script": Rule(
        "tests-placeholder", "Test script is only a placeholder", "medium", "testing", 1.0,
        "Replace the default package.json test script with a real test command.",
    ),
    "dependency.no_manifest": Rule(
        "deps-no-manifest", "No supported dependency manifest", "medium", "dependency", 0.8,
        "Declare dependencies in a manifest so the project can be installed reproducibly.",
    ),
    "dependency.manifest_malformed": Rule(
        "deps-malformed", "Dependency manifest is malformed", "high", "dependency", 1.0,
        "Fix the manifest syntax. Package tools cannot install from a file they cannot parse.",
    ),
    "dependency.manifest_unreadable": Rule(
        "deps-unreadable", "Dependency manifest could not be read", "medium", "dependency", 0.9,
        "Check the manifest's encoding and size.",
    ),
    "dependency.invalid_entries": Rule(
        "deps-invalid-entries", "Manifest has entries that do not parse", "medium", "dependency",
        0.8, "Correct or remove the invalid entries.",
    ),
    "dependency.unbounded": Rule(
        "deps-unbounded", "Dependencies have no version constraint", "medium", "dependency", 1.0,
        "Add version constraints so installs stay reproducible.",
    ),
    "dependency.no_lockfile": Rule(
        "deps-no-lockfile", "No dependency lockfile", "low", "dependency", 0.9,
        "Generate and commit a lockfile with the project's package manager.",
    ),
    "dependency.freshness_unverified": Rule(
        "deps-freshness-unverified", "Dependency freshness was not checked", "info", "dependency",
        1.0, "Run your ecosystem's audit and outdated commands in an isolated environment.",
    ),
    "git.absent": Rule(
        "git-absent", "No Git history available", "info", "maintenance", 1.0,
        "If this is a copy, investigate a full clone to include history.",
    ),
    "git.unsafe": Rule(
        "git-unsafe-metadata", "Git metadata was not followed", "medium", "maintenance", 1.0,
        "Inspect the .git entry by hand. It is a symlink or pointer that could lead elsewhere.",
    ),
    "git.unreadable": Rule(
        "git-unreadable", "Git metadata could not be read", "medium", "maintenance", 0.9,
        "Check whether the repository is corrupt or owned by another user.",
    ),
    "git.no_commits": Rule(
        "git-no-commits", "Repository has no commits", "info", "maintenance", 1.0,
        "Make an initial commit to start tracking history.",
    ),
    "git.no_recent_commits": Rule(
        "git-quiet", "No commits in over a year", "info", "maintenance", 1.0,
        "Check the project's issues and releases before deciding whether it is still maintained.",
    ),
    "git.shallow": Rule(
        "git-shallow", "History is incomplete", "info", "maintenance", 1.0,
        "Fetch full history for complete figures.",
    ),
    "repository.empty": Rule(
        "repo-empty", "Repository has no scannable files", "info", "maintenance", 1.0,
        "Confirm the right directory was selected.",
    ),
    "repository.scan_limited": Rule(
        "repo-scan-limited", "Scan stopped at a limit", "low", "maintenance", 1.0,
        "Raise the scan limits or exclude generated folders, then investigate again.",
    ),
    "repository.skipped_entries": Rule(
        "repo-skipped-entries", "Some files were skipped for safety", "info", "maintenance", 1.0,
        "Review symlinks and unusual file names by hand if they matter to this project.",
    ),
}  # fmt: skip


def _ref(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("structured_data") or {}


def _secret_file_finding(item: dict[str, Any]) -> DraftFinding:
    tracked = _ref(item).get("tracked")
    path = item["source_file"]
    if tracked is True:
        return DraftFinding(
            "config-secret-file-committed",
            f"Secret file is committed: {path}",
            f"{path} is tracked by Git, so anyone with the repository can read it. "
            "GhostRepo did not read its contents.",
            "critical",
            "configuration",
            0.9,
            "Treat its contents as exposed: rotate the credentials, remove the file from Git "
            "and purge it from history.",
            item["detection_method"],
            [item["key"]],
            path,
            [path],
        )
    severity = "low" if tracked is False else "medium"
    state = "not committed to Git" if tracked is False else "of unknown Git status"
    return DraftFinding(
        "config-secret-file-present",
        f"Secret file in working copy: {path}",
        f"{path} looks like a secret file and is {state}. GhostRepo did not read its contents.",
        severity,
        "configuration",
        0.8,
        "Keep this file out of version control and out of anything you share.",
        item["detection_method"],
        [item["key"]],
        path,
        [path],
    )


def _secret_pattern_findings(items: list[dict[str, Any]]) -> list[DraftFinding]:
    fixtures = [i for i in items if _ref(i).get("in_test_or_example")]
    production = [i for i in items if not _ref(i).get("in_test_or_example")]
    specific = [i for i in production if _ref(i).get("rule") != "hardcoded-credential"]
    generic = [i for i in production if _ref(i).get("rule") == "hardcoded-credential"]
    findings = []
    for group, severity, confidence, title in (
        (specific, "critical", 0.85, "Credentials appear to be in the source"),
        (generic, "high", 0.6, "Possible hardcoded credentials"),
        (fixtures, "low", 0.4, "Possible credentials in test or example files"),
    ):
        if not group:
            continue
        files = sorted({i["source_file"] for i in group if i["source_file"]})
        findings.append(
            DraftFinding(
                f"config-secret-{severity}",
                title,
                f"{len(group)} value(s) in {len(files)} file(s) match secret rules. "
                "Values were not recorded. Rule matches can be false positives; review each.",
                severity,
                "configuration",
                confidence,
                "Review each location. Rotate anything real and move it to environment variables.",
                group[0]["detection_method"],
                [i["key"] for i in group],
                files[0] if len(files) == 1 else None,
                files,
            )
        )
    return findings


def _risky_findings(items: list[dict[str, Any]]) -> list[DraftFinding]:
    by_rule: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        by_rule.setdefault(_ref(item).get("rule", "risky"), []).append(item)
    findings = []
    for rule, group in by_rule.items():
        files = sorted({i["source_file"] for i in group if i["source_file"]})
        findings.append(
            DraftFinding(
                f"config-{rule}",
                group[0]["description"].split(" at ")[0],
                "; ".join(i["description"] for i in group[:5]),
                "medium",
                "configuration",
                0.7,
                "Confirm this is not used in production, or make it an explicit setting.",
                group[0]["detection_method"],
                [i["key"] for i in group],
                files[0] if len(files) == 1 else None,
                files,
            )
        )
    return findings


def build_findings(evidence: list[dict[str, Any]]) -> list[DraftFinding]:
    findings: list[DraftFinding] = []
    secret_patterns = []
    risky = []
    for item in evidence:
        kind = item["kind"]
        if kind == "configuration.secret_file":
            findings.append(_secret_file_finding(item))
        elif kind == "configuration.secret_pattern":
            secret_patterns.append(item)
        elif kind == "configuration.risky_setting":
            risky.append(item)
        elif kind in RULES:
            rule = RULES[kind]
            source = item.get("source_file")
            findings.append(
                DraftFinding(
                    rule.rule_id,
                    rule.title,
                    item["description"],
                    rule.severity,
                    rule.category,
                    rule.confidence,
                    rule.recommendation,
                    item["detection_method"],
                    [item["key"]],
                    source,
                    [source] if source else [],
                )
            )
    findings += _secret_pattern_findings(secret_patterns)
    findings += _risky_findings(risky)
    findings.sort(key=lambda finding: SEVERITY_ORDER[finding.severity])
    return findings


def health_score(findings: list[DraftFinding], evidence: list[dict[str, Any]]) -> int | None:
    """None when there is nothing to judge."""
    if not evidence or any(item["kind"] == "repository.empty" for item in evidence):
        return None
    return max(0, 100 - sum(_PENALTY[finding.severity] for finding in findings))
