"""Image localization: download (or copy, for saved pages) and rewrite <img> srcs."""

import os
import shutil
from urllib.parse import unquote, urlparse

from ..config import OUTPUT_DIR
from ..network.polite import polite_get
from ..network.wayback import wayback_image_candidates


def download_image(url, post_img_dir):
    """Download a single image to post_img_dir. Returns the local path, or None on failure."""
    try:
        response = polite_get(url, timeout=15)
        filename = os.path.basename(urlparse(url).path) or "image"
        local_path = os.path.join(post_img_dir, filename)
        with open(local_path, "wb") as f:
            f.write(response.content)
        return local_path
    except Exception as e:
        print(f"  ⚠ Image download failed ({url}): {e}")
        return None


def download_cover(cover_url, slug, target=None):
    """Download the cover image and return its in-document URL, or '' on failure."""
    if not cover_url:
        return ""
    target = target or _default_target()
    post_img_dir = os.path.join(OUTPUT_DIR, target["asset_dir"](slug))
    os.makedirs(post_img_dir, exist_ok=True)

    for url in wayback_image_candidates(cover_url):
        local_path = download_image(url, post_img_dir)
        if local_path:
            return target["asset_url"](slug, os.path.basename(local_path))

    return ""


def download_images(soup, slug, base_dir=None, target=None):
    """
    Download (or, for a local HTML export, copy) all images in the article and
    rewrite their src to the active target's asset URLs. Skips already-localized ones.

    base_dir, when set, is the directory of a saved HTML file; images whose src is
    a relative path are copied straight out of its sibling "<name>_files/" folder
    instead of being fetched over the network.
    """
    target = target or _default_target()
    post_img_dir = os.path.join(OUTPUT_DIR, target["asset_dir"](slug))
    os.makedirs(post_img_dir, exist_ok=True)
    asset_root = target["asset_url"](slug, "")

    for img in soup.find_all("img"):
        src = img.get("src")
        if not src or src.startswith(asset_root):
            continue

        # 1. Local export: copy from the saved files-dir when src resolves on disk.
        if base_dir and not src.startswith(("http://", "https://", "//", "/web/")):
            copied = copy_local_image(src, base_dir, post_img_dir)
            if copied:
                img["src"] = target["asset_url"](slug, os.path.basename(copied))
                continue
            # else fall through: the local file is missing (a cross-origin asset the
            # browser never fetched), so try the real URLs in srcset / data-* below.

        # 2. Download from the best real URL(s) available on the tag — the inline
        # src, then srcset entries (largest first), then common data-* fallbacks.
        localized = False
        for candidate in image_source_urls(img):
            for url in wayback_image_candidates(candidate):
                local_path = download_image(url, post_img_dir)
                if local_path:
                    img["src"] = target["asset_url"](slug, os.path.basename(local_path))
                    localized = True
                    break
            if localized:
                break

        # 3. Nothing worked. Drop a dead local ref so we never emit a broken path;
        # leave a genuine remote src untouched (matches the original behavior).
        if (
            not localized
            and base_dir
            and not src.startswith(("http://", "https://", "//", "/web/"))
        ):
            print(f"  ⚠ Image unrecoverable, dropping: {os.path.basename(src)}")
            img.decompose()

    return soup


def image_source_urls(img):
    """
    Ordered real (http) URLs to try for an <img>: the inline src, then srcset
    candidates (largest width first), then common lazy-load data-* attributes.
    Used as a fallback when a locally saved page's inline src is a dead path — the
    browser typically leaves the original URL behind in srcset.
    """
    urls = []
    src = img.get("src", "")
    if src.startswith(("http://", "https://", "//", "/web/")):
        urls.append(src)
    srcset = img.get("srcset", "")
    if srcset:
        entries = []
        for part in srcset.split(","):
            bits = part.strip().split()
            if bits and bits[0].startswith(("http", "//", "/web/")):
                width = 0
                if len(bits) > 1 and bits[1].endswith("w"):
                    try:
                        width = int(bits[1][:-1])
                    except ValueError:
                        pass
                entries.append((width, bits[0]))
        urls += [u for _, u in sorted(entries, reverse=True)]
    for attr in ("data-orig-file", "data-large-file", "data-src", "data-lazy-src"):
        v = img.get(attr, "")
        if v.startswith(("http", "//", "/web/")):
            urls.append(v)
    seen, ordered = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            ordered.append(u)
    return ordered


def copy_local_image(src, base_dir, post_img_dir):
    """Copy an image referenced by a saved HTML page into post_img_dir. Returns the
    destination path, or None if the source file can't be found on disk."""
    rel = unquote(src.split("?")[0].split("#")[0])
    candidate = os.path.normpath(os.path.join(base_dir, rel))
    if not os.path.isfile(candidate):
        return None
    filename = os.path.basename(candidate) or "image"
    dest = os.path.join(post_img_dir, filename)
    try:
        shutil.copyfile(candidate, dest)
        return dest
    except OSError as e:
        print(f"  ⚠ Local image copy failed ({candidate}): {e}")
        return None


def _default_target():
    # Imported lazily: targets is a consumer of this module's siblings, and the
    # default only matters for direct library calls (the pipeline always passes one).
    from ..targets import resolve_target

    return resolve_target(None)
