from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.attack_sequence_model import (
    AttackResolutionContextPayload,
    PendingDestroyedTransportDisembark,
    PendingDestroyedTransportDisembarkPayload,
)
from warhammer40k_core.engine.attack_sequence_validation import (
    _validate_destroyed_transport_disembark_tuple,
    _validate_destruction_reaction_source_tuple,
    _validate_identifier,
    _validate_identifier_tuple,
)
from warhammer40k_core.engine.damage_allocation import (
    DamageApplication,
    FeelNoPainResolution,
)
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.transports import DestroyedTransportHazardRolls


def validate_pending_destroyed_transport_disembark(
    pending: PendingDestroyedTransportDisembark,
) -> None:
    attack_context = validate_json_value(pending.attack_context)
    if not isinstance(attack_context, dict):
        raise GameLifecycleError("Pending destroyed Transport attack_context must be an object.")
    object.__setattr__(
        pending,
        "attack_context",
        cast(AttackResolutionContextPayload, attack_context),
    )
    if type(pending.damage_application) is not DamageApplication:
        raise GameLifecycleError(
            "Pending destroyed Transport damage_application must be DamageApplication."
        )
    if not pending.damage_application.destroyed:
        raise GameLifecycleError("Pending destroyed Transport requires destroyed damage.")
    if (
        pending.damage_application.target_unit_instance_id
        != pending.attack_context["target_unit_instance_id"]
    ):
        raise GameLifecycleError("Pending destroyed Transport damage target drift.")
    object.__setattr__(
        pending,
        "saving_throw_payload",
        validate_json_value(pending.saving_throw_payload),
    )
    if type(pending.feel_no_pain) is not FeelNoPainResolution:
        raise GameLifecycleError(
            "Pending destroyed Transport feel_no_pain must be FeelNoPainResolution."
        )
    object.__setattr__(
        pending,
        "destroyed_model_controller_player_id",
        _validate_identifier(
            "Pending destroyed Transport controller",
            pending.destroyed_model_controller_player_id,
        ),
    )
    object.__setattr__(
        pending,
        "transport_unit_instance_id",
        _validate_identifier(
            "Pending destroyed Transport transport_unit_instance_id",
            pending.transport_unit_instance_id,
        ),
    )
    object.__setattr__(
        pending,
        "pending_unit_instance_ids",
        _validate_identifier_tuple(
            "Pending destroyed Transport unit ids",
            pending.pending_unit_instance_ids,
        ),
    )
    object.__setattr__(
        pending,
        "resolved_disembarks",
        _validate_destroyed_transport_disembark_tuple(pending.resolved_disembarks),
    )
    if (
        pending.current_hazard_rolls is not None
        and type(pending.current_hazard_rolls) is not DestroyedTransportHazardRolls
    ):
        raise GameLifecycleError("Pending destroyed Transport current hazard rolls are invalid.")
    surviving_model_ids = pending.current_hazard_surviving_model_instance_ids
    if surviving_model_ids is not None:
        surviving_model_ids = _validate_identifier_tuple(
            "Pending destroyed Transport hazard survivor ids",
            surviving_model_ids,
        )
        object.__setattr__(
            pending,
            "current_hazard_surviving_model_instance_ids",
            surviving_model_ids,
        )
    object.__setattr__(
        pending,
        "hazard_destroyed_unit_instance_ids",
        _validate_identifier_tuple(
            "Pending destroyed Transport hazard-destroyed unit ids",
            pending.hazard_destroyed_unit_instance_ids,
        ),
    )
    object.__setattr__(
        pending,
        "pending_sources",
        _validate_destruction_reaction_source_tuple(
            "Pending destroyed Transport pending_sources",
            pending.pending_sources,
        ),
    )
    resolved_unit_ids = {disembark.unit_instance_id for disembark in pending.resolved_disembarks}
    hazard_destroyed_unit_ids = set(pending.hazard_destroyed_unit_instance_ids)
    if (
        resolved_unit_ids & set(pending.pending_unit_instance_ids)
        or hazard_destroyed_unit_ids & set(pending.pending_unit_instance_ids)
        or resolved_unit_ids & hazard_destroyed_unit_ids
    ):
        raise GameLifecycleError("Pending destroyed Transport unit appears in both states.")
    for disembark in pending.resolved_disembarks:
        if disembark.transport_unit_instance_id != pending.transport_unit_instance_id:
            raise GameLifecycleError("Pending destroyed Transport disembark transport drift.")
        if disembark.battle_round < 1:
            raise GameLifecycleError("Pending destroyed Transport disembark round drift.")
    hazard_rolls = pending.current_hazard_rolls
    if hazard_rolls is None:
        if surviving_model_ids is not None:
            raise GameLifecycleError(
                "Pending destroyed Transport survivors require current hazard rolls."
            )
        return
    if pending.next_unit_instance_id != hazard_rolls.unit_instance_id:
        raise GameLifecycleError("Pending destroyed Transport current hazard unit drift.")
    if hazard_rolls.transport_unit_instance_id != pending.transport_unit_instance_id:
        raise GameLifecycleError("Pending destroyed Transport current hazard transport drift.")
    if surviving_model_ids is not None and not set(surviving_model_ids) <= set(
        hazard_rolls.model_instance_ids
    ):
        raise GameLifecycleError("Pending destroyed Transport hazard survivor inventory drift.")


def pending_destroyed_transport_disembark_to_payload(
    pending: PendingDestroyedTransportDisembark,
) -> PendingDestroyedTransportDisembarkPayload:
    return {
        "attack_context": pending.attack_context,
        "damage_application": pending.damage_application.to_payload(),
        "saving_throw": pending.saving_throw_payload,
        "feel_no_pain": pending.feel_no_pain.to_payload(),
        "destroyed_model_controller_player_id": (pending.destroyed_model_controller_player_id),
        "transport_unit_instance_id": pending.transport_unit_instance_id,
        "pending_unit_instance_ids": list(pending.pending_unit_instance_ids),
        "resolved_disembarks": [
            disembark.to_payload() for disembark in pending.resolved_disembarks
        ],
        "current_hazard_rolls": (
            None
            if pending.current_hazard_rolls is None
            else pending.current_hazard_rolls.to_payload()
        ),
        "current_hazard_surviving_model_instance_ids": (
            None
            if pending.current_hazard_surviving_model_instance_ids is None
            else list(pending.current_hazard_surviving_model_instance_ids)
        ),
        "hazard_destroyed_unit_instance_ids": list(pending.hazard_destroyed_unit_instance_ids),
        "pending_sources": [source.to_payload() for source in pending.pending_sources],
    }
