"""Pack or restore the frozen source cache without network access.

Each archive part is <=18,000 bytes to meet this workspace's staged-file limit.
The archive SHA-256 protects the entire byte stream; original per-source metadata
and frozen inventories retain source URL, fetch time and content hash.
"""
import argparse
import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAP = ROOT / "snapshot"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pack", action="store_true", help="replace snapshot from current raw/curated data")
    args = p.parse_args()
    if args.pack:
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as tar:
            for folder in (ROOT / "data/raw", ROOT / "data/curated"):
                if not folder.exists():
                    continue
                for path in sorted(folder.rglob("*")):
                    if path.is_file():
                        info = tar.gettarinfo(str(path), arcname=str(path.relative_to(ROOT)))
                        info.uid = info.gid = info.mtime = 0
                        info.uname = info.gname = ""
                        tar.addfile(info, io.BytesIO(path.read_bytes()))
        blob = gzip.compress(stream.getvalue(), mtime=0)
        SNAP.mkdir(exist_ok=True)
        for old in SNAP.glob("part-*"):
            old.unlink()
        n = 0
        for offset in range(0, len(blob), 18000):
            (SNAP / f"part-{n:04d}").write_bytes(blob[offset:offset + 18000])
            n += 1
        (SNAP / "index.json").write_text(json.dumps({"sha256": hashlib.sha256(blob).hexdigest(),
            "bytes": len(blob), "parts": n, "as_of": "2026-10-21"}, indent=2) + "\n")
    else:
        index = json.loads((SNAP / "index.json").read_text())
        blob = b"".join((SNAP / f"part-{i:04d}").read_bytes() for i in range(index["parts"]))
        if len(blob) != index["bytes"] or hashlib.sha256(blob).hexdigest() != index["sha256"]:
            raise ValueError("snapshot integrity check failed")
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
            tar.extractall(ROOT, filter="data")
        print("Restored verified source snapshot", index["sha256"])


if __name__ == "__main__":
    main()
