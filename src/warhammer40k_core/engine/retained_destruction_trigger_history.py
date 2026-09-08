from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
    DiceRollState,
    DiceRollStatePayload,
)
from warhammer40k_core.engine.attack_sequence_model import AttackSequencePayload
from warhammer40k_core.engine.attack_sequence_state import AttackSequence
from warhammer40k_core.engine.destruction_provenance import (
    DestructionProvenance,
    DestructionSourceKind,
)
from warhammer40k_core.engine.destruction_reaction_conditions import (
    destruction_reaction_fixed_conditions_met,
)
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.retained_attack_permissions import RETAINED_ATTACK_REACTION_KINDS
from warhammer40k_core.engine.retained_destruction_state import (
    DestructionOwnerKind,
    RetainedModelDestruction,
)
from warhammer40k_core.engine.rule_deadly_demise_continuation import (
    destruction_provenance_from_rule_context,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.model_destruction_cause_authority import (
        ModelDestructionCauseAuthority,
    )


def retained_destruction_provenance(record: RetainedModelDestruction) -> DestructionProvenance:
    if record.owner_kind is DestructionOwnerKind.RULE:
        return destruction_provenance_from_rule_context(record.owner_context)
    if record.owner_kind is DestructionOwnerKind.ATTACK_COLLATERAL:
        return DestructionProvenance.for_non_attack(DestructionSourceKind.DEADLY_DEMISE)
    sequence = AttackSequence.from_payload(cast(AttackSequencePayload, record.owner_context))
    pending = sequence.current_pending_attack_destruction
    if pending is None:
        raise GameLifecycleError("Retained source history requires its attack destruction.")
    return DestructionProvenance.for_attack(
        weapon_profile=pending.attack_pool.weapon_profile,
        attack_context_id=pending.attack_context["attack_context_id"],
    )


def validate_retention_trigger_history(
    *,
    record: RetainedModelDestruction,
    cause: ModelDestructionCauseAuthority,
    battle_round: int,
    active_player_id: str,
    phase: str,
    event_records: tuple[EventRecord, ...],
) -> None:
    sources = tuple(
        source
        for source in record.sources
        if source.reaction_kind in RETAINED_ATTACK_REACTION_KINDS
    )
    triggers = tuple(
        event
        for event in event_records
        if event.event_type == "fight_on_death_retention_trigger_resolved"
        and isinstance(event.payload, dict)
        and event.payload.get("cause_id") == record.cause_id
    )
    if len(triggers) != sum(source.payload is not None for source in sources):
        raise GameLifecycleError("Retained source trigger inventory drift.")
    provenance = retained_destruction_provenance(record)
    eligible_ids: list[str] = []
    logical_index = next(
        index
        for index, event in enumerate(event_records)
        if event.event_id == record.logical_death_event_id
    )
    for source in sources:
        descriptor = source.payload
        if descriptor is None:
            eligible_ids.append(source.source_id)
            continue
        if not isinstance(descriptor, dict):
            raise GameLifecycleError("Retained source descriptor must be an object.")
        matches = tuple(
            event
            for event in triggers
            if isinstance(event.payload, dict)
            and event.payload.get("source") == source.to_payload()
        )
        if len(matches) != 1:
            raise GameLifecycleError("Retained source lacks its exact trigger evidence.")
        event = matches[0]
        payload = cast(dict[str, JsonValue], event.payload)
        trigger_index = event_records.index(event)
        if (
            set(payload)
            != {
                "cause_id",
                "logical_death_event_id",
                "model_instance_id",
                "target_unit_instance_id",
                "source",
                "destruction_provenance",
                "applicable",
                "trigger_roll",
                "triggered",
            }
            or trigger_index <= logical_index
            or payload["logical_death_event_id"] != record.logical_death_event_id
            or payload["model_instance_id"] != record.model_instance_id
            or payload["target_unit_instance_id"] != cause.rules_unit_instance_id
            or payload["destruction_provenance"] != provenance.to_payload()
            or type(payload["applicable"]) is not bool
            or type(payload["triggered"]) is not bool
        ):
            raise GameLifecycleError("Retained source trigger provenance drift.")
        applicable = payload["applicable"]
        fixed_conditions_met = destruction_reaction_fixed_conditions_met(
            battle_round=battle_round,
            destruction_provenance=provenance,
            descriptor=descriptor,
        )
        if descriptor.get("requires_not_shot_or_fought_this_phase") is True:
            from warhammer40k_core.engine.model_attack_history import model_has_attacked_this_phase

            fixed_conditions_met = fixed_conditions_met and not model_has_attacked_this_phase(
                event_records=event_records[:logical_index],
                model_instance_id=record.model_instance_id,
                battle_round=battle_round,
                active_player_id=active_player_id,
                phase=phase,
            )
        if (not fixed_conditions_met and applicable) or (
            "requires_active_persisting_effect" not in descriptor
            and descriptor.get("requires_not_fought_this_phase") is not True
            and applicable is not fixed_conditions_met
        ):
            raise GameLifecycleError("Retained source trigger applicability drift.")
        threshold = descriptor.get("trigger_roll_threshold")
        raw_roll = payload["trigger_roll"]
        triggered = applicable
        if applicable and threshold is not None:
            if (
                type(threshold) is not int
                or not 1 <= threshold <= 6
                or not isinstance(raw_roll, dict)
            ):
                raise GameLifecycleError("Retained source trigger roll is missing or malformed.")
            roll = DiceRollState.from_payload(cast(DiceRollStatePayload, raw_roll))
            roll_type = descriptor.get("trigger_roll_type", "destruction_reaction_trigger")
            if not isinstance(roll_type, str):
                raise GameLifecycleError("Retained source trigger roll type is invalid.")
            expected_spec = DiceRollSpec(
                expression=DiceExpression(quantity=1, sides=6),
                reason="Destruction reaction trigger",
                roll_type=roll_type,
                actor_id=record.placement.player_id,
            )
            if (
                roll.original_result.spec != expected_spec
                or roll != DiceRollState.from_result(roll.original_result)
                or sum(
                    prior.event_type == "dice_rolled"
                    and prior.payload == roll.original_result.to_payload()
                    for prior in event_records[logical_index + 1 : trigger_index]
                )
                != 1
            ):
                raise GameLifecycleError("Retained source trigger dice authority drift.")
            triggered = roll.current_total >= threshold
        elif raw_roll is not None:
            raise GameLifecycleError("Retained source has an unsolicited trigger roll.")
        if payload["triggered"] is not triggered:
            raise GameLifecycleError("Retained source trigger outcome drift.")
        if triggered:
            eligible_ids.append(source.source_id)
    if tuple(eligible_ids) != tuple(source.source_id for source in record.eligible_sources):
        raise GameLifecycleError("Retained source options differ from their trigger outcomes.")
