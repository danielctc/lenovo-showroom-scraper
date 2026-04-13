# Quarterly refresh runbook

End-to-end flow for taking a new Lenovo TopSeller spreadsheet and getting the live Spaces Showroom (`https://spaces-showroom.daniel-667.workers.dev`) back in sync.

Owner: Daniel Thomas.
Companion repo: [`danielctc/spaces-showroom`](https://github.com/danielctc/spaces-showroom) — the Astro + Workers app this populates.

---

## TL;DR

```bash
# 0. Save new xlsx into fixtures/
cp ~/Downloads/TS_Price_List_T3_July_2026.xlsx fixtures/

# 1. Activate venv
source .venv/bin/activate

# 2. Parse the spreadsheet → seed.sql (commercial data only)
python3 scripts/generate_seed.py \
  --xlsx fixtures/TS_Price_List_T3_July_2026.xlsx \
  --out /tmp/seed/seed.sql

# 3. Apply the commercial data to D1 (replaces all prices / names / images stubs)
#    ⚠️ see "Full reset vs. patch" below — this runbook assumes a full reset.
export CLOUDFLARE_ACCOUNT_ID=667002b441ec98372c53418ff3879aab
cd ~/spaces-showroom
./node_modules/.bin/wrangler d1 execute SHOWROOM_DB --remote \
  --command "DELETE FROM product_images; DELETE FROM product_specs; DELETE FROM products;"
./node_modules/.bin/wrangler d1 execute SHOWROOM_DB --remote \
  --file=/tmp/seed/seed.sql
cd -

# 4. Scrape PSREF for every part number (≈30 min for ~300 SKUs)
python3 scripts/scrape_all.py | tee /tmp/seed/scrape.log

# 5. Apply scraped specs + real image URLs to D1
python3 scripts/apply_to_d1.py --apply

# 6. Smoke-test the live site
curl -s https://spaces-showroom.daniel-667.workers.dev/product/<known-PN> | grep -c spec-row
```

No Worker redeploy is needed — Kate's data lives in D1, not in the bundled code.

---

## Prerequisites (one-time per laptop)

| Tool | Install | Notes |
|---|---|---|
| Python ≥ 3.10 | Homebrew (`brew install python@3.12`) | Needed for Scrapling + openpyxl |
| `scrapling[all]` + Playwright browsers | `make install` (runs in this repo) | Pulls ~300MB Chromium |
| `wrangler` | Comes with the `spaces-showroom` repo (`npm install`) | `wrangler whoami` should show `daniel@comparethecloud.net` |
| Cloudflare account ID | `667002b441ec98372c53418ff3879aab` (Daniel@comparethecloud.net) | Export as `CLOUDFLARE_ACCOUNT_ID` |

The generated scripts honour these env vars, all with sensible defaults baked in:

| Env var | Default | Meaning |
|---|---|---|
| `CLOUDFLARE_ACCOUNT_ID` | `667002b441ec98372c53418ff3879aab` | Personal Daniel account |
| `WRANGLER_BIN` | `~/spaces-showroom/node_modules/.bin/wrangler` | Path to wrangler |
| `SHOWROOM_DIR` | `~/spaces-showroom` | cwd for wrangler invocations (reads `wrangler.toml`) |
| `SCRAPE_OUT` | `/tmp/seed/scrape_results.jsonl` | JSONL file the scraper appends to (resumable) |
| `APPLY_SQL` | `/tmp/seed/apply.sql` | Generated SQL the apply step writes then executes |

---

## The three moving parts

```
fixtures/TS_Price_List_T*.xlsx
      │
      │ scripts/generate_seed.py     (offline, from openpyxl)
      ▼
/tmp/seed/seed.sql  ──►  D1 products / product_specs (stub) / product_images (placeholder URLs)
                                               │
                                               │ scripts/scrape_all.py     (Scrapling DynamicSession)
                                               ▼
                                /tmp/seed/scrape_results.jsonl
                                               │
                                               │ scripts/apply_to_d1.py --apply
                                               ▼
                  D1 product_specs (full) + product_images (real PSREF URLs)
                                               │
                                               │ /api/img/:pn/:idx.png  (Worker route)
                                               ▼
                               Edge cache → upstream psrefstuff.lenovo.com
```

### Step 1 — `generate_seed.py`

Parses the `All Part Numbers` sheet (canonical per PRD §9). Maps the brand column to a showroom category tile, formats prices, and emits:

- 1 row per SKU into `products`
- 3-6 stub rows per SKU into `product_specs` (processor / memory / storage / OS / weight / warranty from the flat table — enough to render the product card and accordion header until the scraper runs).
- 1 placeholder row per SKU into `product_images` with `r2_key='external'` and a best-effort PSREF URL.

The script skips brands that don't map to a category (Software, Education, bulk Accessories).

### Step 2 — `scrape_all.py`

Opens a single Playwright browser (via `DynamicSession`), iterates through every active part number in D1, hits `psref.lenovo.com/Detail/?M={pn}`, extracts:

- Real product title (`h1`)
- All syspool image URLs (typically 3-9)
- The full PSREF spec table, grouped by section (`Performance`, `Display`, `Connectivity`, `Power & OS`, etc.)

Runs at ~4 s/page with a 2 s delay → full catalogue (~300 SKUs) completes in ~30 minutes. Resumable: append-only JSONL keyed by part number — rerun after a network blip and it'll skip everything already captured.

### Step 3 — `apply_to_d1.py`

Turns `scrape_results.jsonl` into a patch:

- `DELETE FROM product_specs WHERE part_number IN (<scraped>)`
- `DELETE FROM product_images WHERE part_number IN (<scraped>)`
- `INSERT` the real specs and image rows
- `UPDATE products.name` when the scrape found a more canonical title

Run without `--apply` for a dry run (writes `apply.sql` only). Run with `--apply` to execute against remote D1.

---

## Full reset vs. patch

There are two ways to run a refresh:

### Full reset (recommended for schema-changing quarters)

Wipe all three tables and re-import. Use when the xlsx layout changes, part numbers are being renumbered, or something has drifted badly.

```bash
wrangler d1 execute SHOWROOM_DB --remote \
  --command "DELETE FROM product_images; DELETE FROM product_specs; DELETE FROM products;"
wrangler d1 execute SHOWROOM_DB --remote --file=/tmp/seed/seed.sql
python3 scripts/scrape_all.py
python3 scripts/apply_to_d1.py --apply
```

### Incremental patch (safer for price-only updates)

Skip the DELETE. The seed's `INSERT INTO products …` will fail on PK collisions but D1 batches swallow the errors and move on. This is **not idempotent for prices** — better to change `generate_seed.py` to emit `INSERT OR REPLACE` if you want this path. Left as a TODO.

---

## Sanity checks before / after

Before scraping, confirm D1 has products:
```bash
wrangler d1 execute SHOWROOM_DB --remote \
  --command "SELECT category, COUNT(*) FROM products GROUP BY category;"
```

After applying scrape results:
```bash
# Expect hundreds of spec rows per SKU, not the 6 stubs
wrangler d1 execute SHOWROOM_DB --remote \
  --command "SELECT part_number, COUNT(*) FROM product_specs GROUP BY part_number ORDER BY 2 DESC LIMIT 10;"
```

Live HTTP:
```bash
URL=https://spaces-showroom.daniel-667.workers.dev
curl -s $URL/ | grep -c 'href="/product/'        # should be 24 (featured list)
curl -s $URL/category/ThinkPad | grep -c 'href="/product/'   # category count
curl -sI $URL/api/img/<a-real-PN>/0.png            # should be 200 + image/* content-type
```

---

## Troubleshooting

**"Uncaught Error: No such module 'node:child_process'" on deploy.**
The Astro Cloudflare adapter pulls sharp in by default. Fix is already committed (`imageService: 'passthrough'` in `astro.config.mjs`). If someone upgrades and it regresses, re-add the flag and verify `sharp` isn't in `dist/_worker.js/chunks/`.

**Scrapling timeouts.**
`DynamicFetcher.fetch(..., timeout=X)` — `X` is **milliseconds** in Scrapling 0.4+. Use 60000 not 60. Default in `scrape_all.py` is 60 s + 3.5 s wait.

**D1 rejects `BEGIN;` / `COMMIT;`.**
D1 wraps each exec in its own batch. Do not emit explicit transactions. `generate_seed.py` already avoids this, but if you hand-edit SQL, strip them.

**Scraper gets blocked by PSREF.**
Bump `time.sleep()` at the bottom of the loop, or change `SCRAPE_OUT` and let it resume later. Scrapling's StealthySession is an upgrade path if Lenovo starts fingerprinting.

**Wrangler auth.**
`wrangler whoami` should show `daniel@comparethecloud.net`. If not: `wrangler login` and tick the daniel account during OAuth.

---

## Files this runbook depends on

- `scripts/generate_seed.py` — xlsx → seed.sql
- `scripts/scrape_all.py` — D1 → PSREF → JSONL
- `scripts/apply_to_d1.py` — JSONL → apply.sql → D1
- `fixtures/TS_Price_List_*.xlsx` — the raw TopSeller spreadsheet
- `~/spaces-showroom/migrations/0001_init.sql` — the D1 schema (reset with `wrangler d1 migrations apply SHOWROOM_DB --remote`)
- `~/spaces-showroom/wrangler.toml` — bindings, account, database id
