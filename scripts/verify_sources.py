"""Verify frozen source bytes against the committed inventory, offline."""
import csv
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify():
    count = 0
    for part in sorted((ROOT / "provenance").glob("sources-*.csv")):
        with part.open() as f:
            for row in csv.DictReader(f):
                path = ROOT / row["path"]
                body = path.read_bytes()
                if hashlib.sha256(body).hexdigest() != row["sha256"] or len(body) != int(row["bytes"]):
                    raise ValueError(f"source integrity mismatch: {row['path']}")
                count += 1
    if not count:
        raise ValueError("no source inventory")
    return count


if __name__ == "__main__":
    print(f"Verified {verify()} source files")
