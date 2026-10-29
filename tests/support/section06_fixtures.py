"""One selected-source build; fresh native model graphs at the smallest rule owner."""

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from time import perf_counter

import pytest
from tests.support.section02_fixtures import Section02Definitions
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.engine.damage_allocation import MortalWoundApplicationProgress
from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MortalWoundDestructionEvidence,
)
from warhammer40k_core.engine.phase import BattlePhase

NATIVE_IDS = ("000004080", "000004078", "000000968", "000000599", "000000613", "000000602")


@pytest.fixture(scope="session")
def section06_definitions(
    selected_army_source_index: Path | None,
) -> Iterator[Section02Definitions]:
    started = perf_counter()
    package = _ability_support_catalog_package(
        datasheet_ids=NATIVE_IDS, source_index_dir=selected_army_source_index
    )
    elapsed = perf_counter() - started
    before = hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
    print(f"Section06 preparation: {elapsed:.6f}s; one selected build, six native definitions")
    yield Section02Definitions(package, elapsed)
    assert (
        hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
        == before
    )


def mortal_progress(state: GameState, target: str, wounds: int) -> MortalWoundApplicationProgress:
    """Explicit rule-outcome contract, with real provenance and placement authority."""
    source = state.army_definitions[0].units[0]
    return MortalWoundApplicationProgress.start(
        application_id="s06:mortals",
        source_rule_id="constructed:s06:mortal-outcome",
        source_context={
            "source_kind": "ability",
            "source_rule_id": "constructed:s06:mortal-outcome",
        },
        target_unit_instance_id=target,
        defender_player_id="owner",
        mortal_wounds=wounds,
        spill_over=True,
        destruction_evidence=MortalWoundDestructionEvidence.for_non_attack_state(
            state=state,
            destroying_player_id="owner",
            source_rules_unit_instance_id=source.unit_instance_id,
            source_model_instance_id=source.own_models[0].model_instance_id,
            destruction_source_kind=DestructionSourceKind.ABILITY,
            action_phase=BattlePhase.SHOOTING,
            source_step="constructed:s06:rule-outcome",
        ),
    )
