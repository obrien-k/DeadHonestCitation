"""dhc stage / promote / menu — move converted posts into a Jekyll site repo."""

import glob
import os
from typing import Annotated

import typer

from .. import config, staging

_REPO_OPTION = typer.Option("--repo", help="Jekyll repo path (default: $ARCHIVE2MD_JEKYLL_REPO).")


def stage(
    files: Annotated[
        list[str], typer.Argument(help="Post .md files (default: all of output/_posts/).")
    ] = None,
    repo: Annotated[str, _REPO_OPTION] = config.DEFAULT_REPO,
    tag: Annotated[
        str,
        typer.Option(
            "--tag", help='Source tag to inject (default: $ARCHIVE2MD_SOURCE_TAG; "" to skip).'
        ),
    ] = config.DEFAULT_TAG,
    to_posts: Annotated[
        bool, typer.Option("--to-posts", help="Write straight to _posts/ with a date prefix.")
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite an existing destination file.")
    ] = False,
):
    """Copy converted posts into the repo's _drafts/ (or _posts/ with --to-posts),
    injecting a source tag and copying each post's image assets."""
    files = files or sorted(glob.glob(os.path.join(config.OUT_POSTS, "*.md")))
    if not files:
        print("No posts to stage.")
        return
    for path in files:
        dest, n = staging.stage_one(path, repo, tag, to_posts, force)
        if dest is None:
            print(f"  ↷ exists, skip: {os.path.basename(path)}")
        else:
            print(f"  ✓ {os.path.relpath(dest, repo)}  (+{n} asset(s))")


def promote(
    slug: Annotated[str, typer.Argument(help="Draft slug (filename without .md).")],
    repo: Annotated[str, _REPO_OPTION] = config.DEFAULT_REPO,
):
    """Move a draft into _posts/ by its front-matter date."""
    dest = staging.promote_one(slug, repo)
    if dest is None:
        print(f"✗ No draft at _drafts/{slug}.md")
        raise typer.Exit(1)
    print(f"✓ promoted: _drafts/{slug}.md → {os.path.relpath(dest, repo)}")


def run_menu(repo):
    """List drafts and interactively promote a chosen subset into _posts.
    Shared by `dhc menu` and the wizard."""
    drafts = sorted(glob.glob(os.path.join(repo, "_drafts", "*.md")))
    if not drafts:
        print("No drafts to promote.")
        return
    print("Drafts in _drafts/:\n")
    for i, d in enumerate(drafts, 1):
        with open(d, encoding="utf-8") as f:
            date = staging.front_matter_date(f.read()) or "????-??-??"
        print(f"  {i:2}. [{date}]  {os.path.basename(d)[:-3]}")
    try:
        sel = input("\nPromote which into _posts? (e.g. 1,3 or 2-4 or 'all'; blank to cancel): ")
    except EOFError:
        sel = ""
    idxs = staging.parse_selection(sel, len(drafts))
    if not idxs:
        print("Cancelled.")
        return
    for i in idxs:
        slug = os.path.basename(drafts[i - 1])[:-3]
        dest = staging.promote_one(slug, repo)
        print(f"  ✓ {slug} → {os.path.relpath(dest, repo)}")


def menu(
    repo: Annotated[str, _REPO_OPTION] = config.DEFAULT_REPO,
):
    """Interactively list drafts and promote a chosen subset into _posts/."""
    run_menu(repo)
