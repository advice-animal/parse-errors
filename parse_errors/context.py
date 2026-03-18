"""Context manager for better parse error messages."""

from __future__ import annotations

import os
import contextlib
from pathlib import Path
from typing import Iterator

from .source_map import detect_format, build_source_map, closest_entry
from ._jsonpath import extract_jsonpath, jsonpath_to_pointer

__all__ = ["ParseError", "ParseContext"]


class ParseError(Exception):
    """A parse or validation error augmented with filename and line number."""

    def __init__(
        self, message: str, filename: str | os.PathLike[str], line: int, column: int = 0
    ):
        self.filename = str(filename)
        self.line = line
        self.column = column
        super().__init__(message)


@contextlib.contextmanager
def ParseContext(
    filename: str | os.PathLike[str],
    *,
    data: str | bytes | None = None,
    format: str | None = None,
) -> Iterator[None]:
    """Context manager that re-raises parse/validation errors with location info.

    Catches exceptions whose message contains a JSONPath (e.g. as emitted by
    msgspec) and re-raises a :class:`ParseError` with the filename and
    1-based line number derived from the file's source map.

    Args:
        filename: Path to the file being parsed.
        data: The file contents as a string or bytes (UTF-8).  If provided, the
              file is not read from disk.  Regardless of type, reported
              locations (line, column) are always in characters, not bytes.
        format: One of ``"json"``, ``"yaml"``, or ``"toml"``.  If omitted the
                format is inferred from the file extension.
    """
    try:
        yield
    except Exception as exc:
        message = str(exc)
        # This is focused on msgspec-style exceptions, which use JSONPath for
        # some reason.  If there are other formats we know can be raised,
        # adjust this.
        jsonpath = extract_jsonpath(message)
        if jsonpath is None:
            raise

        try:
            pointer = jsonpath_to_pointer(jsonpath)
        except ValueError:  # pragma: no cover
            raise exc

        path = Path(filename)
        fmt = format or detect_format(path)
        assert fmt is not None

        source = data if data is not None else path.read_bytes()
        source_map = build_source_map(source, fmt)

        entry = closest_entry(source_map, pointer)
        if entry is None:  # pragma: no cover
            raise exc

        loc = entry.value_start
        # Lines are 0-based in source maps; convert to 1-based for humans.
        raise ParseError(
            f"{path}:{loc.line + 1}:{loc.column + 1}: {message}",
            filename=path,
            line=loc.line + 1,
            column=loc.column + 1,
        ) from exc
