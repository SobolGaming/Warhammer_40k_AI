from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
    ModelPlacement,
    ModelPlacementPayload,
)
from warhammer40k_core.engine.damage_allocation import (
    DamageApplication,
    DamageApplicationPayload,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.healing import HealingStep, HealingStepKind, HealingStepPayload
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_battlefield_departure import (
    PrimaryBattlefieldDepartureState,
)
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT,
    PrimaryMissionBoundaryCheckpoint,
    PrimaryMissionBoundaryModelState,
)
from warhammer40k_core.engine.primary_mission_event_decision_authority import (
    validate_primary_mission_movement_event_decision_authority,
)
from warhammer40k_core.geometry.pose import Pose

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

_TRANSITION_EVENT_TYPES = frozenset(
    {
        "battlefield_models_placed",
        "catalog_models_materialized",
        "catalog_setup_reactive_charge_move_completed",
        "charge_move_completed",
        "fight_movement_completed",
        "heroic_intervention_charge_move_completed",
        "movement_activation_completed",
        "reinforcement_unit_arrived",
        "triggered_movement_resolved",
        "unit_disembarked",
    }
)


@dataclass(frozen=True, slots=True)
class _PhysicalAuthority:
    presence: str | None
    pose: Pose | None
    wounds_remaining: int | None


def validate_primary_mission_boundary_physical_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    checkpoint_index: int,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> None:
    for event_index, event in enumerate(event_records):
        if event.event_type != "movement_activation_completed":
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError("Primary mission movement event payload is invalid.")
        validate_primary_mission_movement_event_decision_authority(
            event_records=event_records,
            decision_records=decision_records,
            mutation_index=event_index,
            payload=event.payload,
        )
    before = _physical_authority_before_checkpoint(
        event_records=event_records,
        checkpoint_index=checkpoint_index,
    )
    later_records = event_records[checkpoint_index + 1 :]
    checkpoint_authority = {
        row.model_instance_id: _PhysicalAuthority(
            presence=row.presence,
            pose=_checkpoint_pose(row),
            wounds_remaining=row.wounds_remaining,
        )
        for row in checkpoint.model_states
    }
    later = _physical_authority_by_model(
        later_records,
        initial=checkpoint_authority,
    )
    current = _current_authority_by_model(state=state)
    for row in checkpoint.model_states:
        preceding = before.get(row.model_instance_id)
        if preceding is not None:
            _validate_row_against_authority(row=row, authority=preceding, context="preceding")
        _validate_authority_against_current(
            model_instance_id=row.model_instance_id,
            authority=later[row.model_instance_id],
            current=current[row.model_instance_id],
        )


def primary_mission_boundary_physical_event_model_ids(event: EventRecord) -> tuple[str, ...]:
    """Return model IDs mutated by an authenticated physical event family."""

    return tuple(sorted(_physical_authority_by_model((event,))))


def _physical_authority_by_model(
    event_records: tuple[EventRecord, ...],
    *,
    initial: dict[str, _PhysicalAuthority] | None = None,
) -> dict[str, _PhysicalAuthority]:
    authority = {} if initial is None else dict(initial)
    for event in event_records:
        transition = _transition_from_event(event)
        if transition is not None:
            _apply_transition(authority=authority, transition=transition)
        if event.event_type == "attack_sequence_step":
            _apply_damage_step(authority=authority, event=event)
        elif event.event_type == "healing_step_resolved":
            _apply_healing_step(authority=authority, event=event)
        elif event.event_type == "model_destroyed":
            _apply_model_destroyed(authority=authority, event=event)
        elif event.event_type == "primary_battlefield_departure_recorded":
            _apply_departure(authority=authority, event=event)
    return authority


def _physical_authority_before_checkpoint(
    *,
    event_records: tuple[EventRecord, ...],
    checkpoint_index: int,
) -> dict[str, _PhysicalAuthority]:
    prior_checkpoint_rows = tuple(
        (index, event)
        for index, event in enumerate(event_records[:checkpoint_index])
        if event.event_type == PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT
    )
    if not prior_checkpoint_rows:
        return _physical_authority_by_model(event_records[:checkpoint_index])
    prior_index, prior_event = prior_checkpoint_rows[-1]
    prior_checkpoint = PrimaryMissionBoundaryCheckpoint.from_payload(prior_event.payload)
    seeded = {
        row.model_instance_id: _PhysicalAuthority(
            presence=row.presence,
            pose=_checkpoint_pose(row),
            wounds_remaining=row.wounds_remaining,
        )
        for row in prior_checkpoint.model_states
    }
    if len(seeded) != len(prior_checkpoint.model_states):
        raise GameLifecycleError("Primary mission checkpoint model authority is duplicated.")
    return _physical_authority_by_model(
        event_records[prior_index + 1 : checkpoint_index],
        initial=seeded,
    )


