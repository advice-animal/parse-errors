if __name__ == "__main__":  # pragma: no cover
    import sys
    from . import calculate

    source = open(sys.argv[1]).read()
    for pointer, entry in calculate(source).items():
        print(f"{pointer!r:40s} {entry}")
