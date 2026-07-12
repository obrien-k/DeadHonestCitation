"""HTML footnote blocks → Markdown [^n] syntax."""

import re


def convert_footnotes(soup):
    """
    Convert Ghost/HTML footnotes to Markdown footnote syntax [^n].
    Returns (soup, footnote_markdown_string).
    """
    footnote_section = soup.find("div", class_="footnotes")
    if not footnote_section:
        return soup, ""

    # Collect footnote text by id, stripping the back-link arrow
    original_notes = {}
    for li in footnote_section.find_all("li"):
        fn_id = li.get("id")
        if not fn_id:
            continue
        for a in li.find_all("a", string=re.compile(r"↩")):
            a.decompose()
        original_notes[fn_id] = li.get_text(strip=True)

    # Walk inline citations in document order
    citation_order = []
    for sup in soup.find_all("sup"):
        a = sup.find("a")
        if not a:
            continue
        href = a.get("href", "").lstrip("#")
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
