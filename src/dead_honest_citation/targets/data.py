"""
The `data` output target: provenance-stamped citation objects, not posts.

Each source becomes a citation record (_data/sources/<id>.yml) plus its extracted
content (_sources/<id>.md), and the target ships a plugin-free Jekyll include to
render it. Provenance is honest by construction: `archived` (public Wayback
permalink + timestamp), `live` (URL + access date), or `local` (an author's
personal copy — no public link).
"""

import os
import re
import time

from ..network.wayback import WAYBACK_RE
from .base import escape_table_pipes

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


def derive_citation(url, base_dir, platform_name, kind=None):
    """Provenance fields for a source. Honest by construction: a local copy never
    claims a public link, and an archived capture carries its real permalink + date.
    kind overrides the platform→kind map (e.g. a captured image/document)."""
    kind = kind or KIND_BY_PLATFORM.get(platform_name, "page")
    if base_dir is not None:
        # A local saved file or .docx — an author's personal copy, not public.
        return {
            "provenance": "local",
            "source_url": os.path.basename(url),
            "archive_url": None,
            "captured_at": None,
            "kind": kind,
        }
    m = WAYBACK_RE.match(url)
    if m:
        ts = re.search(r"/web/(\d{4})(\d{2})(\d{2})", url)
        captured = f"{ts.group(1)}-{ts.group(2)}-{ts.group(3)}" if ts else None
        return {
            "provenance": "archived",
            "source_url": m.group(1),
            "archive_url": url,
            "captured_at": captured,
            "kind": kind,
        }
    # A live URL fetched directly — record today's access date.
    return {
        "provenance": "live",
        "source_url": url,
        "archive_url": None,
        "captured_at": time.strftime("%Y-%m-%d"),
        "kind": kind,
    }


def _yaml_str(value):
    """Quote a scalar for safe single-line YAML."""
    s = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def ensure_cite_include(out_dir):
    """Write the cite include once, so a site can render citations with no plugin."""
    path = os.path.join(out_dir, "_includes", "cite.html")
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(CITE_INCLUDE)


def emit_citation(out_dir, slug, meta, markdown, footnotes, cite):
    """Write the citation record + extracted content for one source; return the
    record's relpath. (The `data` target's writer.)"""
    content_rel = os.path.join("_sources", f"{slug}.md")
    content_path = os.path.join(out_dir, content_rel)
    os.makedirs(os.path.dirname(content_path), exist_ok=True)
    with open(content_path, "w", encoding="utf-8") as f:
        f.write(markdown)
        if footnotes.strip():
            f.write(footnotes)

    lines = [
        f"id: {slug}",
        f"title: {_yaml_str(meta['title'])}",
        f"kind: {cite['kind']}",
        f"provenance: {cite['provenance']}",
    ]
    if cite["source_url"]:
        lines.append(f"source_url: {_yaml_str(cite['source_url'])}")
    if cite["archive_url"]:
        lines.append(f"archive_url: {_yaml_str(cite['archive_url'])}")
    if cite["captured_at"]:
        lines.append(f"captured_at: {cite['captured_at']}")
    if meta.get("screenshot"):
        lines.append(f"screenshot: {_yaml_str(meta['screenshot'])}")
    lines.append(f"content: {_yaml_str(content_rel)}")
    lines.append(f"note: {_yaml_str(meta.get('screenshot_note', ''))}")

    yml_rel = os.path.join("_data", "sources", f"{slug}.yml")
    yml_path = os.path.join(out_dir, yml_rel)
    os.makedirs(os.path.dirname(yml_path), exist_ok=True)
    with open(yml_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    ensure_cite_include(out_dir)
    return yml_rel


TARGET = {
    "doc_relpath": lambda slug, date: os.path.join("_data", "sources", f"{slug}.yml"),
    "asset_dir": lambda slug: os.path.join("assets", "img", "sources", slug),
    "asset_url": lambda slug, fname: f"/assets/img/sources/{slug}/{fname}",
    "flavor": escape_table_pipes,
    "emit": emit_citation,
}
