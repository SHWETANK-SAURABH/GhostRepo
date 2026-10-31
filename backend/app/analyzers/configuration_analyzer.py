"""Configuration Inspector: templates, deployment files, risky settings and exposed secrets.

Secret values are never kept. A hit records only the rule, the file and the line number.
"""

import re

from app.analyzers.base import AnalyzerResult, Inventory, RawEvidence, ScanContext, read_text
from app.analyzers.git_historian import tracked_paths
from app.security.secret_redaction import find_secrets, is_secret_file

METHOD = "configuration-inspector:pattern-scan"
CATEGORY = "configuration"
MAX_SCANNED_FILES = 3000
MAX_REPORTED_HITS = 40

TEXT_SUFFIXES = {
    ".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".java", ".go", ".rs", ".rb", ".php",
    ".sh", ".yml", ".yaml", ".json", ".toml", ".ini", ".cfg", ".conf", ".xml", ".properties",
    ".tf", ".txt", ".md",
}  # fmt: skip
CODE_SUFFIXES = {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".java", ".go", ".rs"}
ENV_TEMPLATE_NAMES = {
    ".env.example", ".env.sample", ".env.template", ".env.dist", "env.example", "example.env",
}  # fmt: skip
CI_MARKERS = (".github/workflows/", ".gitlab-ci.yml", ".circleci/", "azure-pipelines.yml",
              ".travis.yml", "jenkinsfile")  # fmt: skip
DEPLOYMENT_NAMES = {
    "dockerfile": "Docker", "docker-compose.yml": "Docker Compose",
    "docker-compose.yaml": "Docker Compose", "compose.yml": "Docker Compose",
    "compose.yaml": "Docker Compose", "procfile": "Procfile", "vercel.json": "Vercel",
    "netlify.toml": "Netlify", "fly.toml": "Fly.io", "render.yaml": "Render",
    "serverless.yml": "Serverless Framework",
}  # fmt: skip
LICENSE_NAMES = {"license", "license.md", "license.txt", "licence", "licence.md", "licence.txt",
                 "copying", "copying.md", "copying.txt"}  # fmt: skip
LICENSE_MARKERS = [
    ("MIT", "MIT License"),
    ("Apache-2.0", "Apache License"),
    ("GPL-3.0", "GNU GENERAL PUBLIC LICENSE\n                       Version 3"),
    ("GPL-2.0", "GNU GENERAL PUBLIC LICENSE\n                       Version 2"),
    ("AGPL-3.0", "GNU AFFERO GENERAL PUBLIC LICENSE"),
    ("LGPL", "GNU LESSER GENERAL PUBLIC LICENSE"),
    ("BSD", "Redistribution and use in source and binary forms"),
    ("MPL-2.0", "Mozilla Public License"),
    ("Unlicense", "This is free and unencumbered software"),
]

RISKY_SETTINGS = [
    ("debug-enabled", "Debug mode appears to be enabled",
     re.compile(r"^\s*(?:app\.)?DEBUG\s*[:=]\s*(?:True|true|1)\b", re.M),
     {".py", ".yml", ".yaml"}),
    ("wildcard-allowed-hosts", "ALLOWED_HOSTS accepts every host",
     re.compile(r"ALLOWED_HOSTS\s*=\s*\[\s*['\"]\*['\"]"), {".py"}),
    ("wildcard-cors", "CORS appears to allow every origin",
     re.compile(r"(allow_origins\s*=\s*\[\s*['\"]\*['\"]|origin\s*:\s*['\"]\*['\"]"
                r"|Access-Control-Allow-Origin['\"]?\s*[,:]\s*['\"]\*)"), CODE_SUFFIXES),
    ("tls-verification-disabled", "TLS certificate verification appears to be disabled",
     re.compile(r"(verify\s*=\s*False|NODE_TLS_REJECT_UNAUTHORIZED\s*[=:]\s*['\"]?0"
                r"|rejectUnauthorized\s*:\s*false|InsecureSkipVerify\s*:\s*true)"), CODE_SUFFIXES),
    ("privileged-container", "A container is configured with privileged mode",
     re.compile(r"^\s*privileged\s*:\s*true", re.M), {".yml", ".yaml"}),
]  # fmt: skip

