import msgspec


class Config(msgspec.Struct):
    host: str
    port: int


class Nested(msgspec.Struct):
    server: Config
