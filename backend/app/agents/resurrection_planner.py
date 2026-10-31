"""Resurrection Planner: a prioritized recovery plan from verified findings.

Effort values are rough estimates, not measurements, and are labeled that way in the UI.
"""

from dataclasses import dataclass, field

from app.services.findings_engine import SEVERITY_ORDER, DraftFinding

_PRIORITY = {"critical": "high", "high": "high", "medium": "medium", "low": "low"}


@dataclass(frozen=True)
class Playbook:
    why: str
    effort: str
    verification: tuple[str, ...]


@dataclass
class DraftTask:
    title: str
    description: str
    why_it_matters: str
    solution: str
    files: list[str]
    effort_estimate: str
    verification_steps: list[str]
    priority: str
    evidence_references: list[str] = field(default_factory=list)


PLAYBOOKS: dict[str, Playbook] = {
    "config-secret-file-committed": Playbook(
        "Anyone who can read the repository or its history can use these credentials.",
        "1 to 4 hours",
        (
            "Confirm the old credentials no longer work.",
            "Confirm the file is gone from the current tree and from history.",
            "Confirm the file name is listed in .gitignore.",
        ),
    ),
    "config-secret-file-present": Playbook(
        "A local secret file is easy to commit or share by accident.",
        "Under 1 hour",
        ("Confirm the file name is listed in .gitignore.",),
    ),
    "config-secret-critical": Playbook(
        "Credentials in source are exposed to everyone who can read the code.",
        "1 to 4 hours",
        (
            "Confirm each flagged value was a false positive or has been rotated.",
            "Run a new GhostRepo investigation and confirm the finding is gone.",
        ),
    ),
    "config-secret-high": Playbook(
        "If these are real values, they are exposed to everyone who can read the code.",
        "Under 2 hours",
        (
            "Review each flagged line by hand.",
            "Run a new GhostRepo investigation and confirm the finding is gone.",
        ),
    ),
    "config-secret-low": Playbook(
        "These are usually fake, but a real credential in a fixture is just as exposed.",
        "Under 1 hour",
        ("Confirm each flagged value is fake, or rotate it.",),
    ),
    "docs-no-readme": Playbook(
        "Without a README, nobody can tell what the project does or how to start it.",
        "1 to 2 hours",
        ("Follow the README on a clean machine and fix any step that fails.",),
    ),
    "docs-readme-gaps": Playbook(
        "Missing setup steps make every new contributor rediscover them.",
        "Under 2 hours",
        ("Follow the documented steps on a clean machine.",),
    ),
    "docs-readme-unreadable": Playbook(
        "Tools and people cannot use documentation they cannot read.",
        "Under 1 hour",
        ("Open the README in a text editor and confirm it displays correctly.",),
    ),
    "docs-no-contributing": Playbook(
        "Contributors do not know the expected workflow.",
        "Under 1 hour",
        ("Have someone new follow the guide and report anything unclear.",),
    ),
    "config-no-license": Playbook(
        "Without a license, others have no clear right to use or change the code.",
        "Under 1 hour once the rights holder decides",
        ("Confirm a LICENSE file exists at the repository root.",),
    ),
    "config-no-env-template": Playbook(
        "The application reads settings that nothing documents, so setup becomes guesswork.",
        "Under 1 hour",
        ("Confirm each variable the code reads is in the template, with no real values.",),
    ),
    "config-no-gitignore": Playbook(
        "Build output and local secret files can be committed by accident.",
        "Under 30 minutes",
        ("Run git status after a build and confirm generated files are ignored.",),
    ),
    "config-no-ci": Playbook(
        "Nothing checks changes automatically, so regressions go unnoticed.",
        "2 to 4 hours",
        ("Open a test change and confirm the workflow runs.",),
    ),
    "tests-none": Playbook(
        "Without tests, any revival work risks breaking behavior with no warning.",
        "2 to 8 hours for a first smoke test",
        ("Run the new test and confirm it fails when the tested behavior is broken.",),
    ),
    "tests-no-runner": Playbook(
        "Tests that nobody knows how to run do not protect anything.",
        "Under 2 hours",
        ("Run the documented test command in an isolated environment.",),
    ),
    "tests-placeholder": Playbook(
        "The test script exits with an error instead of testing anything.",
        "1 to 2 hours",
        ("Run the test script in an isolated environment and confirm it runs real tests.",),
    ),
    "deps-no-manifest": Playbook(
        "Without a manifest, the required packages must be guessed from the code.",
        "1 to 4 hours",
        ("Install from the manifest in a fresh isolated environment.",),
    ),
    "deps-malformed": Playbook(
        "Package tools cannot install from a manifest they cannot parse.",
        "Under 1 hour",
        ("Run the package manager's validation or install in an isolated environment.",),
    ),
    "deps-unreadable": Playbook(
        "A manifest that cannot be read cannot be checked or installed.",
        "Under 1 hour",
        ("Run a new GhostRepo investigation and confirm the manifest is parsed.",),
    ),
    "deps-invalid-entries": Playbook(
        "Invalid entries can stop an install or be silently skipped.",
        "Under 1 hour",
        ("Install from the manifest in a fresh isolated environment.",),
    ),
    "deps-unbounded": Playbook(
        "Each install may pull different versions, which makes failures hard to reproduce.",
        "1 to 2 hours",
        ("Install in a fresh isolated environment and run the project.",),
    ),
    "deps-no-lockfile": Playbook(
        "Without a lockfile, two installs of the same commit can differ.",
        "Under 1 hour",
        ("Install from the lockfile in a fresh isolated environment.",),
    ),
    "git-unsafe-metadata": Playbook(
        "A .git pointer can lead tools to run against data outside the repository.",
        "Under 1 hour",
        ("Confirm .git is a normal directory, then investigate again.",),
    ),
    "git-unreadable": Playbook(
        "Without readable history, nobody can see how the project evolved.",
        "Under 2 hours",
        ("Run git log by hand in a safe environment.",),
    ),
    "repo-scan-limited": Playbook(
        "Results may miss files beyond the configured limits.",
        "Under 30 minutes",
        ("Investigate again and confirm the limit finding is gone.",),
    ),
}
_DEFAULT = Playbook(
    "This setting behaves very differently in production and can weaken security.",
    "Under 1 hour",
    ("Confirm the production configuration does not use this value.",),
)


def build_plan(findings: list[DraftFinding]) -> list[DraftTask]:
    """One task per actionable finding, most severe first. Informational findings add none."""
    actionable = [finding for finding in findings if finding.severity != "info"]
    actionable.sort(key=lambda finding: SEVERITY_ORDER[finding.severity])
    tasks = []
    for finding in actionable:
        playbook = PLAYBOOKS.get(finding.rule_id, _DEFAULT)
        tasks.append(
            DraftTask(
                title=finding.title,
                description=finding.description,
                why_it_matters=playbook.why,
                solution=finding.recommendation,
                files=finding.files[:20],
                effort_estimate=playbook.effort,
                verification_steps=list(playbook.verification),
                priority=_PRIORITY[finding.severity],
                evidence_references=finding.evidence_references,
            )
        )
    return tasks
