"""Documentation Inspector: completeness judged only on observable criteria."""

import re

from app.analyzers.base import AnalyzerResult, Inventory, RawEvidence, ScanContext, read_text

METHOD = "documentation-inspector:structure-check"
CATEGORY = "documentation"

_HEADING = re.compile(r"^(?:#{1,6}\s+(.+?)\s*#*\s*$|(.+)\n[=~-]{3,}\s*$)", re.M)
_FENCE = re.compile(r"^```.*?^```", re.M | re.S)
_SECTIONS = {
    "installation": r"install|setup|set up|getting started|quick ?start",
    "usage": r"usage|how to use|running|examples?|getting started",
    "testing": r"test",
    "configuration": r"config|environment|settings",
    "contributing": r"contribut",
    "license": r"licen[cs]e",
}
_MIN_OVERVIEW_WORDS = 15


def _first_paragraph(text: str) -> str:
    stripped = _FENCE.sub("", text)
    for block in re.split(r"\n\s*\n", stripped):
        block = block.strip()
        if not block or block[0] in "#<![|=-" or re.match(r".+\n[=~-]{3,}$", block):
            continue
        return " ".join(block.split())[:600]
    return ""


def inspect_readme(text: str) -> dict:
    headings = [(a or b).strip() for a, b in _HEADING.findall(text)]
    sections = {
        section: any(re.search(pattern, heading, re.I) for heading in headings)
        for section, pattern in _SECTIONS.items()
    }
    overview = _first_paragraph(text)
    return {
        "word_count": len(_FENCE.sub("", text).split()),
        "headings": [heading[:100] for heading in headings[:40]],
        "sections": sections,
        "has_code_blocks": bool(_FENCE.search(text)),
        "overview": overview,
        "has_overview": len(overview.split()) >= _MIN_OVERVIEW_WORDS,
    }


def _find(inventory: Inventory, pattern: str, max_depth: int = 1) -> list[str]:
    regex = re.compile(pattern, re.I)
    return [i.path for i in inventory.files if i.depth <= max_depth and regex.fullmatch(i.name)]


def analyze(ctx: ScanContext, inventory: Inventory) -> AnalyzerResult:
    readmes = [
        i.path for i in inventory.files if i.depth == 0 and i.name.lower().startswith("readme")
    ]
    contributing = _find(inventory, r"contributing(\.\w+)?")
    license_files = _find(inventory, r"(license|licence|copying)(\.\w+)?", 0)
    changelog = _find(inventory, r"(changelog|history|changes)(\.\w+)?")
    has_docs_dir = any(d.split("/")[0].lower() in {"docs", "doc", "documentation"}
                       for d in inventory.directories)  # fmt: skip
    api_docs = [
        i.path
        for i in inventory.files
        if re.fullmatch(r"(openapi|swagger)\.(ya?ml|json)", i.name, re.I)
        or re.search(r"(^|/)docs?/.*api[^/]*\.(md|rst|ya?ml|json)$", i.path, re.I)
    ][:10]
    architecture = [
        i.path
        for i in inventory.files
        if re.search(r"architecture[^/]*\.(md|rst|txt)$", i.name, re.I)
    ][:10]

    readme = None
    if readmes:
        text = read_text(ctx, readmes[0])
        readme = inspect_readme(text) if text is not None else None

    sections = readme["sections"] if readme else {}
    criteria = {
        "README present": bool(readmes),
        "README has an overview": bool(readme and readme["has_overview"]),
        "README covers installation": bool(sections.get("installation")),
        "README covers usage": bool(sections.get("usage")),
        "README covers testing": bool(sections.get("testing")),
        "README covers configuration": bool(sections.get("configuration")),
        "License file present": bool(license_files),
        "Contributing guide present": bool(contributing),
        "Docs directory present": has_docs_dir,
        "Architecture document present": bool(architecture),
    }
    met = sum(criteria.values())
    score = round(met / len(criteria) * 100)

    evidence: list[RawEvidence] = []
    if not readmes:
        if inventory.files:
            evidence.append(
                RawEvidence(
                    "documentation.readme_missing",
                    CATEGORY,
                    "No README file was found at the repository root.",
                    METHOD,
                )
            )
    elif readme is None:
        evidence.append(
            RawEvidence(
                "documentation.readme_unreadable",
                CATEGORY,
                f"{readmes[0]} could not be read as text.",
                METHOD,
                source_file=readmes[0],
            )
        )
    else:
        evidence.append(
            RawEvidence(
                "documentation.readme",
                CATEGORY,
                f"{readmes[0]} has {readme['word_count']} words and "
                f"{len(readme['headings'])} headings.",
                METHOD,
                source_file=readmes[0],
                data={k: readme[k] for k in ("word_count", "headings", "sections")},
            )
        )
        missing = [name for name in ("installation", "usage") if not sections.get(name)]
        if missing:
            evidence.append(
                RawEvidence(
                    "documentation.readme_gaps",
                    CATEGORY,
                    f"{readmes[0]} has no heading covering: {', '.join(missing)}.",
                    METHOD,
                    source_file=readmes[0],
                    data={"missing_sections": missing},
                )
            )
    if inventory.files and not contributing:
        evidence.append(
            RawEvidence(
                "documentation.contributing_missing",
                CATEGORY,
                "No contributing guide was found.",
                METHOD,
            )
        )
    evidence.append(
        RawEvidence(
            "documentation.completeness",
            CATEGORY,
            f"{met} of {len(criteria)} observable documentation criteria are met.",
            METHOD,
            data={"criteria": criteria, "score": score},
        )
    )

    facts = {
        "readme_files": readmes,
        "readme": readme,
        "contributing_files": contributing,
        "license_files": license_files,
        "changelog_files": changelog,
        "has_docs_dir": has_docs_dir,
        "api_docs": api_docs,
        "architecture_docs": architecture,
        "criteria": criteria,
        "completeness_score": score,
    }
    return AnalyzerResult("documentation_analyzer", facts, evidence)
