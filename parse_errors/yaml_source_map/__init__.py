"""Calculate the source map for a YAML document."""

from __future__ import annotations

from typing import Optional

import yaml

from ..source_map import Entry, Location, TSourceMap

# PyYAML's get_single_node() returns a Node tree (Mapping/Sequence/Scalar)
# with start_mark/end_mark before constructing any Python values -- the same
# role tree-sitter plays for json/toml. CSafeLoader (libyaml, C) gives the
# identical Node/Mark interface as the pure-Python SafeLoader, so use it when
# available; no third-party grammar package needed the way JSON needed
# tree_sitter_json.
_LoaderCls = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

_Parsed = tuple[yaml.Node, yaml.SafeLoader]


def calculate(source: str) -> TSourceMap:
    """Calculate the source map for a YAML document.

    Args:
        source: The YAML document as a string.

    Returns:
        A dict mapping JSON Pointer paths to Entry objects with location info.
    """
    loader = _LoaderCls(source)
    try:
        node = loader.get_single_node()
    finally:
        loader.dispose()
    if node is None:
        return {}
    result: TSourceMap = {}
    _walk(node, "", result, loader)
    return result


def _parse(source: str | bytes) -> _Parsed | None:
    """Parse *source* into the (node, loader) pair :func:`_locate_in` walks.

    Split out from :func:`locate` so :class:`~parse_errors.source_map.SourceMap`
    can parse once and reuse it across several ``locate()`` calls on the same
    document, instead of reparsing per pointer. The loader is disposed (its
    input buffer freed) before being returned -- kept only because node
    construction (``construct_scalar``, for mapping keys) reads from the node
    tree itself, not the buffer.
    """
    text = source.decode("utf-8") if isinstance(source, bytes) else source
    loader = _LoaderCls(text)
    try:
        node = loader.get_single_node()
    finally:
        loader.dispose()
    if node is None:
        return None
    return node, loader


def _locate_in(parsed: _Parsed | None, pointer: str) -> Optional[Entry]:
    if parsed is None:
        return None
    node, loader = parsed
    segments = _pointer_segments(pointer)
    return _walk_targeted(node, segments, 0, loader)


def locate(source: str | bytes, pointer: str) -> Optional[Entry]:
    """Find *pointer*'s location, visiting only nodes on the path to it."""
    return _locate_in(_parse(source), pointer)


def _pointer_segments(pointer: str) -> list[str]:
    if not pointer:
        return []
    return [p.replace("~1", "/").replace("~0", "~") for p in pointer.split("/")[1:]]


def _walk_targeted(
    node: yaml.Node,
    segments: list[str],
    idx: int,
    loader: yaml.SafeLoader,
    key_node: Optional[yaml.Node] = None,
) -> Entry:
    if idx == len(segments):
        return _entry(node, key_node)

    if isinstance(node, yaml.MappingNode):
        target_key = segments[idx]
        for k, v in node.value:
            if str(loader.construct_scalar(k)) == target_key:
                return _walk_targeted(v, segments, idx + 1, loader, key_node=k)
        # target_key not present -- this mapping is the closest ancestor
        return _entry(node, key_node)

    if isinstance(node, yaml.SequenceNode):
        try:
            target_index = int(segments[idx])
        except ValueError:
            target_index = -1
        items = node.value
        if 0 <= target_index < len(items):
            return _walk_targeted(items[target_index], segments, idx + 1, loader)
        return _entry(node, key_node)

    # A scalar, but the pointer wants to go deeper -- no such path; this
    # value is the closest ancestor.
    return _entry(node, key_node)


def _entry(node: yaml.Node, key_node: Optional[yaml.Node]) -> Entry:
    return Entry(
        value_start=_location(node.start_mark),
        value_end=_location(node.end_mark),
        key_start=_location(key_node.start_mark) if key_node is not None else None,
        key_end=_location(key_node.end_mark) if key_node is not None else None,
    )


def _location(mark: yaml.Mark) -> Location:
    return Location(line=mark.line, column=mark.column, position=mark.index)


def _walk(
    node: yaml.Node, path: str, result: TSourceMap, loader: yaml.SafeLoader
) -> None:
    value_start = _location(node.start_mark)
    value_end = _location(node.end_mark)

    if isinstance(node, yaml.MappingNode):
        result[path] = Entry(value_start=value_start, value_end=value_end)
        for key_node, value_node in node.value:
            key = loader.construct_scalar(key_node)
            child_path = f"{path}/{_escape(str(key))}"
            key_start = _location(key_node.start_mark)
            key_end = _location(key_node.end_mark)
            _walk(value_node, child_path, result, loader)
            existing = result[child_path]
            result[child_path] = Entry(
                value_start=existing.value_start,
                value_end=existing.value_end,
                key_start=key_start,
                key_end=key_end,
            )
    elif isinstance(node, yaml.SequenceNode):
        result[path] = Entry(value_start=value_start, value_end=value_end)
        for i, item_node in enumerate(node.value):
            _walk(item_node, f"{path}/{i}", result, loader)
    else:
        result[path] = Entry(value_start=value_start, value_end=value_end)


def _escape(key: str) -> str:
    """Escape a key for use in a JSON Pointer (RFC 6901)."""
    return key.replace("~", "~0").replace("/", "~1")
