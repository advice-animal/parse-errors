"""Calculate JSON source locations using tree-sitter, targeted or full.

tree-sitter does the parse in C instead of a hand-written pure-Python
character scanner, and locate() additionally never visits a subtree that
isn't on the path to the one pointer asked for -- indexing directly into
tree-sitter's parsed node tree.

calculate() (the full map, used by anything that still wants build_source_map
+ closest_entry) is kept for comparison/completeness.
"""

from __future__ import annotations

import json

import tree_sitter as ts
import tree_sitter_json

from .._jsonpath import _escape
from ..source_map import Entry, Location, TSourceMap

_LANGUAGE = ts.Language(tree_sitter_json.language())

_Parsed = tuple[ts.Node, list[bytes]]


def calculate(source: str | bytes) -> TSourceMap:
    """Calculate the full source map for a JSON document."""
    src_bytes = source.encode("utf-8") if isinstance(source, str) else source
    root = ts.Parser(_LANGUAGE).parse(src_bytes).root_node
    lines = src_bytes.splitlines(True) + [b""]
    byte_to_char = [_byte_to_char_offsets(line) for line in lines]
    line_start_chars = [0]
    for offsets in byte_to_char[:-1]:
        line_start_chars.append(line_start_chars[-1] + offsets[-1])

    result: TSourceMap = {}
    top = root.named_children[0] if root.named_children else root
    _walk_all(top, [], result, byte_to_char, line_start_chars)
    return result


def _parse(source: str | bytes) -> _Parsed | None:
    """Parse *source* into the (node, lines) pair :func:`_locate_in` walks.

    Split out from :func:`locate` so :class:`~parse_errors.source_map.SourceMap`
    can parse once and reuse it across several ``locate()`` calls on the same
    document, instead of reparsing per pointer.
    """
    src_bytes = source.encode("utf-8") if isinstance(source, str) else source
    root = ts.Parser(_LANGUAGE).parse(src_bytes).root_node
    lines = src_bytes.splitlines(True) + [b""]
    top = root.named_children[0] if root.named_children else root
    return top, lines


def _locate_in(parsed: _Parsed | None, pointer: str) -> Entry | None:
    if parsed is None:
        return None
    top, lines = parsed
    segments = _pointer_segments(pointer)
    return _walk_targeted(top, segments, 0, lines)


def locate(source: str | bytes, pointer: str) -> Entry | None:
    """Find *pointer*'s location, visiting only nodes on the path to it."""
    return _locate_in(_parse(source), pointer)


# --- shared helpers ---


def _pointer_segments(pointer: str) -> list[str]:
    if not pointer:
        return []
    return [p.replace("~1", "/").replace("~0", "~") for p in pointer.split("/")[1:]]


def _to_pointer(segments: list[str]) -> str:
    return "/" + "/".join(_escape(s) for s in segments) if segments else ""


def _byte_to_char_offsets(line: bytes) -> list[int]:
    offsets = [0] * (len(line) + 1)
    char_count = 0
    for i, b in enumerate(line):
        if b < 0x80 or b >= 0xC0:
            char_count += 1
        offsets[i + 1] = char_count
    return offsets


# --- full map (calculate) ---


def _walk_all(
    node: ts.Node,
    segments: list[str],
    result: TSourceMap,
    byte_to_char: list[list[int]],
    line_start_chars: list[int],
    key_node: ts.Node | None = None,
) -> None:
    pointer = _to_pointer(segments)
    result[pointer] = Entry(
        value_start=_loc_precomputed(node.start_point, byte_to_char, line_start_chars),
        value_end=_loc_precomputed(node.end_point, byte_to_char, line_start_chars),
        key_start=_loc_precomputed(key_node.start_point, byte_to_char, line_start_chars)
        if key_node
        else None,
        key_end=_loc_precomputed(key_node.end_point, byte_to_char, line_start_chars)
        if key_node
        else None,
    )
    if node.type == "object":
        for pair in node.named_children:
            if pair.type != "pair":
                continue  # pragma: no cover
            k = pair.child_by_field_name("key")
            v = pair.child_by_field_name("value")
            assert k is not None and k.text is not None
            assert v is not None
            key_text = json.loads(k.text.decode("utf-8"))
            _walk_all(
                v,
                segments + [key_text],
                result,
                byte_to_char,
                line_start_chars,
                key_node=k,
            )
    elif node.type == "array":
        for i, child in enumerate(node.named_children):
            _walk_all(
                child, segments + [str(i)], result, byte_to_char, line_start_chars
            )


def _loc_precomputed(
    point: ts.Point, byte_to_char: list[list[int]], line_start_chars: list[int]
) -> Location:
    char_column = byte_to_char[point.row][point.column]
    return Location(
        line=point.row,
        column=char_column,
        position=line_start_chars[point.row] + char_column,
    )


# --- targeted lookup ---


def _walk_targeted(
    node: ts.Node,
    segments: list[str],
    idx: int,
    lines: list[bytes],
    key_node: ts.Node | None = None,
) -> Entry:
    if idx == len(segments):
        return Entry(
            value_start=_loc(node.start_point, lines),
            value_end=_loc(node.end_point, lines),
            key_start=_loc(key_node.start_point, lines)
            if key_node is not None
            else None,
            key_end=_loc(key_node.end_point, lines) if key_node is not None else None,
        )

    if node.type == "object":
        target_key = segments[idx]
        for pair in node.named_children:
            if pair.type != "pair":
                continue  # pragma: no cover
            k = pair.child_by_field_name("key")
            assert k is not None and k.text is not None
            key_text = json.loads(k.text.decode("utf-8"))
            if key_text == target_key:
                v = pair.child_by_field_name("value")
                assert v is not None
                return _walk_targeted(v, segments, idx + 1, lines, key_node=k)
        # target_key not present -- this object is the closest ancestor
        return _ancestor(node, lines, key_node)

    if node.type == "array":
        try:
            target_index = int(segments[idx])
        except ValueError:
            target_index = -1
        children = node.named_children
        if 0 <= target_index < len(children):
            return _walk_targeted(children[target_index], segments, idx + 1, lines)
        return _ancestor(node, lines, key_node)

    # A scalar, but the pointer wants to go deeper -- no such path; this
    # value is the closest ancestor.
    return _ancestor(node, lines, key_node)


def _ancestor(node: ts.Node, lines: list[bytes], key_node: ts.Node | None) -> Entry:
    # A fallback entry still carries key_start/key_end when this node is
    # itself the value of an enclosing key -- matching the entry it would
    # have gotten in the full map, at the pointer for that key.
    return Entry(
        value_start=_loc(node.start_point, lines),
        value_end=_loc(node.end_point, lines),
        key_start=_loc(key_node.start_point, lines) if key_node is not None else None,
        key_end=_loc(key_node.end_point, lines) if key_node is not None else None,
    )


def _loc(point: ts.Point, lines: list[bytes]) -> Location:
    # Only called O(depth) times per locate() call (a handful), so decoding
    # fresh each time -- rather than precomputing a whole-document table --
    # is cheap; the table only paid for itself when amortized over every
    # node in the document, which locate() deliberately never visits.
    line = lines[point.row]
    char_column = len(line[: point.column].decode("utf-8"))
    position = (
        sum(len(prior.decode("utf-8")) for prior in lines[: point.row]) + char_column
    )
    return Location(line=point.row, column=char_column, position=position)
