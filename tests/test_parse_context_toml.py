try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

import pytest
import msgspec

from parse_errors import ParseContext, ParseError

from ._types import Config, Nested


TOML_SOURCE = """\
host = "localhost"
port = "not-an-int"
"""

TOML_NESTED_SOURCE = """\
[server]
host = "localhost"
port = "not-an-int"
"""


def test_passthrough_non_jsonspec():
    with pytest.raises(ValueError, match="^foo$"):
        with ParseContext("config.toml", data=TOML_SOURCE):
            raise ValueError("foo")


def test_toml_raises_parse_error():
    with pytest.raises(ParseError) as exc_info:
        with ParseContext("config.toml", data=TOML_SOURCE):
            data = tomllib.loads(TOML_SOURCE)
            msgspec.convert(data, Config)

    err = exc_info.value
    assert err.filename == "config.toml"
    assert err.line == 2
    assert str(err) == "config.toml:2:8: Expected `int`, got `str` - at `$.port`"


def test_toml_bytes_data():
    with pytest.raises(ParseError) as exc_info:
        with ParseContext("config.toml", data=TOML_SOURCE.encode()):
            data = tomllib.loads(TOML_SOURCE)
            msgspec.convert(data, Config)

    assert (
        str(exc_info.value)
        == "config.toml:2:8: Expected `int`, got `str` - at `$.port`"
    )


def test_toml_nested_raises_parse_error():
    with pytest.raises(ParseError) as exc_info:
        with ParseContext("config.toml", data=TOML_NESTED_SOURCE):
            data = tomllib.loads(TOML_NESTED_SOURCE)
            msgspec.convert(data, Nested)

    err = exc_info.value
    assert str(err) == "config.toml:3:8: Expected `int`, got `str` - at `$.server.port`"


# --- fallback to nearest parent pointer ---

FALLBACK_SOURCE = """\
[server]
port = 8080
"""


def test_toml_fallback_to_parent():
    # Inject a fake error at a path deeper than the source map tracks.
    # /server/tls/cert doesn't exist; should fall back to /server (line 1).
    with pytest.raises(ParseError) as exc_info:
        with ParseContext("config.toml", data=FALLBACK_SOURCE):
            raise msgspec.ValidationError(
                "Expected `str`, got `int` - at `$.server.tls.cert`"
            )
    assert exc_info.value.line == 1
