#!/usr/bin/env python3
"""Build a public static reading site and a full-content RSS 2.0 feed.

Only exported HTML, article assets, CSS and the RSS feed are published.
The private Org sources and repository metadata are never copied to _site.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time
from email.utils import format_datetime
from html import escape
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "_site"
SOURCE = ROOT / "articulos"
BASE_URL = os.environ.get(
    "SITE_BASE_URL", "https://hylian-from-hyrule.github.io/CG-daily/"
).rstrip("/") + "/"
TZ = ZoneInfo("Europe/Madrid")
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"
ET.register_namespace("content", CONTENT_NS)

def metadata(path: Path) -> tuple[str, datetime]:
    text = path.read_text(encoding="utf-8")
    title = re.search(r"^#\\+TITLE:\\s*(.+)$", text, re.M | re.I)
    date = re.search(r"^#\\+DATE:\\s*<?(\\d{4}-\\d{2}-\\d{2})", text, re.M | re.I)
    if not title or not date:
        raise ValueError(f"Missing #+TITLE or #+DATE: {path}")
    dt = datetime.combine(datetime.strptime(date.group(1), "%Y-%m-%d").date(),
                          time(12, 0), tzinfo=TZ)
    return title.group(1).strip(), dt

def make_absolute_links(fragment: str, article_url: str) -> str:
    # RSS readers do not necessarily resolve relative paths against the article URL.
    def replace(match: re.Match[str]) -> str:
        attr, value = match.group(1), match.group(2)
        if value.startswith(("data:", "mailto:", "tel:", "javascript:")):
            return match.group(0)
        parsed = urlparse(value)
        if parsed.scheme or value.startswith("//"):
            return match.group(0)
        return f'{attr}="{escape(urljoin(article_url, value), quote=True)}"'
    return re.sub(r'\\b(src|href)="([^"]+)"', replace, fragment)

def build() -> None:
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts/site.css", SITE / "style.css")
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    sources = sorted(SOURCE.glob("*/*/*.org"), reverse=True)
    if not sources:
        raise RuntimeError("No Org articles found")
    articles = []
    for source in sources:
        title, date = metadata(source)
        rel = source.relative_to(ROOT).with_suffix(".html")
        output = SITE / rel
        output.parent.mkdir(parents=True, exist_ok=True)
        css_path = os.path.relpath(SITE / "style.css", output.parent)
        subprocess.run(
            ["emacs", "--batch", "-Q", "--script",
             str(ROOT / "scripts/export-article.el"),
             str(source), str(output), css_path],
            check=True, cwd=ROOT
        )
        fragment_path = Path(str(output) + ".fragment")
        fragment = fragment_path.read_text(encoding="utf-8")
        fragment_path.unlink()
        url = urljoin(BASE_URL, rel.as_posix())
        articles.append({"title": title, "date": date, "url": url,
                         "relative": rel.as_posix(),
                         "fragment": make_absolute_links(fragment, url)})
    # Copy only the image/diagram assets referenced by the public HTML.
    for assets in SOURCE.glob("*/*/assets"):
        if assets.is_dir():
            shutil.copytree(assets, SITE / assets.relative_to(ROOT),
                            dirs_exist_ok=True)

    groups = defaultdict(list)
    for article in articles:
        groups[article["date"].strftime("%Y-%m")].append(article)
    items = []
    for month, group in sorted(groups.items(), reverse=True):
        items.append(f"<h2>{escape(month)}</h2><ul class='articles'>")
        for article in group:
            date = article["date"].strftime("%d/%m/%Y")
            items.append(
                f'<li><time datetime="{article["date"].date()}">{date}</time>'
                f'<a href="{escape(article["relative"], quote=True)}">'
                f'{escape(article["title"])}</a></li>')
        items.append("</ul>")
    index = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gráficos por computador — biblioteca</title>
<link rel="stylesheet" href="style.css">
<link rel="alternate" type="application/rss+xml" title="Artículos completos (RSS)"
 href="feed.xml"></head>
<body><main class="home">
<p class="eyebrow">CG DAILY · BIBLIOTECA ABIERTA</p>
<h1>Gráficos por computador</h1>
<p class="intro">Artículos técnicos diarios sobre la historia y el presente
de los gráficos 3D: arquitecturas GPU, rasterización, APIs y algoritmos.</p>
<p><a class="feed" href="feed.xml">Suscribirse al RSS (texto completo)</a></p>
{''.join(items)}
<footer>Artículos originales exportados desde Org mode con Emacs.</footer>
</main></body></html>"""
    (SITE / "index.html").write_text(index, encoding="utf-8")

    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    for key, value in [
        ("title", "CG Daily — Gráficos por computador"),
        ("link", BASE_URL),
        ("description", "Artículos técnicos completos en español sobre gráficos por computador."),
        ("language", "es-ES"),
        ("lastBuildDate", format_datetime(datetime.now(TZ))),
        ("ttl", "60"),
    ]:
        ET.SubElement(channel, key).text = value
    # A rolling full-text feed remains manageable on mobile RSS readers.
    for article in articles[:45]:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = article["title"]
        ET.SubElement(item, "link").text = article["url"]
        ET.SubElement(item, "guid", {"isPermaLink": "true"}).text = article["url"]
        ET.SubElement(item, "pubDate").text = format_datetime(article["date"])
        ET.SubElement(item, "description").text = (
            "Artículo técnico completo disponible en esta entrada RSS y en la web."
        )
        ET.SubElement(item, f"{{{CONTENT_NS}}}encoded").text = article["fragment"]
    ET.indent(rss, space="  ")
    ET.ElementTree(rss).write(SITE / "feed.xml", encoding="utf-8",
                              xml_declaration=True)
    # Verify the resulting feed is valid XML and has the expected item count.
    parsed = ET.parse(SITE / "feed.xml")
    count = len(parsed.findall("./channel/item"))
    assert count == min(len(articles), 45), (count, len(articles))
    print(f"Built {len(articles)} HTML articles and {count} full-text RSS items")
    print(f"RSS URL: {urljoin(BASE_URL, 'feed.xml')}")

if __name__ == "__main__":
    build()
