"""Section 08 native Command boundaries; shared definitions, fresh case state."""

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from time import perf_counter

import pytest
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockTestRequest,
    collect_battle_shock_test_requests,
)
from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.game_state import (
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection

NATIVE_IDS = ("000004080", "000004078", "000000592", "000000968")


@pytest.fixture(scope="session")
def section08_definitions(
    selected_army_source_index: Path | None,
) -> Iterator[Section02Definitions]:
    start = perf_counter()
    package = _ability_support_catalog_package(
        datasheet_ids=NATIVE_IDS, source_index_dir=selected_army_source_index
    )
    elapsed = perf_counter() - start
    before = hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
    print(f"Section08 definition preparation: {elapsed:.6f}s; four selected native definitions")
    yield Section02Definitions(package, elapsed)
    assert (
        hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
        == before
    )


def command_state(definitions: Section02Definitions, datasheet: str = "000004080") -> GameState:
    # Use the supported ten-model Infractor selection for the source's even-count
    # example; other sheets keep their native minimum composition.
    sheet = definitions.package.army_catalog.datasheet_by_id(datasheet)
    composition = (
        tuple(ModelProfileSelection(p.model_profile_id, p.max_models) for p in sheet.composition)
        if datasheet == "000004080"
        else None
    )
    state = native_state(
        definitions,
        definitions.unit(datasheet, composition=composition),
        enemy=definitions.unit("000004078", army_id="enemy", identity="target"),
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.COMMAND)
    for player in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player, SecondaryMissionMode.FIXED, ("assassination", "bring-it-down")
            )
        )
    return state


def damage_to_count(state: GameState, remaining: int, *, player: str = "owner") -> None:
    army = next(a for a in state.army_definitions if a.player_id == player)
    unit = army.units[0]
    for model in unit.own_models[: len(unit.own_models) - remaining]:
        apply_damage_to_model(
            state=state,
            target_unit_instance_id=unit.unit_instance_id,
            model_instance_id=model.model_instance_id,
            damage=model.current_wounds,
            damage_kind=DamageKind.NORMAL,
        )


def requests(
    state: GameState, *, forced: bool = False, duplicate: bool = False
) -> tuple[BattleShockTestRequest, ...]:
    active = state.active_player_id
    assert active is not None
    assert state.battlefield_state is not None
    army = next(a for a in state.army_definitions if a.player_id == active)
    return collect_battle_shock_test_requests(
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=active,
        army=army,
        battlefield_state=state.battlefield_state,
        starting_strength_records=tuple(state.starting_strength_records),
        battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
        state=state,
        forced_below_starting_strength_unit_ids=(army.units[0].unit_instance_id,) if forced else (),
        allow_duplicate_below_half_tests=duplicate,
    )


def mark_shocked(state: GameState) -> str:
    """Constructed prior failed-roll boundary, using the real shock mutation owner."""
    unit = next(a for a in state.army_definitions if a.player_id == state.active_player_id).units[0]
    from warhammer40k_core.engine.battle_shock import BattleShockTestReason
    from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext

    context = BelowHalfStrengthContext.from_unit(
        player_id=next(a.player_id for a in state.army_definitions if unit in a.units),
        unit=unit,
        starting_strength=state.starting_strength_record_for_unit(unit.unit_instance_id),
        current_model_ids=tuple(m.model_instance_id for m in unit.own_models if m.is_alive),
    )
    request = BattleShockTestRequest.for_unit(
        request_id="constructed:s08:prior-roll",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=context.player_id,
        unit_instance_id=unit.unit_instance_id,
        reason=BattleShockTestReason.FORCED_BY_ARMY_RULE,
        leadership_target=6,
        below_half_strength_context=context,
    )
    state.record_battle_shock_result(
        BattleShockResult.from_roll_state(
            result_id="constructed:s08:prior-failure",
            request=request,
            roll_state=DiceRollManager(state.game_id).roll_fixed(request.spec, [1, 1]),
        )
    )
    return unit.unit_instance_id
