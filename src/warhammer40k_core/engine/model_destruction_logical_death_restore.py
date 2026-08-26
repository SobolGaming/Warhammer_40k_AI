from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.model_destruction_cause_authority import (
    ModelDestructionCauseAuthority,
    ModelDestructionCauseKind,
)
from warhammer40k_core.engine.model_logical_death import (
    DamageApplicationLogicalDeathTransition,
    DirectRuleLogicalDeathTransition,
    ModelLogicalDeathRecord,
    model_logical_death_record_from_event,
)
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def validate_model_destruction_logical_death_producer_restore(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
) -> None:
    """Validate each logical-death boundary against its producer grammar.

    The generic cause ledger owns identity, uniqueness, parent/child ordering,
    and boundary-before-consumption ordering.  This validator owns the parts
    that differ by producer: the transition shape, exact damage or rule source,
    placement retention, and the ordering of producer source records around the
    boundary.
    """

    event_indexes = _event_indexes(event_records)
    for authority in state.model_destruction_cause_authorities:
        record = model_logical_death_record_from_event(authority.logical_death_event)
        boundary_index = _event_index(
            event_indexes,
            authority.logical_death_event,
            field_name="logical-death boundary",
        )
        if authority.cause_kind is ModelDestructionCauseKind.ATTACK_DAMAGE:
            _validate_attack_damage_boundary(
                state=state,
                authority=authority,
                record=record,
                boundary_index=boundary_index,
                event_indexes=event_indexes,
            )
        elif authority.cause_kind is ModelDestructionCauseKind.MORTAL_WOUND:
            _validate_mortal_wound_boundary(
                authority=authority,
                record=record,
            )
        elif authority.cause_kind is ModelDestructionCauseKind.RULE_EFFECT:
            _validate_rule_effect_boundary(
                authority=authority,
                record=record,
                boundary_index=boundary_index,
                event_indexes=event_indexes,
            )
        else:
            raise GameLifecycleError("Logical-death cause kind is unsupported.")


def _validate_attack_damage_boundary(
    *,
    state: GameState,
    authority: ModelDestructionCauseAuthority,
    record: ModelLogicalDeathRecord,
    boundary_index: int,
    event_indexes: dict[str, int],
) -> None:
    context = authority.producer_context
    transition = _damage_transition(record, cause_label="Attack")
    if transition.damage_application != _context_object(
        context,
        key="damage_application",
        field_name="attack destruction damage_application",
    ):
        raise GameLifecycleError("Attack logical-death damage binding drift.")
    if not record.placement_retained:
        raise GameLifecycleError("Attack logical death must retain placement.")

    _validate_decision_sources_precede_boundary(
        authority=authority,
        boundary_index=boundary_index,
        event_indexes=event_indexes,
        cause_label="Attack",
    )
    if not authority.source_authority_finalized:
        battlefield = state.battlefield_state
        placement = (
            None
            if battlefield is None
            else battlefield.model_placement_or_none(authority.model_instance_id)
        )
        if placement != record.destroyed_model_placement:
            raise GameLifecycleError("Pending attack logical-death placement drift.")
        return

    _validate_context_placement(authority=authority, record=record, cause_label="Attack")
    raw_damage_event = context.get("damage_event")
    damage_events = tuple(
        event for event in authority.source_event_records if event.to_payload() == raw_damage_event
    )
    if len(damage_events) != 1:
        raise GameLifecycleError("Attack logical death lacks one damage event.")
    damage_event_index = _event_index(
        event_indexes,
        damage_events[0],
        field_name="attack damage source",
    )
    if boundary_index >= damage_event_index:
        raise GameLifecycleError(
            "Attack logical death must follow declaration authority and precede damage emission."
        )


def _validate_mortal_wound_boundary(
    *,
    authority: ModelDestructionCauseAuthority,
    record: ModelLogicalDeathRecord,
) -> None:
    context = authority.producer_context
    transition = _damage_transition(record, cause_label="Mortal-wound")
    application = _context_object(
        context,
        key="application",
        field_name="mortal-wound application",
    )
    raw_applications = application.get("applications")
    if not isinstance(raw_applications, list):
        raise GameLifecycleError("Mortal-wound application damage inventory is invalid.")
    matching = tuple(
        item
        for item in raw_applications
        if isinstance(item, dict)
        and item.get("model_instance_id") == authority.model_instance_id
        and item.get("destroyed") is True
    )
    if len(matching) != 1 or transition.damage_application != matching[0]:
        raise GameLifecycleError("Mortal-wound logical-death damage binding drift.")
    if record.placement_retained:
        raise GameLifecycleError("Finalized mortal-wound logical death cannot retain placement.")
    _validate_context_placement(
        authority=authority,
        record=record,
        cause_label="Mortal-wound",
    )
    if authority.source_event_records or authority.source_decision_records:
        raise GameLifecycleError("Mortal-wound logical death cannot carry source records.")


