"""Detect and redact secrets. Findings carry a rule name and line number, never the value."""

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

REDACTED = "[REDACTED]"

_TEMPLATE_SUFFIXES = (".example", ".sample", ".template", ".dist", ".defaults")
_SECRET_NAMES = {
    ".env",
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".htpasswd",
    "credentials",
    "credentials.json",
    "secrets.json",
    "secrets.yaml",
    "secrets.yml",
    "secrets.toml",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "service-account.json",
}
_SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".asc", ".ppk")

_TOKEN_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "private-key",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----(?:.*?-----END [A-Z ]*PRIVATE KEY-----)?", re.S
        ),
    ),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b")),
    ("github-fine-grained-token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("gitlab-token", re.compile(r"\bglpat-[A-Za-z0-9_-]{16,}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("stripe-key", re.compile(r"\b[sr]k_live_[A-Za-z0-9]{16,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("api-secret-key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("npm-token", re.compile(r"\bnpm_[A-Za-z0-9]{30,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
]

_URL_CREDENTIALS = re.compile(r"\b([a-z][a-z0-9+.-]*://)[^\s/:@'\"]+:[^\s/@'\"]+@", re.I)

_SENSITIVE_NAME = (
    r"[\w.-]*(?:password|passwd|pwd|secret|token|api[_-]?key|private[_-]?key|access[_-]?key)[\w.-]*"
)
_ASSIGNMENT = re.compile(
    rf"(?i)(?P<name>[\"']?{_SENSITIVE_NAME}[\"']?)(?P<sep>\s*(?::=|=>|=|:)\s*)"
    r"(?P<quote>[\"']?)(?P<value>[^\s\"',;]{4,})(?P=quote)"
)
_QUOTED_ASSIGNMENT = re.compile(
    rf"(?i)[\"']?{_SENSITIVE_NAME}[\"']?\s*(?::=|=>|=|:)\s*"
    r"(?P<quote>[\"'])(?P<value>[^\"'\n]{8,})(?P=quote)"
)
_PLACEHOLDER = re.compile(
    r"(?i)(change.?me|example|placeholder|your[_-]|xxx|dummy|sample|test|fake|none|null|todo"
    r"|<.*>|\$\{|\{\{|%\(|^\*+$)"
)


@dataclass(frozen=True)
class SecretHit:
    rule: str
    line: int


def is_secret_file(path: str) -> bool:
    """True for files that must never be read into evidence or model context."""
    name = PurePosixPath(path.replace("\\", "/")).name.lower()
    if name.endswith(_TEMPLATE_SUFFIXES):
        return False
    if name in _SECRET_NAMES or name.startswith(".env."):
        return True
    return name.endswith(_SECRET_SUFFIXES)


def find_secrets(text: str) -> list[SecretHit]:
    hits: set[SecretHit] = set()
    for rule, pattern in _TOKEN_RULES:
        for match in pattern.finditer(text):
            hits.add(SecretHit(rule, text.count("\n", 0, match.start()) + 1))
    for match in _URL_CREDENTIALS.finditer(text):
        if not _PLACEHOLDER.search(match.group(0)):
            hits.add(SecretHit("url-credentials", text.count("\n", 0, match.start()) + 1))
    for match in _QUOTED_ASSIGNMENT.finditer(text):
        if not _PLACEHOLDER.search(match.group("value")):
            hits.add(SecretHit("hardcoded-credential", text.count("\n", 0, match.start()) + 1))
    return sorted(hits, key=lambda hit: (hit.line, hit.rule))


def redact(text: str) -> str:
    for _, pattern in _TOKEN_RULES:
        text = pattern.sub(REDACTED, text)
    text = _URL_CREDENTIALS.sub(lambda match: f"{match.group(1)}{REDACTED}@", text)
    return _ASSIGNMENT.sub(
        lambda match: f"{match.group('name')}{match.group('sep')}{REDACTED}", text
    )


def redact_data(value: Any) -> Any:
    """Redact every string inside JSON-like data, keys included."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {redact(str(key)): redact_data(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [redact_data(item) for item in value]
    return value