def _transition_from_event(event: EventRecord) -> BattlefieldTransitionBatch | None:
    if event.event_type not in _TRANSITION_EVENT_TYPES:
        return None
    if not isinstance(event.payload, dict):
        raise GameLifecycleError("Primary mission physical event payload is invalid.")
    raw_transition = event.payload.get("transition_batch")
    if raw_transition is None:
        return None
    if not isinstance(raw_transition, dict):
        raise GameLifecycleError("Primary mission physical transition payload is invalid.")
    return BattlefieldTransitionBatch.from_payload(
        cast(BattlefieldTransitionBatchPayload, raw_transition)
    )


def _apply_transition(
    *,
    authority: dict[str, _PhysicalAuthority],
    transition: BattlefieldTransitionBatch,
) -> None:
    for placement in transition.placements:
        prior = authority.get(placement.model_instance_id)
        if prior is not None and prior.presence == "battlefield":
            raise GameLifecycleError("Primary mission placement history starts on battlefield.")
        authority[placement.model_instance_id] = _PhysicalAuthority(
            presence="battlefield",
            pose=placement.pose,
            wounds_remaining=None if prior is None else prior.wounds_remaining,
        )
    for displacement in transition.displacements:
        prior = authority.get(displacement.model_instance_id)
        if prior is not None and (
            prior.presence != "battlefield" or prior.pose != displacement.start_pose
        ):
            raise GameLifecycleError("Primary mission displacement history is discontinuous.")
        authority[displacement.model_instance_id] = _PhysicalAuthority(
            presence="battlefield",
            pose=displacement.end_pose,
            wounds_remaining=None if prior is None else prior.wounds_remaining,
        )
    for removal in transition.removals:
        prior = authority.get(removal.model_instance_id)
        if prior is not None and prior.presence != "battlefield":
            raise GameLifecycleError("Primary mission removal history is discontinuous.")
        authority[removal.model_instance_id] = _PhysicalAuthority(
            presence=_presence_for_removal(removal.removal_kind),
            pose=None,
            wounds_remaining=(
                0
                if removal.removal_kind is BattlefieldRemovalKind.DESTROYED
                else None
                if prior is None
                else prior.wounds_remaining
            ),
        )


def _apply_damage_step(
    *,
    authority: dict[str, _PhysicalAuthority],
    event: EventRecord,
) -> None:
    if not isinstance(event.payload, dict) or event.payload.get("step") != "damage":
        return
    step_payload = event.payload.get("payload")
    if not isinstance(step_payload, dict):
        raise GameLifecycleError("Primary mission damage-step payload is invalid.")
    raw_damage = step_payload.get("damage_application")
    if raw_damage is None:
        return
    if not isinstance(raw_damage, dict):
        raise GameLifecycleError("Primary mission damage authority payload is invalid.")
    damage = DamageApplication.from_payload(cast(DamageApplicationPayload, raw_damage))
    prior = authority.get(damage.model_instance_id)
    if prior is not None and (
        (
            prior.wounds_remaining is not None
            and prior.wounds_remaining != damage.starting_wounds_remaining
        )
        or (prior.presence is not None and prior.presence != "battlefield")
    ):
        raise GameLifecycleError("Primary mission damage history is discontinuous.")
    authority[damage.model_instance_id] = _PhysicalAuthority(
        presence="destroyed" if damage.destroyed else None if prior is None else prior.presence,
        pose=None if damage.destroyed else None if prior is None else prior.pose,
        wounds_remaining=damage.final_wounds_remaining,
    )


def _apply_healing_step(
    *,
    authority: dict[str, _PhysicalAuthority],
    event: EventRecord,
) -> None:
    if not isinstance(event.payload, dict):
        raise GameLifecycleError("Primary mission healing-step payload is invalid.")
    raw_step = event.payload.get("step")
    if not isinstance(raw_step, dict):
        raise GameLifecycleError("Primary mission healing authority payload is invalid.")
    step = HealingStep.from_payload(cast(HealingStepPayload, raw_step))
    prior = None if step.model_instance_id is None else authority.get(step.model_instance_id)
    if (
        prior is not None
        and step.starting_wounds_remaining is not None
        and prior.wounds_remaining is not None
        and prior.wounds_remaining != step.starting_wounds_remaining
    ):
        raise GameLifecycleError("Primary mission healing history is discontinuous.")
    if step.transition_batch is not None:
        _apply_transition(authority=authority, transition=step.transition_batch)
    if step.model_instance_id is None or step.final_wounds_remaining is None:
        return
    updated = authority.get(step.model_instance_id)
    presence = None if updated is None else updated.presence
    pose = None if updated is None else updated.pose
    if step.step_kind is HealingStepKind.REVIVE_MODEL_EMBARKED:
        presence, pose = "embarked", None
    elif step.step_kind is HealingStepKind.REVIVE_MODEL_DESTROYED_NO_CAPACITY:
        presence, pose = "destroyed", None
    authority[step.model_instance_id] = _PhysicalAuthority(
        presence=presence,
        pose=pose,
        wounds_remaining=step.final_wounds_remaining,
    )


