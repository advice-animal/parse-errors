import msgspec
import pytest
import yaml

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


# A raw (non-msgspec) PyYAML syntax error, failing on line 2 rather than
# line 1 so an off-by-one bug can't hide. PyYAML's own str(exc) is multi-line
# (the problem, then a quoted source excerpt with a caret under the column),
# which .problem/.problem_mark avoid embedding into the single-line message.

RAW_YAML_SYNTAX_ERROR = "host: x\n  port: 1\n"


def test_yaml_raw_decode_error_location():
    with pytest.raises(ParseError) as exc_info:
        with ParseContext("config.yaml", data=RAW_YAML_SYNTAX_ERROR):
            yaml.safe_load(RAW_YAML_SYNTAX_ERROR)
    err = exc_info.value
    assert err.line == 2
    assert err.column == 7
    assert str(err) == "config.yaml:2:7: mapping values are not allowed here"
