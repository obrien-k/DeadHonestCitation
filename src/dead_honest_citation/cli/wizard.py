"""dhc wizard — guided, interactive archive→Jekyll flow.

1. pick source(s) — a URL/paths file, a folder of saved .html, or one path/URL
2. convert them
3. review each new post — keep as draft, send straight to a post, skip, or leave
4. stage the kept ones into the Jekyll repo
5. optionally open the promote menu to push drafts into _posts
"""

import glob
import os
import re
import shutil

from .. import config, staging
from ..adapters import PLATFORM_ALIASES
from ..core.pipeline import process_url
from .stage import run_menu


def ask(prompt, default=""):
    try:
        return input(prompt).strip() or default
    except EOFError:
        return default


def resolve_sources(raw):
    """Turn the user's answer into a list of source lines (URLs or local paths)."""
    raw = os.path.expanduser(raw)
    if os.path.isdir(raw):
        return sorted(glob.glob(os.path.join(raw, "*.html")))
    if os.path.isfile(raw) and raw.lower().endswith((".txt",)):
        with open(raw, encoding="utf-8") as f:
            return [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    return [raw] if raw else []


def post_summary(path):
    """A compact (title, date, words, links, images) summary of an output post."""
    text = open(path, encoding="utf-8").read()
    fm = re.match(r"^---\n.*?\n---\n(.*)$", text, re.S)
    body = fm.group(1) if fm else text
    title = re.search(r'^title:\s*"?(.*?)"?\s*$', text, re.M)
    date = re.search(r"^date:\s*(\d{4}-\d{2}-\d{2})", text, re.M)
    return {
        "title": title.group(1) if title else os.path.basename(path),
        "date": date.group(1) if date else "????-??-??",
        "words": len(re.sub(r"\s+", " ", body).split()),
        "links": len(re.findall(r"\]\(", body)),
        "images": len(re.findall(r"!\[", body)),
    }


def discard(path):
    """Delete an output post and its asset folder (a skipped review)."""
    slug = staging.split_name(path)[1]
    if os.path.isfile(path):
        os.remove(path)
    assets = os.path.join(config.ASSETS_DIR, slug)
    if os.path.isdir(assets):
        shutil.rmtree(assets, ignore_errors=True)


def wizard():
    """Guided interactive flow: pick source → convert → review each → stage/promote."""
    print("=== DeadHonestCitation · guided converter ===\n")
    sources = resolve_sources(ask("Source (a .txt list, a folder of .html, or one URL/path): "))
    if not sources:
        print("No sources found.")
        return

    plat_in = ask("Platform [auto / ghost / wordpress / html] (default auto): ", "auto").lower()
    platform = None if plat_in in ("", "auto") else PLATFORM_ALIASES.get(plat_in, plat_in)

    before = set(glob.glob(os.path.join(config.POSTS_DIR, "*.md")))
    print(f"\nConverting {len(sources)} source(s)…\n")
    for src in sources:
        process_url(src, platform)
    new = sorted(set(glob.glob(os.path.join(config.POSTS_DIR, "*.md"))) - before)

    if not new:
        print("\nNo new posts were produced (already converted, or nothing meaningful).")
        return

    repo = ask(f"\nJekyll repo [{config.DEFAULT_REPO}]: ", config.DEFAULT_REPO)
    tag = ask(f"Source tag to add [{config.DEFAULT_TAG}] (blank for none): ", config.DEFAULT_TAG)

    print(f"\n{len(new)} new post(s) to review:\n")
    staged = 0
    for path in new:
        s = post_summary(path)
        print(f"— {s['title']}")
        print(f"   {s['date']} · {s['words']} words · {s['links']} links · {s['images']} image(s)")
        choice = ask(
            "   [d]raft · [p]ost · [s]kip(delete) · [l]eave in output  (default d): ", "d"
        ).lower()
        if choice.startswith("s"):
            discard(path)
            print("   ✗ skipped (deleted)\n")
            continue
        if choice.startswith("l"):
            print("   · left in output/\n")
            continue
        dest, n = staging.stage_one(
            path, repo, tag=tag, to_posts=choice.startswith("p"), force=False
        )
        if dest is None:
            print("   ↷ already staged, skipped\n")
        else:
            print(f"   ✓ {os.path.relpath(dest, repo)}  (+{n} asset(s))\n")
            staged += 1

    print(f"Staged {staged} post(s).")
    if ask("\nOpen the promote menu (drafts → _posts) now? [y/N]: ", "n").lower().startswith("y"):
        run_menu(repo)
    print("\nDone.")
