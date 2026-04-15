#!/usr/bin/env python3
"""
Optimizely Translation Audit Crawler
Crawls vapaaehtoistieto.punainenristi.fi and reports which pages
have translations based on hreflang tags and URL language patterns.

Usage:
    pip install requests beautifulsoup4 rich
    python optimizely_translation_crawler.py
"""

import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import defaultdict
import time
import csv
import json
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

# ─── Configuration ────────────────────────────────────────────────────────────

BASE_URL = "https://vapaaehtoistieto.punainenristi.fi"

# Sitemap — seeds the crawler with ALL published pages so nothing is missed
SITEMAP_URL = "https://vapaaehtoistieto.punainenristi.fi/fi/vapaaehtoistieto.sitemap.xml"

# Languages you expect the site to support (adjust as needed)
EXPECTED_LANGUAGES = ["fi", "sv", "en"]

# Crawl limits (increase if site is large)
MAX_PAGES = 1000
DELAY_SECONDS = 0.5         # Be polite, don't hammer the server
REQUEST_TIMEOUT = 10

# Output files
OUTPUT_CSV  = "translation_audit.csv"
OUTPUT_JSON = "translation_audit.json"

HEADERS = {
    "User-Agent": "TranslationAuditBot/1.0 (internal audit; contact: webmaster)"
}

# ─── Helpers ──────────────────────────────────────────────────────────────────

console = Console()


