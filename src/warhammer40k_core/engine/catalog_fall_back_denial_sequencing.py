from __future__ import annotations

# Source-effect payload validation is shared with the mode-selection owner.
# pyright: reportPrivateUsage=false
from collections.abc import Mapping
from functools import partial

from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.modified_dice import ModifiedRollResult, UnmodifiedRollResult
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.battle_shock import battle_shock_leadership_target_for_unit
from warhammer40k_core.engine.catalog_attack_context_rule_runtime import rules_units_within
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_current_placed_alive_model_instance_ids_for_unit,
)
from warhammer40k_core.engine.catalog_selectable_ability_mode_runtime import (
    CATALOG_ABILITY_MODE_EFFECT_KIND,
    CATALOG_FALL_BACK_LEADERSHIP_TEST_EVENT,
    _payload_string,
)
from warhammer40k_core.engine.catalog_selectable_ability_mode_support import (
    ENTHRALLING_HYPNOSIS_MODE_SEMANTIC,
)
from warhammer40k_core.engine.catalog_selected_target_test_modifiers import (
    LEADERSHIP_TEST_ROLL_TYPE,
    selected_target_test_roll_modifiers,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.phases.movement_model import (
    MovementPhaseActionKind,
    PendingMovementActionSelection,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate


def fall_back_denial_candidates(
    *,
    state: GameState,
    decisions: DecisionController,
    pending: PendingMovementActionSelection,
    ability_indexes: Mapping[str, AbilityCatalogIndex],
    modifiers: RuntimeModifierRegistry,
) -> tuple[TimingRuleCandidate, ...]:
    if pending.movement_phase_action is not MovementPhaseActionKind.FALL_BACK:
        return ()
    target = rules_unit_view_by_id(state=state, unit_instance_id=pending.unit_instance_id)
    candidates: list[TimingRuleCandidate] = []
    for effect in state.persisting_effects:
        payload = effect.effect_payload
        if not isinstance(payload, dict) or (
            payload.get("effect_kind") != CATALOG_ABILITY_MODE_EFFECT_KIND
            or payload.get("mode_semantic") != ENTHRALLING_HYPNOSIS_MODE_SEMANTIC
            or effect.owner_player_id == target.owner_player_id
        ):
            continue
        source_unit = _payload_string(payload, "source_rules_unit_instance_id")
        source_model = _payload_string(payload, "source_model_instance_id")
        distance = _payload_positive_float(payload, "aura_range_inches")
        if (
            state.battlefield_state is None
            or state.battlefield_state.model_placement_or_none(source_model) is None
            or not rules_units_within(
                state,
                source_unit,
                target.unit_instance_id,
                distance,
                attacker_model_instance_id=source_model,
            )
        ):
            continue
        identity = f"fall-back-denial:{pending.result_id}:{effect.effect_id}"
        if any(
            event.event_type == CATALOG_FALL_BACK_LEADERSHIP_TEST_EVENT
            and isinstance(event.payload, dict)
            and event.payload.get("timing_participant_id") == identity
            for event in decisions.event_log.records
        ):
            continue
        candidates.append(
            TimingRuleCandidate(
                participant=SequencingParticipant(
                    participant_id=identity,
                    player_id=effect.owner_player_id,
                    source_rule_id=effect.source_rule_id,
                    requirement=SequencingRequirement.MANDATORY,
                    payload={
                        "movement_action_result_id": pending.result_id,
                        "source_effect_id": effect.effect_id,
                    },
                ),
                activate=partial(
                    _resolve_denial,
                    state=state,
                    decisions=decisions,
                    pending=pending,
                    effect=effect,
                    identity=identity,
                    ability_indexes=ability_indexes,
                    modifiers=modifiers,
                ),
            )
        )
    return tuple(candidates)


def _payload_positive_float(payload: Mapping[str, object], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, int | float) or type(value) is bool or float(value) <= 0.0:
        raise GameLifecycleError(f"Catalog ability mode payload {key} must be positive.")
    return float(value)


def fall_back_denied_for_action(
    *, decisions: DecisionController, pending: PendingMovementActionSelection
) -> bool:
    return any(
        event.event_type == CATALOG_FALL_BACK_LEADERSHIP_TEST_EVENT
        and isinstance(event.payload, dict)
        and event.payload.get("movement_action_result_id") == pending.result_id
        and event.payload.get("fall_back_denied") is True
        for event in decisions.event_log.records
    )


def _resolve_denial(
    *,
    state: GameState,
    decisions: DecisionController,
    pending: PendingMovementActionSelection,
    effect: PersistingEffect,
    identity: str,
    ability_indexes: Mapping[str, AbilityCatalogIndex],
    modifiers: RuntimeModifierRegistry,
) -> None:
    target = rules_unit_view_by_id(state=state, unit_instance_id=pending.unit_instance_id)
    index = ability_indexes[target.owner_player_id]
    components = tuple(
        (
            component,
            catalog_rule_current_placed_alive_model_instance_ids_for_unit(
                state=state, unit=component.unit
            ),
        )
        for component in target.components
    )
    living = tuple((component, ids) for component, ids in components if ids)
    if not living:
        raise GameLifecycleError("Fall Back denial target has no placed alive models.")
    leadership = min(
        battle_shock_leadership_target_for_unit(
            component.unit,
            current_model_ids=ids,
            ability_index=index,
            state=state,
            runtime_modifier_registry=modifiers,
        )
        for component, ids in living
    )
    roll = DiceRollManager(state.game_id, event_log=decisions.event_log).roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=2, sides=6),
            reason=f"Fall Back Leadership test for {target.unit_instance_id}",
            roll_type="catalog.fall_back_leadership_denial",
            actor_id=target.owner_player_id,
        )
    )
    modified = ModifiedRollResult.from_unmodified(
        UnmodifiedRollResult.from_state(roll),
        modifiers=selected_target_test_roll_modifiers(
            state=state,
            unit_instance_id=target.unit_instance_id,
            roll_type=LEADERSHIP_TEST_ROLL_TYPE,
        ),
    )
    source = effect.effect_payload
    if not isinstance(source, dict):
        raise GameLifecycleError("Fall Back denial effect payload must be an object.")
    payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "phase": BattlePhase.MOVEMENT.value,
        "active_player_id": state.active_player_id,
        "target_unit_instance_id": target.unit_instance_id,
        "target_player_id": target.owner_player_id,
        "source_rule_id": effect.source_rule_id,
        "source_unit_instance_id": source["source_rules_unit_instance_id"],
        "source_model_instance_id": source["source_model_instance_id"],
        "source_effect_id": effect.effect_id,
        "timing_participant_id": identity,
        "movement_action_result_id": pending.result_id,
        "leadership_target": leadership,
        "roll": validate_json_value(roll.to_payload()),
        "modified_roll": validate_json_value(modified.to_payload()),
        "passed": modified.final_value >= leadership,
        "fall_back_denied": modified.final_value < leadership,
    }
    decisions.event_log.append(CATALOG_FALL_BACK_LEADERSHIP_TEST_EVENT, payload)
