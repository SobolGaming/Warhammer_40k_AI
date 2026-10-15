from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import cast

import pytest

from tests.parameterized_projection_helpers import assert_parameterized_projection
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.dice import DiceExpression, DiceRollResult, DiceRollSpec
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine import (
    catalog_return_on_death_runtime as catalog_return_on_death_runtime_module,
)
from warhammer40k_core.engine import return_on_death as return_on_death_module
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilitySourceKind,
    AbilityTimingDescriptor,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import ModelPlacement, UnitPlacement
from warhammer40k_core.engine.catalog_return_on_death_runtime import CatalogReturnOnDeathRuntime
from warhammer40k_core.engine.catalog_rule_consumption import catalog_rule_clauses_from_record
from warhammer40k_core.engine.command_points import initial_command_point_ledgers
from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.direct_mortal_wound_application import (
    apply_direct_mortal_wounds_to_unit,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MortalWoundDestructionEvidence,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.primary_destruction_evidence import RulesUnitObjectiveProximityWitness
from warhammer40k_core.engine.return_on_death import (
    SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE,
    PendingReturnOnDeath,
    ReturnDestroyedTargetScope,
    ReturnRestoreWoundsMode,
    apply_return_on_death_placement_decision,
    build_return_on_death_placement_request,
    invalid_return_on_death_placement_status,
)
from warhammer40k_core.engine.return_on_death_sequencing import resolve_return_phase_end_candidates
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import initial_victory_point_ledgers
from warhammer40k_core.engine.sticky_objective_control import PhaseEndObjectiveControlContext
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedContext
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14 as datasheet_keyword_lexicon_source,
)

FIRST_DEATH_RETURN_TEXT = (
    "The first time this model is destroyed, at the end of the phase, roll one D6: on "
    "a 2+, set this model back up on the battlefield as close as possible to where it "
    "was destroyed and not within Engagement Range of one or more enemy units, with "
    "3 wounds remaining."
)
SOURCE_KEYWORD_SEQUENCE_PARTS = (
    datasheet_keyword_lexicon_source.canonical_datasheet_keyword_sequence_parts()
)


def _placement_result(*, request: DecisionRequest, placement: UnitPlacement) -> DecisionResult:
    return DecisionResult(
        result_id=f"result:{request.request_id}",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=cast(
            JsonValue,
            {
                "submission_kind": SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE,
                "attempted_placement": placement.to_payload(),
            },
        ),
    )


def _pending_return_on_death(
    *,
    state: GameState,
    success_threshold: int = 2,
    target_scope: ReturnDestroyedTargetScope = ReturnDestroyedTargetScope.DESTROYED_UNIT,
    restore_mode: ReturnRestoreWoundsMode = ReturnRestoreWoundsMode.FULL_HEALTH,
    wounds_remaining: int | None = None,
) -> PendingReturnOnDeath:
    beta = _beta_unit(state)
    return PendingReturnOnDeath(
        pending_id="pending:return",
        source_rule_id="rule:return",
        source_ability_id="ability:return",
        source_clause_id="clause:return",
        source_effect_index=0,
        owner_player_id="player-b",
        target_scope=target_scope,
        destroyed_unit_instance_id=beta.unit_instance_id,
        destroyed_model_instance_id=(
            beta.own_models[0].model_instance_id
            if target_scope is ReturnDestroyedTargetScope.DESTROYED_MODEL
            else None
        ),
        destroyed_position_payload=_destroyed_position_payload_for_model(
            model_instance_id=beta.own_models[0].model_instance_id,
        ),
        trigger_battle_round=1,
        trigger_phase="command",
        resolution_timing="phase_end",
        roll_expression="D6",
        roll_count=1,
        success_threshold=success_threshold,
        placement_anchor="destroyed_position",
        placement_preference="as_close_as_possible",
        engagement_range_restriction=True,
        restore_wounds_mode=restore_mode,
        wounds_remaining=wounds_remaining,
        resolved=False,
    )


def _roll_result(*, pending: PendingReturnOnDeath, value: int) -> DiceRollResult:
    return DiceRollResult.from_values(
        roll_id=f"roll:return:{value}",
        spec=DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason="return_on_death_phase_end_gate",
            roll_type="return_on_death",
            actor_id=pending.owner_player_id,
            reroll_forbidden_rule_ids=(pending.source_rule_id,),
        ),
        values=(value,),
        source="injected",
    )


def _battle_state_with_destroyed_beta_unit() -> GameState:
    state = _battle_state_with_scenario()
    beta = _beta_unit(state)
    _set_unit_wounds(state, unit_instance_id=beta.unit_instance_id, wounds_remaining=0)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.with_removed_models(beta.own_model_ids())
    return state


def _set_unit_wounds(
    state: GameState,
    *,
    unit_instance_id: str,
    wounds_remaining: int,
) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            if unit.unit_instance_id != unit_instance_id:
                updated_units.append(unit)
                continue
            updated_units.append(
                replace(
                    unit,
                    own_models=tuple(
                        replace(model, wounds_remaining=wounds_remaining)
                        for model in unit.own_models
                    ),
                )
            )
        updated_armies.append(replace(army, units=tuple(updated_units)))
    state.army_definitions = updated_armies


