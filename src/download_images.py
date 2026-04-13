"""Download PSREF product images to a local tempdir before pushing to R2."""
from __future__ import annotations
from pathlib import Path
import httpx


def download(urls: list[str], dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        for idx, url in enumerate(urls):
            resp = client.get(url)
            resp.raise_for_status()
            path = dest / f"{idx}.png"
            path.write_bytes(resp.content)
            saved.append(path)
    return saved
