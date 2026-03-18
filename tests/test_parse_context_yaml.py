import pytest
import msgspec

from parse_errors import ParseContext, ParseError

from ._types import Config, Nested

YAML_SOURCE = """\
host: localhost
port: not-an-int
"""

YAML_NESTED_SOURCE = """\
server:
  host: localhost
  port: not-an-int
"""


def test_yaml_raises_parse_error():
    with pytest.raises(ParseError) as exc_info:
        with ParseContext("config.yaml", data=YAML_SOURCE):
            msgspec.yaml.decode(YAML_SOURCE.encode(), type=Config)

    err = exc_info.value
    assert err.filename == "config.yaml"
    assert err.line == 2
    assert str(err) == "config.yaml:2:7: Expected `int`, got `str` - at `$.port`"


def test_yaml_bytes_data():
    with pytest.raises(ParseError) as exc_info:
        with ParseContext("config.yaml", data=YAML_SOURCE.encode()):
            msgspec.yaml.decode(YAML_SOURCE.encode(), type=Config)

    assert (
        str(exc_info.value)
        == "config.yaml:2:7: Expected `int`, got `str` - at `$.port`"
    )


def test_yaml_nested_raises_parse_error():
    with pytest.raises(ParseError) as exc_info:
        with ParseContext("config.yaml", data=YAML_NESTED_SOURCE):
            msgspec.yaml.decode(YAML_NESTED_SOURCE.encode(), type=Nested)

    err = exc_info.value
    assert str(err) == "config.yaml:3:9: Expected `int`, got `str` - at `$.server.port`"