def _set_model_wounds(
    state: GameState,
    *,
    model_instance_id: str,
    wounds_remaining: int,
) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            updated_units.append(
                replace(
                    unit,
                    own_models=tuple(
                        replace(model, wounds_remaining=wounds_remaining)
                        if model.model_instance_id == model_instance_id
                        else model
                        for model in unit.own_models
                    ),
                )
            )
        updated_armies.append(replace(army, units=tuple(updated_units)))
    state.army_definitions = updated_armies


def _return_on_death_record(*, wounds_remaining: int = 3) -> AbilityCatalogRecord:
    source = RuleSourceText.from_raw(
        objective_scope=ObjectiveRuleScope.CORE_RULES,
        source_id="rule:first-death-return",
        raw_text=FIRST_DEATH_RETURN_TEXT.replace(
            "3 wounds remaining",
            f"{wounds_remaining} wounds remaining",
        ),
    )
    rule_ir = compile_rule_source_text(
        source,
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    ).rule_ir
    return AbilityCatalogRecord(
        record_id="record:first-death-return",
        definition=AbilityDefinition(
            ability_id="ability:first-death-return",
            name="First Death Return",
            source_id=source.source_id,
            when_descriptor="First destroyed model.",
            effect_descriptor="Set back up at phase end.",
            restrictions_descriptor="Not within Engagement Range.",
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.AFTER_MODEL_DESTROYED),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=cast(JsonValue, {"rule_ir": rule_ir.to_payload()}),
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id="core-intercessor-like-infantry",
    )


def _unit_placement_at_destroyed_position(*, state: GameState, unit: UnitInstance) -> UnitPlacement:
    anchor = _destroyed_model_placement_for_model(
        model_instance_id=unit.own_models[0].model_instance_id,
    )
    base_placement = _unit_placement_for_unit(
        state=state,
        unit=unit,
        x=anchor.pose.position.x,
        y=anchor.pose.position.y,
    )
    return base_placement.with_model_placements(
        tuple(
            anchor if placement.model_instance_id == anchor.model_instance_id else placement
            for placement in base_placement.model_placements
        )
    )


def _unit_placement_for_model_at_destroyed_position(
    *,
    state: GameState,
    unit: UnitInstance,
    model_instance_id: str,
) -> UnitPlacement:
    anchor = _destroyed_model_placement_for_model(model_instance_id=model_instance_id)
    return UnitPlacement(
        army_id=anchor.army_id,
        player_id=anchor.player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=(anchor,),
    )


def _destroyed_position_payload_for_model(*, model_instance_id: str) -> JsonValue:
    destroyed_placement_payload = _destroyed_model_placement_for_model(
        model_instance_id=model_instance_id,
    ).to_payload()
    return _destroyed_position_payload_for_placement_payload(
        model_instance_id=model_instance_id,
        destroyed_placement_payload=cast(JsonValue, destroyed_placement_payload),
    )


def _destroyed_position_payload_for_placement(placement: ModelPlacement) -> JsonValue:
    return _destroyed_position_payload_for_placement_payload(
        model_instance_id=placement.model_instance_id,
        destroyed_placement_payload=cast(JsonValue, placement.to_payload()),
    )


def _destroyed_position_payload_for_placement_payload(
    *,
    model_instance_id: str,
    destroyed_placement_payload: JsonValue,
) -> JsonValue:
    return cast(
        JsonValue,
        {
            "source": "model_destroyed_event",
            "model_destroyed_event_id": "event:test-destroyed-position",
            "model_destroyed_payload": {
                "model_instance_id": model_instance_id,
                "destroyed_model_placement": destroyed_placement_payload,
            },
        },
    )


def _destroyed_model_placement_for_model(*, model_instance_id: str) -> ModelPlacement:
    source_state = _battle_state_with_scenario()
    assert source_state.battlefield_state is not None
    return source_state.battlefield_state.model_placement_by_id(model_instance_id)


def _unit_placement_for_unit(
    *,
    state: GameState,
    unit: UnitInstance,
    x: float,
    y: float,
) -> UnitPlacement:
    army = next(
        army for army in state.army_definitions if any(stored == unit for stored in army.units)
    )
    return UnitPlacement(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=Pose.at(x + (index * 2.0), y),
            )
            for index, model in enumerate(unit.own_models)
        ),
    )


def _beta_unit(state: GameState) -> UnitInstance:
    for army in state.army_definitions:
        if army.player_id != "player-b":
            continue
        return army.units[0]
    raise AssertionError("missing beta unit")


def _first_alpha_model_pose(state: GameState) -> Pose:
    assert state.battlefield_state is not None
    for army in state.battlefield_state.placed_armies:
        if army.player_id != "player-a":
            continue
        return army.unit_placements[0].model_placements[0].pose
    raise AssertionError("missing alpha placement")


