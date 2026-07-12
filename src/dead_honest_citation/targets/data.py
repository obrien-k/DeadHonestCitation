"""
The `data` output target: provenance-stamped citation objects, not posts.

Each source becomes a citation record (_data/sources/<id>.yml) plus its extracted
content (_sources/<id>.md), and the target ships a plugin-free Jekyll include to
render it. Provenance is honest by construction: `archived` (public Wayback
permalink + timestamp), `live` (URL + access date), or `local` (an author's
personal copy — no public link).
"""

import datetime as dt
import os
import re
import time
from typing import ClassVar

from ..config import OUTPUT_DIR
from ..models import Citation, PostMetadata
from ..network.wayback import WAYBACK_RE
from .base import OutputTarget

KIND_BY_PLATFORM = {
    "ghost": "post",
    "wordpress": "post",
    "generic": "page",
    "docx": "document",
    "proboards": "thread",
    "txt": "document",
}

CITE_INCLUDE = """{%- comment -%}
Render a source citation by id from _data/sources/.  Usage:
  {% include cite.html id="some-slug" %}
Shipped by DeadHonestCitation's `data` target; safe to edit/restyle.
{%- endcomment -%}
{%- assign s = site.data.sources[include.id] -%}
{%- if s -%}
<figure class="citation" id="cite-{{ include.id }}">
  {%- if s.screenshot %}
  <a href="{% if s.archive_url %}{{ s.archive_url }}{% else %}{{ s.source_url }}{% endif %}"><img src="{{ s.screenshot | relative_url }}" alt="{{ s.title | escape }}"></a>
  {%- endif %}
  <figcaption>
    <strong>{{ s.title | escape }}</strong>
    {%- if s.provenance == "archived" %} — <a href="{{ s.archive_url }}">archived {{ s.captured_at }}</a>
    {%- elsif s.provenance == "live" %} — <a href="{{ s.source_url }}">live</a> (accessed {{ s.captured_at }})
    {%- else %} — author's personal copy{% endif -%}
    {%- if s.note and s.note != "" %}<br>{{ s.note }}{% endif -%}
  </figcaption>
</figure>
{%- else -%}
<!-- cite: '{{ include.id }}' not found in _data/sources -->
{%- endif -%}
"""


def derive_citation(
    url: str, base_dir: str | None, platform_name: str, kind: str | None = None
) -> Citation:
    """Provenance fields for a source — honest by construction.

    A local copy never claims a public link, and an archived capture carries
    its real permalink + date.

    Args:
        url: The source URL or local path.
        base_dir: Directory of a local source, or None for a fetched URL.
        platform_name: Resolved adapter name, mapped to a content kind.
        kind: Overrides the platform→kind map (e.g. a captured image/document).
    """
    kind = kind or KIND_BY_PLATFORM.get(platform_name, "page")
    if base_dir is not None:
        # A local saved file or .docx — an author's personal copy, not public.
        return Citation(
            provenance="local",
            source_url=os.path.basename(url),
            archive_url=None,
            captured_at=None,
            kind=kind,
        )
    m = WAYBACK_RE.match(url)
    if m:
        ts = re.search(r"/web/(\d{4})(\d{2})(\d{2})", url)
        captured = f"{ts.group(1)}-{ts.group(2)}-{ts.group(3)}" if ts else None
        return Citation(
            provenance="archived",
            source_url=m.group(1),
            archive_url=url,
            captured_at=captured,
            kind=kind,
        )
    # A live URL fetched directly — record today's access date.
    return Citation(
        provenance="live",
        source_url=url,
        archive_url=None,
        captured_at=time.strftime("%Y-%m-%d"),
        kind=kind,
    )


def _yaml_str(value: str) -> str:
    """Quote a scalar for safe single-line YAML."""
    s = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def ensure_cite_include(out_dir: str) -> None:
    """Write the cite include once, so a site can render citations with no plugin."""
    path = os.path.join(out_dir, "_includes", "cite.html")
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(CITE_INCLUDE)


def emit_citation(
    out_dir: str,
    slug: str,
    meta: PostMetadata,
    markdown: str,
    footnotes: str,
    cite: Citation,
) -> str:
    """Write the citation record + extracted content for one source.

    Returns:
        The citation record's relpath (under out_dir).
    """
    content_rel = os.path.join("_sources", f"{slug}.md")
    content_path = os.path.join(out_dir, content_rel)
    os.makedirs(os.path.dirname(content_path), exist_ok=True)
    with open(content_path, "w", encoding="utf-8") as f:
        f.write(markdown)
        if footnotes.strip():
            f.write(footnotes)

    lines = [
        f"id: {slug}",
        f"title: {_yaml_str(meta.title)}",
        f"kind: {cite.kind}",
        f"provenance: {cite.provenance}",
    ]
    if cite.source_url:
        lines.append(f"source_url: {_yaml_str(cite.source_url)}")
    if cite.archive_url:
        lines.append(f"archive_url: {_yaml_str(cite.archive_url)}")
    if cite.captured_at:
        lines.append(f"captured_at: {cite.captured_at}")
    if meta.screenshot:
        lines.append(f"screenshot: {_yaml_str(meta.screenshot)}")
    lines.append(f"content: {_yaml_str(content_rel)}")
    lines.append(f"note: {_yaml_str(meta.screenshot_note)}")

    yml_rel = os.path.join("_data", "sources", f"{slug}.yml")
    yml_path = os.path.join(out_dir, yml_rel)
    os.makedirs(os.path.dirname(yml_path), exist_ok=True)
    with open(yml_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    ensure_cite_include(out_dir)
    return yml_rel


class DataTarget(OutputTarget):
    """Citation records: _data/sources/<id>.yml + _sources/<id>.md + cite.html."""

    name: ClassVar[str] = "data"
    is_citation: ClassVar[bool] = True

    def doc_relpath(self, slug: str, date: dt.date | None) -> str:
        return os.path.join("_data", "sources", f"{slug}.yml")

    def asset_dir(self, slug: str) -> str:
        return os.path.join("assets", "img", "sources", slug)

    def asset_url(self, slug: str, fname: str) -> str:
        return f"/assets/img/sources/{slug}/{fname}"

    def write(
        self,
        doc_relpath: str,
        url: str,
        base_dir: str | None,
        platform_name: str,
        slug: str,
        meta: PostMetadata,
        body: str,
        footnotes: str,
        kind: str | None = None,
    ) -> str:
        cite = derive_citation(url, base_dir, platform_name, kind=kind)
        return emit_citation(OUTPUT_DIR, slug, meta, body, footnotes, cite)
