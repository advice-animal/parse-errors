"""Thin wrapper around the json-source-map package that returns our own types."""

from __future__ import annotations

import json_source_map as _ext

from ..source_map import Entry, Location, TSourceMap


def calculate(source: str) -> TSourceMap:
    """Calculate the source map for a JSON document."""
    return {
        pointer: Entry(
            value_start=_loc(e.value_start),
            value_end=_loc(e.value_end),
            key_start=_loc(e.key_start) if e.key_start is not None else None,
            key_end=_loc(e.key_end) if e.key_end is not None else None,
        )
        for pointer, e in _ext.calculate(source).items()
    }


def _loc(ext: _ext.Location) -> Location:
    """Translate to our internal structure."""
    return Location(line=ext.line, column=ext.column, position=ext.position)
