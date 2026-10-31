"""Dependency Detective: parse manifests offline. Nothing is installed or fetched."""

import json
import re
import tomllib
from collections import Counter
from dataclasses import asdict, dataclass
from xml.etree.ElementTree import ParseError  # noqa: S405

from defusedxml import ElementTree as SafeElementTree
from defusedxml.common import DefusedXmlException
from packaging.requirements import InvalidRequirement, Requirement

from app.analyzers.base import AnalyzerResult, Inventory, RawEvidence, ScanContext, read_text

METHOD = "dependency-detective:manifest-parser"
CATEGORY = "dependency"
FRESHNESS_NOTE = (
    "Dependency freshness has not been externally verified: GhostRepo reads manifests "
    "offline and does not query package registries."
)

LOCKFILES = {
    "npm": ["package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lock", "bun.lockb"],
    "pypi": ["poetry.lock", "uv.lock", "pipfile.lock", "pdm.lock"],
    "cargo": ["cargo.lock"],
    "go": ["go.sum"],
}

FRAMEWORK_DEPENDENCIES = {
    "django": "Django",
    "flask": "Flask",
    "fastapi": "FastAPI",
    "starlette": "Starlette",
    "tornado": "Tornado",
    "react": "React",
    "next": "Next.js",
    "vue": "Vue",
    "nuxt": "Nuxt",
    "@angular/core": "Angular",
    "svelte": "Svelte",
    "express": "Express",
    "koa": "Koa",
    "@nestjs/core": "NestJS",
    "org.springframework.boot:spring-boot-starter": "Spring Boot",
    "org.springframework.boot:spring-boot-starter-web": "Spring Boot",
    "github.com/gin-gonic/gin": "Gin",
    "github.com/labstack/echo/v4": "Echo",
    "github.com/gofiber/fiber/v2": "Fiber",
    "actix-web": "Actix Web",
    "axum": "Axum",
    "rocket": "Rocket",
}


class ManifestError(ValueError):
    pass


@dataclass
class Dependency:
    name: str
    constraint: str
    ecosystem: str
    manifest: str
    dev: bool
    pinning: str  # exact | range | unbounded | external

    def to_dict(self) -> dict:
        return asdict(self)


def _python_pinning(specifier: str) -> str:
    if not specifier:
        return "unbounded"
    return "exact" if re.fullmatch(r"(==|===)[^,*]+", specifier) else "range"


def _dep(name: str, constraint: str, eco: str, manifest: str, dev: bool, pinning: str):
    return Dependency(name[:200], constraint[:120], eco, manifest, dev, pinning)


def parse_requirements(text: str, manifest: str) -> tuple[list[Dependency], list[str]]:
    deps: list[Dependency] = []
    invalid: list[str] = []
    dev = "dev" in manifest.lower() or "test" in manifest.lower()
    joined = text.replace("\\\n", " ")
    for number, raw in enumerate(joined.splitlines(), start=1):
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        try:
            requirement = Requirement(line)
        except InvalidRequirement:
            invalid.append(f"line {number}")
            continue
        if requirement.url:
            deps.append(
                _dep(requirement.name, "direct reference", "pypi", manifest, dev, "external")
            )
            continue
        specifier = str(requirement.specifier)
        deps.append(
            _dep(
                requirement.name,
                specifier or "*",
                "pypi",
                manifest,
                dev,
                _python_pinning(specifier),
            )
        )
    return deps, invalid


def _pep508(values: object, manifest: str, dev: bool) -> tuple[list[Dependency], list[str]]:
    deps: list[Dependency] = []
    invalid: list[str] = []
    if not isinstance(values, list):
        return deps, invalid
    for value in values:
        if not isinstance(value, str):
            continue
        try:
            requirement = Requirement(value)
        except InvalidRequirement:
            invalid.append("an invalid requirement entry")
            continue
        specifier = str(requirement.specifier)
        deps.append(
            _dep(
                requirement.name,
                specifier or "*",
                "pypi",
                manifest,
                dev,
                _python_pinning(specifier),
            )
        )
    return deps, invalid


def _poetry_constraint(name: str, value: object, manifest: str, dev: bool) -> Dependency:
    if isinstance(value, dict):
        if "git" in value or "path" in value or "url" in value:
            return _dep(name, "direct reference", "pypi", manifest, dev, "external")
        value = value.get("version", "*")
    constraint = str(value)
    if constraint in {"*", ""}:
        pinning = "unbounded"
    else:
        pinning = "exact" if re.fullmatch(r"=?=?\d[\w.]*", constraint) else "range"
    return _dep(name, constraint or "*", "pypi", manifest, dev, pinning)


