#!/usr/bin/env python3
"""Convert /tmp/seed/scrape_results.jsonl → SQL patches for D1.

Emits /tmp/seed/apply.sql which:
 - DELETE FROM product_specs WHERE part_number IN (…)
 - DELETE FROM product_images WHERE part_number IN (…)
 - INSERT new specs (full PSREF table)
 - INSERT new images (one row per scraped image URL)
 - UPDATE products.name where scrape found a better title

Then executes via wrangler d1 execute --remote.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

IN_JSONL = Path(os.environ.get("SCRAPE_OUT", "/tmp/seed/scrape_results.jsonl"))
OUT_SQL = Path(os.environ.get("APPLY_SQL", "/tmp/seed/apply.sql"))
CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "667002b441ec98372c53418ff3879aab")
WRANGLER = os.environ.get("WRANGLER_BIN", "/Users/comparethecloud/spaces-showroom/node_modules/.bin/wrangler")
SHOWROOM_DIR = os.environ.get("SHOWROOM_DIR", "/Users/comparethecloud/spaces-showroom")


def sql(v) -> str:
    if v is None or v == "":
        return "NULL"
    s = str(v).strip().replace("'", "''")
    return "'" + s + "'"


def main() -> int:
    rows = []
    for line in IN_JSONL.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    ok = [r for r in rows if "specs" in r and r.get("specs")]
    errored = [r for r in rows if "error" in r]
    print(f"[info] scraped={len(rows)} ok={len(ok)} errored={len(errored)}")

    pns = [r["partNumber"] for r in ok]
    if not pns:
        print("nothing to apply")
        return 0

    # Chunk the IN list to keep single statements sane (D1 limit is 100 binds)
    lines: list[str] = ["-- Generated from scrape_results.jsonl"]

    def chunks(lst, n):
        for i in range(0, len(lst), n):
            yield lst[i : i + n]

    for group in chunks(pns, 80):
        in_list = ",".join(sql(p) for p in group)
        lines.append(f"DELETE FROM product_specs WHERE part_number IN ({in_list});")
        lines.append(f"DELETE FROM product_images WHERE part_number IN ({in_list});")

    # Insert specs and images
    for r in ok:
        pn = r["partNumber"]
        title = (r.get("title") or "").strip()
        if title and 4 <= len(title) <= 200:
            lines.append(f"UPDATE products SET name={sql(title)}, updated_at=datetime('now') WHERE part_number={sql(pn)};")
        for s in r["specs"]:
            lines.append(
                "INSERT INTO product_specs (part_number,category,label,value,sort_order) VALUES ("
                f"{sql(pn)},{sql(s['category'])},{sql(s['label'])},{sql(s['value'])},{int(s.get('sort_order') or 0)});"
            )
        # first image = r2_key placeholder 'external', source_url = real PSREF URL
        for idx, url in enumerate(r.get("images", [])):
            lines.append(
                "INSERT INTO product_images (part_number,source_url,r2_key,sort_order) VALUES ("
                f"{sql(pn)},{sql(url)},'external',{idx});"
            )

    OUT_SQL.write_text("\n".join(lines) + "\n")
    print(f"[info] wrote {OUT_SQL} ({OUT_SQL.stat().st_size} bytes, {len(lines)} statements)")

    if "--apply" in sys.argv:
        env = {**os.environ, "CLOUDFLARE_ACCOUNT_ID": CLOUDFLARE_ACCOUNT_ID}
        cmd = [
            WRANGLER, "d1", "execute", "SHOWROOM_DB", "--remote",
            f"--file={OUT_SQL}",
        ]
        print("[info] running wrangler d1 execute…")
        p = subprocess.run(cmd, cwd=SHOWROOM_DIR, env=env)
        return p.returncode
    else:
        print("[info] dry run — pass --apply to execute on D1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
