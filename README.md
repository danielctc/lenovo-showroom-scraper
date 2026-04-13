# lenovo-showroom-scraper

Quarterly PSREF refresh tool for the Spaces Metaverse Product Showroom.

Any team member can clone this repo and run the quarterly refresh when Kate Bennett distributes a new TopSeller spreadsheet. The scraper pushes enriched product data into the `spaces-showroom` Cloudflare Worker (D1 + R2).

Companion repo: [`spaces-showroom`](../spaces-showroom) (Astro + CF Workers).
Plan: `~/.claude/plans/bubbly-rolling-wilkinson.md`

## Quick start

```bash
git clone https://github.com/<org>/lenovo-showroom-scraper
cd lenovo-showroom-scraper
cp .env.example .env    # fill in SHOWROOM_API_URL, tokens
make install            # creates .venv, installs Scrapling + Playwright browsers
make refresh SPREADSHEET=~/Downloads/TS_Price_List_T2_April_2026.xlsx
```

## Requirements

- Python 3.10+
- Node.js 18+ (for Playwright browsers — `scrapling install` pulls them)
- Valid tokens for `SHOWROOM_UPLOAD_TOKEN` and `SHOWROOM_INGEST_TOKEN` (ask Daniel)

## How it works

1. **Upload** — spreadsheet POSTed to the Worker. The Worker parses the "All Part Numbers" sheet, diffs against D1, writes commercial columns, returns new + removed part numbers.
2. **Scrape** — for each new part number, Scrapling's `DynamicFetcher` renders the PSREF page and extracts the title, images, spec table and tab sections. 2-second delay between requests (PRD §6.3).
3. **Download** — PSREF images saved to a local tempdir.
4. **Ingest** — structured JSON + PNGs POSTed to `/api/ingest`. Worker writes specs to D1 and uploads images to R2.

## Only re-scrape specific part numbers

```bash
make refresh SPREADSHEET=file.xlsx     # full diff
# or skip the diff and target a few:
.venv/bin/showroom-refresh --spreadsheet file.xlsx --only ZAFN0060GB 21MQ004GUK
```

## Layout

```
src/
├─ parse_xlsx.py     # canonical "All Part Numbers" sheet parser
├─ scrape_psref.py   # Scrapling DynamicFetcher wrapper
├─ download_images.py
├─ push.py           # Worker HTTP client
└─ cli.py            # `showroom-refresh` entrypoint
config/sheet_mapping.json  # per-quarter column drift config
tests/fixtures/            # golden HTML + xlsx fixture
```
