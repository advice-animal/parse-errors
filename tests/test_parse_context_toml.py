import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

import msgspec
import pytest
from msgspec.toml import decode as decode_toml

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
    with pytest.raises(ParseError, match=r"^config.toml: ValueError\('foo'\)$"):
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


INCOMPLETE_TOML = """\

[foo
"""


def test_toml_decode_raises_decode_error():
    with pytest.raises(ParseError, match="config.toml:2:5: Expected"):
        with ParseContext("config.toml", data=INCOMPLETE_TOML):
            decode_toml(INCOMPLETE_TOML, type=Config)


# A raw (non-msgspec) tomllib.loads() syntax error, failing on line 2 rather
# than line 1 so an off-by-one or unconditional-line-1 bug can't hide. The
# message text itself isn't asserted verbatim: tomllib sets .msg (a clean,
# non-redundant message) only from Python 3.14 on and on tomli's backport;
# stdlib tomllib on 3.11-3.13 has no .msg, so decode_error_message() falls
# back to str(exc), which already has the position folded in.

RAW_TOML_SYNTAX_ERROR = 'host = "x"\nport ! 1\n'


def test_toml_raw_decode_error_location():
    with pytest.raises(ParseError) as exc_info:
        with ParseContext("config.toml", data=RAW_TOML_SYNTAX_ERROR):
            tomllib.loads(RAW_TOML_SYNTAX_ERROR)
    err = exc_info.value
    assert err.line == 2
    assert err.column == 6
    assert str(err).startswith(
        "config.toml:2:6: Expected '=' after a key in a key/value pair"
    )


def test_toml_raw_decode_error_at_end_of_document(monkeypatch):
    # tomllib.TOMLDecodeError phrases a failure at EOF as "(at end of
    # document)" instead of "(at line N, column N)" -- the regex fallback
    # only matches the latter, but .lineno/.colno are set either way on the
    # Python versions/backports that set them at all (locate_decode_error's
    # own tests cover the ones that don't). A plain stand-in with those
    # attributes set is enough -- locate_decode_error()/decode_error_message()
    # only duck-type the attributes, and this doesn't depend on which
    # tomllib is running here, or trip its real class's own constructor
    # (whose deprecated single-string-arg form warns).
    class FakeTOMLDecodeError(Exception):
        pass

    def fake_loads(s):
        exc = FakeTOMLDecodeError("Invalid value (at end of document)")
        exc.lineno, exc.colno, exc.msg = 1, 8, "Invalid value"
        raise exc

    monkeypatch.setattr(tomllib, "loads", fake_loads)
    with pytest.raises(ParseError, match=r"^config\.toml:1:8: Invalid value$"):
        with ParseContext("config.toml", data="port = "):
            tomllib.loads("port = ")
