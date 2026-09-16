"""Calculate TOML source locations using tree-sitter, targeted or full.

locate() extends the existing tree-sitter-based calculate() with a targeted
walk that only visits table/pair/array members on the path to the one
pointer asked for -- a sibling pair under a non-matching key, or a whole
non-matching [[array-of-tables]] element, is skipped without recursing into
it or building any Entry for it. Array-of-tables members still have to be
counted in document order to know which occurrence is index N (TOML doesn't
number them explicitly), but skipped occurrences are only counted, not
walked. calculate() and locate() share that counting through a single
_header_candidates() generator rather than each keeping its own.
"""

from __future__ import annotations

from typing import Iterator, Optional

import tree_sitter as ts
import tree_sitter_toml

from .._jsonpath import _escape
from ..source_map import Entry, Location, TSourceMap

_LANGUAGE = ts.Language(tree_sitter_toml.language())

_Parsed = tuple[ts.Node, bytes]


def calculate(source: str | bytes) -> TSourceMap:
    """Calculate the full source map for a TOML document."""
    src_bytes = source if isinstance(source, bytes) else source.encode("utf-8")
    root = ts.Parser(_LANGUAGE).parse(src_bytes).root_node

    result: TSourceMap = {}
    result[""] = _own_entry(root, src_bytes)
    for child in root.children:
        if child.type == "pair":
            _process_pair(child, [], result, src_bytes)
    for key_segs, node, entry in _header_candidates(root.children, src_bytes):
        result[_to_pointer(key_segs)] = entry
        if node is not None:
            for grandchild in node.children:
                if grandchild.type == "pair":
                    _process_pair(grandchild, key_segs, result, src_bytes)
    return result


def _parse(source: str | bytes) -> _Parsed | None:
    """Parse *source* into the (root, src_bytes) pair :func:`_locate_in` walks.

    Split out from :func:`locate` so :class:`~parse_errors.source_map.SourceMap`
    can parse once and reuse it across several ``locate()`` calls on the same
    document, instead of reparsing per pointer.
    """
    src_bytes = source if isinstance(source, bytes) else source.encode("utf-8")
    root = ts.Parser(_LANGUAGE).parse(src_bytes).root_node
    return root, src_bytes


def _locate_in(parsed: _Parsed | None, pointer: str) -> Optional[Entry]:
    if parsed is None:
        return None
    root, src_bytes = parsed
    segments = _pointer_segments(pointer)
    if not segments:
        return _own_entry(root, src_bytes)
    found = _find_in_container(root.children, segments, 0, src_bytes)
    return found if found is not None else _own_entry(root, src_bytes)


def locate(source: str | bytes, pointer: str) -> Optional[Entry]:
    """Find *pointer*'s location, visiting only members on the path to it."""
    return _locate_in(_parse(source), pointer)


def _find_in_container(
    children: list[ts.Node], target: list[str], idx: int, src: bytes
) -> Optional[Entry]:
    """*children* is a document's or table's direct pair/table/table_array_element
    nodes. Returns the entry for target[idx:] if reachable through them, else None.

    Matches calculate()'s existing scope exactly: a plain array is a leaf --
    its elements are never individually addressable, only [[[array-of-
    tables]]] elements are (by document-order occurrence, counted here as
    they're seen; a skipped occurrence is counted, never walked).
    """
    remaining = target[idx:]

    # A bare pair's key can't be extended by anything else -- pairs are
    # always leaves (or an inline_table to descend into, see
    # _find_in_value) -- so the first matching one is unambiguously the
    # answer, unlike headers below.
    for child in children:
        if child.type != "pair":
            continue
        key_node, value_node = _pair_key_value(child)
        key_segs = _key_segments(key_node)
        if _is_prefix(key_segs, remaining):
            new_idx = idx + len(key_segs)
            if new_idx == len(target):
                return _own_entry(value_node, src, key_node)
            return _find_in_value(value_node, target, new_idx, src, key_node)

    # Headers (tables and array-of-tables elements) form one flat,
    # document-ordered namespace where a later header can continue an
    # earlier one's dotted path -- e.g. `[items.detail]` implicitly nests
    # under whichever `[[items]]` element most recently opened, even though
    # tree-sitter parses it as a sibling, not a child, of that element. So
    # unlike a pair, the first header whose key is a prefix of `remaining`
    # isn't necessarily the answer: resolve every header's fully expanded
    # path via _header_candidates() -- shared with calculate(), see its
    # docstring -- then take the one whose path is the longest prefix of
    # `remaining`, mirroring closest_entry()'s longest-prefix-wins rule over
    # calculate()'s full map.
    best: Optional[tuple[list[str], Optional[ts.Node], Entry]] = None
    for key_segs, node, entry in _header_candidates(children, src):
        if _is_prefix(key_segs, remaining) and (
            best is None or len(key_segs) > len(best[0])
        ):
            best = (key_segs, node, entry)

    if best is None:
        return None
    key_segs, node, entry = best
    new_idx = idx + len(key_segs)
    if new_idx == len(target) or node is None:
        return entry
    found = _find_in_container(node.children, target, new_idx, src)
    return found if found is not None else entry


