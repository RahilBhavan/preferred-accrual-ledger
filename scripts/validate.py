"""Run source checks, tests and two identical offline demos; record output hashes."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMOS = [['-m', 'ledger'], ['-m', 'ledger', '--scenario', 'approved', '--out', 'results/approved']]


def run(args):
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def hashes():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for directory in (ROOT / "results", ROOT / "data/derived")
            if directory.exists() for p in sorted(directory.rglob("*")) if p.is_file()}


def main():
    run(["scripts/verify_sources.py"])
    run(["-m", "unittest", "discover", "-s", "tests", "-v"])
    for demo in DEMOS:
        run(demo)
    first = hashes()
    for demo in DEMOS:
        run(demo)
    if first != hashes():
        raise RuntimeError("demo output hashes changed between identical runs")
    evidence = {"financial_as_of": "2026-10-21", "python": sys.version.split()[0],
                "demo_commands": [[sys.executable, *d] for d in DEMOS],
                "reproducible_output_files": first}
    (ROOT / "docs/validation.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(f"Reproduced {len(first)} output file hashes")


if __name__ == "__main__":
    main()
