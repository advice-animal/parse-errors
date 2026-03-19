import pytest
import msgspec

from parse_errors import ParseContext, ParseError

from ._types import Config, Nested


JSON_GOOD = b'{"host": "localhost", "port": 8080}'
JSON_BAD = b'{"host": "localhost", "port": "not-an-int"}'
JSON_NESTED_BAD = b'{"server": {"host": "localhost", "port": "not-an-int"}}'

JSON_SOURCE = """\
{
  "host": "localhost",
  "port": "not-an-int"
}
"""

JSON_NESTED_SOURCE = """\
{
  "server": {
    "host": "localhost",
    "port": "not-an-int"
  }
}
"""


def test_json_no_error():
    with ParseContext("config.json", data=JSON_GOOD.decode()):
        msgspec.json.decode(JSON_GOOD, type=Config)


def test_json_non_jsonpath_exception_passes_through():
    with pytest.raises(ZeroDivisionError):
        with ParseContext("config.json", data=JSON_SOURCE):
            raise ZeroDivisionError("oops")


def test_json_raises_parse_error():
    with pytest.raises(ParseError) as exc_info:
        with ParseContext("config.json", data=JSON_SOURCE):
            msgspec.json.decode(JSON_SOURCE.encode(), type=Config)

    err = exc_info.value
    assert err.filename == "config.json"
    assert err.line == 3
    assert str(err) == "config.json:3:11: Expected `int`, got `str` - at `$.port`"


def test_json_nested_raises_parse_error():
    with pytest.raises(ParseError) as exc_info:
        with ParseContext("config.json", data=JSON_NESTED_SOURCE):
            msgspec.json.decode(JSON_NESTED_SOURCE.encode(), type=Nested)

    err = exc_info.value
    assert (
        str(err) == "config.json:4:13: Expected `int`, got `str` - at `$.server.port`"
    )


def test_json_bytes_data():
    with pytest.raises(ParseError) as exc_info:
        with ParseContext("config.json", data=JSON_SOURCE.encode()):
            msgspec.json.decode(JSON_SOURCE.encode(), type=Config)

    assert (
        str(exc_info.value)
        == "config.json:3:11: Expected `int`, got `str` - at `$.port`"
    )


def test_json_original_exception_is_cause():
    with pytest.raises(ParseError) as exc_info:
        with ParseContext("config.json", data=JSON_SOURCE):
            msgspec.json.decode(JSON_SOURCE.encode(), type=Config)

    assert isinstance(exc_info.value.__cause__, msgspec.ValidationError)
