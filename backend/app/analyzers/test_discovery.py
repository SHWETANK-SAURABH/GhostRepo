"""Test Investigator: finds tests and test commands. It never runs them."""

import json
import re

from app.analyzers.base import AnalyzerResult, Inventory, RawEvidence, ScanContext, read_text

METHOD = "test-investigator:file-discovery"
CATEGORY = "testing"

_TEST_DIR_NAMES = {"test", "tests", "__tests__", "spec", "specs"}
_TEST_FILE = re.compile(
    r"^(test_.+\.py|.+_test\.py|.+\.(test|spec)\.(js|jsx|ts|tsx|mjs|cjs)|.+_test\.go"
    r"|.+(Test|Tests|IT)\.java|.+_test\.rs)$"
)
_CONFIG_FRAMEWORKS = {
    "pytest.ini": "pytest",
    "conftest.py": "pytest",
    "tox.ini": "tox",
    "jest.config.js": "Jest",
    "jest.config.ts": "Jest",
    "jest.config.mjs": "Jest",
    "vitest.config.js": "Vitest",
    "vitest.config.ts": "Vitest",
    "vitest.config.mts": "Vitest",
    ".mocharc.json": "Mocha",
    ".mocharc.js": "Mocha",
    ".mocharc.yml": "Mocha",
    "playwright.config.ts": "Playwright",
    "cypress.config.js": "Cypress",
    "cypress.config.ts": "Cypress",
}
_DEPENDENCY_FRAMEWORKS = {
    "pytest": "pytest",
    "nose": "nose",
    "jest": "Jest",
    "vitest": "Vitest",
    "mocha": "Mocha",
    "ava": "AVA",
    "junit:junit": "JUnit",
    "org.junit.jupiter:junit-jupiter": "JUnit",
    "org.junit.jupiter:junit-jupiter-api": "JUnit",
}
_NPM_PLACEHOLDER = "no test specified"


def _declared_commands(ctx: ScanContext, inventory: Inventory) -> tuple[list[dict], bool]:
    commands: list[dict] = []
    placeholder = False
    for item in inventory.at_root("package.json"):
        text = read_text(ctx, item.path)
        if not text:
            continue
        try:
            data = json.loads(text)
        except (ValueError, RecursionError):
            continue
        scripts = data.get("scripts") if isinstance(data, dict) else None
        script = scripts.get("test") if isinstance(scripts, dict) else None
        if not isinstance(script, str):
            continue
        if _NPM_PLACEHOLDER in script:
            placeholder = True
        else:
            commands.append({"command": "npm test", "source": "declared", "file": item.path})
    for item in inventory.at_root("makefile"):
        text = read_text(ctx, item.path)
        if text and re.search(r"^test\s*:", text, re.M):
            commands.append({"command": "make test", "source": "declared", "file": item.path})
    if inventory.at_root("tox.ini"):
        commands.append({"command": "tox", "source": "declared", "file": "tox.ini"})
    return commands, placeholder


def _inferred_commands(
    inventory: Inventory, test_files: list[str], frameworks: set[str]
) -> list[dict]:
    """Conventional commands for what was found. Labeled inferred; never run."""
    commands = []
    if "pytest" in frameworks:
        commands.append({"command": "pytest", "source": "inferred", "file": None})
    if any(path.endswith("_test.go") for path in test_files):
        commands.append({"command": "go test ./...", "source": "inferred", "file": None})
    if inventory.at_root("cargo.toml") and (any(path.endswith(".rs") for path in test_files)):
        commands.append({"command": "cargo test", "source": "inferred", "file": None})
    if inventory.at_root("pom.xml") and test_files:
        commands.append({"command": "mvn test", "source": "inferred", "file": None})
    return commands


