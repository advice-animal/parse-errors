"""Source map types and utilities for parse_errors."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, TypeVar

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
TEntry = TypeVar("TEntry")


def detect_format(path: Path) -> str | None:
    """Detect the format of a file based on its extension."""
    suffix = path.suffix.lower()
    return {
        ".json": "json",
        ".toml": "toml",
        ".yaml": "yaml",
        ".yml": "yaml",
    }.get(suffix)


def build_source_map(source: str | bytes, fmt: str) -> TSourceMap:
    """Build a source map for the given source in the given format."""
    if fmt == "toml":
        from . import toml_source_map

        return toml_source_map.calculate(source)
    elif fmt in ("yaml", "yml"):
        from . import yaml_source_map

        return yaml_source_map.calculate(
            source.decode("utf-8") if isinstance(source, bytes) else source
        )
    elif fmt == "json":
        from . import json_source_map

        return json_source_map.calculate(
            source.decode("utf-8") if isinstance(source, bytes) else source
        )
    else:
        raise ValueError(f"Unknown format: {fmt!r}")


def _parse_for(fmt: str, source: str | bytes) -> Any:
    # The three formats' parse trees (tree-sitter nodes for json/toml, a
    # PyYAML Node for yaml) share no common type -- this is deliberately
    # opaque, threaded straight to the matching format's own _locate_in().
    if fmt == "json":
        from . import json_source_map

        return json_source_map._parse(source)
    if fmt == "toml":
        from . import toml_source_map

        return toml_source_map._parse(source)
    if fmt in ("yaml", "yml"):
        from . import yaml_source_map

        return yaml_source_map._parse(source)
    raise ValueError(f"Unknown format: {fmt!r}")


def _locate_in_for(fmt: str, parsed: Any, pointer: str) -> Entry | None:
    if fmt == "json":
        from . import json_source_map

        return json_source_map._locate_in(parsed, pointer)
    if fmt == "toml":
        from . import toml_source_map

        return toml_source_map._locate_in(parsed, pointer)
    if fmt in ("yaml", "yml"):
        from . import yaml_source_map

        return yaml_source_map._locate_in(parsed, pointer)
    raise ValueError(f"Unknown format: {fmt!r}")


def locate_pointer(source: str | bytes, fmt: str, pointer: str) -> Entry | None:
    """Find the location of one pointer directly, without building the whole map.

    A targeted walk over each format's own parse tree -- tree-sitter for
    json/toml, PyYAML's Node tree (via ``get_single_node()``, CSafeLoader when
    available) for yaml -- visiting only nodes on the path to *pointer*,
    unlike :func:`build_source_map` which computes an entry for every value
    in the document regardless of which one is wanted.

    Looking up several pointers in the same document this way reparses it
    each time; use :class:`SourceMap` instead to parse once and reuse it.
    """
    return _locate_in_for(fmt, _parse_for(fmt, source), pointer)


class SourceMap:
    """Repeated pointer lookups against one document, parsed at most once.

    :func:`locate_pointer` costs O(pointer depth) per call, but reparses the
    document from scratch every time -- fine for one lookup, wasteful for
    several against the same source, such as a merged config reporting one
    error per field. ``SourceMap`` defers parsing until the first
    :meth:`locate` call, caches that parse, and reuses it for every pointer
    asked after -- still never building a whole-document map the way
    :func:`build_source_map` does, since each lookup still only walks the
    path to the one pointer it was asked for.
    """

    __slots__ = ("_source", "_fmt", "_parsed", "_has_parsed")

    def __init__(self, source: str | bytes, fmt: str) -> None:
        self._source = source
        self._fmt = fmt
        self._parsed: Any = None
        self._has_parsed = False

    def locate(self, pointer: str) -> Entry | None:
        if not self._has_parsed:
            self._parsed = _parse_for(self._fmt, self._source)
            self._has_parsed = True
        return _locate_in_for(self._fmt, self._parsed, pointer)


def closest_entry(source_map: Mapping[str, TEntry], pointer: str) -> TEntry | None:
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
