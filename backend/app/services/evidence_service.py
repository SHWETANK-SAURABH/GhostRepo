"""Turn analyzer output into stable, redacted evidence, and prepare it for a model."""

import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from app.analyzers.base import AnalyzerResult
from app.security.secret_redaction import is_secret_file, redact, redact_data

PREFIXES = {
    "repository": "repo",
    "git": "git",
    "dependency": "dep",
    "configuration": "cfg",
    "documentation": "doc",
    "testing": "tst",
    "static_analysis": "sta",
}
MAX_DESCRIPTION = 1000
MAX_STRING = 400
MAX_ITEMS = 50
MODEL_CONTEXT_LIMIT = 12_000


@dataclass
class NormalizedEvidence:
    key: str
    kind: str
    category: str
    description: str
    detection_method: str
    source_file: str | None = None
    structured_data: dict[str, Any] = field(default_factory=dict)


def _bound(value: Any) -> Any:
    if isinstance(value, str):
        return value[:MAX_STRING]
    if isinstance(value, dict):
        return {str(k)[:100]: _bound(v) for k, v in list(value.items())[:MAX_ITEMS]}
    if isinstance(value, list | tuple):
        return [_bound(item) for item in list(value)[:MAX_ITEMS]]
    if isinstance(value, int | float | bool) or value is None:
        return value
    return str(value)[:MAX_STRING]


def normalize(results: list[AnalyzerResult]) -> list[NormalizedEvidence]:
    counters: Counter[str] = Counter()
    normalized: list[NormalizedEvidence] = []
    seen: set[tuple[str, str]] = set()
    for result in results:
        for raw in result.evidence:
            fingerprint = (raw.kind, raw.description)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            prefix = PREFIXES[raw.category]
            counters[prefix] += 1
            normalized.append(
                NormalizedEvidence(
                    key=f"ev-{prefix}-{counters[prefix]:03d}",
                    kind=raw.kind,
                    category=raw.category,
                    description=redact(raw.description)[:MAX_DESCRIPTION],
                    detection_method=raw.method,
                    source_file=redact(raw.source_file)[:500] if raw.source_file else None,
                    structured_data=_bound(redact_data(raw.data)),
                )
            )
    return normalized


def build_model_context(evidence: list[dict[str, Any]], limit: int = MODEL_CONTEXT_LIMIT) -> str:
    """Serialize evidence for a model, within a size budget.

    Evidence is passed as data and bounded here, so a repository cannot grow the prompt.
    """

    # Findings-bearing evidence first, so the budget drops descriptive detail before problems.
    def priority(item: dict[str, Any]) -> int:
        kind = item.get("kind", "")
        return (
            0
            if any(mark in kind for mark in ("secret", "missing", "no_", "malformed", "risky"))
            else 1
        )

    lines: list[str] = []
    used = 0
    for item in sorted(evidence, key=priority):
        source = item.get("source_file")
        if source and is_secret_file(source):
            # The path is enough to discuss; the structured data adds nothing here.
            record = {"id": item["key"], "category": item["category"], "source_file": source,
                      "observation": redact(item["description"])}  # fmt: skip
        else:
            record = {
                "id": item["key"],
                "category": item["category"],
                "source_file": source,
                "observation": redact(item["description"]),
                "data": redact_data(item.get("structured_data") or {}),
            }
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        if used + len(line) > limit:
            line = json.dumps(
                {"id": item["key"], "category": item["category"],
                 "observation": redact(item["description"])[:300]},
                ensure_ascii=False, separators=(",", ":"),
            )  # fmt: skip
            if used + len(line) > limit:
                continue
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines)
