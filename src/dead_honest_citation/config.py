"""Shared paths and environment-derived settings.

Personal defaults (Jekyll repo path, source tag) come from the environment or a
.env file at the current working directory's root, never from source — a fresh
clone runs without leaking anyone's paths or tags.
"""

import os

OUTPUT_DIR = "output"
POSTS_DIR = os.path.join(OUTPUT_DIR, "_posts")
ASSETS_REL = os.path.join("assets", "img", "blog", "posts")
ASSETS_DIR = os.path.join(OUTPUT_DIR, ASSETS_REL)
RUNLOG = os.path.join(OUTPUT_DIR, "runlog.jsonl")

OUT_POSTS = POSTS_DIR
OUT_ASSETS = ASSETS_DIR


def load_dotenv(path=None):
    """Populate os.environ from a simple KEY=VALUE .env file, without adding a
    dependency. Existing environment variables win; lines that are blank or start
    with '#' are ignored. Quotes around values are stripped."""
    path = path or os.path.join(os.getcwd(), ".env")
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


load_dotenv()

DEFAULT_REPO = os.path.expanduser(os.environ.get("ARCHIVE2MD_JEKYLL_REPO") or "~/jekyll-site")
DEFAULT_TAG = os.environ.get("ARCHIVE2MD_SOURCE_TAG", "")
