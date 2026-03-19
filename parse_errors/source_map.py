"""Source map types and utilities for parse_errors."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Dict, Optional


# These are identical to the ones in json-source-map, but I feel icky exporting
# some other project's types because they may change.


@dataclasses.dataclass
class Location:
    line: int  # 0-based line number
    column: int  # 0-based character offset within the line (not bytes)
    position: int  # 0-based character offset from start of document (not bytes)


@dataclasses.dataclass
class Entry:
    value_start: Location
    value_end: Location
    key_start: Optional[Location] = None
    key_end: Optional[Location] = None


TSourceMap = Dict[str, Entry]


def detect_format(path: Path) -> str | None:
    """Detect the format of a file based on its extension."""
    suffix = path.suffix.lower()
    return {
        ".toml": "toml",
    }.get(suffix)


def build_source_map(source: str | bytes, fmt: str) -> TSourceMap:
    """Build a source map for the given source in the given format."""
    if fmt == "toml":
        from .toml_source_map import calculate

        return calculate(source)
    else:
        raise ValueError(f"Unknown format: {fmt!r}")


def closest_entry(source_map: TSourceMap, pointer: str) -> Entry | None:
    """Return the source map entry for ``pointer``, falling back to the longest prefix."""
    if pointer in source_map:
        return source_map[pointer]

    # Walk up the pointer path until we find a match.
    parts = pointer.split("/")  # e.g. ['', 'foo', 'bar']
    for length in range(len(parts) - 1, 0, -1):
        candidate = "/".join(parts[:length])
        if candidate in source_map:
            return source_map[candidate]

    return None
