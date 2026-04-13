"""POST structured product data + images to the showroom Worker."""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import json
import httpx

from .scrape_psref import PsrefProduct


def push_upload(api_url: str, token: str, xlsx_path: Path) -> dict:
    """POST the spreadsheet to /api/upload. Returns {newPartNumbers, removed}."""
    with httpx.Client(timeout=120) as client:
        with xlsx_path.open("rb") as fh:
            resp = client.post(
                f"{api_url.rstrip('/')}/api/upload",
                headers={"authorization": f"Bearer {token}"},
                files={"file": (xlsx_path.name, fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        resp.raise_for_status()
        return resp.json()


def push_ingest(api_url: str, token: str, product: PsrefProduct, images: list[Path]) -> None:
    """POST enriched specs + image files for one part number."""
    files: list[tuple] = [("payload", (None, json.dumps(asdict(product)), "application/json"))]
    for idx, img in enumerate(images):
        files.append((f"png_{idx}", (img.name, img.read_bytes(), "image/png")))
    with httpx.Client(timeout=120) as client:
        resp = client.post(
            f"{api_url.rstrip('/')}/api/ingest",
            headers={"authorization": f"Bearer {token}"},
            files=files,
        )
        resp.raise_for_status()
