#!/usr/bin/env python3
"""Deprecated shim — the guided flow now lives in the dead_honest_citation package.

Use `dhc wizard`; run `pip install -e .` once to get the `dhc` command.
"""

import sys

from dead_honest_citation.cli import app


def main():
    print("note: wizard.py is deprecated — use `dhc wizard` instead.", file=sys.stderr)
    app(["wizard"])


if __name__ == "__main__":
    main()