def _validate_rule_effect_boundary(
    *,
    authority: ModelDestructionCauseAuthority,
    record: ModelLogicalDeathRecord,
    boundary_index: int,
    event_indexes: dict[str, int],
) -> None:
    context = authority.producer_context
    if not record.placement_retained:
        raise GameLifecycleError("Rule-effect logical death must retain placement.")
    _validate_context_placement(
        authority=authority,
        record=record,
        cause_label="Rule-effect",
    )
    raw_damage = context.get("damage_application")
    if raw_damage is None:
        transition = record.transition
        if not isinstance(transition, DirectRuleLogicalDeathTransition):
            raise GameLifecycleError("Direct rule logical death requires direct-rule evidence.")
        if (
            transition.source_rule_id != context.get("source_rule_id")
            or transition.source_result_id != authority.producer_id
            or transition.source_result_id != context.get("source_result_id")
        ):
            raise GameLifecycleError("Direct rule logical-death source binding drift.")
    else:
        transition = _damage_transition(record, cause_label="Applied rule")
        if transition.damage_application != _json_object(
            raw_damage,
            field_name="applied rule damage_application",
        ):
            raise GameLifecycleError("Applied rule logical-death damage binding drift.")

    _validate_decision_sources_precede_boundary(
        authority=authority,
        boundary_index=boundary_index,
        event_indexes=event_indexes,
        cause_label="Rule-effect",
    )
    if any(event.event_type != "decision_recorded" for event in authority.source_event_records):
        raise GameLifecycleError("Rule-effect logical-death source event kind drift.")


def _validate_decision_sources_precede_boundary(
    *,
    authority: ModelDestructionCauseAuthority,
    boundary_index: int,
    event_indexes: dict[str, int],
    cause_label: str,
) -> None:
    for decision in authority.source_decision_records:
        matches = tuple(
            event
            for event in authority.source_event_records
            if event.event_type == "decision_recorded" and event.payload == decision.to_payload()
        )
        if (
            len(matches) != 1
            or _event_index(
                event_indexes,
                matches[0],
                field_name=f"{cause_label.lower()} declaration source",
            )
            >= boundary_index
        ):
            raise GameLifecycleError(
                f"{cause_label} logical death must follow its decision authority."
            )


def _damage_transition(
    record: ModelLogicalDeathRecord,
    *,
    cause_label: str,
) -> DamageApplicationLogicalDeathTransition:
    transition = record.transition
    if not isinstance(transition, DamageApplicationLogicalDeathTransition):
        raise GameLifecycleError(
            f"{cause_label} logical death requires damage-application evidence."
        )
    return transition


def _validate_context_placement(
    *,
    authority: ModelDestructionCauseAuthority,
    record: ModelLogicalDeathRecord,
    cause_label: str,
) -> None:
    raw = _context_object(
        authority.producer_context,
        key="destroyed_model_placement",
        field_name=f"{cause_label.lower()} destroyed_model_placement",
    )
    if raw != record.destroyed_model_placement.to_payload():
        raise GameLifecycleError(f"{cause_label} logical-death placement binding drift.")


def _context_object(
    context: dict[str, JsonValue],
    *,
    key: str,
    field_name: str,
) -> dict[str, JsonValue]:
    return _json_object(context.get(key), field_name=field_name)


def _json_object(value: object, *, field_name: str) -> dict[str, JsonValue]:
    validated = validate_json_value(value)
    if not isinstance(validated, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    return validated


def _event_indexes(event_records: tuple[EventRecord, ...]) -> dict[str, int]:
    if type(event_records) is not tuple or any(
        type(event) is not EventRecord for event in event_records
    ):
        raise GameLifecycleError("Logical-death restore requires EventRecord history.")
    indexes = {event.event_id: index for index, event in enumerate(event_records)}
    if len(indexes) != len(event_records):
        raise GameLifecycleError("Logical-death event history contains duplicate IDs.")
    return indexes


def _event_index(
    event_indexes: dict[str, int],
    event: EventRecord,
    *,
    field_name: str,
) -> int:
    index = event_indexes.get(event.event_id)
    if index is None:
        raise GameLifecycleError(f"{field_name} is absent from canonical history.")
    return index


__all__ = ("validate_model_destruction_logical_death_producer_restore",)
