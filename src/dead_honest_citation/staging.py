"""
Move converted posts from output/ into a Jekyll site repo.

  stage    Copy posts into the repo's _drafts/ as <slug>.md (no date prefix, the
           Jekyll-draft convention; the date stays in front matter), optionally
           inject a source tag, and copy each post's image assets.
  promote  Move a draft into _posts/<date>-<slug>.md, reading the date from the
           post's own front matter. This is the "trickle a draft into _posts" step.

The Jekyll repo path and the injected source tag default from the environment —
set DHC_JEKYLL_REPO and DHC_SOURCE_TAG, or drop them in a .env file
(see .env.example).
"""

import os
import re
import shutil

from .config import ASSETS_REL, DEFAULT_TAG, OUT_ASSETS

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