_NON_PRODUCTION_DIRS = {
    "test",
    "tests",
    "__tests__",
    "spec",
    "specs",
    "testdata",
    "fixtures",
    "examples",
    "example",
    "samples",
    "docs",
}
_TEST_FILE_NAME = re.compile(r"^(test_.+|.+_test\.\w+|.+\.(test|spec)\.\w+)$")

ENV_REFERENCES = [
    re.compile(r"os\.environ(?:\.get)?[\[(]\s*['\"]([A-Z][A-Z0-9_]{1,63})['\"]"),
    re.compile(r"os\.getenv\(\s*['\"]([A-Z][A-Z0-9_]{1,63})['\"]"),
    re.compile(r"process\.env\.([A-Z][A-Z0-9_]{1,63})\b"),
    re.compile(r"process\.env\[['\"]([A-Z][A-Z0-9_]{1,63})['\"]\]"),
    re.compile(r"os\.Getenv\(\"([A-Z][A-Z0-9_]{1,63})\"\)"),
    re.compile(r"env::var\(\"([A-Z][A-Z0-9_]{1,63})\"\)"),
    re.compile(r"System\.getenv\(\"([A-Z][A-Z0-9_]{1,63})\"\)"),
]


def is_test_or_example_path(path: str) -> bool:
    """Fixtures often hold fake credentials and deliberately risky settings."""
    parts = path.lower().split("/")
    return bool(_NON_PRODUCTION_DIRS.intersection(parts[:-1])) or bool(
        _TEST_FILE_NAME.match(parts[-1])
    )


def _detect_license(ctx: ScanContext, path: str) -> str | None:
    text = read_text(ctx, path)
    if not text:
        return None
    for name, marker in LICENSE_MARKERS:
        if marker.lower() in text.lower():
            return name
    return None


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _is_scannable(name: str, suffix: str) -> bool:
    return suffix in TEXT_SUFFIXES or name in {"dockerfile", "makefile"}


