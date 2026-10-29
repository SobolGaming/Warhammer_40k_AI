# pyright: reportPrivateUsage=false
# Extracted sibling of the rule-destruction owner; shared typed validation remains there.
"""Physical rule-casualty finalization shared by ordinary and retained cleanup."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldTransitionBatch,
    ModelPlacement,
    ModelPlacementPayload,
    ModelRemovalRecord,
    ModelRemovalRecordPayload,
)
from warhammer40k_core.engine.damage_allocation import remove_destroyed_model_from_battlefield
from warhammer40k_core.engine.destruction_provenance import ModelDestructionAttribution
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.model_destruction_cause_producers import (
    append_rule_effect_model_destroyed_event as _append_model_destroyed,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_destruction_evidence import (
    destruction_source_objective_proximity_witness,
    rules_unit_objective_proximity_witness,
)
from warhammer40k_core.engine.retained_demise_removal import retained_fight_removed_event
from warhammer40k_core.engine.retained_destruction_state import retained_destruction_for_model
from warhammer40k_core.engine.rule_deadly_demise_continuation import (
    damage_application_from_rule_context,
    destruction_provenance_from_rule_context,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState


def validate_removed_rule_context(
    *, state: GameState, root_context: dict[str, JsonValue], removed: EventRecord
) -> None:
    model_id = root_context.get("model_instance_id")
    if not isinstance(model_id, str):
        raise GameLifecycleError("Removed rule casualty lacks a model ID.")
    retained = retained_destruction_for_model(state=state, model_instance_id=model_id)
    if retained is None or not isinstance(removed.payload, dict):
        raise GameLifecycleError("Removed rule casualty lacks retained authority.")
    keys = (
        "model_instance_id",
        "source_result_id",
        "source_rule_id",
        "source_effect_ids",
        "target_unit_instance_id",
        "rules_unit_instance_id",
        "destroyed_model_placement",
    )
    if any(retained.owner_context.get(key) != root_context.get(key) for key in keys):
        raise GameLifecycleError("Removed rule casualty continuation source drift.")
    if removed.payload.get("model_instance_id") != model_id:
        raise GameLifecycleError("Removed rule casualty event identity drift.")


def finalize_rule_casualty(
    *, state: GameState, decisions: DecisionController, root_context: dict[str, JsonValue]
) -> tuple[EventRecord, ModelRemovalRecord, BattlefieldTransitionBatch]:
    # Sibling extraction: these helpers retain the original rule-owner checks.
    from warhammer40k_core.engine.rule_model_destruction import (
        _payload_identifier_list,
        _payload_string,
        _validate_pre_removal_context_matches_state,
    )

    model_id = _payload_string(root_context, "model_instance_id")
    removed = retained_fight_removed_event(state=state, model_instance_id=model_id)
    if removed is not None:
        validate_removed_rule_context(state=state, root_context=root_context, removed=removed)
        if not isinstance(removed.payload, dict) or not isinstance(
            removed.payload.get("removal_record"), dict
        ):
            raise GameLifecycleError("Removed rule casualty lacks its removal artifact.")
        removal = ModelRemovalRecord.from_payload(
            cast(ModelRemovalRecordPayload, removed.payload["removal_record"])
        )
        return removed, removal, BattlefieldTransitionBatch(removals=(removal,))
    _validate_pre_removal_context_matches_state(state=state, context=root_context)
    model_id = _payload_string(root_context, "model_instance_id")
    rules_unit_id = _payload_string(root_context, "rules_unit_instance_id")
    physical_unit_id = _payload_string(root_context, "target_unit_instance_id")
    remove_destroyed_model_from_battlefield(state=state, model_instance_id=model_id)
    removal_record = ModelRemovalRecord(
        model_instance_id=model_id,
        removal_kind=BattlefieldRemovalKind.DESTROYED,
        source_phase=_payload_string(root_context, "phase"),
        source_step=_payload_string(root_context, "source_step"),
        source_rule_id=_payload_string(root_context, "source_rule_id"),
        source_event_id=_payload_string(root_context, "source_result_id"),
    )
    transition_batch = BattlefieldTransitionBatch(removals=(removal_record,))
    damage = damage_application_from_rule_context(root_context)
    provenance = destruction_provenance_from_rule_context(root_context)
    attribution = ModelDestructionAttribution(
        destroying_player_id=_payload_string(root_context, "destroying_player_id"),
        source_rules_unit_instance_id=_optional_payload_string(
            root_context,
            "source_rules_unit_instance_id",
        ),
        source_model_instance_id=_optional_payload_string(
            root_context,
            "source_model_instance_id",
        ),
        attacking_unit_instance_id=None,
        attacking_model_instance_id=None,
        destruction_provenance=provenance,
    )
    raw_destroyed_placement = root_context.get("destroyed_model_placement")
    if not isinstance(raw_destroyed_placement, dict):
        raise GameLifecycleError("Rule destruction requires exact pre-removal placement evidence.")
    destroyed_model_placement = ModelPlacement.from_payload(
        cast(ModelPlacementPayload, raw_destroyed_placement)
    )
    if (
        destroyed_model_placement.model_instance_id != model_id
        or destroyed_model_placement.unit_instance_id != physical_unit_id
    ):
        raise GameLifecycleError("Rule destruction placement identity drift.")
    destroyed_rules_unit_objective_witness = rules_unit_objective_proximity_witness(
        state=state,
        rules_unit_instance_id=rules_unit_id,
        included_destroyed_model_placement=destroyed_model_placement,
    )
    source_rules_unit_objective_witness = destruction_source_objective_proximity_witness(
        state=state,
        event_log=decisions.event_log,
        attribution=attribution,
        destroyed_model_placement=destroyed_model_placement,
    )
    destroyed_event = _append_model_destroyed(
        state=state,
        decisions=decisions,
        root_context=root_context,
        payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": _payload_string(root_context, "active_player_id"),
            "phase": _payload_string(root_context, "phase"),
            **attribution.to_payload(),
            "source_rules_unit_objective_proximity_witness": (
                None
                if source_rules_unit_objective_witness is None
                else source_rules_unit_objective_witness.to_payload()
            ),
            "destroyed_rules_unit_objective_proximity_witness": (
                destroyed_rules_unit_objective_witness.to_payload()
            ),
            "target_unit_instance_id": physical_unit_id,
            "rules_unit_instance_id": rules_unit_id,
            "model_instance_id": model_id,
            "damage_kind": None if damage is None else damage.damage_kind.value,
            "damage_event_id": None,
            "source_rule_id": _payload_string(root_context, "source_rule_id"),
            "source_effect_ids": list(_payload_identifier_list(root_context, "source_effect_ids")),
            "removal_record": removal_record.to_payload(),
            "transition_batch": transition_batch.to_payload(),
            "destroyed_model_placement": root_context.get("destroyed_model_placement"),
            "damage_application": None if damage is None else damage.to_payload(),
            "destroyed_model_rules_triggered": True,
        },
    )
    return destroyed_event, removal_record, transition_batch


def _optional_payload_string(payload: dict[str, JsonValue], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    return IdentifierValidator(GameLifecycleError)(key, value)
