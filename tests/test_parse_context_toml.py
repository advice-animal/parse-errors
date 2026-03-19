from parse_errors import toml_source_map


TRICKY = """\
# comment
"quoted key" = 42
dotted.key   = true      # inline comment after value

[server]                 # inline comment on table header
host = "localhost"
path = "/etc/ssl/key.pem"   # value contains key substring
"""


def test_toml_quoted_key_present():
    sm = toml_source_map.calculate(TRICKY)
    assert "/quoted key" in sm, f"missing '/quoted key', got: {sorted(sm)}"


def test_toml_val_end_excludes_comment():
    sm = toml_source_map.calculate(TRICKY)
    entry = sm["/dotted/key"]
    val = TRICKY[entry.value_start.position : entry.value_end.position]
    assert val == "true", f"got {val!r}"


# --- _escape: keys containing / and ~ ---

ESCAPE_SOURCE = """\
"path/to/thing" = 1
"tilde~zero" = 2
"""


def test_toml_escape_slash_in_key():
    sm = toml_source_map.calculate(ESCAPE_SOURCE)
    assert "/path~1to~1thing" in sm


def test_toml_escape_tilde_in_key():
    sm = toml_source_map.calculate(ESCAPE_SOURCE)
    assert "/tilde~0zero" in sm


# --- non-consecutive array-of-tables with intermediate sub-table ---

AOT_SOURCE = """\
[[fruits]]
name = "apple"

[fruits.details]
color = "red"

[bar]

[[fruits]]
name = "banana"
"""


def test_toml_nonconsecutive_aot():
    sm = toml_source_map.calculate(AOT_SOURCE)
    # [fruits.details] appears after the first [[fruits]], so it belongs to fruits[0]
    assert "/fruits/0/details" in sm, f"got: {sorted(sm)}"
    assert "/fruits/0/details/color" in sm
    # The erroneous flat entry must not exist
    assert "/fruits/details" not in sm
