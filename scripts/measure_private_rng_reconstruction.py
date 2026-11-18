"""Matched native restore/fork with one shared explicit configuration payload."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import platform
import time
from pathlib import Path
from typing import cast

from scripts.measure_ingress_reconstruction import CHECKPOINTS, OPERATIONS, sample
from scripts.measure_order63 import _host_inventory, _select_runtime_src

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD_ID = "loaded-ingress-numerical-identity-reconstruction-v3"
FIXTURE = ROOT / "tests/support/fixtures/private_rng_reconstruction_config.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-src", type=Path, default=ROOT / "src")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--config-encoding",
        choices=("unbound-legacy-v2", "engine-numerical-identity-v1"),
        default="engine-numerical-identity-v1",
    )
    args = parser.parse_args()
    _select_runtime_src(args.runtime_src)
    from warhammer40k_core.adapters.local_session import (
        LOCAL_GAME_SESSION_PERSISTENCE_SCHEMA_VERSION,
    )

    expected_schema = {
        "unbound-legacy-v2": "local-game-session-persistence-v2-private-rng",
        "engine-numerical-identity-v1": "local-game-session-persistence-v3-numerical-identity",
    }[args.config_encoding]
    if expected_schema != LOCAL_GAME_SESSION_PERSISTENCE_SCHEMA_VERSION:
        raise ValueError("Benchmark encoding does not match the selected runtime schema.")
    from tests.order63_reserve_transport_helpers import (
        rapid_disembark,
        reserve_transport_session,
        submit_ingress,
    )
    from tests.psychic_modifier_helpers import pending_request

    from warhammer40k_core.build_identity import verified_engine_build_identity
    from warhammer40k_core.engine.game_state import GameConfig
    from warhammer40k_core.engine.game_state_payloads import GameConfigPayload
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    rows = []
    effective_config_hashes: set[str] = set()
    for checkpoint in CHECKPOINTS:
        # Same semantic source fixture, explicitly encoded for each arm's schema.
        # The retained source bytes are never rewritten; this workload rolls no dice.
        config_payload = json.loads(FIXTURE.read_bytes())
        if "numerical_identity" in config_payload:
            raise ValueError("Retained source fixture unexpectedly contains numerical identity.")
        if args.config_encoding == "engine-numerical-identity-v1":
            config_payload["numerical_identity"] = {
                "version": "engine-numerical-identity-v1",
                "numerical_policy_id": "legacy-binary-inch-v1",
                "coordinate_representation_id": "binary-float-pose-v1",
            }
        effective_config_hashes.add(
            hashlib.sha256(json.dumps(config_payload, sort_keys=True).encode()).hexdigest()
        )
        config = GameConfig.from_payload(cast(GameConfigPayload, config_payload))
        session = reserve_transport_session(config=config)
        submit_ingress(session)
        if checkpoint != "ingress":
            outcome = rapid_disembark(session, y=5)
            assert outcome.status_kind is not LifecycleStatusKind.INVALID, outcome
        if checkpoint == "later_decision":
            request = pending_request(session)
            outcome = session.submit_option(
                request_id=request.request_id,
                result_id="reconstruction:later-selection",
                option_id="army-alpha:remaining-unit",
            )
            assert outcome.status_kind is not LifecycleStatusKind.INVALID, outcome
        state = session.lifecycle.state
        assert state is not None
        saved = session.lifecycle.to_payload()
        for operation in OPERATIONS:
            rows.append(
                {
                    "checkpoint": checkpoint,
                    "operation": operation,
                    "samples": [sample(session, operation) for _ in range(7)],
                    "profile": sample(session, operation, profile=True),
                    "unit_count": sum(len(a.units) for a in state.army_definitions),
                    "model_count": sum(
                        len(u.own_models) for a in state.army_definitions for u in a.units
                    ),
                    "decision_records": len(saved["decisions"]["records"]),
                    "event_records": len(saved["decisions"]["event_log"]),
                }
            )
            print(f"Completed {checkpoint}/{operation}", flush=True)
    if args.config_encoding == "unbound-legacy-v2":
        from warhammer40k_core.adapters.checkpoint_reconstruction import (
            PROFILE_ID,
            reconstruct_local_checkpoint,
        )
    else:
        from warhammer40k_core.adapters.numerical_checkpoint_reconstruction import (
            PROFILE_ID,
            reconstruct_local_checkpoint,
        )
    original = gzip.decompress(
        (ROOT / "data/source_audits/a32_recovery/oct14-post-exception.json.gz").read_bytes()
    )
    operator_samples = []
    for _ in range(7):
        started = time.perf_counter()
        package = reconstruct_local_checkpoint(original, profile_id=PROFILE_ID)
        operator_samples.append(time.perf_counter() - started)
        provenance = package["provenance"]
        assert isinstance(provenance, dict)
        assert provenance["original_event_count"] == 137
        assert provenance["reconstructed_event_count"] == 138
        assert provenance["decision_count"] == 18
        assert provenance["original_decisions_and_gameplay_outcomes_preserved"] is True
    rows.append(
        {
            "case": "audit_operator/reconstruct",
            "samples_seconds": operator_samples,
            "complete": True,
            "source_sha256": hashlib.sha256(original).hexdigest(),
            "recipe_profile_id": PROFILE_ID,
        }
    )
    assert len(effective_config_hashes) == 1
    cpu, memory = _host_inventory()
    report = {
        "workload_id": WORKLOAD_ID,
        "revision": args.revision,
        "config_encoding": args.config_encoding,
        "source_fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        "effective_fixture_sha256": next(iter(effective_config_hashes)),
        "runtime_build_id": verified_engine_build_identity().build_id,
        "cpu": cpu,
        "memory_bytes": memory,
        "cpu_allocation": os.cpu_count(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "concurrency": 1,
        "coverage": False,
        "completed": True,
        "rows": rows,
        "full_game_certified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
