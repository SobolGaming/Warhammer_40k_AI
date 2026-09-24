"""Serial derived-projection diagnostic against PR #501 review base and repaired head."""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
from dataclasses import replace
from pathlib import Path
from time import perf_counter
from typing import cast

from tests.order81_projection_helpers import revival_projection_session

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.projection import (
    _nested_interaction_request_views,
    _proposal_view,
    public_decision_request_view,
)
from warhammer40k_core.build_identity import current_engine_build_id
from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.engine.interaction_metadata import (
    interaction_annotated_decision_request_payload,
)

ROOT = Path(__file__).resolve().parents[1]


def measure() -> dict[str, object]:
    session, _ = revival_projection_session(
        source_context={"public": [{"cause_id": "private-authority", "public_note": "keep"}]}
    )
    request = session.lifecycle.pending_decision_request()
    assert request is not None
    nested = interaction_annotated_decision_request_payload(request)
    outer = replace(
        request,
        payload={
            **cast(dict[str, JsonValue], request.payload),
            "nested_interaction_requests": [cast(JsonValue, nested)],
        },
    )
    viewer = ViewerContext.for_player("player-a")
    rows: list[dict[str, object]] = []
    for name, project in (
        ("pending_decision", lambda: public_decision_request_view(request, viewer=viewer)),
        ("pending_proposal", lambda: _proposal_view(request, viewer=viewer)),
        ("nested_interactions", lambda: _nested_interaction_request_views(outer, viewer=viewer)),
    ):
        samples: list[float] = []
        for _sample in range(9):
            started = perf_counter()
            for _iteration in range(2000):
                project()
            samples.append((perf_counter() - started) / 2000)
        rows.append(
            {
                "case": name,
                "iterations_per_sample": 2000,
                "samples_seconds": samples,
                "mean_seconds": statistics.mean(samples),
                "median_seconds": statistics.median(samples),
                "maximum_seconds": max(samples),
                "protected_authority_exposed": "private-authority" in json.dumps(project()),
            }
        )
    return {
        "workload": "order81-derived-projection-redaction-v1",
        "runtime_build_id": current_engine_build_id(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpu": "Apple M5 Pro",
        "logical_cpus": 18,
        "memory_bytes": 68719476736,
        "hardware_status": "provisional",
        "workers": 1,
        "coverage": False,
        "scope": "Derived request projections only; setup excluded; no full-game timing claim.",
        "fixture": "5-model recipient/enemy; one destroyed recipient; no terrain or random draws.",
        "input_sha256": hashlib.sha256(canonical_json(outer.to_payload()).encode()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "fixture_sha256": hashlib.sha256(
            (ROOT / "tests/order81_projection_helpers.py").read_bytes()
        ).hexdigest(),
        "lock_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "rows": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(measure(), indent=2) + "\n")
