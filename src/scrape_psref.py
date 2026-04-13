"""Scrape PSREF product pages using Scrapling's DynamicFetcher (Playwright-backed).

PSREF is client-rendered — standard HTTP scrapers return empty content, so we must
render. Per PRD §6.3: 2s delay between requests, adaptive selectors survive DOM drift.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import time


PSREF_URL = "https://psref.lenovo.com/Detail/?M={part_number}"


@dataclass
class PsrefProduct:
    part_number: str
    title: str
    image_urls: list[str] = field(default_factory=list)
    key_specs: list[str] = field(default_factory=list)
    spec_table: list[dict] = field(default_factory=list)   # {category,label,value,sort_order}
    tabs: dict = field(default_factory=dict)                # accessories / services / docs


def fetch(part_number: str, *, delay: float = 2.0) -> PsrefProduct:
    """Fetch one PSREF page. Returns structured product data."""
    # Scrapling import is local so tests that skip the live scrape do not require
    # Playwright browsers to be installed.
    from scrapling.fetchers import DynamicFetcher  # type: ignore

    url = PSREF_URL.format(part_number=part_number)
    page = DynamicFetcher.fetch(url, timeout=30)
    title = page.css_first("h1::text") or part_number
    images = list({el.attrib.get("src", "") for el in page.css("img[src*='syspool']")})
    # TODO: extract key specs, full spec table, tab sections.
    time.sleep(delay)
    return PsrefProduct(part_number=part_number, title=title, image_urls=images)
