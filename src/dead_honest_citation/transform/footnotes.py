"""HTML footnote blocks → Markdown [^n] syntax."""

import re

from bs4 import Tag


def convert_footnotes(soup: Tag) -> tuple[Tag, str]:
    """Convert Ghost/HTML footnotes to Markdown footnote syntax [^n].

    Returns:
        (soup, footnote_markdown_string) — the body with inline citations
        replaced, and the trailing footnote definitions ("" when the page has
        no footnote section).
    """
    footnote_section = soup.find("div", class_="footnotes")
    if not isinstance(footnote_section, Tag):
        return soup, ""

    # Collect footnote text by id, stripping the back-link arrow
    original_notes = {}
    for li in footnote_section.find_all("li"):
        fn_id = li.get("id")
        if not isinstance(fn_id, str) or not fn_id:
            continue
        # Valid at runtime; bs4's overloads type name+string= as string-only results.
        for a in li.find_all("a", string=re.compile(r"↩")):  # type: ignore[call-overload]
            a.decompose()
        original_notes[fn_id] = li.get_text(strip=True)

    # Walk inline citations in document order
    citation_order = []
    for sup in soup.find_all("sup"):
        a = sup.find("a")
        if not isinstance(a, Tag):
            continue
        href = a.get("href")
        href = href.lstrip("#") if isinstance(href, str) else ""
        if href in original_notes:
            if href not in citation_order:
                citation_order.append(href)
            idx = citation_order.index(href) + 1
            sup.replace_with(f"[^{idx}]")

    footnote_section.decompose()

    md_footnotes = "\n\n"
    for i, fn_id in enumerate(citation_order, start=1):
        content = original_notes.get(fn_id, "")
        md_footnotes += f"[^{i}]: {content}\n"

    return soup, md_footnotes
