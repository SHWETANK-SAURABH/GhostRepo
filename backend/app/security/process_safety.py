"""The only place GhostRepo starts subprocesses: argument arrays, timeouts, bounded output."""

import os
import subprocess  # noqa: S404
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MAX_OUTPUT_BYTES = 2_000_000
_ALLOWED_PROGRAMS = {"git", "ruff", "ruff.exe"}


class ProcessError(Exception):
    """Failed to start or finish in time. The message is safe to show."""


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str
    truncated: bool


def run_command(
    args: list[str],
    cwd: Path,
    timeout: float,
    env: dict[str, str] | None = None,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
) -> ProcessResult:
    if not isinstance(args, list) or not args or not all(isinstance(a, str) for a in args):
        raise ProcessError("Commands must be argument arrays.")
    program = Path(args[0]).name
    if program not in _ALLOWED_PROGRAMS:
        raise ProcessError(f"The program {program} is not allowed.")

    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            completed = subprocess.run(  # noqa: S603
                args,
                cwd=cwd,
                env=env if env is not None else os.environ.copy(),
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                timeout=timeout,
                shell=False,
                check=False,
                creationflags=creationflags,
            )
        except subprocess.TimeoutExpired as exc:
            raise ProcessError(f"{program} did not finish within {timeout:g} seconds.") from exc
        except OSError as exc:
            raise ProcessError(f"{program} could not be started.") from exc

        stdout, truncated = _read_bounded(out, max_output_bytes)
        stderr, _ = _read_bounded(err, 8_000)
    return ProcessResult(completed.returncode, stdout, stderr, truncated)


def _read_bounded(handle, limit: int) -> tuple[str, bool]:
    handle.seek(0)
    data = handle.read(limit + 1)
    return data[:limit].decode("utf-8", errors="replace"), len(data) > limit