def _header_candidates(
    children: list[ts.Node], src: bytes
) -> Iterator[tuple[list[str], Optional[ts.Node], Entry]]:
    """Yield (expanded key segments, header node to recurse into or None, own
    Entry) for each table/table_array_element among *children*, in document
    order.

    The one place that resolves a header's key path: a `[dotted.table]`
    header implicitly nesting under the array element it continues
    (`_expand_aot_segments`), and an array-of-tables element's occurrence
    index among same-named siblings (TOML doesn't number them explicitly).
    calculate() writes every candidate into its result dict and recurses
    into all of them; `_find_in_container()` picks the longest-prefix match
    against the pointer it wants and recurses into just that one. Both share
    this single `aot_counts`.

    An array's own group pointer (e.g. "/arr", not "/arr/0") is yielded once,
    at its first occurrence, as a childless (node=None) candidate: calculate()
    records this as a zero-width entry, and locate() needs it as a leaf, in
    case a pointer stops exactly there or names an occurrence that never
    happened.
    """
    aot_counts: dict[str, int] = {}
    for child in children:
        if child.type == "table":
            key_node = _table_key(child)
            key_segs = _expand_aot_segments(_key_segments(key_node), aot_counts)
            yield key_segs, child, _own_entry(child, src)
        elif child.type == "table_array_element":
            key_node = _table_key(child)
            raw_segs = _key_segments(key_node)
            # Expand parent AoT indices into the prefix, but not the final
            # segment, which names the AoT being defined.
            key_segs = _expand_aot_segments(raw_segs[:-1], aot_counts) + raw_segs[-1:]
            array_pointer = _to_pointer(key_segs)
            occurrence = aot_counts.get(array_pointer, 0)
            if occurrence == 0:
                loc0 = _loc(child.start_point, src)
                yield key_segs, None, Entry(value_start=loc0, value_end=loc0)
            aot_counts[array_pointer] = occurrence + 1
            yield key_segs + [str(occurrence)], child, _own_entry(child, src)


def _find_in_value(
    node: ts.Node, target: list[str], idx: int, src: bytes, key_node: ts.Node
) -> Entry:
    """*node* is a pair's value; target[idx:] wants to navigate past it, but
    only an inline_table can be navigated into -- a plain array (like a
    scalar) is always a leaf here, matching calculate()'s existing scope."""
    if node.type == "inline_table":
        pairs = [c for c in node.children if c.type == "pair"]
        found = _find_in_container(pairs, target, idx, src)
        if found is not None:
            return found
    return _own_entry(node, src, key_node)


def _is_prefix(prefix: list[str], target: list[str]) -> bool:
    return len(prefix) <= len(target) and target[: len(prefix)] == prefix


def _pointer_segments(pointer: str) -> list[str]:
    if not pointer:
        return []
    return [p.replace("~1", "/").replace("~0", "~") for p in pointer.split("/")[1:]]


# --- shared by calculate() and locate() ---


def _process_pair(
    node: ts.Node, prefix: list[str], result: TSourceMap, src: bytes
) -> None:
    key_node, value_node = _pair_key_value(node)
    segments = prefix + _key_segments(key_node)
    result[_to_pointer(segments)] = _own_entry(value_node, src, key_node)

    if value_node.type == "inline_table":
        for child in value_node.children:
            if child.type == "pair":
                _process_pair(child, segments, result, src)


def _pair_key_value(node: ts.Node) -> tuple[ts.Node, ts.Node]:
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
    for child in node.children:
        if child.type in ("bare_key", "quoted_key", "dotted_key"):
            return child
    raise ValueError(f"No key found in {node.type}")  # pragma: no cover


def _key_segments(node: ts.Node) -> list[str]:
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
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1].encode("raw_unicode_escape").decode("unicode_escape")
    elif s.startswith("'") and s.endswith("'"):
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
    lines = src.splitlines(True) + [b""]
    char_column = len(lines[point.row][: point.column].decode("utf-8"))
    position = (
        sum(len(line.decode("utf-8")) for line in lines[: point.row]) + char_column
    )
    return Location(line=point.row, column=char_column, position=position)


def _own_entry(node: ts.Node, src: bytes, key_node: Optional[ts.Node] = None) -> Entry:
    """*node*'s own span, with *key_node*'s span attached if it has one."""
    return Entry(
        value_start=_loc(node.start_point, src),
        value_end=_loc(node.end_point, src),
        key_start=_loc(key_node.start_point, src) if key_node is not None else None,
        key_end=_loc(key_node.end_point, src) if key_node is not None else None,
    )
