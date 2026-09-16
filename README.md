# parse-errors

`parse-errors` improves the errors you get when parsing config files (JSON,
TOML, YAML).  Instead of a bare exception with a vague message, you get a
`ParseError` that includes the filename, line number, and column — so you can
point users straight to the problem.

It understands msgspec validation errors and TOML syntax errors, mapping them
back to the line of config they came from.  Even unrelated exceptions get the
filename attached.

## Usage

Wrap your parse/validate call in `ParseContext`:

```python
import msgspec
import tomllib
from parse_errors import ParseContext

class Config(msgspec.Struct):
    host: str
    port: int

filename = "config.toml"

with open(filename, "rb") as f:
    raw = f.read()

with ParseContext(filename, data=raw, format="toml"):
    data = tomllib.loads(raw.decode())
    config = msgspec.convert(data, Config)
```

`ParseContext` will intercept exceptions. If it can analyze them for precise
locations, it will raise a `ParseError` exception with the original exception as
the cause. If it can't find location information, the original exception is
raised as-is. No exceptions are swallowed.

As a concrete example, if the `msgspec.convert` raises because `port` is a
string instead of an integer, you get something like:

```
parse_errors.ParseError: config.toml:3:8: Expected `int`, got `str` - at `$.port`
```

rather than the bare `msgspec.ValidationError` with no location.

`ParseContext` also handles errors from TOML and other decoders that include
positional information (`at line N, column M`) and re-raises them in the same
`filename:line:col: message` format.

## API

```python
from parse_errors import ParseContext, ParseError
from parse_errors.source_map import SourceMap, build_source_map, locate_pointer
```

**`ParseContext(filename, *, data=None, format=None)`** — context manager.

- `filename`: path to the file being parsed (used in error messages and to
  infer the format from the extension when `format` is omitted).
- `data`: the file contents as `str` or `bytes`.  If omitted, the file is read
  from disk automatically when location info is needed.
- `format`: `"json"`, `"toml"`, or `"yaml"`.  Inferred from `filename`'s
  extension when not supplied.

**`ParseError`** — the exception raised inside the context.  Has attributes
`filename`, `line` (1-based), and `column` (1-based).

**`locate_pointer(source, fmt, pointer)`** — returns the best source-map entry
for one JSON Pointer without building a full map.  `fmt` is `"json"`,
`"toml"`, or `"yaml"`; `source` is `str` or UTF-8 `bytes`; `pointer` uses RFC
6901 escaping.  If the exact pointer is not present, the result matches
`closest_entry(build_source_map(source, fmt), pointer)`: the nearest enclosing
value when one exists, otherwise `None`.

**`SourceMap(source, fmt)`** — caches the parsed document for repeated targeted
lookups.  Use `SourceMap(...).locate(pointer)` when several errors in the same
document need locations.  It still avoids constructing a full pointer-to-entry
map.

**`build_source_map(source, fmt)`** — builds the full pointer-to-location map.
This is useful when callers need many arbitrary entries or need to inspect all
locations.

**Warning:** source-map helpers locate nodes in a document; they are not
validating parsers.  JSON and TOML location support uses tree-sitter so it can
return a location from a syntax tree even when a real decoder would reject the
source.  Parse or validate the document with your normal parser first, then use
these helpers only to map known error paths back to source locations.

# Version Compat

This library is compatile with Python 3.10+, but should be linted under the
newest stable version.

# Versioning

This library follows [meanver](https://meanver.org/) which basically means
[semver](https://semver.org/) along with a promise to rename when the major
version changes.

# License

parse-errors is copyright [Tim Hatch](https://timhatch.com/), and licensed under
the MIT license.  See the `LICENSE` file for details.
