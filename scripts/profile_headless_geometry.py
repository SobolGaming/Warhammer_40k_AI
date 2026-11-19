"""Profile a fixed native Cavalcade mirror slice using the ordinary adapter facade."""

from __future__ import annotations

import argparse
import cProfile
import json
import platform
import time
from contextlib import nullcontext
from pathlib import Path
from typing import TYPE_CHECKING

from tests.support.cavalcade_native_approach import submit_approach_choice
from tests.support.cavalcade_native_prefix import complete_native_prefix
from tests.support.cavalcade_v995 import run_mirror_to_command

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.visibility import TerrainVisibilityContext
from warhammer40k_core.engine.objective_control import resolve_objective_control
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.physical_engagement import (
    scenario_physically_engaged_enemy_rules_unit_ids,
)
from warhammer40k_core.engine.shooting_selection_range import target_in_range_model_ids
from warhammer40k_core.geometry.pathing import PathValidationContext, TerrainPathLegalityContext
from warhammer40k_core.geometry.physical_visibility import (
    resolve_physical_any_visibility,
    resolve_physical_visibility,
)
from warhammer40k_core.geometry.volume import Model

if TYPE_CHECKING:
    from warhammer40k_core.engine.event_log import JsonValue


METRICS = {
    "pathing.model_path": PathValidationContext.validate.__code__,
    "pathing.terrain_path": TerrainPathLegalityContext.validate.__code__,
    "range.engaged_enemy_units": scenario_physically_engaged_enemy_rules_unit_ids.__code__,
    "range.model_engagement": Model.is_within_engagement_range.__code__,
    "range.target_models": target_in_range_model_ids.__code__,
    "range.model_distance": Model.range_to.__code__,
    "los.boolean": TerrainVisibilityContext.has_line_of_sight.__code__,
    "los.witness": TerrainVisibilityContext.resolve_line_of_sight.__code__,
    "other.objective_control": resolve_objective_control.__code__,
}


def _board(session: LocalGameSession) -> dict[str, int]:
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    board = state.battlefield_state
    units = [unit for army in board.placed_armies for unit in army.unit_placements]
    return {
        "units": len(units),
        "models": sum(len(unit.model_placements) for unit in units),
        "terrain_features": len(board.terrain_features),
    }


def _prepare(checkpoint: Path) -> dict[str, object]:
    started = time.perf_counter()
    session, _ = run_mirror_to_command()
    setup_seconds = time.perf_counter() - started
    board = _board(session)
    assert board["units"] == 18
    assert board["models"] == 78
    started = time.perf_counter()
    checkpoint.write_text(json.dumps(session.to_persistence_payload()), encoding="utf-8")
    return {
        "mirror_setup_seconds": setup_seconds,
        "checkpoint_write_seconds": time.perf_counter() - started,
        "board": board,
        "setup_decisions": session.decision_record_count(),
    }


def _play(session: LocalGameSession) -> None:
    complete_native_prefix(session)
    status = submit_approach_choice(session, recipe="revised-v5")
    assert status.status_kind not in (
        LifecycleStatusKind.INVALID,
        LifecycleStatusKind.UNSUPPORTED,
    ), status
    advanced = session.advance_until_decision_or_terminal()
    request = advanced.decision_request
    assert request is not None, advanced
    assert request.decision_type == "select_shooting_unit", advanced
    assert session.decision_record_count() == 69


def _profile_rows(profile: cProfile.Profile) -> dict[str, object]:
    entries = {entry.code: entry for entry in profile.getstats()}
    rows: dict[str, object] = {}
    for name, code in METRICS.items():
        entry = entries.get(code)
        rows[name] = {
            "calls": entry.callcount if entry else 0,
            "inclusive_seconds": entry.totaltime if entry else 0.0,
            "self_seconds": entry.inlinetime if entry else 0.0,
        }
    return rows


def _sample(checkpoint: Path, *, profiled: bool) -> dict[str, object]:
    started = time.perf_counter()
    session = LocalGameSession.from_persistence_payload(
        json.loads(checkpoint.read_text(encoding="utf-8"))
    )
    restore_seconds = time.perf_counter() - started
    before = session.decision_record_count()
    assert before == 42
    caches = {
        "any_visibility": resolve_physical_any_visibility,
        "full_visibility": resolve_physical_visibility,
    }
    cache_before = {name: fn.cache_info() for name, fn in caches.items()}
    profile = cProfile.Profile() if profiled else None
    started = time.perf_counter()
    with profile if profile is not None else nullcontext():
        _play(session)
    gameplay_seconds = time.perf_counter() - started
    cache_after = {name: fn.cache_info() for name, fn in caches.items()}
    state = session.lifecycle.state
    request = session.lifecycle.pending_decision_request()
    payload: JsonValue = session.to_persistence_payload()
    assert state is not None
    assert state.current_battle_phase is not None
    assert request is not None
    assert isinstance(payload, dict)
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "restore_seconds": restore_seconds,
        "gameplay_seconds": gameplay_seconds,
        "gameplay_decisions": session.decision_record_count() - before,
        "boundary": [
            state.battle_round,
            state.active_player_id,
            state.current_battle_phase.value,
            request.decision_type,
        ],
        "checkpoint_content_hash": payload["content_hash"],
        "board": _board(session),
        "solver_cache_deltas": {
            name: {
                "hits": after.hits - cache_before[name].hits,
                "misses": after.misses - cache_before[name].misses,
            }
            for name, after in cache_after.items()
        },
        "profile": _profile_rows(profile) if profile is not None else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--prepare", action="store_true", help="Create the mirror command checkpoint."
    )
    mode.add_argument("--profile", action="store_true", help="Collect per-function wall times.")
    args = parser.parse_args()
    report = (
        _prepare(args.checkpoint)
        if args.prepare
        else _sample(args.checkpoint, profiled=args.profile)
    )
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
