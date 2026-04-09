from parse_errors.source_map import build_source_map, Location, Entry, closest_entry


def test_build_toml():
    # This isn't an exhaustive test of the toml source mapper, just as something
    # a minimal example that lets us exercise str/bytes
    sm1 = build_source_map("""\
x=1
b='foo'
""", fmt="toml")
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
    sm = build_source_map("""\
[section]
key = "val"
""", fmt="toml")
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
    sm = build_source_map("""\
[[items]]
name = "a"
[[items]]
name = "b"
""", fmt="toml")
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
    sm = build_source_map('''\
"foo" = 1
'bar' = 2
''', fmt="toml")
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
        "[[fruits]]\nname=\"apple\"\n[fruits.details]\ncolor=\"red\"\n", fmt="toml"
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
