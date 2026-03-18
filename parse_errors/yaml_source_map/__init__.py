"""Calculate the source map for a YAML document."""

from __future__ import annotations

import yaml
from ..source_map import Entry, Location, TSourceMap


def calculate(source: str) -> TSourceMap:
    """Calculate the source map for a YAML document.

    Args:
        source: The YAML document as a string.

    Returns:
        A dict mapping JSON Pointer paths to Entry objects with location info.
    """
    loader = yaml.SafeLoader(source)
    node = loader.get_single_node()
    if node is None:
        return {}
    result: TSourceMap = {}
    _walk(node, "", result, loader)
    return result


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
