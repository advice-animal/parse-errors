from parse_errors.source_map import build_source_map, Location, Entry, closest_entry


def test_build_toml():
    sm1 = build_source_map("x=1\nb='foo'\n", fmt="toml")
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
    # Only ascii, so str vs bytes should be the same
    assert sm1 == sm2


def test_closest_entry():
    sm = {"": "root", "/foo": "foo", "/foo/1": "idx 1", "/foo/1/bar": "bar"}
    assert closest_entry(sm, "/baz") == "root"
    assert closest_entry(sm, "/foo") == "foo"
    assert closest_entry(sm, "/foo/0") == "foo"
    assert closest_entry(sm, "/foo/1") == "idx 1"


def test_closest_entry_fallthrough():
    sm = {}
    assert closest_entry(sm, "/baz") is None
