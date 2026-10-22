"""Cached fetching from primary sources (SEC EDGAR).

Each response is written to data/raw/<name> with a sidecar <name>.meta.json holding
the URL, the UTC fetch time and the SHA-256 of the body. Later runs read the cache.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
# SEC fair-access policy rejects agents without a contact email (HTTP 403 observed
# 2026-10-21), so set EDGAR_USER_AGENT to "<name> <email>" before fetching.
USER_AGENT = os.environ.get("EDGAR_USER_AGENT", "RahilBhavan-research (github.com/RahilBhavan)")
# Observed: "RahilBhavan-research <email>" works; the parenthesised URL form is refused.
_last_request = [0.0]


def get(url: str, name: str, refresh: bool = False) -> bytes:
    """Return the body for url from data/raw/name, fetching it once if absent."""
    path = RAW / name
    if path.exists() and not refresh:
        return path.read_bytes()
    wait = 0.2 - (time.time() - _last_request[0])  # <= 5 requests per second
    if wait > 0:
        time.sleep(wait)
    agent = USER_AGENT if "sec.gov" in url else "RahilBhavan-research (github.com/RahilBhavan)"
    request = urllib.request.Request(url, headers={"User-Agent": agent})
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read()
    _last_request[0] = time.time()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    sidecar = {
        "url": url,
        "fetched_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
    }
    path.with_name(path.name + ".meta.json").write_text(json.dumps(sidecar, indent=1) + "\n")
    return body


def meta(name: str) -> dict:
    return json.loads((RAW / (name + ".meta.json")).read_text())


if __name__ == "__main__":
    get(sys.argv[1], sys.argv[2], refresh="--refresh" in sys.argv)
    print(meta(sys.argv[2]))
