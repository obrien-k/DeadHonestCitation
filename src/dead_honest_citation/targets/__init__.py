"""
Output targets: each OutputTarget subclass decides how results are written —
front-matter format, file naming/layout, asset paths, Markdown-flavor tweaks,
or (for citation targets) a whole different record shape. The conversion core
stays target-agnostic, so supporting another static-site generator means one
subclass plus one entry here.
"""

from .base import DocumentTarget, OutputTarget
from .commonmark import CommonMarkTarget
from .data import DataTarget
from .jekyll import JekyllTarget

__all__ = [
    "TARGETS",
    "TARGET_ALIASES",
    "DocumentTarget",
    "OutputTarget",
    "resolve_target",
]

TARGETS: dict[str, OutputTarget] = {
    target.name: target for target in (JekyllTarget(), CommonMarkTarget(), DataTarget())
}

TARGET_ALIASES = {
    "jekyll": "jekyll",
    "jk": "jekyll",
    "commonmark": "commonmark",
    "cm": "commonmark",
    "plain": "commonmark",
    "md": "commonmark",
    "data": "data",
    "citation": "data",
    "cite": "data",
}


def resolve_target(name: str | None) -> OutputTarget:
    """Map a target name/alias to its OutputTarget (defaults to jekyll)."""
    return TARGETS[TARGET_ALIASES.get(name or "jekyll", name or "jekyll")]