def _apply_model_destroyed(
    *,
    authority: dict[str, _PhysicalAuthority],
    event: EventRecord,
) -> None:
    if not isinstance(event.payload, dict):
        raise GameLifecycleError("Primary mission destroyed-model payload is invalid.")
    model_id = event.payload.get("model_instance_id")
    if type(model_id) is not str:
        raise GameLifecycleError("Primary mission destroyed-model identity is invalid.")
    authority[model_id] = _PhysicalAuthority(
        presence="destroyed",
        pose=None,
        wounds_remaining=0,
    )


def _apply_departure(
    *,
    authority: dict[str, _PhysicalAuthority],
    event: EventRecord,
) -> None:
    if not isinstance(event.payload, dict):
        raise GameLifecycleError("Primary mission departure payload is invalid.")
    departure = PrimaryBattlefieldDepartureState.from_payload(
        event.payload.get("primary_battlefield_departure_state")
    )
    presence = _presence_for_removal(departure.removal_kind)
    for model_id in departure.removed_model_instance_ids:
        prior = authority.get(model_id)
        authority[model_id] = _PhysicalAuthority(
            presence=presence,
            pose=None,
            wounds_remaining=(
                0
                if departure.removal_kind is BattlefieldRemovalKind.DESTROYED
                else None
                if prior is None
                else prior.wounds_remaining
            ),
        )


def _current_authority_by_model(*, state: GameState) -> dict[str, _PhysicalAuthority]:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Primary mission physical authority requires battlefield state.")
    reserve_ids = set(state.unarrived_reserve_model_ids())
    embarked_ids = set(state.embarked_model_ids())
    current: dict[str, _PhysicalAuthority] = {}
    for army in state.army_definitions:
        for unit in army.units:
            for model in unit.own_models:
                placement = battlefield.model_placement_or_none(model.model_instance_id)
                if placement is not None:
                    presence, pose = "battlefield", placement.pose
                elif model.wounds_remaining == 0:
                    presence, pose = "destroyed", None
                elif model.model_instance_id in reserve_ids:
                    presence, pose = "reserves", None
                elif model.model_instance_id in embarked_ids:
                    presence, pose = "embarked", None
                else:
                    presence, pose = "off_battlefield", None
                current[model.model_instance_id] = _PhysicalAuthority(
                    presence=presence,
                    pose=pose,
                    wounds_remaining=model.wounds_remaining,
                )
    return current


def _validate_row_against_authority(
    *,
    row: PrimaryMissionBoundaryModelState,
    authority: _PhysicalAuthority,
    context: str,
) -> None:
    if authority.presence is not None and row.presence != authority.presence:
        raise GameLifecycleError(
            f"Primary mission boundary contradicts {context} physical history."
        )
    if authority.pose is not None and _checkpoint_pose(row) != authority.pose:
        raise GameLifecycleError(
            f"Primary mission boundary contradicts {context} movement history."
        )
    if authority.wounds_remaining is not None and (
        row.wounds_remaining != authority.wounds_remaining
        or row.alive is not (authority.wounds_remaining > 0)
    ):
        raise GameLifecycleError(f"Primary mission boundary contradicts {context} wound history.")


def _validate_authority_against_current(
    *,
    model_instance_id: str,
    authority: _PhysicalAuthority,
    current: _PhysicalAuthority,
) -> None:
    if (
        (authority.presence is not None and authority.presence != current.presence)
        or (authority.pose is not None and authority.pose != current.pose)
        or (
            authority.wounds_remaining is not None
            and authority.wounds_remaining != current.wounds_remaining
        )
    ):
        raise GameLifecycleError(
            f"Primary mission physical history for {model_instance_id} drifted from restored state."
        )


def _checkpoint_pose(row: PrimaryMissionBoundaryModelState) -> Pose | None:
    if row.model_placement_json is None:
        return None
    decoded: object = json.loads(row.model_placement_json)
    if not isinstance(decoded, dict):
        raise GameLifecycleError("Primary mission boundary placement payload is invalid.")
    return ModelPlacement.from_payload(cast(ModelPlacementPayload, decoded)).pose


def _presence_for_removal(removal_kind: BattlefieldRemovalKind) -> str:
    return {
        BattlefieldRemovalKind.DESTROYED: "destroyed",
        BattlefieldRemovalKind.EMBARK: "embarked",
        BattlefieldRemovalKind.INTO_RESERVES: "reserves",
        BattlefieldRemovalKind.TEMPORARILY_REMOVED: "off_battlefield",
    }[removal_kind]


__all__ = (
    "primary_mission_boundary_physical_event_model_ids",
    "validate_primary_mission_boundary_physical_authority",
)
