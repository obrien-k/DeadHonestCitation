#!/usr/bin/env python3
"""Deprecated shim — the converter now lives in the dead_honest_citation package.

Use `dhc convert` (and `dhc clean` / `dhc prune`); run `pip install -e .` once to
get the `dhc` command. This wrapper just translates the old flags and delegates.
"""

import sys

from dead_honest_citation.cli import app


def main():
    args = list(sys.argv[1:])
    if "--clean" in args:
        new = ["clean"] + (["-y"] if ("-y" in args or "--yes" in args) else [])
    elif "--prune" in args:
        new = ["prune"]
    else:
        new = ["convert", *args]
    print(f"note: index.py is deprecated — use `dhc {new[0]}` instead.", file=sys.stderr)
    app(new)


if __name__ == "__main__":
    main()
