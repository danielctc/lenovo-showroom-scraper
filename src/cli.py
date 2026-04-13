"""End-to-end quarterly refresh orchestrator.

Run: `make refresh SPREADSHEET=TS_Price_List_T2_April_2026.xlsx`

Flow:
  1. POST spreadsheet → Worker parses + diffs, returns new part numbers
  2. For each new part number: Scrapling fetches PSREF, download images
  3. POST enriched payload + images to /api/ingest
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import tempfile

from dotenv import load_dotenv

from .scrape_psref import fetch
from .download_images import download
from .push import push_upload, push_ingest


def main() -> int:
    parser = argparse.ArgumentParser(description="Spaces Showroom quarterly refresh")
    parser.add_argument("--spreadsheet", required=True, type=Path)
    parser.add_argument("--only", nargs="*", help="Limit to specific part numbers (skip upload diff)")
    args = parser.parse_args()

    load_dotenv()
    api_url = os.environ["SHOWROOM_API_URL"]
    upload_token = os.environ["SHOWROOM_UPLOAD_TOKEN"]
    ingest_token = os.environ["SHOWROOM_INGEST_TOKEN"]

    if args.only:
        new_part_numbers = args.only
    else:
        diff = push_upload(api_url, upload_token, args.spreadsheet)
        new_part_numbers = diff.get("newPartNumbers", [])
        print(f"Upload accepted. new={len(new_part_numbers)} removed={len(diff.get('removed', []))}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        for pn in new_part_numbers:
            try:
                product = fetch(pn)
                images = download(product.image_urls, tmp_root / pn)
                push_ingest(api_url, ingest_token, product, images)
                print(f"ok  {pn}  images={len(images)}")
            except Exception as e:  # noqa: BLE001
                print(f"err {pn}  {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
