from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


class UnsafePathError(ValueError):
    pass


def resolved_file_within(
    value: str | Path,
    roots: Iterable[str | Path],
    *,
    suffixes: set[str] | None = None,
) -> Path:
    """Resolve a persisted path and require it to stay below an approved root."""

    path = Path(value).expanduser().resolve()
    approved_roots = [Path(root).expanduser().resolve() for root in roots]
    if not any(root in path.parents for root in approved_roots):
        raise UnsafePathError("path is outside the approved storage roots")
    if not path.is_file():
        raise UnsafePathError("path does not identify a regular file")
    if suffixes is not None and path.suffix.lower() not in suffixes:
        raise UnsafePathError("file extension is not allowed")
    return path
