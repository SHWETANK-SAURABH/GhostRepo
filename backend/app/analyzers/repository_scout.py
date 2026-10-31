"""Repository Scout: languages, frameworks, build tools, entry points and layout."""

from collections import Counter

from app.analyzers.base import AnalyzerResult, FileEntry, Inventory, RawEvidence, ScanContext

METHOD = "repository-scout:file-inventory"
CATEGORY = "repository"

# Ecosystems with manifest and test support. Other languages are counted, nothing more.
SUPPORTED_LANGUAGES = {"Python", "JavaScript", "TypeScript", "Java", "Go", "Rust"}

LANGUAGES = {
    ".py": "Python",
    ".pyi": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".hpp": "C++",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".kt": "Kotlin",
    ".swift": "Swift",
    ".scala": "Scala",
    ".sh": "Shell",
    ".bash": "Shell",
    ".ps1": "PowerShell",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "CSS",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".sql": "SQL",
}
MARKUP_LANGUAGES = {"HTML", "CSS", "SQL", "Shell", "PowerShell"}

BUILD_TOOLS = {
    "makefile": "Make",
    "package-lock.json": "npm",
    "yarn.lock": "Yarn",
    "pnpm-lock.yaml": "pnpm",
    "poetry.lock": "Poetry",
    "uv.lock": "uv",
    "pipfile": "Pipenv",
    "setup.py": "setuptools",
    "pyproject.toml": "PEP 517 build",
    "pom.xml": "Maven",
    "build.gradle": "Gradle",
    "build.gradle.kts": "Gradle",
    "cargo.toml": "Cargo",
    "go.mod": "Go modules",
    "dockerfile": "Docker",
    "tsconfig.json": "TypeScript compiler",
    "webpack.config.js": "webpack",
}

FRAMEWORK_FILES = {
    "manage.py": "Django",
    "next.config.js": "Next.js",
    "next.config.mjs": "Next.js",
    "next.config.ts": "Next.js",
    "nuxt.config.js": "Nuxt",
    "nuxt.config.ts": "Nuxt",
    "angular.json": "Angular",
    "vite.config.js": "Vite",
    "vite.config.ts": "Vite",
    "svelte.config.js": "SvelteKit",
}

ENTRY_POINTS = {
    "main.py",
    "app.py",
    "__main__.py",
    "manage.py",
    "wsgi.py",
    "asgi.py",
    "index.js",
    "index.ts",
    "server.js",
    "server.ts",
    "app.js",
    "main.js",
    "main.ts",
    "main.go",
    "main.rs",
}

CONFIG_NAMES = {
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    "tox.ini",
    "setup.cfg",
    ".editorconfig",
    ".gitignore",
    ".dockerignore",
    "tsconfig.json",
    "makefile",
}
DOC_NAMES = ("readme", "contributing", "changelog", "license", "licence", "code_of_conduct")


def _languages(inventory: Inventory) -> list[dict]:
    totals: Counter[str] = Counter()
    counts: Counter[str] = Counter()
    for item in inventory.files:
        language = LANGUAGES.get(item.suffix)
        if language:
            totals[language] += item.size
            counts[language] += 1
    total = sum(totals.values()) or 1
    return [
        {
            "name": name,
            "files": counts[name],
            "bytes": size,
            "share": round(size / total * 100, 1),
            "deep_support": name in SUPPORTED_LANGUAGES,
        }
        for name, size in totals.most_common()
    ]


def _primary(languages: list[dict]) -> str | None:
    """Prefer programming languages over HTML, CSS and SQL when choosing the primary one."""
    programming = [item for item in languages if item["name"] not in MARKUP_LANGUAGES]
    return (programming or languages or [{"name": None}])[0]["name"]


def _entry_points(files: list[FileEntry]) -> list[str]:
    found = []
    for item in files:
        name = item.name.lower()
        parts = item.path.split("/")
        if name not in ENTRY_POINTS:
            continue
        if item.depth == 0 or parts[0] in {"src", "app", "cmd", "bin"}:
            found.append(item.path)
    for item in files:
        if item.name.lower() == "application.java" and "src/main/java" in item.path:
            found.append(item.path)
    return sorted(set(found))[:30]


