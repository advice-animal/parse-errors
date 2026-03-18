"""re-raise parse errors with filename and line number."""

try:
    from ._version import __version__
except ImportError:  # pragma: no cover
    __version__ = "dev"

__all__ = []