def parse_pyproject(text: str, manifest: str) -> tuple[list[Dependency], list[str], dict]:
    data = tomllib.loads(text)
    deps: list[Dependency] = []
    invalid: list[str] = []
    project = data.get("project") if isinstance(data.get("project"), dict) else {}

    found, bad = _pep508(project.get("dependencies"), manifest, False)
    deps += found
    invalid += bad
    optional = project.get("optional-dependencies")
    if isinstance(optional, dict):
        for values in optional.values():
            found, bad = _pep508(values, manifest, True)
            deps += found
            invalid += bad
    groups = data.get("dependency-groups")
    if isinstance(groups, dict):
        for values in groups.values():
            found, bad = _pep508(values, manifest, True)
            deps += found
            invalid += bad

    tool = data.get("tool") if isinstance(data.get("tool"), dict) else {}
    poetry = tool.get("poetry") if isinstance(tool.get("poetry"), dict) else {}
    poetry_sections = [(poetry.get("dependencies"), False), (poetry.get("dev-dependencies"), True)]
    poetry_groups = poetry.get("group")
    if isinstance(poetry_groups, dict):
        poetry_sections += [
            (group.get("dependencies"), True)
            for group in poetry_groups.values()
            if isinstance(group, dict)
        ]
    for section, dev in poetry_sections:
        if isinstance(section, dict):
            deps += [
                _poetry_constraint(name, value, manifest, dev)
                for name, value in section.items()
                if name.lower() != "python"
            ]

    meta = {
        "name": project.get("name") or poetry.get("name"),
        "description": project.get("description") or poetry.get("description"),
        "requires_python": project.get("requires-python"),
        "scripts": sorted(project.get("scripts", {}))
        if isinstance(project.get("scripts"), dict)
        else [],
        "has_pytest_config": "pytest" in tool,
        "build_backend": (data.get("build-system") or {}).get("build-backend")
        if isinstance(data.get("build-system"), dict)
        else None,
    }
    return deps, invalid, meta


def _npm_pinning(constraint: str) -> str:
    value = constraint.strip()
    if value in {"", "*", "latest", "x"}:
        return "unbounded"
    if re.match(r"^(git|github:|https?:|file:|link:|workspace:)", value) or "/" in value:
        return "external"
    return "exact" if re.fullmatch(r"v?\d+\.\d+\.\d+[\w.+-]*", value) else "range"


def parse_package_json(text: str, manifest: str) -> tuple[list[Dependency], dict]:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ManifestError("package.json is not an object")
    deps: list[Dependency] = []
    for section, dev in (
        ("dependencies", False),
        ("optionalDependencies", False),
        ("peerDependencies", False),
        ("devDependencies", True),
    ):
        values = data.get(section)
        if not isinstance(values, dict):
            continue
        for name, constraint in values.items():
            if isinstance(constraint, str):
                deps.append(
                    _dep(name, constraint or "*", "npm", manifest, dev, _npm_pinning(constraint))
                )
    scripts = data.get("scripts") if isinstance(data.get("scripts"), dict) else {}
    engines = data.get("engines") if isinstance(data.get("engines"), dict) else {}
    meta = {
        "name": data.get("name") if isinstance(data.get("name"), str) else None,
        "description": data.get("description")
        if isinstance(data.get("description"), str)
        else None,
        "main": data.get("main") if isinstance(data.get("main"), str) else None,
        "bin": isinstance(data.get("bin"), str | dict),
        "scripts": {str(key)[:60]: str(value)[:200] for key, value in list(scripts.items())[:40]},
        "engines": {str(key)[:30]: str(value)[:40] for key, value in engines.items()},
    }
    return deps, meta


