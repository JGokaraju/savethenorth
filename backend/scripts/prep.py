"""`make prep`: precompute science outputs and charts into data/processed/ (after the inventory)."""
from __future__ import annotations

import json
import time

from backend.settings import PROCESSED


def main() -> None:
    t0 = time.time()
    from backend.tools.pipeline import precompute
    summary = precompute()
    (PROCESSED / "prep_summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    for k, v in summary.items():
        print(f"{k:24s} {v}")
    print(f"prep finished in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
