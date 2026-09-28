"""Canonical Command fixture with persisted source operations and permissions."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from tests.generic_modifier_helpers import generic_effect
from tests.phase11c_command_phase_helpers import (
    destroy_models_with_recorded_mortal_wounds,
    phase11c_config,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.datasheet import DatasheetAbilityDescriptor
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.effects import EffectExpiration
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.reaction_queue import ReactionQueue


def add_nonattack_effects(
    state: GameState, *, unit_id: str, owner: str, characteristic: str, operations: bool = True
) -> None:
    phase = state.current_battle_phase
    assert phase is not None
    assert state.active_player_id is not None
    for name, kind, parameters in (
        (
            "permission",
            "grant_ability",
            {"ability": "modifier_ignore_permission", "selection": "any_or_all"},
        ),
        ("penalty", "modify_characteristic", {"characteristic": characteristic, "delta": 1}),
        ("bonus", "modify_characteristic", {"characteristic": characteristic, "delta": -1}),
    ):
        if name != "permission" and not operations:
            continue
        effect = generic_effect(
            effect_id=f"nonattack:{unit_id}:{characteristic}:{name}",
            owner_player_id=owner,
            target_unit_instance_ids=(unit_id,),
            target_kind="this_unit",
            effect_kind=kind,
            parameters=cast(dict[str, JsonValue], parameters),
        )
        payload = cast(dict[str, JsonValue], effect.effect_payload)
        context = cast(dict[str, JsonValue], payload["context"])
        state.record_persisting_effect(
            replace(
                effect,
                started_phase=phase,
                effect_payload={**payload, "context": {**context, "phase": phase.value}},
                expiration=EffectExpiration.end_phase(
                    battle_round=state.battle_round, phase=phase, player_id=state.active_player_id
                ),
            )
        )


def command_modifier_session(
    *, characteristic_name: str = "leadership", random_profile: bool = False
) -> LocalGameSession:
    decisions = DecisionController()
    from tests.phase11c_command_phase_helpers import (
        complete_setup_through_gate,
        mustered_armies,
        secondary_choice,
    )
    from warhammer40k_core.core.attributes import Characteristic
    from warhammer40k_core.core.dice import DiceExpression
    from warhammer40k_core.core.random_profile_values import RandomProfileValue
    from warhammer40k_core.engine.game_state import SecondaryMissionMode
    from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
    from warhammer40k_core.engine.profile_modifiers import profile_with_delta

    config = phase11c_config()
    catalog = config.army_catalog
    assert catalog is not None
    config = replace(
        config,
        army_catalog=replace(
            catalog,
            datasheets=tuple(
                replace(
                    sheet,
                    abilities=(*sheet.abilities, random_nonattack_descriptor(characteristic_name))
                    if random_profile
                    else sheet.abilities,
                    model_profiles=tuple(
                        replace(
                            profile,
                            characteristics=tuple(
                                (
                                    RandomProfileValue(
                                        value.characteristic,
                                        DiceExpression(
                                            1, 6, 3 if characteristic_name == "leadership" else 0
                                        ),
                                        profile.source_ids[0],
                                    )
                                    if random_profile
                                    else profile_with_delta(
                                        profile_with_delta(
                                            value,
                                            1,
                                            source_id="source:ld-plus",
                                            modifier_id="ld:plus",
                                            bound_numeric=True,
                                        ),
                                        -1,
                                        source_id="source:ld-minus",
                                        modifier_id="ld:minus",
                                        bound_numeric=True,
                                    )
                                )
                                if value.characteristic is Characteristic(characteristic_name)
                                else value
                                for value in profile.characteristics
                            ),
                        )
                        for profile in sheet.model_profiles
                    ),
                )
                for sheet in catalog.datasheets
            ),
        ),
    )
    state = GameState.from_config(config)
    for army in mustered_armies(config):
        state.record_army_definition(army)
    state.record_battlefield_state(
        create_deterministic_battlefield_scenario(
            battlefield_id="phase11c-battlefield",
            armies=tuple(state.army_definitions),
        ).battlefield_state
    )
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            secondary_choice(player_id=player_id, mode=SecondaryMissionMode.FIXED)
        )
    if characteristic_name == "objective_control":
        from tests.phase11c_command_phase_helpers import with_model_offsets

        assert state.battlefield_state is not None
        assert state.mission_setup is not None
        marker = state.mission_setup.objective_markers[0]
        unit_id = state.army_definitions[0].units[0].unit_instance_id
        placement = state.battlefield_state.unit_placement_by_id(unit_id)
        state.battlefield_state = state.battlefield_state.with_unit_placement(
            with_model_offsets(
                placement,
                marker,
                offsets=((0.0, 0.0), (0.8, 0.0), (1.6, 0.0), (0.0, 0.8), (0.8, 0.8)),
            )
        )
    complete_setup_through_gate(state=state, decisions=decisions, config=config)
    unit = state.army_definitions[0].units[0]
    if characteristic_name == "leadership":
        destroy_models_with_recorded_mortal_wounds(
            state=state,
            decisions=decisions,
            unit_instance_id=unit.unit_instance_id,
            model_instance_ids=unit.own_model_ids()[:3],
            application_id="nonattack:casualties",
            destroying_player_id="player-b",
        )
    add_nonattack_effects(
        state,
        unit_id=unit.unit_instance_id,
        owner="player-a",
        characteristic=characteristic_name,
        operations=False,
    )
    if random_profile:
        from warhammer40k_core.engine.rule_execution import RuleExecutionContext, execute_rule_ir
        from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRPayload

        descriptor = random_nonattack_descriptor(characteristic_name)
        assert descriptor.rule_ir_payload is not None
        result = execute_rule_ir(
            rule_ir=RuleIR.from_payload(cast(RuleIRPayload, descriptor.rule_ir_payload)),
            context=RuleExecutionContext(
                game_id=state.game_id,
                player_id="player-a",
                battle_round=state.battle_round,
                phase=state.current_battle_phase,
                active_player_id=state.active_player_id,
                source_unit_instance_id=unit.unit_instance_id,
                target_unit_instance_ids=(unit.unit_instance_id,),
                source_keywords=tuple(sorted({*unit.keywords, *unit.faction_keywords})),
                state=state,
                event_log=decisions.event_log,
            ),
        )
        assert len(result.created_persisting_effects) == 2
    lifecycle = GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": decisions.to_payload(),
            "reaction_queue": ReactionQueue().to_payload(),
        }
    )
    return LocalGameSession(lifecycle=lifecycle)


def random_nonattack_descriptor(characteristic: str) -> DatasheetAbilityDescriptor:
    from warhammer40k_core.core.datasheet import (
        CatalogAbilitySourceKind,
        CatalogAbilitySupport,
        CatalogJsonObject,
    )
    from warhammer40k_core.rules.parsed_tokens import TextSpan
    from warhammer40k_core.rules.rule_ir import (
        RuleClause,
        RuleDuration,
        RuleDurationKind,
        RuleEffectKind,
        RuleEffectSpec,
        RuleIR,
        RuleTargetKind,
        RuleTargetSpec,
        parameters_from_pairs,
    )

    identity = f"test:nonattack:{characteristic}:operations"
    span = TextSpan(text="Test characteristic modifier source", start=0, end=35)
    rule_ir = RuleIR(
        rule_id=f"{identity}:rule",
        source_id=identity,
        normalized_text=span.text,
        parser_version="test-canonical-nonattack",
        clauses=tuple(
            RuleClause(
                clause_id=f"{identity}:{name}",
                source_span=span,
                target=RuleTargetSpec(kind=RuleTargetKind.THIS_UNIT, source_span=span),
                duration=RuleDuration(
                    kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
                    source_span=span,
                    parameters=parameters_from_pairs((("endpoint", "phase"),)),
                ),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.MODIFY_CHARACTERISTIC,
                        source_span=span,
                        parameters=parameters_from_pairs(
                            (
                                ("characteristic", characteristic),
                                ("delta", delta),
                            )
                        ),
                    ),
                ),
            )
            for name, delta in (("negative", -1), ("positive", 1))
        ),
    )
    return DatasheetAbilityDescriptor(
        ability_id=identity,
        name="Test characteristic operations",
        source_id=identity,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=span.text,
        rule_ir_payload=cast(CatalogJsonObject, rule_ir.to_payload()),
    )
