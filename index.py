import os
import re
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from slugify import slugify
from dateutil import parser as dateparser
from urllib.parse import urljoin, urlparse

OUTPUT_DIR = "output"
POSTS_DIR = os.path.join(OUTPUT_DIR, "_posts")
ASSETS_DIR = os.path.join(OUTPUT_DIR, "assets", "img", "blog", "posts")

os.makedirs(POSTS_DIR, exist_ok=True)
os.makedirs(ASSETS_DIR, exist_ok=True)


def clean_ghost_classes(soup):
    for tag in soup.find_all(True):
        if tag.has_attr("class"):
            tag["class"] = [
                c for c in tag["class"]
                if not c.startswith(("gh-", "kg-"))
            ]
            if not tag["class"]:
                del tag["class"]
        if tag.has_attr("data-ghost"):
            del tag["data-ghost"]
    return soup


def normalize_headings(soup):
    h1s = soup.find_all("h1")
    if len(h1s) > 1:
        for h in h1s[1:]:
            h.name = "h2"
    return soup


def remove_ghost_footnote_arrows(html):
    return html.replace("↩︎", "")


def download_images(soup, slug):
    post_img_dir = os.path.join(ASSETS_DIR, slug)
    os.makedirs(post_img_dir, exist_ok=True)

    for img in soup.find_all("img"):
        src = img.get("src")
        if not src:
            continue

        try:
            response = requests.get(src)
            response.raise_for_status()

            filename = os.path.basename(urlparse(src).path)
            local_path = os.path.join(post_img_dir, filename)

            with open(local_path, "wb") as f:
                f.write(response.content)

            img["src"] = f"/assets/img/blog/posts/{slug}/{filename}"
        except Exception as e:
            print(f"Failed to download {src}: {e}")

    return soup


def extract_metadata(soup):
    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else "Untitled"

    date_meta = soup.find("meta", property="article:published_time")
    date_str = date_meta["content"] if date_meta else None
    date = dateparser.parse(date_str).date() if date_str else None

    tags = []
    for tag_meta in soup.find_all("meta", property="article:tag"):
        tags.append(tag_meta["content"])

    return title, date, tags


def build_front_matter(title, date, tags):
    fm = "---\n"
    fm += "layout: post\n"
    fm += f'title: "{title}"\n'
    fm += f"date: {date}\n"
    if tags:
        fm += "tags:\n"
        for t in tags:
            fm += f"  - {t}\n"
    fm += "---\n\n"
    return fm


def process_url(url):
    print(f"Processing: {url}")
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")

    title, date, tags = extract_metadata(soup)

    article = soup.find("section", class_=re.compile("gh-content"))
    if not article:
        print("No content section found.")
        return

    slug = slugify(title)
    article = clean_ghost_classes(article)
    article = normalize_headings(article)
    article = download_images(article, slug)
    article, md_footnotes = convert_footnotes(article)

    html_content = str(article)

    markdown = md(html_content, heading_style="ATX")
    
    filename = f"{date}-{slug}.md"
    filepath = os.path.join(POSTS_DIR, filename)

    if os.path.exists(filepath):
        print(f"Skipping existing: {filename}")
        return

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(build_front_matter(title, date, tags))
        f.write(markdown)
        f.write(md_footnotes)

    print(f"Saved: {filepath}")

def convert_footnotes(soup):
    footnote_section = soup.find("div", class_="footnotes")
    if not footnote_section:
        return soup, ""

    original_notes = {}
    for li in footnote_section.find_all("li"):
        fn_id = li.get("id")
        if not fn_id:
            continue

        for a in li.find_all("a"):
            a.decompose()

        original_notes[fn_id] = li.get_text(strip=True)

    citation_order = []
    for sup in soup.find_all("sup"):
        a = sup.find("a")
        if not a:
            continue

        href = a.get("href", "").replace("#", "")
        if href in original_notes:
            if href not in citation_order:
                citation_order.append(href)
            new_index = citation_order.index(href) + 1
            sup.replace_with(f"[^{new_index}]")

    footnote_section.decompose()

    md_footnotes = "\n\n"
    for i, fn_id in enumerate(citation_order, start=1):
        content = original_notes.get(fn_id, "")
        md_footnotes += f"[^{i}]: {content}\n"

    return soup, md_footnotes



def main():
    with open("urls.txt") as f:
        urls = [line.strip() for line in f if line.strip()]

    for url in urls:
        process_url(url)


if __name__ == "__main__":
    main()