def _structure(inventory: Inventory) -> list[dict]:
    file_counts: Counter[str] = Counter()
    for item in inventory.files:
        top = item.path.split("/", 1)[0] if "/" in item.path else None
        if top:
            file_counts[top] += 1
    top_dirs = [d for d in inventory.directories if "/" not in d][:40]
    root_files = [item.name for item in inventory.files if item.depth == 0][:40]
    tree = [{"path": d, "type": "directory", "files": file_counts.get(d, 0)} for d in top_dirs]
    tree += [{"path": name, "type": "file"} for name in root_files]
    return tree


def analyze(ctx: ScanContext, inventory: Inventory) -> AnalyzerResult:
    languages = _languages(inventory)
    primary = _primary(languages)
    names = [item.name.lower() for item in inventory.files]

    build_tools = sorted({BUILD_TOOLS[name] for name in names if name in BUILD_TOOLS})
    frameworks = sorted({FRAMEWORK_FILES[name] for name in names if name in FRAMEWORK_FILES})
    entry_points = _entry_points(inventory.files)
    config_files = [
        item.path
        for item in inventory.files
        if item.name.lower() in CONFIG_NAMES or item.path.startswith(".github/workflows/")
    ][:60]
    doc_files = [
        item.path
        for item in inventory.files
        if item.depth <= 1 and item.name.lower().split(".")[0] in DOC_NAMES
    ][:40]

    facts = {
        "name": ctx.root.name,
        "file_count": len(inventory.files),
        "directory_count": len(inventory.directories),
        "total_bytes": sum(item.size for item in inventory.files),
        "languages": languages,
        "primary_language": primary,
        "secondary_languages": [item["name"] for item in languages if item["name"] != primary],
        "frameworks": frameworks,
        "build_tools": build_tools,
        "entry_points": entry_points,
        "config_files": config_files,
        "doc_files": doc_files,
        "structure": _structure(inventory),
        "limits": {
            "file_limit_reached": inventory.truncated,
            "depth_limit_reached": inventory.depth_limited,
            "skipped_symlinks": inventory.skipped_symlinks,
            "skipped_special_files": inventory.skipped_special,
            "skipped_unsafe_names": inventory.skipped_unsafe_names,
        },
    }

    evidence: list[RawEvidence] = []
    if not inventory.files:
        evidence.append(
            RawEvidence("repository.empty", CATEGORY, "No scannable files were found.", METHOD)
        )
    else:
        summary = ", ".join(f"{item['name']} {item['share']}%" for item in languages[:5])
        evidence.append(
            RawEvidence(
                "repository.languages",
                CATEGORY,
                f"Language share by file size: {summary or 'none recognized'}. "
                f"Scanned {len(inventory.files)} files.",
                METHOD,
                data={"languages": languages[:10], "primary": primary},
            )
        )
    if frameworks:
        evidence.append(
            RawEvidence(
                "repository.frameworks",
                CATEGORY,
                f"Framework indicator files found for: {', '.join(frameworks)}.",
                METHOD,
                data={"frameworks": frameworks},
            )
        )
    if build_tools:
        evidence.append(
            RawEvidence(
                "repository.build_tools",
                CATEGORY,
                f"Build tooling files found for: {', '.join(build_tools)}.",
                METHOD,
                data={"build_tools": build_tools},
            )
        )
    if entry_points:
        evidence.append(
            RawEvidence(
                "repository.entry_points",
                CATEGORY,
                f"Conventional entry point files: {', '.join(entry_points[:8])}.",
                METHOD,
                data={"entry_points": entry_points},
            )
        )
    if inventory.truncated or inventory.depth_limited:
        evidence.append(
            RawEvidence(
                "repository.scan_limited",
                CATEGORY,
                "The scan stopped at a configured limit, so results may be incomplete.",
                METHOD,
                data=facts["limits"],
            )
        )
    if inventory.skipped_symlinks or inventory.skipped_unsafe_names or inventory.skipped_special:
        evidence.append(
            RawEvidence(
                "repository.skipped_entries",
                CATEGORY,
                f"Not followed: {inventory.skipped_symlinks} symlink(s), "
                f"{inventory.skipped_special} special file(s), "
                f"{inventory.skipped_unsafe_names} file name(s) with unsafe characters.",
                METHOD,
                data=facts["limits"],
            )
        )
    return AnalyzerResult("repository_scout", facts, evidence)
