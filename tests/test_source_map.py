import pytest

from parse_errors.source_map import (
    build_source_map,
    closest_entry,
    decode_error_message,
    Entry,
    locate_decode_error,
    locate_pointer,
    Location,
    SourceMap,
)


def test_build_toml():
    # This isn't an exhaustive test of the toml source mapper, just as something
    # a minimal example that lets us exercise str/bytes
    sm1 = build_source_map(
        """\
x=1
b='foo'
""",
        fmt="toml",
    )
    assert sm1 == {
        "": Entry(
            value_start=Location(line=0, column=0, position=0),
            value_end=Location(line=2, column=0, position=12),
        ),
        "/x": Entry(
            value_start=Location(line=0, column=2, position=2),
            value_end=Location(line=0, column=3, position=3),
            key_start=Location(line=0, column=0, position=0),
            key_end=Location(line=0, column=1, position=1),
        ),
        "/b": Entry(
            value_start=Location(line=1, column=2, position=6),
            value_end=Location(line=1, column=7, position=11),
            key_start=Location(line=1, column=0, position=4),
            key_end=Location(line=1, column=1, position=5),
        ),
    }
    sm2 = build_source_map(b"x=1\nb='foo'\n", fmt="toml")
    # Only ASCII, so str vs bytes should be the same
    assert sm1 == sm2


def test_closest_entry():
    sm = {"": "root", "/foo": "foo", "/foo/1": "idx 1", "/foo/1/bar": "bar"}
    assert closest_entry(sm, "/baz") == "root"
    assert closest_entry(sm, "/foo") == "foo"
    assert closest_entry(sm, "/foo/0") == "foo"
    assert closest_entry(sm, "/foo/1") == "idx 1"


def test_build_toml_table():
    sm = build_source_map(
        """\
[section]
key = "val"
""",
        fmt="toml",
    )
    assert sm[""] == Entry(
        value_start=Location(line=0, column=0, position=0),
        value_end=Location(line=2, column=0, position=22),
    )
    assert sm["/section"] == Entry(
        value_start=Location(line=0, column=0, position=0),
        value_end=Location(line=2, column=0, position=22),
    )
    assert sm["/section/key"] == Entry(
        value_start=Location(line=1, column=6, position=16),
        value_end=Location(line=1, column=11, position=21),
        key_start=Location(line=1, column=0, position=10),
        key_end=Location(line=1, column=3, position=13),
    )


def test_build_toml_aot():
    sm = build_source_map(
        """\
[[items]]
name = "a"
[[items]]
name = "b"
""",
        fmt="toml",
    )
    assert sm["/items"] == Entry(
        value_start=Location(line=0, column=0, position=0),
        value_end=Location(line=0, column=0, position=0),
    )
    assert sm["/items/0"] == Entry(
        value_start=Location(line=0, column=0, position=0),
        value_end=Location(line=2, column=0, position=21),
    )
    assert sm["/items/0/name"] == Entry(
        value_start=Location(line=1, column=7, position=17),
        value_end=Location(line=1, column=10, position=20),
        key_start=Location(line=1, column=0, position=10),
        key_end=Location(line=1, column=4, position=14),
    )
    assert sm["/items/1"] == Entry(
        value_start=Location(line=2, column=0, position=21),
        value_end=Location(line=4, column=0, position=42),
    )
    assert sm["/items/1/name"] == Entry(
        value_start=Location(line=3, column=7, position=38),
        value_end=Location(line=3, column=10, position=41),
        key_start=Location(line=3, column=0, position=31),
        key_end=Location(line=3, column=4, position=35),
    )


def test_build_toml_inline_table():
    sm = build_source_map("x = {a = 1}\n", fmt="toml")
    assert sm["/x"] == Entry(
        value_start=Location(line=0, column=4, position=4),
        value_end=Location(line=0, column=11, position=11),
        key_start=Location(line=0, column=0, position=0),
        key_end=Location(line=0, column=1, position=1),
    )
    assert sm["/x/a"] == Entry(
        value_start=Location(line=0, column=9, position=9),
        value_end=Location(line=0, column=10, position=10),
        key_start=Location(line=0, column=5, position=5),
        key_end=Location(line=0, column=6, position=6),
    )


def test_build_toml_dotted_key():
    sm = build_source_map("a.b = 1\n", fmt="toml")
    assert sm["/a/b"] == Entry(
        value_start=Location(line=0, column=6, position=6),
        value_end=Location(line=0, column=7, position=7),
        key_start=Location(line=0, column=0, position=0),
        key_end=Location(line=0, column=3, position=3),
    )