def load_sitemap(session: requests.Session) -> set:
    """Fetch all URLs from the sitemap using built-in XML parser (no lxml needed)."""
    urls = set()
    try:
        console.print(f"[cyan]Loading sitemap:[/] {SITEMAP_URL}")
        resp = session.get(SITEMAP_URL, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        # Strip namespace so ElementTree can find tags easily
        xml_text = resp.text.replace(' xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"', '')
        root = ET.fromstring(xml_text)
        for loc in root.iter("loc"):
            url = normalize_url(loc.text.strip())
            if is_same_domain(url):
                urls.add(url)
        console.print(f"[green]Sitemap loaded successfully:[/] {len(urls)} URLs found")
    except Exception as e:
        console.print(f"[red]Sitemap load failed: {e}[/]")
        console.print("[yellow]Falling back to homepage crawl only[/]")
    return urls

def is_same_domain(url: str) -> bool:
    parsed = urlparse(url)
    base   = urlparse(BASE_URL)
    return parsed.netloc == base.netloc or parsed.netloc == ""

def normalize_url(url: str) -> str:
    """Strip fragment and trailing slash for deduplication."""
    parsed = urlparse(url)
    clean  = parsed._replace(fragment="", query="")
    path   = clean.path.rstrip("/") or "/"
    return clean._replace(path=path).geturl()

def detect_language_from_url(url: str) -> str | None:
    """Detect language segment from URL path, e.g. /en/ or /sv/."""
    parts = urlparse(url).path.strip("/").split("/")
    for part in parts:
        if part.lower() in EXPECTED_LANGUAGES:
            return part.lower()
    return None

def get_hreflang_map(soup: BeautifulSoup, page_url: str) -> dict[str, str]:
    """
    Returns {lang_code: absolute_url} from <link rel="alternate" hreflang="..."> tags.
    Also handles x-default.
    """
    result = {}
    for tag in soup.find_all("link", rel="alternate"):
        lang = tag.get("hreflang", "").strip().lower()
        href = tag.get("href", "").strip()
        if lang and href:
            abs_href = urljoin(page_url, href)
            result[lang] = abs_href
    return result

def get_page_title(soup: BeautifulSoup) -> str:
    tag = soup.find("title")
    return tag.get_text(strip=True) if tag else "(no title)"

def get_links(soup: BeautifulSoup, page_url: str) -> list[str]:
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        abs_url = urljoin(page_url, href)
        if is_same_domain(abs_url):
            links.append(normalize_url(abs_url))
    return links

# ─── Crawler ──────────────────────────────────────────────────────────────────

def crawl() -> list[dict]:
    session   = requests.Session()
    session.headers.update(HEADERS)

    # Seed from sitemap first, then fall back to crawling from homepage
    sitemap_urls = load_sitemap(session)
    to_visit = sitemap_urls if sitemap_urls else {normalize_url(BASE_URL)}
    to_visit.add(normalize_url(BASE_URL))  # always include homepage
    visited   = set()
    results   = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Crawling…", total=None)

        while to_visit and len(visited) < MAX_PAGES:
            url = to_visit.pop()
            if url in visited:
                continue
            visited.add(url)

            progress.update(task, description=f"[cyan]Crawling[/] ({len(visited)}/{MAX_PAGES}) {url[:80]}")

            try:
                resp = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
                final_url = normalize_url(resp.url)

                if resp.status_code != 200:
                    results.append({
                        "url": url,
                        "final_url": final_url,
                        "title": "",
                        "status_code": resp.status_code,
                        "url_language": detect_language_from_url(url),
                        "hreflang_languages": [],
                        "hreflang_map": {},
                        "translated_languages": [],
                        "missing_languages": EXPECTED_LANGUAGES[:],
                        "translation_status": "error",
                        "error": f"HTTP {resp.status_code}",
                    })
                    continue

                content_type = resp.headers.get("Content-Type", "")
                if "text/html" not in content_type:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")

                title        = get_page_title(soup)
                hreflang_map = get_hreflang_map(soup, final_url)
                url_lang     = detect_language_from_url(final_url)

                # Languages found via hreflang (ignore x-default for the count)
                hreflang_langs = [
                    lang for lang in hreflang_map
                    if lang != "x-default"
                ]

                # Which expected languages are present / missing
                translated   = [l for l in EXPECTED_LANGUAGES if l in hreflang_langs]
                missing      = [l for l in EXPECTED_LANGUAGES if l not in hreflang_langs]

                if len(translated) == len(EXPECTED_LANGUAGES):
                    status = "fully_translated"
                elif len(translated) > 0:
                    status = "partially_translated"
                else:
                    status = "not_translated"

                results.append({
                    "url": url,
                    "final_url": final_url,
                    "title": title,
                    "status_code": resp.status_code,
                    "url_language": url_lang,
                    "hreflang_languages": hreflang_langs,
                    "hreflang_map": hreflang_map,
                    "translated_languages": translated,
                    "missing_languages": missing,
                    "translation_status": status,
                    "error": None,
                })

                # Enqueue new links
                for link in get_links(soup, final_url):
                    if link not in visited:
                        to_visit.add(link)

            except requests.RequestException as e:
                results.append({
                    "url": url,
                    "final_url": url,
                    "title": "",
                    "status_code": None,
                    "url_language": detect_language_from_url(url),
                    "hreflang_languages": [],
                    "hreflang_map": {},
                    "translated_languages": [],
                    "missing_languages": EXPECTED_LANGUAGES[:],
                    "translation_status": "error",
                    "error": str(e),
                })

            time.sleep(DELAY_SECONDS)

    return results

# ─── Reporting ────────────────────────────────────────────────────────────────

STATUS_STYLE = {
    "fully_translated":    "green",
    "partially_translated":"yellow",
    "not_translated":      "red",
    "error":               "dim",
}

def print_summary(results: list[dict]):
    counts = defaultdict(int)
    for r in results:
        counts[r["translation_status"]] += 1

    console.rule("[bold]Translation Audit Summary[/]")
    rprint(f"  Total pages crawled : [bold]{len(results)}[/]")
    rprint(f"  ✅ Fully translated  : [green]{counts['fully_translated']}[/]")
    rprint(f"  ⚠️  Partially        : [yellow]{counts['partially_translated']}[/]")
    rprint(f"  ❌ Not translated    : [red]{counts['not_translated']}[/]")
    rprint(f"  💥 Errors            : [dim]{counts['error']}[/]")
    console.print()

def print_table(results: list[dict]):
    table = Table(title="Page Translation Status", show_lines=True)
    table.add_column("Status",   style="bold", width=20)
    table.add_column("URL",      overflow="fold", max_width=60)
    table.add_column("Title",    overflow="fold", max_width=35)
    table.add_column("Found",    width=12)
    table.add_column("Missing",  width=12)

    for r in sorted(results, key=lambda x: x["translation_status"]):
        status = r["translation_status"]
        style  = STATUS_STYLE.get(status, "")
        table.add_row(
            f"[{style}]{status}[/]",
            r["final_url"],
            r["title"] or r.get("error", ""),
            ", ".join(r["translated_languages"]) or "—",
            ", ".join(r["missing_languages"])    or "—",
            style=style if status == "not_translated" else "",
        )

    console.print(table)

def save_csv(results: list[dict], path: str):
    fields = [
        "translation_status", "final_url", "title",
        "url_language", "translated_languages", "missing_languages",
        "hreflang_languages", "status_code", "error"
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            row = dict(r)
            for key in ("translated_languages", "missing_languages", "hreflang_languages"):
                row[key] = ", ".join(r.get(key, []))
            writer.writerow(row)
    console.print(f"[green]CSV saved →[/] {path}")

def save_json(results: list[dict], path: str):
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "base_url": BASE_URL,
        "expected_languages": EXPECTED_LANGUAGES,
        "pages": results,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    console.print(f"[green]JSON saved →[/] {path}")

# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    console.rule(f"[bold blue]Optimizely Translation Audit[/]")
    console.print(f"Target : [cyan]{BASE_URL}[/]")
    console.print(f"Expect : [cyan]{', '.join(EXPECTED_LANGUAGES)}[/]")
    console.print(f"Limit  : [cyan]{MAX_PAGES} pages[/]\n")

    results = crawl()

    print_summary(results)
    print_table(results)
    save_csv(results, OUTPUT_CSV)
    save_json(results, OUTPUT_JSON)
