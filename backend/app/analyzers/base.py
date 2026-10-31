"""Shared analyzer types and the bounded repository walker.

Repository contents are untrusted: nothing here follows symlinks, opens non-regular files
or reads past the configured limits.
"""

import os
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.security.secret_redaction import is_secret_file


class ScanTimeout(Exception):
    pass


@dataclass
class ScanContext:
    root: Path
    max_file_size: int = 1_000_000
    max_depth: int = 12
    max_files: int = 20_000
    excluded_dirs: frozenset[str] = frozenset()
    git_timeout: float = 20
    deadline: float | None = None

    def check_deadline(self) -> None:
        if self.deadline is not None and time.monotonic() > self.deadline:
            raise ScanTimeout("The analysis time limit was reached.")


@dataclass(frozen=True)
class FileEntry:
    path: str
    size: int

    @property
    def name(self) -> str:
        return self.path.rsplit("/", 1)[-1]

    @property
    def suffix(self) -> str:
        return os.path.splitext(self.name)[1].lower()

    @property
    def depth(self) -> int:
        return self.path.count("/")


@dataclass
class Inventory:
    files: list[FileEntry] = field(default_factory=list)
    directories: list[str] = field(default_factory=list)
    truncated: bool = False
    depth_limited: bool = False
    skipped_symlinks: int = 0
    skipped_special: int = 0
    skipped_unsafe_names: int = 0

    def by_name(self, *names: str) -> list[FileEntry]:
        wanted = {name.lower() for name in names}
        return [item for item in self.files if item.name.lower() in wanted]

    def at_root(self, *names: str) -> list[FileEntry]:
        return [item for item in self.by_name(*names) if item.depth == 0]

    def paths(self) -> set[str]:
        return {item.path for item in self.files}


@dataclass
class RawEvidence:
    kind: str
    category: str
    description: str
    method: str
    source_file: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalyzerResult:
    name: str
    facts: dict[str, Any] = field(default_factory=dict)
    evidence: list[RawEvidence] = field(default_factory=list)


def _safe_name(name: str) -> bool:
    """Control characters and undecodable bytes could forge output or break JSON."""
    return name.isprintable() and not any(0xD800 <= ord(char) <= 0xDFFF for char in name)


def _is_link(info: os.stat_result) -> bool:
    """Symlinks everywhere, plus Windows junctions, which are reparse points but not S_ISLNK."""
    reparse_point = getattr(info, "st_file_attributes", 0) & 0x400
    return stat.S_ISLNK(info.st_mode) or bool(reparse_point)


def walk_repository(ctx: ScanContext) -> Inventory:
    inventory = Inventory()
    stack: list[tuple[str, str, int]] = [(str(ctx.root), "", 0)]

    while stack:
        ctx.check_deadline()
        absolute, relative, depth = stack.pop()
        try:
            entries = sorted(os.scandir(absolute), key=lambda entry: entry.name)
        except OSError:
            continue

        for entry in entries:
            if not _safe_name(entry.name):
                inventory.skipped_unsafe_names += 1
                continue
            rel = f"{relative}/{entry.name}" if relative else entry.name
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError:
                continue

            if _is_link(info):
                inventory.skipped_symlinks += 1
            elif stat.S_ISDIR(info.st_mode):
                if entry.name in ctx.excluded_dirs:
                    continue
                if depth + 1 > ctx.max_depth:
                    inventory.depth_limited = True
                    continue
                inventory.directories.append(rel)
                stack.append((entry.path, rel, depth + 1))
            elif stat.S_ISREG(info.st_mode):
                if len(inventory.files) >= ctx.max_files:
                    inventory.truncated = True
                    return inventory
                inventory.files.append(FileEntry(rel, info.st_size))
            else:
                inventory.skipped_special += 1

    inventory.files.sort(key=lambda item: item.path)
    inventory.directories.sort()
    return inventory


def read_text(ctx: ScanContext, relative: str, *, allow_secret_files: bool = False) -> str | None:
    """Read a small regular text file, or return None. Secret files are refused by default."""
    if not allow_secret_files and is_secret_file(relative):
        return None
    path = ctx.root / relative
    try:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_size > ctx.max_file_size:
            return None
        if not path.resolve().is_relative_to(ctx.root.resolve()):
            return None
        with open(path, "rb") as handle:
            data = handle.read(ctx.max_file_size + 1)
    except OSError:
        return None
    if len(data) > ctx.max_file_size or b"\x00" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")
