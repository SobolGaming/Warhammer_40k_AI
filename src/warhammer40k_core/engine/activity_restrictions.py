"""Source-backed activity restrictions using the existing persistent-effect authority."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Literal

import msgspec

from warhammer40k_core.engine.actions import MissionActionState
from warhammer40k_core.engine.effects import (
    EffectExpiration,
    EffectExpirationKind,
    PersistingEffect,
)
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_unit_effects import (
    rules_unit_effect_applications_from_inventory,
)
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_actions_2026_09 import (
    RESTRICTION_POLICY,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence
    from warhammer40k_core.engine.game_state import GameState

ACTIVITY_RESTRICTION_KIND: Final = "core_unit_activity_restriction"
ActivityKind = Literal["started_action", "completed_shooting"]


class ActivityRestrictionPayload(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    effect_kind: Literal["core_unit_activity_restriction"]
    activity: ActivityKind
    activity_id: str
    source_rule_ids: tuple[str, ...]


def activity_restriction_payload(effect: PersistingEffect) -> ActivityRestrictionPayload | None:
    payload = effect.effect_payload
    if not isinstance(payload, dict) or payload.get("effect_kind") != ACTIVITY_RESTRICTION_KIND:
        return None
    try:
        activity = msgspec.convert(payload, type=ActivityRestrictionPayload)
    except msgspec.ValidationError as exc:
        raise GameLifecycleError("Activity restriction payload is invalid.") from exc
    if not activity.activity_id or activity.activity_id != activity.activity_id.strip():
        raise GameLifecycleError("Activity restriction requires an activity identity.")
    action = activity.activity == "started_action"
    expected_sources = (
        (RESTRICTION_POLICY.action_source_rule_id,)
        if action
        else RESTRICTION_POLICY.after_shooting_source_rule_ids
    )
    expected_source = (
        RESTRICTION_POLICY.action_source_rule_id
        if action
        else RESTRICTION_POLICY.after_shooting_descriptor_id
    )
    if (
        activity.source_rule_ids != expected_sources
        or effect.source_rule_id != expected_source
        or effect.effect_id != f"activity-restriction:{activity.activity}:{activity.activity_id}"
        or effect.started_phase is None
        or effect.expiration.battle_round != effect.started_battle_round
        or effect.expiration.expiration_kind
        is not (EffectExpirationKind.END_TURN if action else EffectExpirationKind.END_PHASE)
        or (not action and effect.expiration.phase is not effect.started_phase)
    ):
        raise GameLifecycleError("Activity restriction source or timing identity drifted.")
    return activity


def has_activity_restriction(
    *, state: GameState, rules_unit: RulesUnitView, activity: ActivityKind
) -> bool:
    # Only live effects are examined; historical decisions/actions are not scanned.
    for application in rules_unit_effect_applications_from_inventory(
        armies=tuple(state.army_definitions),
        effects=tuple(state.persisting_effects),
        rules_unit=rules_unit,
    ):
        effect = application.effect
        payload = activity_restriction_payload(effect)
        if payload is None or payload.activity != activity:
            continue
        if effect.owner_player_id != rules_unit.owner_player_id:
            raise GameLifecycleError("Activity restriction ownership drifted.")
        if (
            effect.expiration.battle_round == state.battle_round
            and effect.expiration.player_id == state.active_player_id
            and (
                activity == "started_action"
                or effect.expiration.phase is state.current_battle_phase
            )
        ):
            return True
    return False


def record_action_restriction(*, state: GameState, action: MissionActionState) -> None:
    """An accepted start remains restrictive even when its Action is already terminal."""
    active_player_id = state.active_player_id
    if active_player_id is None:
        raise GameLifecycleError("Action activity requires a current turn.")
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=action.unit_instance_id)
    _record_restriction(
        state=state,
        rules_unit=rules_unit,
        activity="started_action",
        activity_id=action.action_id,
        battle_round=action.battle_round_started,
        phase=BattlePhase(action.phase_started),
        expiration=EffectExpiration.end_turn(
            battle_round=action.battle_round_started,
            player_id=active_player_id,
        ),
    )


def record_completed_shooting_restriction(*, state: GameState, sequence: AttackSequence) -> None:
    if sequence.source_phase is not BattlePhase.SHOOTING:
        return
    phase = state.current_battle_phase
    active_player = state.active_player_id
    if phase is None or active_player is None or not sequence.is_complete:
        raise GameLifecycleError("Shooting activity requires completed attacks in a current turn.")
    rules_unit = rules_unit_view_by_id(
        state=state, unit_instance_id=sequence.attacking_unit_instance_id
    )
    _record_restriction(
        state=state,
        rules_unit=rules_unit,
        activity="completed_shooting",
        activity_id=sequence.sequence_id,
        battle_round=state.battle_round,
        phase=phase,
        expiration=EffectExpiration.end_phase(
            battle_round=state.battle_round,
            phase=phase,
            player_id=active_player,
        ),
    )


def _record_restriction(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
    activity: ActivityKind,
    activity_id: str,
    battle_round: int,
    phase: BattlePhase,
    expiration: EffectExpiration,
) -> None:
    action = activity == "started_action"
    effect = PersistingEffect(
        effect_id=f"activity-restriction:{activity}:{activity_id}",
        source_rule_id=(
            RESTRICTION_POLICY.action_source_rule_id
            if action
            else RESTRICTION_POLICY.after_shooting_descriptor_id
        ),
        owner_player_id=rules_unit.owner_player_id,
        target_unit_instance_ids=tuple(
            sorted({rules_unit.unit_instance_id, *rules_unit.component_unit_instance_ids})
        ),
        started_battle_round=battle_round,
        started_phase=phase,
        expiration=expiration,
        effect_payload=validate_json_value(
            msgspec.to_builtins(
                ActivityRestrictionPayload(
                    effect_kind=ACTIVITY_RESTRICTION_KIND,
                    activity=activity,
                    activity_id=activity_id,
                    source_rule_ids=(
                        (RESTRICTION_POLICY.action_source_rule_id,)
                        if action
                        else RESTRICTION_POLICY.after_shooting_source_rule_ids
                    ),
                )
            )
        ),
    )
    activity_restriction_payload(effect)
    state.record_persisting_effect(effect)


def record_mission_action_state(*, state: GameState, action: MissionActionState) -> None:
    """Keep the action-history mutation and its restriction under one engine owner."""
    if type(action) is not MissionActionState:
        raise GameLifecycleError("mission_action_state must be a MissionActionState.")
    if action.player_id not in state.player_ids:
        raise GameLifecycleError("MissionActionState player_id is not in this game.")
    if any(stored.action_id == action.action_id for stored in state.mission_action_states):
        raise GameLifecycleError("MissionActionState already exists for action_id.")
    record_action_restriction(state=state, action=action)
    state.mission_action_states.append(action)
    state.mission_action_states.sort(key=lambda stored: stored.action_id)
