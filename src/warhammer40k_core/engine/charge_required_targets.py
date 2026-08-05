from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.catalog_selected_target_charge_effects import (
    catalog_selected_target_required_charge_target_unit_instance_ids,
    selected_target_charge_constraint_for_unit,
)
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY = "charge_move_required_target_unit_instance_ids"


def charge_target_constraints_satisfied(
    *,
    state: GameState,
    unit_instance_id: str,
    candidate_target_unit_instance_ids: tuple[str, ...],
) -> bool:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    candidate_ids = _validate_identifier_tuple(
        "candidate_target_unit_instance_ids",
        candidate_target_unit_instance_ids,
    )
    selected_target_constraint = selected_target_charge_constraint_for_unit(
        state=state,
        unit_instance_id=requested_unit_id,
    )
    if selected_target_constraint is not None and not selected_target_constraint.is_satisfied_by(
        candidate_ids
    ):
        return False
    required_ids = required_charge_target_unit_instance_ids(
        state=state,
        unit_instance_id=requested_unit_id,
        reachable_target_unit_instance_ids=candidate_ids,
    )
    return set(required_ids).issubset(candidate_ids)


def required_charge_target_unit_instance_ids(
    *,
    state: GameState,
    unit_instance_id: str,
    reachable_target_unit_instance_ids: tuple[str, ...],
) -> tuple[str, ...]:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    _validate_identifier_tuple(
        "reachable_target_unit_instance_ids",
        reachable_target_unit_instance_ids,
    )
    required_ids = set(
        catalog_selected_target_required_charge_target_unit_instance_ids(
            state=state,
            unit_instance_id=requested_unit_id,
        )
    )
    for effect in state.persisting_effects_for_unit(requested_unit_id):
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            continue
        for candidate_payload in _charge_target_requirement_payloads(payload):
            required_ids.update(
                _payload_identifier_list(
                    candidate_payload,
                    key=CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
                )
            )
    return tuple(sorted(required_ids))


def _charge_target_requirement_payloads(
    effect_payload: Mapping[str, object],
) -> tuple[Mapping[str, object], ...]:
    payloads: list[Mapping[str, object]] = []
    if CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY in effect_payload:
        payloads.append(effect_payload)
    raw_source_payload = effect_payload.get("source_payload")
    if isinstance(raw_source_payload, dict) and (
        CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY in raw_source_payload
    ):
        payloads.append(cast(Mapping[str, object], raw_source_payload))
    return tuple(payloads)


def _payload_identifier_list(payload: Mapping[str, object], *, key: str) -> tuple[str, ...]:
    raw_values = payload.get(key)
    if not isinstance(raw_values, list):
        raise GameLifecycleError(f"{key} must be a list.")
    return _validate_identifier_tuple(key, cast(list[object], raw_values))


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise GameLifecycleError(f"{field_name} must be a list or tuple.")
    raw_values = cast(list[object] | tuple[object, ...], values)
    validated = tuple(_validate_identifier(field_name, value) for value in raw_values)
    if len(set(validated)) != len(validated):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return validated


_validate_identifier = IdentifierValidator(GameLifecycleError)
