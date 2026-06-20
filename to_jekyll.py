#!/usr/bin/env python3
"""
Move converted posts from this tool's output/ into a Jekyll site repo.

  stage    Copy posts into the repo's _drafts/ as <slug>.md (no date prefix, the
           Jekyll-draft convention; the date stays in front matter), optionally
           inject a source tag, and copy each post's image assets.
  promote  Move a draft into _posts/<date>-<slug>.md, reading the date from the
           post's own front matter. This is the "trickle a draft into _posts" step.

The Jekyll repo path and the injected source tag default from the environment —
set ARCHIVE2MD_JEKYLL_REPO and ARCHIVE2MD_SOURCE_TAG, or drop them in a .env file
at the repo root (see .env.example). --repo / --tag override either.

Examples:
  python to_jekyll.py stage output/_posts/2018-*.md        # stage to _drafts
  python to_jekyll.py stage --to-posts output/_posts/2018-08-21-nationwide-us-prison-strike-8-21-9-9.md
  python to_jekyll.py promote unix-as-an-ide               # _drafts -> _posts
"""

import argparse
import glob
import os
import re
import shutil
import sys


def _load_dotenv(path=None):
    """Populate os.environ from a simple KEY=VALUE .env file at the repo root,
    without adding a dependency. Existing environment variables win; lines that
    are blank or start with '#' are ignored. Quotes around values are stripped."""
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


_load_dotenv()

# Personal defaults live in the environment / .env, not in the source. Fall back to
# neutral placeholders so a fresh clone runs without leaking anyone's paths or tags.
DEFAULT_REPO = os.path.expanduser(os.environ.get("ARCHIVE2MD_JEKYLL_REPO") or "~/jekyll-site")
DEFAULT_TAG = os.environ.get("ARCHIVE2MD_SOURCE_TAG", "")
ASSETS_REL = os.path.join("assets", "img", "blog", "posts")
OUT_POSTS = os.path.join("output", "_posts")
OUT_ASSETS = os.path.join("output", ASSETS_REL)

DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)\.md$")
FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.S)


def split_name(path):
    """Return (date_or_None, slug) parsed from a YYYY-MM-DD-slug.md filename."""
    name = os.path.basename(path)
    m = DATE_RE.match(name)
    if m:
        return m.group(1), m.group(2)
    return None, re.sub(r"\.md$", "", name)


def front_matter_date(text):
    m = re.search(r"^date:\s*(\d{4}-\d{2}-\d{2})", text, re.M)
    return m.group(1) if m else None


def inject_tag(text, tag):
    """Add `tag` to the YAML tags: block (creating the block if absent)."""
    if not tag:
        return text
    fm = FM_RE.match(text)
    if not fm:
        return text
    block = fm.group(1)
    if re.search(rf"^\s*-\s*{re.escape(tag)}\s*$", block, re.M):
        return text  # already tagged
    lines, out, injected = block.split("\n"), [], False
    for line in lines:
        out.append(line)
        if re.match(r"^tags:\s*$", line):
            out.append(f"  - {tag}")
            injected = True
    if not injected:
        out += ["tags:", f"  - {tag}"]
    return text[: fm.start()] + "---\n" + "\n".join(out) + "\n---\n" + text[fm.end() :]


def copy_assets(slug, repo):
    src = os.path.join(OUT_ASSETS, slug)
    if not os.path.isdir(src):
        return 0
    dst = os.path.join(repo, ASSETS_REL, slug)
    os.makedirs(dst, exist_ok=True)
    n = 0
    for f in os.listdir(src):
        shutil.copy2(os.path.join(src, f), os.path.join(dst, f))
        n += 1
    return n


def stage_one(path, repo, tag=DEFAULT_TAG, to_posts=False, force=False):
    """Stage one converted post into repo/_drafts (or _posts with to_posts), injecting
    the tag and copying assets. Returns (dest_path, asset_count), or (None, 0) if the
    destination already exists and force is False."""
    date, slug = split_name(path)
    with open(path, encoding="utf-8") as f:
        text = inject_tag(f.read(), tag)
    target_dir = os.path.join(repo, "_posts" if to_posts else "_drafts")
    os.makedirs(target_dir, exist_ok=True)
    if to_posts:
        out_name = f"{date or front_matter_date(text) or '0000-00-00'}-{slug}.md"
    else:
        out_name = f"{slug}.md"
    dest = os.path.join(target_dir, out_name)
    if os.path.exists(dest) and not force:
        return None, 0
    with open(dest, "w", encoding="utf-8") as f:
        f.write(text)
    return dest, copy_assets(slug, repo)


