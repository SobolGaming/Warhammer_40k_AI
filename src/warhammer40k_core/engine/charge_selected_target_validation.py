from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.catalog_selected_target_charge_effects import (
    selected_target_charge_constraint_for_unit,
)
from warhammer40k_core.engine.charge_required_targets import (
    CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
    charge_target_constraints_satisfied,
    required_charge_target_unit_instance_ids,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.phases.charge import legal_charge_target_unit_instance_ids
from warhammer40k_core.engine.target_restriction_hooks import (
    ChargeTargetRestrictionHookRegistry,
)


def invalid_charge_roll_reroll_context_status(
    *,
    state: GameState,
    request: DecisionRequest,
    ruleset_descriptor: RulesetDescriptor,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry,
) -> LifecycleStatus | None:
    if request.decision_type != DICE_REROLL_DECISION_TYPE:
        return None
    request_payload = request.payload
    if not isinstance(request_payload, dict):
        return None
    charge_context = request_payload.get("charge_context")
    if not isinstance(charge_context, dict):
        return None
    constraint_snapshot = charge_context.get("selected_target_charge_constraint")
    if constraint_snapshot is not None and not isinstance(constraint_snapshot, dict):
        return _invalid_status(state=state, field="selected_target_charge_constraint")
    unit_instance_id = _validate_identifier(
        "unit_instance_id",
        charge_context.get("unit_instance_id"),
    )
    charge_state = state.charge_phase_state
    if (
        charge_state is None
        or charge_state.active_selection is None
        or charge_state.active_selection.unit_instance_id != unit_instance_id
    ):
        return _invalid_status(state=state, field="charge_phase_state")
    current_constraint = selected_target_charge_constraint_for_unit(
        state=state,
        unit_instance_id=unit_instance_id,
    )
    current_constraint_payload = (
        None if current_constraint is None else current_constraint.to_payload()
    )
    if current_constraint_payload != constraint_snapshot:
        return _invalid_status(state=state, field="selected_target_charge_constraint")
    requested_required_ids = _payload_identifier_list(
        charge_context,
        key=CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
    )
    current_required_ids = required_charge_target_unit_instance_ids(
        state=state,
        unit_instance_id=unit_instance_id,
        reachable_target_unit_instance_ids=(),
    )
    if current_required_ids != requested_required_ids:
        return _invalid_status(
            state=state,
            field=CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
        )
    if current_constraint is None and not current_required_ids:
        return None
    requested_legal_ids = _payload_identifier_list(
        charge_context,
        key="legal_target_unit_instance_ids",
    )
    current_legal_ids = legal_charge_target_unit_instance_ids(
        state=state,
        unit_instance_id=unit_instance_id,
        ruleset_descriptor=ruleset_descriptor,
        charge_target_restriction_hooks=charge_target_restriction_hooks,
    )
    if current_legal_ids != requested_legal_ids:
        return _invalid_status(state=state, field="legal_target_unit_instance_ids")
    if not charge_target_constraints_satisfied(
        state=state,
        unit_instance_id=unit_instance_id,
        candidate_target_unit_instance_ids=current_legal_ids,
    ):
        return _invalid_status(state=state, field="legal_target_unit_instance_ids")
    return None


def _invalid_status(*, state: GameState, field: str) -> LifecycleStatus:
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Charge reroll target context no longer matches current state.",
        payload={
            "invalid_reason": "invalid_charge_roll_reroll_context",
            "field": field,
        },
    )


def _payload_identifier_list(payload: Mapping[str, object], *, key: str) -> tuple[str, ...]:
    raw_values = payload.get(key)
    if not isinstance(raw_values, list):
        raise GameLifecycleError(f"{key} must be a list.")
    values = tuple(_validate_identifier(key, value) for value in cast(list[object], raw_values))
    if len(set(values)) != len(values):
        raise GameLifecycleError(f"{key} must not contain duplicates.")
    return values


_validate_identifier = IdentifierValidator(GameLifecycleError)
