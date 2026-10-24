"""FAQ27 constructed generic permission at an opponent's Movement end boundary."""

from dataclasses import replace
from typing import cast

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_session import movement_session
from tests.support.section11_fixtures import LORD, state_case

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.engine.catalog_setup_reactive_shoot_charge import (
    request_catalog_setup_reactive_shoot_charge_if_available,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText


def reactive_case(
    definitions: Section02Definitions,
) -> tuple[LocalGameSession, GameState, UnitInstance, UnitInstance]:
    state, source, target = state_case(definitions, gap=3)
    state.active_player_id = "opponent"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    # Only one potential reactor; no unrelated choice/visibility scene.
    state.army_definitions[:] = [
        replace(a, units=(source,)) if a.player_id == "owner" else a for a in state.army_definitions
    ]
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        replace(
            state.battlefield_state,
            placed_armies=tuple(
                replace(
                    a,
                    unit_placements=tuple(
                        p
                        for p in a.unit_placements
                        if p.unit_instance_id == source.unit_instance_id
                    ),
                )
                if a.player_id == "owner"
                else a
                for a in state.battlefield_state.placed_armies
            ),
        )
    )
    state.starting_strength_records[:] = [
        r for r in state.starting_strength_records if r.unit_instance_id != "section02:spare"
    ]
    text = (
        "At the end of your opponent's Movement phase, you can select one enemy unit that was "
        'set up on the battlefield within 12" of this model; this model can then either: '
        "Shoot at that unit, but only if it is an eligible target. Declare a charge. This unit "
        "must end that charge move engaged with the enemy unit you selected (note that even if "
        "this charge is successful, this unit does not receive any Charge bonus this turn)."
    )
    identity = "constructed:section11:out-of-phase-charge-permission"
    rule = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id=identity, raw_text=text, objective_scope=ObjectiveRuleScope.CORE_RULES
        ),
        source_keyword_sequence_parts=("CHARACTER", "INFANTRY"),
    ).rule_ir
    assert not rule.diagnostics
    assert all(c.is_supported for c in rule.clauses)
    ability = DatasheetAbilityDescriptor(
        ability_id=identity,
        name="Constructed reactive Charge permission",
        source_id=identity,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=text,
        rule_ir_payload=cast(CatalogJsonObject, rule.to_payload()),
    )
    source = replace(source, datasheet_abilities=(*source.datasheet_abilities, ability))
    state.army_definitions[:] = [
        replace(a, units=(source,)) if a.player_id == "owner" else a for a in state.army_definitions
    ]
    catalog = replace(
        definitions.package.army_catalog,
        datasheets=tuple(
            replace(s, abilities=(*s.abilities, ability)) if s.datasheet_id == LORD else s
            for s in definitions.package.army_catalog.datasheets
        ),
    )
    config = replace(movement_session(definitions, state).lifecycle.config, army_catalog=catalog)
    movement = MovementPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor, army_catalog=catalog
    )
    session = LocalGameSession(
        GameLifecycle(state=state, _config=config, _movement_phase_handler=movement)
    )
    bundle = session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    decisions = session.lifecycle.decision_controller
    # Authentic constructed already-completed arrival boundary; does not certify
    # reserve ingress, setup permission or a named faction ability.
    decisions.event_log.append(
        "reinforcement_unit_arrived",
        {
            "game_id": state.game_id,
            "battle_round": 1,
            "active_player_id": "opponent",
            "player_id": "opponent",
            "phase": "movement",
            "unit_instance_id": target.unit_instance_id,
            "step": "move_units",
            "placement_kind": "strategic_reserves",
            "request_id": "constructed:arrival",
            "result_id": "constructed:arrival-result",
            "phase_body_status": "reinforcement_unit_arrived",
        },
    )
    status = request_catalog_setup_reactive_shoot_charge_if_available(
        state=state,
        decisions=decisions,
        reaction_queue=session.lifecycle.reaction_queue,
        ability_indexes_by_player_id=bundle.ability_indexes_by_player_id,
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=catalog,
        runtime_modifier_registry=bundle.runtime_modifier_registry,
        charge_target_restriction_hooks=bundle.charge_target_restriction_hook_registry,
    )
    assert status is not None
    assert status.decision_request is not None, status
    return session, state, source, target
