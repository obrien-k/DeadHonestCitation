#!/usr/bin/env python3
"""Deprecated shim — staging now lives in the dead_honest_citation package.

Use `dhc stage` / `dhc promote` / `dhc menu`; run `pip install -e .` once to get
the `dhc` command. This wrapper just translates the old flags and delegates.
"""

import sys

from dead_honest_citation.cli import app


def main():
    args = list(sys.argv[1:])
    # The old parser took --repo before the subcommand; dhc takes it after.
    repo = None
    if args and args[0] == "--repo" and len(args) > 1:
        repo, args = args[1], args[2:]
    elif args and args[0].startswith("--repo="):
        repo, args = args[0].split("=", 1)[1], args[1:]
    new = args + (["--repo", repo] if repo else [])
    cmd = new[0] if new else "stage"
    print(f"note: to_jekyll.py is deprecated — use `dhc {cmd}` instead.", file=sys.stderr)
    app(new)


if __name__ == "__main__":
    main()