def test_build_toml_quoted_keys():
    sm = build_source_map(
        """\
"foo" = 1
'bar' = 2
""",
        fmt="toml",
    )
    assert sm["/foo"] == Entry(
        value_start=Location(line=0, column=8, position=8),
        value_end=Location(line=0, column=9, position=9),
        key_start=Location(line=0, column=0, position=0),
        key_end=Location(line=0, column=5, position=5),
    )
    assert sm["/bar"] == Entry(
        value_start=Location(line=1, column=8, position=18),
        value_end=Location(line=1, column=9, position=19),
        key_start=Location(line=1, column=0, position=10),
        key_end=Location(line=1, column=5, position=15),
    )


def test_build_toml_aot_nested_table():
    sm = build_source_map(
        '[[fruits]]\nname="apple"\n[fruits.details]\ncolor="red"\n', fmt="toml"
    )
    assert "/fruits/0/details" in sm
    assert sm["/fruits/0/details/color"] == Entry(
        value_start=Location(line=3, column=6, position=47),
        value_end=Location(line=3, column=11, position=52),
        key_start=Location(line=3, column=0, position=41),
        key_end=Location(line=3, column=5, position=46),
    )


def test_closest_entry_fallthrough():
    sm = {}
    assert closest_entry(sm, "/baz") is None


_JSON_DOC = '{"a": {"b": [1, 2, {"c": 3}]}, "x": 1}'
_YAML_DOC = "a:\n  b:\n    - 1\n    - 2\n    - c: 3\nx: 1\n"

_JSON_YAML_POINTERS = [
    "",
    "/a",
    "/a/b",
    "/a/b/0",
    "/a/b/2",
    "/a/b/2/c",
    "/x",
    "/nonexistent",
    "/a/b/99",
]

# A plain array is a leaf in TOML -- only [[array-of-tables]] elements are
# individually addressable -- so it needs its own doc/pointer shape rather
# than sharing the json/yaml ones above.
_TOML_DOC = (
    "top = 1\n"
    '[[items]]\nname = "a"\n'
    '[[items]]\nname = "b"\n'
    # A [dotted.table] header right after an array-of-tables element nests
    # under that most-recently-opened element, even though tree-sitter
    # parses it as a sibling, not a child, of the [[items]] node.
    '[items.detail]\ncolor = "red"\n'
    "nested = { deep = { deeper = 5 } }\n"
    "[[other.sub]]\nbar = 2\n"
    "[[other.sub]]\nbar = 3\n"
)

_TOML_POINTERS = [
    "",
    "/top",
    "/items",
    "/items/0",
    "/items/0/name",
    "/items/1",
    "/items/1/name",
    "/items/1/detail",
    "/items/1/detail/color",
    "/items/1/detail/nested/deep/deeper",
    "/items/1/detail/nonexistent",
    "/items/99",
    "/other/sub/0/bar",
    "/other/sub/1/bar",
    "/other/sub/2/bar",
    "/nonexistent",
    "/items/1/name/toofar",  # past a scalar pair value
    "/items/1/detail/nested/deep/deeper/toofar",  # past a scalar inside an inline_table
]

# (fmt, doc, its own pointer list) -- the one place each format's example
# document and matching pointers are paired up, so no test looks either up
# by fmt at run time.
_FMT_DOC_POINTERS = [
    ("json", _JSON_DOC, _JSON_YAML_POINTERS),
    ("yaml", _YAML_DOC, _JSON_YAML_POINTERS),
    ("toml", _TOML_DOC, _TOML_POINTERS),
]

# Flattened to one (fmt, doc, pointer) row per pointer, for tests that check
# one pointer per case rather than iterating a whole document's list.
_FMT_DOC_POINTER = [
    (fmt, doc, pointer)
    for fmt, doc, pointers in _FMT_DOC_POINTERS
    for pointer in pointers
]

# Grows over time: add a document here whenever a bug is found, so the
# regression is covered by a full-map/locate_pointer comparison over every
# pointer that document has, not just the specific pointer that was wrong.
_EXAMPLE_DOCS = [(fmt, doc) for fmt, doc, _ in _FMT_DOC_POINTERS]


