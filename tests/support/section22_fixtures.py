"""Section22 native definitions and explicit Core rule-input checkpoints.

The rule inputs below test generic Core semantics, not named faction admission.
No setup, mission or prior-phase traversal is needed by these owner kernels.
"""

import hashlib
import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from time import perf_counter

import pytest
from tests.support.section01_fixtures import core_rule
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state, placement
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.rule_execution import RuleExecutionContext
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.rule_ir import RuleIR

BODY = "000004080"
LORD = "000004078"
PSYKER = "000000588"
AVENGERS = "000000593"
CRUSHERS = "000001115"
IDS = (BODY, LORD, PSYKER, AVENGERS, CRUSHERS)


@pytest.fixture(scope="session")
def section22_definitions(
    selected_army_source_index: Path | None,
) -> Iterator[Section02Definitions]:
    start = perf_counter()
    package = _ability_support_catalog_package(
        datasheet_ids=IDS, source_index_dir=selected_army_source_index
    )

    def digest() -> str:
        return hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()

    before = digest()
    seconds = perf_counter() - start
    print(f"Section22 preparation: {seconds:.6f}s; one immutable selected five-datasheet package")
    yield Section02Definitions(package, seconds)
    assert digest() == before


def pair(
    d: Section02Definitions, *, psychic: bool = False
) -> tuple[GameState, UnitInstance, UnitInstance]:
    source = d.unit(PSYKER if psychic else LORD, identity="source")
    target = d.unit(LORD, identity="target", army_id="enemy")
    state = native_state(
        d, source, (Pose.at(10, 10),), enemy=target, enemy_poses=(Pose.at(18, 10),)
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.COMMAND)
    return state, source, target


def relocate(state: GameState, unit: UnitInstance, x: float, z: float = 0) -> None:
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        state.battlefield_state.with_unit_placement(
            placement(
                unit,
                tuple(Pose.at(x + i * 1.5, 10, z) for i in range(len(unit.own_models))),
                enemy=unit.unit_instance_id.startswith("enemy:"),
            )
        )
    )


def context(
    state: GameState, source: UnitInstance, log: EventLog | None = None
) -> RuleExecutionContext:
    return RuleExecutionContext(
        game_id=state.game_id,
        player_id="owner",
        battle_round=state.battle_round,
        phase=state.current_battle_phase,
        active_player_id=state.active_player_id,
        timing_window_id="constructed:s22:core-input",
        source_unit_instance_id=source.unit_instance_id,
        source_model_instance_id=source.own_model_ids()[0],
        state=state,
        event_log=log,
    )


def rule(text: str, *, identity: str = "generic") -> RuleIR:
    ir = core_rule(text)
    return replace(
        ir, rule_id=f"constructed:s22:{identity}", source_id=f"constructed:s22:{identity}"
    )


def psychic_public_scene(
    definitions: Section02Definitions, *, retained: bool = False
) -> tuple[LocalGameSession, GameState, UnitInstance]:
    """Declared native/Core Command boundary; retained FoD is explicit permission."""
    from typing import cast

    from tests.fight_on_death_helpers import retain_destroyed_model_for_fixture
    from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture
    from tests.support.section07_fixtures import boundary_session
    from tests.support.section09_fixtures import add_unit, attach_mission

    from warhammer40k_core.core.datasheet import (
        CatalogAbilitySourceKind,
        CatalogAbilitySupport,
        CatalogJsonObject,
        DatasheetAbilityDescriptor,
    )
    from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model
    from warhammer40k_core.engine.game_state import SecondaryMissionChoice, SecondaryMissionMode
    from warhammer40k_core.rules.parsed_tokens import TextSpan
    from warhammer40k_core.rules.rule_ir import RuleParameter, RuleTrigger, RuleTriggerKind

    ir = rule(
        "Might (Psychic level 1): Once per battle, at the start of any phase, "
        "this model can use this ability. If it does, until the end of the phase, "
        "add 3 to the Attacks characteristic of melee weapons equipped by this model "
        "and those weapons have the [DEVASTATING WOUNDS] ability.",
        identity="checkpoint-might",
    )
    # Explicit typed Core any-phase trigger: the parser does not own this
    # catalog trigger shape. This does not admit a named native Psychic ability.
    phrase = "at the start of any phase"
    start = ir.normalized_text.index(phrase)
    trigger = RuleTrigger(
        kind=RuleTriggerKind.TIMING_WINDOW,
        source_span=TextSpan(phrase, start, start + len(phrase)),
        parameters=(RuleParameter("edge", "start"), RuleParameter("phase", "any")),
    )
    ir = replace(ir, clauses=tuple(replace(c, trigger=trigger) for c in ir.clauses))
    descriptor = DatasheetAbilityDescriptor(
        ability_id="constructed:s22:psychic",
        name="Constructed Core Psychic input",
        source_id=ir.source_id,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        effect_description=ir.normalized_text,
        rule_ir_payload=cast(CatalogJsonObject, ir.to_payload()),
    )
    catalog = replace(
        definitions.package.army_catalog,
        datasheets=tuple(
            replace(sheet, abilities=(descriptor,)) if sheet.datasheet_id == PSYKER else sheet
            for sheet in definitions.package.army_catalog.datasheets
        ),
    )
    d = Section02Definitions(
        replace(definitions.package, army_catalog=catalog),
        definitions.preparation_seconds,
    )
    state, source, _ = pair(d, psychic=True)
    add_unit(state, d.unit(LORD, identity="spare"), (Pose.at(7, 30),))
    attach_mission(state)
    for player in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player, SecondaryMissionMode.FIXED, ("assassination", "bring-it-down")
            )
        )
    session = boundary_session(d, state)
    record_primary_turn_start_evidence_for_fixture(
        state, decisions=session.lifecycle.decision_controller
    )
    if retained:
        assert state.battlefield_state is not None
        saved = state.battlefield_state.model_placement_by_id(source.own_model_ids()[0])
        apply_damage_to_model(
            state=state,
            target_unit_instance_id=source.unit_instance_id,
            model_instance_id=source.own_model_ids()[0],
            damage=source.own_models[0].current_wounds,
            damage_kind=DamageKind.NORMAL,
            remove_destroyed_model=False,
        )
        retain_destroyed_model_for_fixture(
            state=state,
            placement=saved,
            effect_id="constructed:s22:public-retained",
            source_rule_id="constructed:s22:fod",
            source_phase=BattlePhase.COMMAND,
            decisions=session.lifecycle.decision_controller,
        )
    session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    return session, state, source
