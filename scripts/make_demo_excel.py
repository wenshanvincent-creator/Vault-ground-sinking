"""Generate the public synthetic export for an isolated browser check."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vault.demo import synthetic_excel


if __name__ == "__main__":
    output = ROOT / "tmp" / "demo-export.xlsx"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(synthetic_excel())
    print("Synthetic export generated under tmp/ (excluded from Git).")
