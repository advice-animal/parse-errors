"""Convert JSONPath expressions to JSON Pointer (RFC 6901)."""

from __future__ import annotations

import re


# Matches a single step in a JSONPath: .key or [index] or ['key'] or ["key"]
_STEP = re.compile(
    r"\.(?P<name>[^.\[]+)"  # .key
    r"|\[(?P<idx>\d+)\]"  # [0]
    r"|\[\'(?P<sq>[^\']*)\'\]"  # ['key']
    r'|\["(?P<dq>[^"]*)"\]'  # ["key"]
)

# Pattern to extract JSONPath from msgspec-style error messages: "... - at `$.foo.bar`"
_AT_PATH = re.compile(r" - at `(\$[^`]*)`")


def jsonpath_to_pointer(jsonpath: str) -> str:
    """Convert a JSONPath string like ``$.foo[0].bar`` to a JSON Pointer like ``/foo/0/bar``.

    Only supports simple dot-notation and bracket-index forms as produced by
    msgspec.  Does not support filter expressions or wildcards.

    Args:
        jsonpath: A JSONPath string starting with ``$``.

    Returns:
        A JSON Pointer string (RFC 6901), e.g. ``/foo/0/bar``.
    """
    if jsonpath == "$":
        return ""
    if not jsonpath.startswith("$"):
        raise ValueError(f"JSONPath must start with '$', got: {jsonpath!r}")

    tail = jsonpath[1:]  # strip leading $
    parts: list[str] = []

    pos = 0
    while pos < len(tail):
        m = _STEP.match(tail, pos)
        if m is None:
            raise ValueError(
                f"Cannot parse JSONPath step at position {pos}: {tail[pos:]!r}"
            )
        for group in ("name", "sq", "dq", "idx"):
            if (name := m.group(group)) is not None:
                break
        parts.append(_escape(name))
        pos = m.end()

    return "/" + "/".join(parts) if parts else ""


def extract_jsonpath(message: str) -> str | None:
    """Extract a JSONPath expression from an error message.

    Looks for the pattern ``- at `$.path``` as used by msgspec.

    Args:
        message: The exception message string.

    Returns:
        The JSONPath string if found, otherwise ``None``.
    """
    m = _AT_PATH.search(message)
    return m.group(1) if m else None


def _escape(segment: str) -> str:
    return segment.replace("~", "~0").replace("/", "~1")
