#!/usr/bin/env python3
"""Scrape PSREF for every part number in spaces-showroom D1.

Output: /tmp/seed/scrape_results.jsonl (one product per line).
Resumable — reads existing JSONL and skips already-scraped PNs.

Usage: python3 /tmp/seed/scrape_all.py [LIMIT]
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from scrapling.fetchers import DynamicSession

OUT = Path(os.environ.get("SCRAPE_OUT", "/tmp/seed/scrape_results.jsonl"))
PROGRESS = Path(os.environ.get("SCRAPE_PROGRESS", "/tmp/seed/scrape_progress.txt"))
CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "667002b441ec98372c53418ff3879aab")
WRANGLER = os.environ.get("WRANGLER_BIN", "/Users/comparethecloud/spaces-showroom/node_modules/.bin/wrangler")
SHOWROOM_DIR = os.environ.get("SHOWROOM_DIR", "/Users/comparethecloud/spaces-showroom")


def load_part_numbers() -> list[str]:
    env = {**os.environ, "CLOUDFLARE_ACCOUNT_ID": CLOUDFLARE_ACCOUNT_ID}
    result = subprocess.run(
        [
            WRANGLER,
            "d1", "execute", "SHOWROOM_DB", "--remote",
            "--command", "SELECT part_number FROM products WHERE is_active=1 ORDER BY category, name;",
            "--json",
        ],
        cwd=SHOWROOM_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        print("wrangler failed:", result.stderr, file=sys.stderr)
        sys.exit(1)
    data = json.loads(result.stdout)
    return [r["part_number"] for r in data[0]["results"]]


def already_done() -> set[str]:
    if not OUT.exists():
        return set()
    done: set[str] = set()
    with OUT.open() as fh:
        for line in fh:
            try:
                done.add(json.loads(line)["partNumber"])
            except Exception:
                pass
    return done


def extract(page) -> dict:
    # Title — several possible locations; fall back to h1/h3
    title = ""
    for sel in ("h1", "h3", ".productTitle"):
        el = page.find(sel)
        if el and el.get_all_text().strip():
            title = el.get_all_text().strip()
            break

    # Images — unique syspool URLs
    imgs = []
    seen = set()
    for a in page.find_all("img"):
        src = a.attrib.get("src") or ""
        if ("syspool" in src or "Compressedimage" in src) and src not in seen:
            imgs.append(src)
            seen.add(src)

    # Spec table — the one with class containing as_level rows
    spec_table = None
    for t in page.find_all("table"):
        rows = t.find_all("tr")
        for r in rows[:5]:
            if "structureTitleTR" in (r.attrib.get("class") or "") or "as_level2" in (r.attrib.get("class") or ""):
                spec_table = t
                break
        if spec_table:
            break

    specs: list[dict] = []
    if spec_table:
        current_cat = "General"
        sort_counter = 0
        for r in spec_table.find_all("tr"):
            cls = r.attrib.get("class") or ""
            if "structureTitleTR" in cls:
                tds = r.find_all("td")
                if tds:
                    current_cat = tds[0].get_all_text().strip().title()
                sort_counter = 0
                continue
            if "as_level2" in cls:
                tds = r.find_all("td")
                if len(tds) < 2:
                    continue
                label = tds[0].get_all_text().strip()
                val_el = tds[1].find(".rightValue")
                value = (val_el.get_all_text() if val_el else tds[1].get_all_text()).strip()
                # Normalise newlines
                value = re.sub(r"\s+\n\s+", "; ", value)
                value = re.sub(r"\s{2,}", " ", value)
                if label and value:
                    specs.append({
                        "category": current_cat,
                        "label": label,
                        "value": value,
                        "sort_order": sort_counter,
                    })
                    sort_counter += 1

    return {
        "title": title,
        "images": imgs,
        "specs": specs,
    }


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    pns = load_part_numbers()
    print(f"[info] D1 returned {len(pns)} part numbers")
    done = already_done()
    print(f"[info] already scraped {len(done)}")
    todo = [p for p in pns if p not in done]
    if limit:
        todo = todo[:limit]
    print(f"[info] will scrape {len(todo)}")

    session = DynamicSession(max_pages=1)
    session.start()
    try:
        with OUT.open("a") as out:
            for i, pn in enumerate(todo):
                url = f"https://psref.lenovo.com/Detail/?M={pn}"
                started = time.monotonic()
                try:
                    page = session.fetch(url, timeout=60000, wait=3500)
                    data = extract(page)
                    data["partNumber"] = pn
                    data["url"] = url
                    out.write(json.dumps(data, ensure_ascii=False) + "\n")
                    out.flush()
                    dur = time.monotonic() - started
                    msg = f"[{i+1}/{len(todo)}] {pn} {dur:.1f}s  imgs={len(data['images'])} specs={len(data['specs'])} title={data['title'][:40]!r}"
                except Exception as e:
                    msg = f"[{i+1}/{len(todo)}] {pn} ERR {e!r}"
                    out.write(json.dumps({"partNumber": pn, "error": str(e)}) + "\n")
                    out.flush()
                print(msg, flush=True)
                PROGRESS.write_text(f"{i+1}/{len(todo)} {pn}\n")
                time.sleep(2)
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
