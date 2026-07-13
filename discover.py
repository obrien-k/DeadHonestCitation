#!/usr/bin/env python3
"""Deprecated shim — discovery now lives in the dead_honest_citation package.

Use `dhc discover domain|recover|save`; run `pip install -e .` once to get the
`dhc` command. This wrapper just translates the old flags and delegates.
"""

import sys

from dead_honest_citation.cli import app


def main():
    args = list(sys.argv[1:])
    if "--save" in args:
        i = args.index("--save")
        new = ["discover", "save", args[i + 1]]
    elif "--recover" in args:
        i = args.index("--recover")
        new = ["discover", "recover", args[i + 1], *args[:i], *args[i + 2 :]]
    else:
        new = ["discover", "domain", *args]
    print(
        f"note: discover.py is deprecated — use `dhc discover {new[1]}` instead.", file=sys.stderr
    )
    app(new)


if __name__ == "__main__":
    main()