def parse_cargo(text: str, manifest: str) -> tuple[list[Dependency], dict]:
    data = tomllib.loads(text)
    deps: list[Dependency] = []
    workspace = data.get("workspace") if isinstance(data.get("workspace"), dict) else {}
    for section, dev, source in (
        ("dependencies", False, data),
        ("build-dependencies", False, data),
        ("dev-dependencies", True, data),
        ("dependencies", False, workspace),
    ):
        values = source.get(section)
        if not isinstance(values, dict):
            continue
        for name, value in values.items():
            if isinstance(value, dict):
                if "git" in value or "path" in value:
                    deps.append(_dep(name, "direct reference", "cargo", manifest, dev, "external"))
                    continue
                if value.get("workspace") is True:
                    continue
                value = value.get("version", "*")
            constraint = str(value)
            if constraint == "*":
                pinning = "unbounded"
            else:
                pinning = "exact" if constraint.startswith("=") else "range"
            deps.append(_dep(name, constraint, "cargo", manifest, dev, pinning))
    package = data.get("package") if isinstance(data.get("package"), dict) else {}
    return deps, {"name": package.get("name"), "description": package.get("description"),
                  "edition": package.get("edition")}  # fmt: skip


def parse_go_mod(text: str, manifest: str) -> tuple[list[Dependency], dict]:
    deps: list[Dependency] = []
    module = None
    go_version = None
    in_require = False
    for raw in text.splitlines():
        line = raw.split("//", 1)[0].strip()
        indirect = "// indirect" in raw
        if line.startswith("module "):
            module = line.split(None, 1)[1]
        elif line.startswith("go "):
            go_version = line.split(None, 1)[1]
        elif line.startswith("require ("):
            in_require = True
        elif in_require and line == ")":
            in_require = False
        elif in_require or line.startswith("require "):
            parts = line.removeprefix("require ").split()
            if len(parts) == 2:
                deps.append(_dep(parts[0], parts[1], "go", manifest, indirect, "exact"))
    return deps, {"name": module, "go_version": go_version}


def parse_pom(text: str, manifest: str) -> tuple[list[Dependency], dict]:
    try:
        root = SafeElementTree.fromstring(text)
    except (ParseError, DefusedXmlException) as exc:
        raise ManifestError("pom.xml could not be parsed safely") from exc

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    def child_text(element, name: str) -> str | None:
        for child in element:
            if local(child.tag) == name and child.text:
                return child.text.strip()
        return None

    deps: list[Dependency] = []
    for element in root.iter():
        if local(element.tag) != "dependency":
            continue
        group = child_text(element, "groupId")
        artifact = child_text(element, "artifactId")
        if not group or not artifact:
            continue
        version = child_text(element, "version")
        scope = child_text(element, "scope")
        if version is None:
            pinning = "unbounded"
        elif version.startswith("${") or version[:1] in "[(":
            pinning = "range"
        else:
            pinning = "exact"
        deps.append(
            _dep(f"{group}:{artifact}", version or "managed or unspecified", "maven", manifest,
                 scope == "test", pinning)
        )  # fmt: skip
    return deps, {
        "name": child_text(root, "artifactId"),
        "description": child_text(root, "description"),
    }


def _manifests(inventory: Inventory) -> list[tuple[str, str]]:
    found = []
    for item in inventory.files:
        name = item.name.lower()
        if re.fullmatch(r"requirements([-_.][\w.-]+)?\.txt", name) or (
            name.endswith(".txt") and "/requirements/" in f"/{item.path.lower()}"
        ):
            found.append((item.path, "requirements"))
        elif name in {"pyproject.toml", "package.json", "cargo.toml", "go.mod", "pom.xml"}:
            found.append((item.path, name))
    return found


def _parse(kind: str, text: str, path: str) -> tuple[list[Dependency], list[str], dict]:
    if kind == "requirements":
        deps, invalid = parse_requirements(text, path)
        return deps, invalid, {}
    if kind == "pyproject.toml":
        return parse_pyproject(text, path)
    parser = {
        "package.json": parse_package_json,
        "cargo.toml": parse_cargo,
        "go.mod": parse_go_mod,
        "pom.xml": parse_pom,
    }[kind]
    deps, meta = parser(text, path)
    return deps, [], meta


