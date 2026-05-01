"""Calculate the source map for a TOML document using tree-sitter."""

from __future__ import annotations

import tree_sitter_toml
import tree_sitter as ts
from ..source_map import Entry, Location, TSourceMap
from .._jsonpath import _escape


def calculate(source: str | bytes) -> TSourceMap:
    """Calculate the source map for a TOML document.

    Args:
        source: The TOML document as a string or bytes.

    Returns:
        A dict mapping JSON Pointer paths to Entry objects with location info.
    """
    src_bytes = source if isinstance(source, bytes) else source.encode("utf-8")
    parser = ts.Parser(ts.Language(tree_sitter_toml.language()))
    root = parser.parse(src_bytes).root_node

    result: TSourceMap = {}
    aot_counts: dict[str, int] = {}

    result[""] = Entry(
        value_start=_loc(root.start_point, src_bytes),
        value_end=_loc(root.end_point, src_bytes),
    )

    for child in root.children:
        if child.type == "pair":
            _process_pair(child, [], result, src_bytes)
        elif child.type == "table":
            _process_table(child, result, aot_counts, src_bytes)
        elif child.type == "table_array_element":
            _process_aot(child, result, aot_counts, src_bytes)

    return result


def _process_pair(
    node: ts.Node,
    prefix: list[str],
    result: TSourceMap,
    src: bytes,
) -> None:
    key_node, value_node = _pair_key_value(node)
    segments = prefix + _key_segments(key_node)
    pointer = _to_pointer(segments)

    if value_node.type == "inline_table":
        result[pointer] = Entry(
            value_start=_loc(value_node.start_point, src),
            value_end=_loc(value_node.end_point, src),
            key_start=_loc(key_node.start_point, src),
            key_end=_loc(key_node.end_point, src),
        )
        for child in value_node.children:
            if child.type == "pair":
                _process_pair(child, segments, result, src)
    else:
        result[pointer] = Entry(
            value_start=_loc(value_node.start_point, src),
            value_end=_loc(value_node.end_point, src),
            key_start=_loc(key_node.start_point, src),
            key_end=_loc(key_node.end_point, src),
        )


def _process_table(
    node: ts.Node,
    result: TSourceMap,
    aot_counts: dict[str, int],
    src: bytes,
) -> None:
    key_node = _table_key(node)
    segments = _expand_aot_segments(_key_segments(key_node), aot_counts)
    pointer = _to_pointer(segments)

    result[pointer] = Entry(
        value_start=_loc(node.start_point, src),
        value_end=_loc(node.end_point, src),
    )

    for child in node.children:
        if child.type == "pair":
            _process_pair(child, segments, result, src)


def _process_aot(
    node: ts.Node,
    result: TSourceMap,
    aot_counts: dict[str, int],
    src: bytes,
) -> None:
    key_node = _table_key(node)
    raw_segments = _key_segments(key_node)
    # Expand parent AoT indices into the prefix, but not the final segment
    # (which names the AoT being defined, not a parent of it).
    segments = _expand_aot_segments(raw_segments[:-1], aot_counts) + raw_segments[-1:]
    array_pointer = _to_pointer(segments)

    idx = aot_counts.get(array_pointer, 0)
    aot_counts[array_pointer] = idx + 1

    item_segments = segments + [str(idx)]
    item_pointer = _to_pointer(item_segments)

    entry_loc = _loc(node.start_point, src)
    result.setdefault(array_pointer, Entry(value_start=entry_loc, value_end=entry_loc))
    result[item_pointer] = Entry(
        value_start=entry_loc,
        value_end=_loc(node.end_point, src),
    )

    for child in node.children:
        if child.type == "pair":
            _process_pair(child, item_segments, result, src)


def _pair_key_value(node: ts.Node) -> tuple[ts.Node, ts.Node]:
    """Return (key_node, value_node) from a pair node."""
    key_node = value_node = None
    for child in node.children:
        if child.type in ("bare_key", "quoted_key", "dotted_key"):
            key_node = child
        elif child.type not in ("=", "comment"):
            value_node = child

    assert key_node is not None
    assert value_node is not None
    return key_node, value_node


def _table_key(node: ts.Node) -> ts.Node:
    """Return the key node from a table or table_array_element node."""
    for child in node.children:
        if child.type in ("bare_key", "quoted_key", "dotted_key"):
            return child
    raise ValueError(f"No key found in {node.type}")  # pragma: no cover


def _key_segments(node: ts.Node) -> list[str]:
    """Extract key path segments from a key node."""
    if node.type == "bare_key":
        assert node.text is not None
        return [node.text.decode()]
    elif node.type == "quoted_key":
        assert node.text is not None
        return [_unquote(node.text.decode())]
    elif node.type == "dotted_key":
        return sum((_key_segments(child) for child in node.children), [])
    return []


def _unquote(s: str) -> str:
    """Strip surrounding quotes from a TOML quoted key."""
    if s.startswith('"') and s.endswith('"'):
        # Basic string: full TOML escape sequences via unicode_escape codec.
        # Encode to latin-1 first to preserve non-ASCII literals, then decode escapes.
        return s[1:-1].encode("raw_unicode_escape").decode("unicode_escape")
    elif s.startswith("'") and s.endswith("'"):
        # Literal string: no escaping
        return s[1:-1]
    return s  # pragma: no cover


def _expand_aot_segments(segments: list[str], aot_counts: dict[str, int]) -> list[str]:
    """Splice the current AoT index after each segment that is a known AoT key.

    Walks segments left-to-right, building up the pointer incrementally.
    After appending each segment, if the resulting pointer is a known AoT,
    the current index (count - 1) is inserted before moving to the next segment.
    This handles arbitrarily deep nesting.

    e.g. segments=[fruits, details] with aot_counts={/fruits: 1}
    → [fruits, 0, details]
    """
    result: list[str] = []
    for seg in segments:
        result.append(seg)
        candidate = _to_pointer(result)
        if candidate in aot_counts:
            result.append(str(aot_counts[candidate] - 1))
    return result


def _to_pointer(segments: list[str]) -> str:
    return "/" + "/".join(_escape(s) for s in segments) if segments else ""


def _loc(point: ts.Point, src: bytes) -> Location:
    # tree-sitter gives byte-based row/column; convert to char-based for consistency
    # with json-source-map and yaml-source-map.
    # Append b"" so end_point row (one past final newline) is always a valid index.
    lines = src.splitlines(True) + [b""]
    char_column = len(lines[point.row][: point.column].decode("utf-8"))
    position = (
        sum(len(line.decode("utf-8")) for line in lines[: point.row]) + char_column
    )
    return Location(line=point.row, column=char_column, position=position)
