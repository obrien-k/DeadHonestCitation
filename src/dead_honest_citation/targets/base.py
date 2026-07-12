"""Helpers shared across output targets."""

import re


def escape_table_pipes(markdown):
    """Escape | inside link text so kramdown/GFM won't read it as table syntax."""
    return re.sub(
        r"\[([^\]]*\|[^\]]*)\]",
        lambda m: "[" + m.group(1).replace("|", r"\|") + "]",
        markdown,
    )
