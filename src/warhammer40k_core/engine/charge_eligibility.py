from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

# pyright: reportPrivateUsage=false
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.catalog_conditional_leader_queries import (
    conditional_charge_after_movement_action_allowed,
)
from warhammer40k_core.engine.charge_effects import charge_after_advance_allowed_by_effects
from warhammer40k_core.engine.charge_phase_state import ChargePhaseState as ChargePhaseState
from warhammer40k_core.engine.charge_required_targets import charge_target_constraints_satisfied
from warhammer40k_core.engine.mission_action_eligibility import (
    rules_unit_started_mission_action_this_turn,
)
from warhammer40k_core.engine.phases import charge as _charge
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.target_restriction_hooks import ChargeTargetRestrictionHookRegistry


def legal_charging_unit_ids(
    *,
    state: GameState,
    charge_state: ChargePhaseState,
    ruleset_descriptor: RulesetDescriptor,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry | None = None,
) -> tuple[str, ...]:
    active_player_id = _charge._active_player_id(state)
    placed_unit_ids = _charge._active_player_placed_unit_ids(
        state=state, player_id=active_player_id
    )
    legal_ids: list[str] = []
    for unit_id in placed_unit_ids:
        if (
            charge_state.interruption is not None
            and unit_id != charge_state.interruption.unit_instance_id
        ):
            continue
        ineligible_reason = charge_unit_ineligibility_reason(
            state=state,
            unit_instance_id=unit_id,
            ruleset_descriptor=ruleset_descriptor,
            charge_state=charge_state,
            ignore_already_selected=False,
            charge_target_restriction_hooks=charge_target_restriction_hooks,
        )
        if ineligible_reason is None:
            legal_ids.append(unit_id)
    return tuple(sorted(legal_ids))


def charge_unit_ineligibility_reason(
    *,
    state: GameState,
    unit_instance_id: str,
    ruleset_descriptor: RulesetDescriptor,
    charge_state: ChargePhaseState,
    ignore_already_selected: bool,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry | None = None,
) -> str | None:
    requested_unit_id = _charge._validate_identifier("unit_instance_id", unit_instance_id)
    from warhammer40k_core.engine.large_model_restrictions import large_model_activity_reason
    from warhammer40k_core.engine.movement_locks import movement_lock_reason

    locked = large_model_activity_reason(state, requested_unit_id, "charge")
    if locked is not None:
        return locked
    locked = movement_lock_reason(state, requested_unit_id)
    if locked is not None:
        return locked
    if (
        charge_state.interruption is not None
        and requested_unit_id != charge_state.interruption.unit_instance_id
    ):
        return "charge_unit_not_authorized_by_source"
    if not ignore_already_selected and requested_unit_id in charge_state.selected_unit_ids:
        return "charge_unit_already_selected"
    if requested_unit_id not in _charge._active_player_placed_unit_ids(
        state=state, player_id=charge_state.active_player_id
    ):
        return "charge_unit_off_battlefield"
    if rules_unit_started_mission_action_this_turn(
        state=state, player_id=charge_state.active_player_id, unit_instance_id=requested_unit_id
    ):
        return "charge_unit_started_action"
    view = rules_unit_view_by_id(state=state, unit_instance_id=requested_unit_id)
    identity_ids = tuple(sorted({requested_unit_id, *view.component_unit_instance_ids}))
    for identity_id in identity_ids:
        advanced_state = state.advanced_unit_state_for_unit(
            player_id=charge_state.active_player_id,
            battle_round=state.battle_round,
            unit_instance_id=identity_id,
        )
        if (
            advanced_state is not None
            and ruleset_descriptor.charge_policy.forbids_advance
            and (not advanced_state.can_declare_charge)
            and (
                not charge_after_advance_allowed_by_effects(
                    state=state, unit_instance_id=requested_unit_id
                )
            )
        ):
            return "charge_unit_advanced"
        fell_back_state = state.fell_back_unit_state_for_unit(
            player_id=charge_state.active_player_id,
            battle_round=state.battle_round,
            unit_instance_id=identity_id,
        )
        if (
            fell_back_state is not None
            and ruleset_descriptor.charge_policy.forbids_fall_back
            and (not fell_back_state.can_declare_charge)
            and (
                not charge_after_fall_back_allowed_by_effects(
                    state=state, unit_instance_id=requested_unit_id
                )
            )
        ):
            return "charge_unit_fell_back"
        disembarked_state = state.disembarked_unit_state_for_unit(
            player_id=charge_state.active_player_id,
            battle_round=state.battle_round,
            unit_instance_id=identity_id,
        )
        if disembarked_state is not None and (not disembarked_state.can_declare_charge):
            return "charge_unit_disembarked"
    if not _charge._charge_actor_can_declare_charge(
        state=state, unit_instance_id=requested_unit_id, ruleset_descriptor=ruleset_descriptor
    ):
        return "charge_unit_aircraft"
    if charge_forbidden_by_effects(state=state, unit_instance_id=requested_unit_id):
        return "charge_unit_forbidden_by_effect"
    if ruleset_descriptor.charge_policy.requires_unengaged_unit and _charge._unit_is_engaged(
        state=state,
        unit_instance_id=requested_unit_id,
        player_id=charge_state.active_player_id,
        ruleset_descriptor=ruleset_descriptor,
    ):
        return "charge_unit_engaged"
    legal_target_ids = _charge.legal_charge_target_unit_instance_ids(
        state=state,
        unit_instance_id=requested_unit_id,
        ruleset_descriptor=ruleset_descriptor,
        charge_target_restriction_hooks=charge_target_restriction_hooks,
    )
    if not charge_target_constraints_satisfied(
        state=state,
        unit_instance_id=requested_unit_id,
        candidate_target_unit_instance_ids=legal_target_ids,
    ):
        return "charge_unit_required_target_unavailable"
    if not legal_target_ids:
        return "charge_unit_no_legal_targets"
    return None


def charge_forbidden_by_effects(*, state: GameState, unit_instance_id: str) -> bool:
    requested_unit_id = _charge._validate_identifier("unit_instance_id", unit_instance_id)
    for effect in state.persisting_effects_for_unit(requested_unit_id):
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            continue
        if payload.get("charge_forbidden") is True and (
            not (
                type(payload.get("effect_kind")) is str
                and conditional_charge_after_movement_action_allowed(
                    state=state,
                    rules_unit_instance_id=requested_unit_id,
                    movement_action_effect_kind=str(payload["effect_kind"]),
                )
            )
        ):
            return True
    return False


def charge_after_fall_back_allowed_by_effects(*, state: GameState, unit_instance_id: str) -> bool:
    for effect in state.persisting_effects_for_unit(unit_instance_id):
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            continue
        if payload.get("effect_kind") == _charge.CHARGE_AFTER_FALL_BACK_EFFECT_KIND:
            return True
    return False