def analyze(ctx: ScanContext, inventory: Inventory) -> AnalyzerResult:
    evidence: list[RawEvidence] = []
    names = {item.name.lower() for item in inventory.files}

    env_templates = [i.path for i in inventory.files if i.name.lower() in ENV_TEMPLATE_NAMES]
    deployment = sorted(
        {
            DEPLOYMENT_NAMES[i.name.lower()]
            for i in inventory.files
            if i.name.lower() in DEPLOYMENT_NAMES
        }
    )
    ci_files = [
        item.path
        for item in inventory.files
        if any(marker in item.path.lower() for marker in CI_MARKERS)
    ]
    has_gitignore = bool(inventory.at_root(".gitignore"))
    license_files = [
        i.path for i in inventory.files if i.depth == 0 and i.name.lower() in LICENSE_NAMES
    ]
    license_type = _detect_license(ctx, license_files[0]) if license_files else None

    secret_files = [item.path for item in inventory.files if is_secret_file(item.path)]
    tracked = tracked_paths(ctx, secret_files) if secret_files else None

    secret_hits: list[dict] = []
    risky_hits: list[dict] = []
    env_references: set[str] = set()
    files_scanned = 0
    for item in inventory.files:
        name = item.name.lower()
        if files_scanned >= MAX_SCANNED_FILES:
            break
        if is_secret_file(item.path) or not _is_scannable(name, item.suffix):
            continue
        ctx.check_deadline()
        text = read_text(ctx, item.path)
        if text is None:
            continue
        files_scanned += 1
        non_production = is_test_or_example_path(item.path)
        if len(secret_hits) < MAX_REPORTED_HITS:
            secret_hits += [
                {
                    "rule": hit.rule,
                    "file": item.path,
                    "line": hit.line,
                    "in_test_or_example": non_production,
                }
                for hit in find_secrets(text)
            ]
        for rule, _, pattern, suffixes in RISKY_SETTINGS:
            if non_production:
                break
            if item.suffix in suffixes and len(risky_hits) < MAX_REPORTED_HITS:
                match = pattern.search(text)
                if match:
                    risky_hits.append(
                        {"rule": rule, "file": item.path, "line": _line_of(text, match.start())}
                    )
        if item.suffix in CODE_SUFFIXES:
            for pattern in ENV_REFERENCES:
                env_references.update(pattern.findall(text))

    secret_hits = secret_hits[:MAX_REPORTED_HITS]

    for path in secret_files:
        is_tracked = tracked.get(path) if tracked else None
        state = {True: "committed to Git", False: "present but not committed"}.get(
            is_tracked, "present (Git status unknown)"
        )
        evidence.append(
            RawEvidence(
                "configuration.secret_file",
                CATEGORY,
                f"{path} looks like a secret file and is {state}. Its contents were not read.",
                METHOD,
                source_file=path,
                data={"tracked": is_tracked},
            )
        )
    for hit in secret_hits:
        evidence.append(
            RawEvidence(
                "configuration.secret_pattern",
                CATEGORY,
                f"A value matching the {hit['rule']} rule is at {hit['file']} line {hit['line']}. "
                "The value is not recorded.",
                "configuration-inspector:secret-rules",
                source_file=hit["file"],
                data=hit,
            )
        )
    descriptions = {rule: text for rule, text, _, _ in RISKY_SETTINGS}
    for hit in risky_hits:
        evidence.append(
            RawEvidence(
                "configuration.risky_setting",
                CATEGORY,
                f"{descriptions[hit['rule']]} at {hit['file']} line {hit['line']}.",
                METHOD,
                source_file=hit["file"],
                data=hit,
            )
        )

    if license_files:
        label = license_type or "an unrecognized license"
        evidence.append(
            RawEvidence(
                "configuration.license",
                CATEGORY,
                f"{license_files[0]} appears to contain {label}.",
                METHOD,
                source_file=license_files[0],
                data={"license": license_type},
            )
        )
    elif inventory.files:
        evidence.append(
            RawEvidence(
                "configuration.license_missing",
                CATEGORY,
                "No license file was found at the repository root.",
                METHOD,
            )
        )

    sorted_env = sorted(env_references)
    if env_templates:
        evidence.append(
            RawEvidence(
                "configuration.env_template",
                CATEGORY,
                f"Environment template found: {env_templates[0]}.",
                METHOD,
                source_file=env_templates[0],
            )
        )
    elif sorted_env:
        evidence.append(
            RawEvidence(
                "configuration.env_template_missing",
                CATEGORY,
                f"Code reads {len(sorted_env)} environment variable name(s), "
                "but no environment template was found.",
                METHOD,
                data={"variables": sorted_env[:40]},
            )
        )

    if inventory.files and not has_gitignore:
        evidence.append(
            RawEvidence(
                "configuration.gitignore_missing",
                CATEGORY,
                "No .gitignore file was found at the repository root.",
                METHOD,
            )
        )
    if deployment:
        evidence.append(
            RawEvidence(
                "configuration.deployment",
                CATEGORY,
                f"Deployment configuration found for: {', '.join(deployment)}.",
                METHOD,
                data={"deployment": deployment},
            )
        )
    if ci_files:
        evidence.append(
            RawEvidence(
                "configuration.ci",
                CATEGORY,
                f"Continuous integration configuration found: {ci_files[0]}.",
                METHOD,
                source_file=ci_files[0],
                data={"files": ci_files[:10]},
            )
        )
    elif inventory.files:
        evidence.append(
            RawEvidence(
                "configuration.ci_missing",
                CATEGORY,
                "No continuous integration configuration was found.",
                METHOD,
            )
        )

    facts = {
        "env_templates": env_templates,
        "env_variables": sorted_env[:100],
        "deployment": deployment,
        "ci_files": ci_files[:10],
        "has_gitignore": has_gitignore,
        "has_editorconfig": ".editorconfig" in names,
        "license_files": license_files,
        "license": license_type,
        "secret_files": secret_files[:40],
        "secret_hit_count": len(secret_hits),
        "risky_setting_count": len(risky_hits),
        "files_scanned": files_scanned,
    }
    return AnalyzerResult("configuration_analyzer", facts, evidence)