def analyze(ctx: ScanContext, inventory: Inventory) -> AnalyzerResult:
    manifests = _manifests(inventory)
    evidence: list[RawEvidence] = []
    all_deps: list[Dependency] = []
    metadata: dict[str, dict] = {}
    malformed: list[str] = []

    for path, kind in manifests:
        ctx.check_deadline()
        text = read_text(ctx, path)
        if text is None:
            malformed.append(path)
            evidence.append(
                RawEvidence(
                    "dependency.manifest_unreadable",
                    CATEGORY,
                    f"{path} could not be read. It may be binary or over the size limit.",
                    METHOD,
                    source_file=path,
                )
            )
            continue
        try:
            deps, invalid, meta = _parse(kind, text, path)
        except (ValueError, TypeError, AttributeError, KeyError, RecursionError):
            malformed.append(path)
            evidence.append(
                RawEvidence(
                    "dependency.manifest_malformed",
                    CATEGORY,
                    f"{path} is malformed and could not be parsed.",
                    METHOD,
                    source_file=path,
                )
            )
            continue

        all_deps += deps
        metadata[path] = meta
        pinning = Counter(dep.pinning for dep in deps)
        evidence.append(
            RawEvidence(
                "dependency.manifest",
                CATEGORY,
                f"{path} declares {len(deps)} dependencies: {pinning['exact']} exact, "
                f"{pinning['range']} range, {pinning['unbounded']} without a version constraint, "
                f"{pinning['external']} external.",
                METHOD,
                source_file=path,
                data={
                    "kind": kind,
                    "count": len(deps),
                    "pinning": dict(pinning),
                    "dependencies": [f"{d.name} {d.constraint}" for d in deps[:40]],
                },
            )
        )
        unbounded = [dep.name for dep in deps if dep.pinning == "unbounded"]
        if unbounded:
            evidence.append(
                RawEvidence(
                    "dependency.unbounded",
                    CATEGORY,
                    f"{path} has {len(unbounded)} dependencies with no version constraint.",
                    METHOD,
                    source_file=path,
                    data={"dependencies": unbounded[:40], "count": len(unbounded)},
                )
            )
        if invalid:
            evidence.append(
                RawEvidence(
                    "dependency.invalid_entries",
                    CATEGORY,
                    f"{path} has {len(invalid)} entries that could not be parsed.",
                    METHOD,
                    source_file=path,
                    data={"locations": invalid[:20]},
                )
            )

    ecosystems = sorted({dep.ecosystem for dep in all_deps})
    names = [item.name.lower() for item in inventory.files]
    lockfiles = sorted(item.path for item in inventory.by_name(*sum(LOCKFILES.values(), [])))
    for ecosystem, candidates in LOCKFILES.items():
        if ecosystem in ecosystems and not any(lock in names for lock in candidates):
            evidence.append(
                RawEvidence(
                    "dependency.no_lockfile",
                    CATEGORY,
                    f"{ecosystem} dependencies are declared, but no lockfile was found.",
                    METHOD,
                    data={"ecosystem": ecosystem, "expected_any_of": candidates},
                )
            )

    if not manifests:
        evidence.append(
            RawEvidence(
                "dependency.no_manifest",
                CATEGORY,
                "No supported dependency manifest was found (requirements.txt, pyproject.toml, "
                "package.json, Cargo.toml, go.mod, pom.xml).",
                METHOD,
            )
        )
    else:
        evidence.append(
            RawEvidence(
                "dependency.freshness_unverified",
                CATEGORY,
                FRESHNESS_NOTE,
                METHOD,
                data={"freshness_verified": False},
            )
        )

    dep_names = {dep.name.lower() for dep in all_deps}
    frameworks = sorted(
        {label for name, label in FRAMEWORK_DEPENDENCIES.items() if name.lower() in dep_names}
    )
    if frameworks:
        evidence.append(
            RawEvidence(
                "dependency.frameworks",
                CATEGORY,
                f"Declared dependencies indicate: {', '.join(frameworks)}.",
                METHOD,
                data={"frameworks": frameworks},
            )
        )

    pinning_totals = Counter(dep.pinning for dep in all_deps)
    facts = {
        "manifests": [path for path, _ in manifests],
        "malformed_manifests": malformed,
        "ecosystems": ecosystems,
        "dependency_count": len(all_deps),
        "direct_runtime_count": sum(1 for dep in all_deps if not dep.dev),
        "dev_count": sum(1 for dep in all_deps if dep.dev),
        "pinning": dict(pinning_totals),
        "lockfiles": lockfiles,
        "frameworks": frameworks,
        "freshness_verified": False,
        "freshness_note": FRESHNESS_NOTE,
        "dependencies": [dep.to_dict() for dep in all_deps[:300]],
        "metadata": metadata,
    }
    return AnalyzerResult("dependency_analyzer", facts, evidence)
