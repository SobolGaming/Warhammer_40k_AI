"""Retain cold exact-fit diagnostics, including the two repaired solver stalls."""

import json
import platform
import time
from pathlib import Path

from warhammer40k_core.geometry.base import CircularBase, OvalBase, RectangularBase
from warhammer40k_core.geometry.disembark_fit import base_fits_disembark_distance

CASES = (
    ("ellipse-circle-positive", OvalBase(5, 1), CircularBase(2), True),
    ("ellipse-circle-negative", OvalBase(8, 2), CircularBase(2), False),
    ("rectangle-circle-negative", RectangularBase(8, 2), CircularBase(2), False),
    ("ellipse-ellipse-positive", OvalBase(8, 2), OvalBase(6, 2), True),
    ("rectangle-ellipse-positive", RectangularBase(8, 2), OvalBase(6, 2), True),
    ("ellipse-rectangle-positive", OvalBase(8, 2), RectangularBase(6, 2), True),
)


def main() -> None:
    samples = []
    for _ in range(7):
        base_fits_disembark_distance.cache_clear()
        start = time.perf_counter()
        results = [
            base_fits_disembark_distance(base, transport, 3) for _, base, transport, _ in CASES
        ]
        assert results == [expected for _, _, _, expected in CASES]
        samples.append({"seconds": time.perf_counter() - start, "fits": results})
    report = {
        "workload_id": "order55-cold-analytic-fit-v1",
        "platform": platform.platform(),
        "python": platform.python_version(),
        "concurrency": 1,
        "distance_inches": 3,
        "maximum_sample_budget_seconds": 1,
        "cases": [
            {"id": name, "base": base.to_payload(), "transport": transport.to_payload()}
            for name, base, transport, _ in CASES
        ],
        "samples": samples,
        "earlier_quantified_prototype": {
            "ellipse-circle-positive": "interrupted without a proved result",
            "ellipse-ellipse-positive": "interrupted without a proved result",
            "elapsed_seconds": None,
            "resolution": (
                "Exact tangent, PSD and rational containment certificates; no guessed result."
            ),
        },
        "full_game_certified": False,
    }
    assert max(sample["seconds"] for sample in samples) < 1
    output = Path(__file__).resolve().parents[1] / "docs/performance/order55/geometry.json"
    output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
