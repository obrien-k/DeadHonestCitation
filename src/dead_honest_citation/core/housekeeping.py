"""Output housekeeping: wipe or de-duplicate the generated output tree."""

import glob
import os
import re
import shutil

from ..config import ASSETS_DIR, POSTS_DIR
from ..ui import detail, status, success, warn


def post_slug(path: str) -> str:
    """Slug of an output post file (its name minus the YYYY-MM-DD- prefix and .md)."""
    m = re.match(r"\d{4}-\d{2}-\d{2}-(.+)\.md$", os.path.basename(path))
    return m.group(1) if m else re.sub(r"\.md$", "", os.path.basename(path))


def clean_output(assume_yes: bool = False) -> None:
    """Delete everything under output/ (posts + per-post asset folders)."""
    posts = sorted(glob.glob(os.path.join(POSTS_DIR, "*.md")))
    assets = [d for d in glob.glob(os.path.join(ASSETS_DIR, "*")) if os.path.isdir(d)]
    if not posts and not assets:
        status("output/ is already clean.")
        return
    status(f"This deletes {len(posts)} post(s) and {len(assets)} asset folder(s) under output/.")
    if not assume_yes:
        try:
            if input("Proceed? [y/N] ").strip().lower() not in ("y", "yes"):
                warn("Aborted.")
                return
        except EOFError:
            warn("Aborted.")
            return
    for p in posts:
        os.remove(p)
    for d in assets:
        shutil.rmtree(d, ignore_errors=True)
    success(f"✓ Cleaned output/ ({len(posts)} post(s), {len(assets)} asset folder(s)).")


def prune_output() -> None:
    """Remove stale output: older duplicates of a slug, and orphaned asset folders
    (an asset folder whose slug no longer has a post). Keeps the newest per slug."""
    posts = glob.glob(os.path.join(POSTS_DIR, "*.md"))
    by_slug: dict[str, list[str]] = {}
    for p in posts:
        by_slug.setdefault(post_slug(p), []).append(p)
    removed = 0
    for slug, files in by_slug.items():
        if len(files) > 1:
            files.sort(key=os.path.getmtime, reverse=True)  # newest first
            for old in files[1:]:
                detail(f"  ↺ older duplicate of '{slug}', removing: {os.path.basename(old)}")
                os.remove(old)
                removed += 1
    live = set(by_slug)
    for d in glob.glob(os.path.join(ASSETS_DIR, "*")):
        if os.path.isdir(d) and os.path.basename(d) not in live:
            detail(f"  ↺ orphaned assets (no post), removing: {os.path.basename(d)}/")
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
    success(f"✓ Prune complete — {removed} item(s) removed." if removed else "✓ Nothing to prune.")
