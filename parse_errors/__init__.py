"""re-raise parse errors with filename and line number."""

from .context import ParseContext, ParseError
from .source_map import decode_error_message, locate_decode_error

try:
    from ._version import __version__
except ImportError:  # pragma: no cover
    __version__ = "dev"

__all__ = [
    "ParseContext",
    "ParseError",
    "decode_error_message",
    "locate_decode_error",
]