def promote_one(slug, repo):
    """Move repo/_drafts/<slug>.md → repo/_posts/<date>-<slug>.md (date from front
    matter). Returns the destination path, or None if no such draft exists."""
    src = os.path.join(repo, "_drafts", f"{slug}.md")
    if not os.path.isfile(src):
        return None
    with open(src, encoding="utf-8") as f:
        d = front_matter_date(f.read()) or "0000-00-00"
    os.makedirs(os.path.join(repo, "_posts"), exist_ok=True)
    dest = os.path.join(repo, "_posts", f"{d}-{slug}.md")
    shutil.move(src, dest)
    return dest


def parse_selection(sel, n):
    """Parse '1,3 5', '2-4', or 'all' into a sorted list of 1-based indices in 1..n."""
    sel = sel.strip().lower()
    if sel in ("all", "*"):
        return list(range(1, n + 1))
    picked = set()
    for part in re.split(r"[,\s]+", sel):
        if "-" in part:
            a, b = part.split("-", 1)
            if a.isdigit() and b.isdigit():
                picked.update(range(int(a), int(b) + 1))
        elif part.isdigit():
            picked.add(int(part))
    return sorted(i for i in picked if 1 <= i <= n)


def cmd_stage(args):
    files = args.files or sorted(glob.glob(os.path.join(OUT_POSTS, "*.md")))
    if not files:
        print("No posts to stage.")
        return
    for path in files:
        dest, n = stage_one(path, args.repo, args.tag, args.to_posts, args.force)
        if dest is None:
            print(f"  ↷ exists, skip: {os.path.basename(path)}")
        else:
            print(f"  ✓ {os.path.relpath(dest, args.repo)}  (+{n} asset(s))")


def cmd_promote(args):
    dest = promote_one(args.slug, args.repo)
    if dest is None:
        print(f"✗ No draft at _drafts/{args.slug}.md")
        sys.exit(1)
    print(f"✓ promoted: _drafts/{args.slug}.md → {os.path.relpath(dest, args.repo)}")


def cmd_menu(args):
    """List drafts and interactively promote a chosen subset into _posts."""
    drafts = sorted(glob.glob(os.path.join(args.repo, "_drafts", "*.md")))
    if not drafts:
        print("No drafts to promote.")
        return
    print("Drafts in _drafts/:\n")
    for i, d in enumerate(drafts, 1):
        with open(d, encoding="utf-8") as f:
            date = front_matter_date(f.read()) or "????-??-??"
        print(f"  {i:2}. [{date}]  {os.path.basename(d)[:-3]}")
    try:
        sel = input("\nPromote which into _posts? (e.g. 1,3 or 2-4 or 'all'; blank to cancel): ")
    except EOFError:
        sel = ""
    idxs = parse_selection(sel, len(drafts))
    if not idxs:
        print("Cancelled.")
        return
    for i in idxs:
        slug = os.path.basename(drafts[i - 1])[:-3]
        dest = promote_one(slug, args.repo)
        print(f"  ✓ {slug} → {os.path.relpath(dest, args.repo)}")


def main():
    p = argparse.ArgumentParser(description="Stage/promote converted posts into a Jekyll repo.")
    p.add_argument(
        "--repo", default=DEFAULT_REPO, help=f"Jekyll repo path (default: {DEFAULT_REPO})"
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("stage", help="Copy posts into _drafts/ (or _posts/ with --to-posts).")
    s.add_argument("files", nargs="*", help="Post .md files (default: all of output/_posts/).")
    s.add_argument(
        "--tag",
        default=DEFAULT_TAG,
        help="Source tag to inject (default: $ARCHIVE2MD_SOURCE_TAG, "
        f'currently {DEFAULT_TAG!r}; "" to skip).',
    )
    s.add_argument(
        "--to-posts", action="store_true", help="Write straight to _posts/ with a date prefix."
    )
    s.add_argument("--force", action="store_true", help="Overwrite an existing destination file.")
    s.set_defaults(func=cmd_stage)

    pr = sub.add_parser("promote", help="Move a draft into _posts/ by its front-matter date.")
    pr.add_argument("slug", help="Draft slug (filename without .md).")
    pr.set_defaults(func=cmd_promote)

    mn = sub.add_parser("menu", help="Interactively list drafts and promote a chosen subset.")
    mn.set_defaults(func=cmd_menu)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
