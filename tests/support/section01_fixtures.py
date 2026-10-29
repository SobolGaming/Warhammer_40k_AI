"""Small Section01 states: real definitions, fresh mutable payloads, no mission setup."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from time import perf_counter

import pytest
from tests.support.section02_fixtures import (
    AVENGERS,
    CHAOS_SPAWN,
    INFRACTORS,
    LORD_EXULTANT,
    MAULERFIEND,
    Section02Definitions,
    health_state,
)
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    ModelPlacement,
    PlacedArmy,
    UnitPlacement,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.reserves import (
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReserveOrigin,
    ReserveState,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_state import StartingStrengthRecord
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.rule_ir import RuleIR
from warhammer40k_core.rules.source_data import RuleSourceText


@pytest.fixture(scope="session")
def section01_definitions(
    selected_army_source_index: Path | None,
) -> Iterator[Section02Definitions]:
    start = perf_counter()
    package = _ability_support_catalog_package(
        datasheet_ids=(
            INFRACTORS,
            LORD_EXULTANT,
            CHAOS_SPAWN,
            AVENGERS,
            MAULERFIEND,
            "000000599",
        ),
        source_index_dir=selected_army_source_index,
    )
    seconds = perf_counter() - start

    def digest() -> str:
        return hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()

    before = digest()
    print(f"Section01 preparation: {seconds:.6f}s; one build, six real definitions")
    yield Section02Definitions(package, seconds)
    assert digest() == before


def minimal_state(definitions: Section02Definitions, *units: UnitInstance) -> GameState:
    """Army identity metadata only; no detachment rule grants or mustering lifecycle."""
    state = health_state(definitions, definitions.unit())
    # Match the public deserializer's canonical ordering of player-owned ledgers.
    state.command_point_ledgers.sort(key=lambda row: row.player_id)
    state.faction_resource_ledgers.sort(key=lambda row: row.player_id)
    state.victory_point_ledgers.sort(key=lambda row: row.player_id)
    actual = units or (definitions.unit(),)
    state.army_definitions[:] = [replace(state.army_definitions[0], units=actual)]
    state.starting_strength_records[:] = [
        StartingStrengthRecord.from_unit(player_id="owner", unit=u) for u in actual
    ]
    return state


def place_units(state: GameState) -> None:
    state.record_battlefield_state(
        BattlefieldRuntimeState(
            "section01-board",
            60,
            44,
            placed_armies=tuple(
                PlacedArmy(
                    army.army_id,
                    army.player_id,
                    tuple(
                        UnitPlacement(
                            army.army_id,
                            army.player_id,
                            unit.unit_instance_id,
                            tuple(
                                ModelPlacement(
                                    army.army_id,
                                    army.player_id,
                                    unit.unit_instance_id,
                                    m.model_instance_id,
                                    Pose.at(
                                        10 + 12 * army_index + 5 * unit_index + 2 * (index % 3),
                                        10 + 2 * (index // 3),
                                    ),
                                )
                                for index, m in enumerate(unit.own_models)
                                if m.is_alive
                            ),
                        )
                        for unit_index, unit in enumerate(army.units)
                    ),
                )
                for army_index, army in enumerate(state.army_definitions)
            ),
        )
    )


def reserve_unit(state: GameState, unit: UnitInstance) -> None:
    state.record_reserve_state(
        ReserveState(
            "owner",
            unit.unit_instance_id,
            ReserveOrigin.DECLARE_BATTLE_FORMATIONS,
            ReserveKind.STRATEGIC_RESERVES,
            "declare_battle_formations",
            None,
            None,
            ReserveDestructionTimingPolicy.core_rules_default(),
        )
    )


def core_rule(text: str) -> RuleIR:
    """Explicit Core-contract rule input; never attributed to a real datasheet."""
    rule = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id="constructed:section01:core-contract",
            raw_text=text,
            objective_scope=ObjectiveRuleScope.CORE_RULES,
        ),
        source_keyword_sequence_parts=("INFANTRY", "CHARACTER", "VEHICLE", "TRANSPORT"),
    ).rule_ir
    assert not rule.diagnostics
    return rule