def _battle_state_with_scenario() -> GameState:
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="return-on-death-battlefield",
        armies=_mustered_armies(),
    )
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    state = GameState(
        game_id="return-on-death-game",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=tuple(descriptor.battle_phase_sequence.phases),
        setup_step_index=None,
        battle_phase_index=0,
        battle_round=1,
        active_player_id="player-a",
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
        command_point_ledgers=initial_command_point_ledgers(("player-a", "player-b")),
        victory_point_ledgers=initial_victory_point_ledgers(("player-a", "player-b")),
    )
    for army in scenario.armies:
        state.record_army_definition(army)
    state.battlefield_state = scenario.battlefield_state
    return state


def _mustered_armies() -> tuple[ArmyDefinition, ...]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return (
        muster_army(
            catalog=catalog,
            request=_muster_request(catalog=catalog, player_id="player-a", army_id="army-alpha"),
        ),
        muster_army(
            catalog=catalog,
            request=_muster_request(catalog=catalog, player_id="player-b", army_id="army-beta"),
        ),
    )


def _muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id="purge-the-foe",
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=f"{army_id}-unit",
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
        ),
    )


def _record_return_captures(
    runtime: CatalogReturnOnDeathRuntime,
    context: PhaseEndObjectiveControlContext,
) -> tuple[()]:
    for event_id, pending in runtime.pending_captures_for(context):
        assert catalog_return_on_death_runtime_module.record_pending_return_on_death(
            pending=pending,
            state=context.state,
            event_log=context.event_log,
            phase=context.completed_phase.value,
            model_destroyed_event_id=event_id,
        )
    return ()


__all__: list[str] = []
__all__ += ["AbilityCatalogIndex", "AbilityCatalogRecord", "AbilityDefinition"]
__all__ += ["AbilitySourceKind", "AbilityTimingDescriptor", "ArmyCatalog", "ArmyDefinition"]
__all__ += ["ArmyMusterRequest", "BattlePhase", "Callable", "CatalogReturnOnDeathRuntime"]
__all__ += ["DamageKind", "DecisionController", "DecisionRequest", "DecisionResult"]
__all__ += ["DestructionSourceKind", "DetachmentSelection", "DiceExpression", "DiceRollManager"]
__all__ += ["FIRST_DEATH_RETURN_TEXT", "DiceRollResult", "DiceRollSpec"]
__all__ += ["GENERIC_RULE_IR_ABILITY_HANDLER_ID", "GameLifecycle", "GameLifecycleError"]
__all__ += ["GameLifecycleStage", "GameState", "JsonValue", "ModelPlacement"]
__all__ += ["ModelProfileSelection", "MortalWoundDestructionEvidence", "ObjectiveRuleScope"]
__all__ += ["PARAMETERIZED_DECISION_OPTION_ID", "PendingReturnOnDeath"]
__all__ += ["PhaseEndObjectiveControlContext", "Pose", "ReturnDestroyedTargetScope"]
__all__ += ["ReturnRestoreWoundsMode", "RuleSourceText", "RulesUnitObjectiveProximityWitness"]
__all__ += ["SOURCE_KEYWORD_SEQUENCE_PARTS", "RulesetDescriptor", "RuntimeModifierRegistry"]
__all__ += ["SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE", "TimingTriggerKind"]
__all__ += ["UnitDestroyedContext", "UnitInstance", "UnitMusterSelection", "UnitPlacement"]
__all__ += ["_battle_state_with_destroyed_beta_unit", "_battle_state_with_scenario", "_beta_unit"]
__all__ += ["_destroyed_model_placement_for_model", "_destroyed_position_payload_for_model"]
__all__ += ["_destroyed_position_payload_for_placement"]
__all__ += ["_destroyed_position_payload_for_placement_payload", "_first_alpha_model_pose"]
__all__ += ["_muster_request", "_mustered_armies", "_pending_return_on_death"]
__all__ += ["_placement_result", "_record_return_captures", "_return_on_death_record"]
__all__ += ["_roll_result", "_set_model_wounds", "_set_unit_wounds"]
__all__ += ["_unit_placement_at_destroyed_position"]
__all__ += ["_unit_placement_for_model_at_destroyed_position", "_unit_placement_for_unit"]
__all__ += ["apply_damage_to_model", "apply_direct_mortal_wounds_to_unit"]
__all__ += ["apply_return_on_death_placement_decision", "assert_parameterized_projection"]
__all__ += ["build_return_on_death_placement_request", "cast"]
__all__ += ["catalog_return_on_death_runtime_module", "catalog_rule_clauses_from_record"]
__all__ += ["compile_rule_source_text", "create_deterministic_battlefield_scenario"]
__all__ += ["datasheet_keyword_lexicon_source", "initial_command_point_ledgers"]
__all__ += ["initial_victory_point_ledgers", "invalid_return_on_death_placement_status"]
__all__ += ["muster_army", "pytest", "replace", "resolve_return_phase_end_candidates"]
__all__ += ["return_on_death_module"]