def analyze(
    ctx: ScanContext, inventory: Inventory, dependency_names: set[str] | None = None,
    pyproject_pytest: bool = False,
) -> AnalyzerResult:  # fmt: skip
    dependency_names = {name.lower() for name in dependency_names or set()}

    test_dirs = [
        path for path in inventory.directories if path.rsplit("/", 1)[-1].lower() in _TEST_DIR_NAMES
    ]
    test_files = []
    for item in inventory.files:
        parts = item.path.lower().split("/")
        in_test_dir = any(part in _TEST_DIR_NAMES for part in parts[:-1])
        is_source = item.suffix in {
            ".py",
            ".js",
            ".jsx",
            ".ts",
            ".tsx",
            ".go",
            ".java",
            ".rs",
            ".mjs",
        }
        java_test_tree = "src/test/java" in item.path.lower()
        if _TEST_FILE.match(item.name) or (is_source and (in_test_dir or java_test_tree)):
            test_files.append(item.path)

    config_files = [
        item.path for item in inventory.files if item.name.lower() in _CONFIG_FRAMEWORKS
    ]
    frameworks = {_CONFIG_FRAMEWORKS[path.rsplit("/", 1)[-1].lower()] for path in config_files}
    frameworks |= {
        label for name, label in _DEPENDENCY_FRAMEWORKS.items() if name in dependency_names
    }
    if pyproject_pytest:
        frameworks.add("pytest")
    if any(path.endswith("_test.go") for path in test_files):
        frameworks.add("go test")
    if (
        test_files
        and inventory.at_root("cargo.toml")
        and any(p.endswith(".rs") for p in test_files)
    ):
        frameworks.add("cargo test")

    declared, placeholder = _declared_commands(ctx, inventory)
    commands = declared + _inferred_commands(inventory, test_files, frameworks)

    source_files = sum(
        1
        for item in inventory.files
        if item.suffix in {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".rs"}
    ) - len(test_files)

    facts = {
        "executed": False,
        "test_directories": test_dirs[:30],
        "test_file_count": len(test_files),
        "test_files": test_files[:60],
        "source_file_count": max(0, source_files),
        "config_files": config_files[:20],
        "frameworks": sorted(frameworks),
        "commands": commands,
        "placeholder_test_script": placeholder,
    }

    evidence: list[RawEvidence] = []
    if test_files:
        evidence.append(
            RawEvidence(
                "testing.tests_found",
                CATEGORY,
                f"{len(test_files)} test file(s) found. They were discovered, not executed, "
                "so whether they pass is unknown.",
                METHOD,
                data={
                    "count": len(test_files),
                    "directories": test_dirs[:10],
                    "sample": test_files[:10],
                    "executed": False,
                },
            )
        )
    elif inventory.files:
        evidence.append(
            RawEvidence(
                "testing.no_tests",
                CATEGORY,
                "No test files or test directories were found by naming convention.",
                METHOD,
                data={"source_file_count": max(0, source_files)},
            )
        )
    if frameworks:
        evidence.append(
            RawEvidence(
                "testing.frameworks",
                CATEGORY,
                f"Test tooling indicators: {', '.join(sorted(frameworks))}.",
                METHOD,
                data={"frameworks": sorted(frameworks), "config_files": config_files[:10]},
            )
        )
    if commands:
        evidence.append(
            RawEvidence(
                "testing.commands",
                CATEGORY,
                "Test commands: "
                + ", ".join(f"{c['command']} ({c['source']})" for c in commands)
                + ".",
                METHOD,
                data={"commands": commands, "executed": False},
            )
        )
    if placeholder:
        evidence.append(
            RawEvidence(
                "testing.placeholder_script",
                CATEGORY,
                "package.json has only the default placeholder test script.",
                METHOD,
                source_file="package.json",
            )
        )
    if test_files and not frameworks and not commands:
        evidence.append(
            RawEvidence(
                "testing.no_runner",
                CATEGORY,
                "Test files exist, but no test runner or test command was identified.",
                METHOD,
            )
        )
    return AnalyzerResult("test_discovery", facts, evidence)
