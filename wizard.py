#!/usr/bin/env python3
"""
Guided, interactive archive→Jekyll flow. Ties the pieces together:

  1. pick source(s) — a URL/paths file, a folder of saved .html, or one path/URL
  2. convert them (index.py)
  3. review each new post — keep as draft, send straight to a post, skip, or leave
  4. stage the kept ones into the Jekyll repo (to_jekyll.py)
  5. optionally open the promote menu to push drafts into _posts

Run it with no arguments:  python wizard.py
"""

import glob
import os
import re
import shutil

import index
import to_jekyll as tj


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
    slug = tj.split_name(path)[1]
    if os.path.isfile(path):
        os.remove(path)
    assets = os.path.join(index.ASSETS_DIR, slug)
    if os.path.isdir(assets):
        shutil.rmtree(assets, ignore_errors=True)


def main():
    print("=== DeadHonestCitation · guided converter ===\n")
    sources = resolve_sources(ask("Source (a .txt list, a folder of .html, or one URL/path): "))
    if not sources:
        print("No sources found.")
        return

    plat_in = ask("Platform [auto / ghost / wordpress / html] (default auto): ", "auto").lower()
    platform = None if plat_in in ("", "auto") else index.PLATFORM_ALIASES.get(plat_in, plat_in)

    before = set(glob.glob(os.path.join(index.POSTS_DIR, "*.md")))
    print(f"\nConverting {len(sources)} source(s)…\n")
    for src in sources:
        index.process_url(src, platform)
    new = sorted(set(glob.glob(os.path.join(index.POSTS_DIR, "*.md"))) - before)

    if not new:
        print("\nNo new posts were produced (already converted, or nothing meaningful).")
        return

    repo = ask(f"\nJekyll repo [{tj.DEFAULT_REPO}]: ", tj.DEFAULT_REPO)
    tag = ask(f"Source tag to add [{tj.DEFAULT_TAG}] (blank for none): ", tj.DEFAULT_TAG)

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
        dest, n = tj.stage_one(path, repo, tag=tag, to_posts=choice.startswith("p"), force=False)
        if dest is None:
            print("   ↷ already staged, skipped\n")
        else:
            print(f"   ✓ {os.path.relpath(dest, repo)}  (+{n} asset(s))\n")
            staged += 1

    print(f"Staged {staged} post(s).")
    if ask("\nOpen the promote menu (drafts → _posts) now? [y/N]: ", "n").lower().startswith("y"):
        ns = type("NS", (), {"repo": repo})()
        tj.cmd_menu(ns)
    print("\nDone.")


if __name__ == "__main__":
    main()