@pytest.mark.parametrize("fmt,doc", _EXAMPLE_DOCS)
def test_locate_pointer_matches_every_full_map_entry(fmt, doc):
    """locate_pointer() must agree with build_source_map() + a direct lookup
    (not just closest_entry()'s fallback) for every pointer the full map
    actually has an entry for."""
    full = build_source_map(doc, fmt=fmt)
    for pointer, expected in full.items():
        assert locate_pointer(doc, fmt, pointer) == expected, pointer


@pytest.mark.parametrize("fmt,doc,pointer", _FMT_DOC_POINTER)
def test_locate_pointer_matches_closest_entry(fmt, doc, pointer):
    full = build_source_map(doc, fmt=fmt)
    assert locate_pointer(doc, fmt, pointer) == closest_entry(full, pointer)


@pytest.mark.parametrize("fmt", ["json", "toml", "yaml"])
def test_locate_pointer_empty_document(fmt):
    full = build_source_map("", fmt=fmt)
    assert locate_pointer("", fmt, "/x") == closest_entry(full, "/x")


def test_locate_pointer_unknown_format():
    with pytest.raises(ValueError, match="Unknown format"):
        locate_pointer("{}", "ini", "/x")


@pytest.mark.parametrize("fmt,doc,pointers", _FMT_DOC_POINTERS)
def test_source_map_matches_locate_pointer(fmt, doc, pointers):
    sm = SourceMap(doc, fmt)
    for pointer in pointers:
        assert sm.locate(pointer) == locate_pointer(doc, fmt, pointer)


def _submodule(fmt):
    import importlib

    return importlib.import_module(f"parse_errors.{fmt}_source_map")


def _count_parse_calls(mod, monkeypatch):
    real_parse = mod._parse
    calls = []

    def counting_parse(source):
        calls.append(source)
        return real_parse(source)

    monkeypatch.setattr(mod, "_parse", counting_parse)
    return calls


@pytest.mark.parametrize("fmt,doc,pointers", _FMT_DOC_POINTERS)
def test_source_map_parses_once(fmt, doc, pointers, monkeypatch):
    calls = _count_parse_calls(_submodule(fmt), monkeypatch)

    sm = SourceMap(doc, fmt)
    for pointer in pointers:
        sm.locate(pointer)

    assert len(calls) == 1


@pytest.mark.parametrize("fmt", ["json", "toml", "yaml"])
def test_source_map_empty_document_parses_once(fmt, monkeypatch):
    calls = _count_parse_calls(_submodule(fmt), monkeypatch)

    full = build_source_map("", fmt=fmt)
    sm = SourceMap("", fmt)
    assert sm.locate("/x") == closest_entry(full, "/x")
    assert sm.locate("/y") == closest_entry(full, "/y")

    assert len(calls) == 1


# --- locate_decode_error / decode_error_message ---
#
# Exercised against synthetic exceptions rather than real json/tomllib/yaml
# errors, since which attributes a real one carries depends on the
# interpreter (tomllib.TOMLDecodeError only sets .lineno/.colno from Python
# 3.14 on) and the installed library version -- these test the four branches
# directly, independent of either.


class _FakeError(Exception):
    pass


def test_locate_decode_error_prefers_lineno_colno():
    exc = _FakeError("ignored")
    exc.lineno, exc.colno = 3, 5
    assert locate_decode_error(exc) == Location(line=2, column=4, position=0)


def test_locate_decode_error_uses_problem_mark_without_lineno():
    class FakeMark:
        line, column = 2, 6  # already 0-based, like PyYAML's Mark

    exc = _FakeError("mapping values are not allowed here")
    exc.problem_mark = FakeMark()
    assert locate_decode_error(exc) == Location(line=2, column=6, position=0)


def test_locate_decode_error_falls_back_to_message_regex():
    exc = _FakeError(
        "Expected ']' at the end of a table declaration (at line 4, column 9)"
    )
    assert locate_decode_error(exc) == Location(line=3, column=8, position=0)


def test_locate_decode_error_returns_none_without_any_signal():
    assert locate_decode_error(ValueError("no position here")) is None


def test_decode_error_message_prefers_msg():
    exc = _FakeError('multi\nline\n"noise"')
    exc.msg = "Expected value"
    assert decode_error_message(exc) == "Expected value"


def test_decode_error_message_prefers_problem_over_str():
    exc = _FakeError(
        'mapping values are not allowed here\n  in "<file>", line 2, column 7:\n      port: 1\n          ^'
    )
    exc.problem = "mapping values are not allowed here"
    assert decode_error_message(exc) == "mapping values are not allowed here"


def test_decode_error_message_falls_back_to_str():
    assert decode_error_message(ValueError("plain message")) == "plain message"
