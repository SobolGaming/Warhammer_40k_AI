from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypedDict, cast

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.capability_manifest import project_capability_manifest
from warhammer40k_core.adapters.external_contract import ERROR_ENVELOPE_SCHEMA_VERSION
from warhammer40k_core.adapters.support_profile import SupportProfilePayload
from warhammer40k_core.core.descriptor_hash import canonical_payload_sha256
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import (
    EventRecordPayload,
    JsonValue,
    validate_json_value,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mission_decisions import (
    TACTICAL_SECONDARY_SCORE_DECISION_TYPE,
)
from warhammer40k_core.engine.model_logical_death import (
    MODEL_LOGICAL_DEATH_RECORDED_EVENT,
)
from warhammer40k_core.engine.mortal_wound_application_authority import (
    MORTAL_WOUND_APPLICATION_STARTED_EVENT,
)
from warhammer40k_core.engine.mortal_wound_model_allocation import (
    MORTAL_WOUND_MODEL_ALLOCATED_EVENT_TYPE,
)
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
    SetupStep,
)
from warhammer40k_core.engine.primary_destruction_evidence import (
    RulesUnitObjectiveProximityWitness,
)
from warhammer40k_core.engine.primary_mission_action_decline_integrity import (
    MISSION_ACTION_OPPORTUNITY_DECLINED_EVENT,
)
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT,
    PrimaryMissionBoundaryCheckpoint,
)
from warhammer40k_core.engine.primary_scoring_commit_checkpoint import (
    PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT,
)
from warhammer40k_core.engine.primary_turn_start_evidence import (
    PrimaryRulesUnitTurnStartSnapshot,
    PrimaryRulesUnitTurnStartSnapshotPayload,
)
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardState,
    SecondaryMissionCardStatePayload,
    VictoryPointLedger,
    VictoryPointTransaction,
    VictoryPointTransactionPayload,
)

HIDDEN_DECISION_TYPE = "hidden_decision"
HIDDEN_REQUEST_ID = "hidden-request"
HIDDEN_RESULT_ID = "hidden-result"
_TACTICAL_SECONDARY_SCORE_DECLINED_EVENT_TYPE = "tactical_secondary_mission_score_declined"
_INTERNAL_SECONDARY_AUTHORITY_COMMITMENT_KEYS = frozenset(
    {
        "scoring_commit_checkpoint_id",
        "scoring_commit_checkpoint_hash",
        "secondary_scoring_state_evidence_id",
        "secondary_scoring_state_evidence_hash",
    }
)
_INTERNAL_MODEL_DESTRUCTION_AUTHORITY_KEYS = frozenset(
    {
        "allocation_occurrence",
        "logical_death_cause_binding",
        "logical_death_event",
        "logical_death_events",
        "model_destruction_cause_authorities",
        "model_destruction_cause_id",
        "parent_model_destruction_cause_id",
    }
)


class RedactedLifecycleStatusPayload(TypedDict):
    stage: str
    status_kind: str
    message: str | None
    payload: JsonValue
    pending_request_id: str | None
    decision_type: str | None
    actor_id: str | None


def battle_formation_declarations_are_unresolved(state: GameState) -> bool:
    """Return whether simultaneous Declare Battle Formations choices remain private."""
    if type(state) is not GameState:
        raise GameLifecycleError("Battle-formation redaction requires a GameState.")
    declaration_step = SetupStep.DECLARE_BATTLE_FORMATIONS
    if declaration_step not in state.setup_sequence:
        return False
    if state.stage is not GameLifecycleStage.SETUP or state.setup_step_index is None:
        return False
    declaration_index = state.setup_sequence.index(declaration_step)
    return state.setup_step_index <= declaration_index


def public_primary_rules_unit_turn_start_snapshots(
    snapshots: Sequence[PrimaryRulesUnitTurnStartSnapshot],
) -> list[PrimaryRulesUnitTurnStartSnapshotPayload]:
    """Project complete public rules-unit history without viewer filtering."""
    if any(type(snapshot) is not PrimaryRulesUnitTurnStartSnapshot for snapshot in snapshots):
        raise GameLifecycleError("Turn-start snapshot redaction requires typed snapshots.")
    return [snapshot.to_payload() for snapshot in snapshots]


def public_victory_point_transaction_payload(
    transaction: VictoryPointTransaction,
    *,
    viewer: ViewerContext,
    domain_viewer_player_id: str,
    secondary_mission_choices_revealed: bool,
) -> dict[str, JsonValue]:
    """Project one transaction without exposing internal authority commitments."""

    if type(transaction) is not VictoryPointTransaction:
        raise GameLifecycleError("Victory-point redaction requires a typed transaction.")
    if type(viewer) is not ViewerContext:
        raise GameLifecycleError("Victory-point redaction requires a ViewerContext.")
    if viewer.policy.omniscient:
        return cast(dict[str, JsonValue], transaction.to_payload())
    payload = transaction.to_public_payload(
        viewer_player_id=domain_viewer_player_id,
        secondary_mission_choices_revealed=secondary_mission_choices_revealed,
    )
    if "source_kind" in payload:
        payload["metadata"] = _without_internal_secondary_authority_commitments(
            transaction.metadata
        )
    return cast(dict[str, JsonValue], validate_json_value(payload))


def public_victory_point_ledger_payload(
    ledger: VictoryPointLedger,
    *,
    viewer: ViewerContext,
    domain_viewer_player_id: str,
    secondary_mission_choices_revealed: bool,
) -> dict[str, JsonValue]:
    """Project one ledger through the shared transaction redaction path."""

    if type(ledger) is not VictoryPointLedger:
        raise GameLifecycleError("Victory-point redaction requires a typed ledger.")
    if type(viewer) is not ViewerContext:
        raise GameLifecycleError("Victory-point redaction requires a ViewerContext.")
    return {
        "player_id": ledger.player_id,
        "victory_points": ledger.victory_points,
        "transactions": [
            public_victory_point_transaction_payload(
                transaction,
                viewer=viewer,
                domain_viewer_player_id=domain_viewer_player_id,
                secondary_mission_choices_revealed=secondary_mission_choices_revealed,
            )
            for transaction in ledger.transactions
        ],
    }


def public_error_envelope(*, code: str, message: str) -> dict[str, JsonValue]:
    public_code = _public_error_string("error code", code)
    public_message = _public_error_string("error message", message)
    return {
        "schema_version": ERROR_ENVELOPE_SCHEMA_VERSION,
        "error": {
            "code": public_code,
            "message": public_message,
        },
    }


def public_support_profile_payload(
    payload: SupportProfilePayload,
    *,
    viewer: ViewerContext,
) -> JsonValue:
    if type(viewer) is not ViewerContext:
        raise GameLifecycleError("Support-profile redaction requires a ViewerContext.")
    if not viewer.policy.may_view_support:
        raise GameLifecycleError("Viewer role cannot receive a support profile.")
    public_payload = dict(payload)
    capability_manifest = project_capability_manifest(
        payload["capability_manifest"],
        viewer_player_id=viewer.viewer_player_id,
        omniscient=viewer.policy.omniscient,
    )
    public_payload["capability_manifest"] = capability_manifest
    if not viewer.policy.omniscient:
        visible_datasheet_ids = {
            _required_metadata_string(row["metadata"], key="datasheet_id")
            for row in capability_manifest["unit_rows"]
        }
        visible_runtime_content_ids = {
            row["owner_id"]
            for row in capability_manifest["rule_rows"]
            if "content_family" in row["metadata"]
        }
        mustering_rows = [
            row
            for row in payload["mustering_support_rows"]
            if row["player_id"] == viewer.viewer_player_id
        ]
        datasheet_rows = [
            row
            for row in payload["datasheet_support_rows"]
            if row["datasheet_id"] in visible_datasheet_ids
        ]
        runtime_rows = [
            row
            for row in payload["detachment_faction_support_rows"]
            if row["content_id"] in visible_runtime_content_ids
        ]
        public_payload["mustering_support_rows"] = mustering_rows
        public_payload["datasheet_support_rows"] = datasheet_rows
        public_payload["detachment_faction_support_rows"] = runtime_rows
        visible_statuses = [
            *(row["status"] for row in mustering_rows),
            *(row["status"] for row in datasheet_rows),
            *(row["status"] for row in runtime_rows),
        ]
        public_payload["overall_status"] = _public_legacy_support_status(visible_statuses)
        public_payload["status_counts"] = {
            "unsupported": visible_statuses.count("unsupported"),
            "playable": visible_statuses.count("playable"),
            "full": visible_statuses.count("full"),
        }
        public_payload["eligible_for_headless_self_play_smoke"] = False
    return validate_json_value(cast(JsonValue, public_payload))


def _required_metadata_string(payload: Mapping[str, JsonValue], *, key: str) -> str:
    value = payload[key]
    if type(value) is not str or not value.strip():
        raise GameLifecycleError("Capability manifest metadata field must be a string.")
    return value


def _public_legacy_support_status(statuses: Sequence[str]) -> str:
    if any(status == "unsupported" for status in statuses):
        return "unsupported"
    if not statuses or any(status == "playable" for status in statuses):
        return "playable"
    if all(status == "full" for status in statuses):
        return "full"
    raise GameLifecycleError("Viewer-scoped legacy support status is invalid.")


def decision_request_hidden_from_context(
    *,
    request: DecisionRequest,
    viewer: ViewerContext,
) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("DecisionRequest redaction requires a DecisionRequest.")
    if type(viewer) is not ViewerContext:
        raise GameLifecycleError("DecisionRequest redaction requires a ViewerContext.")
    if request.decision_type == TACTICAL_SECONDARY_SCORE_DECISION_TYPE:
        return not (viewer.policy.omniscient or viewer.owns_player(request.actor_id))
    return secret_payload_hidden_from_context(
        actor_id=request.actor_id,
        payload=request.payload,
        viewer=viewer,
    )


def decision_request_payload_hidden_from_context(
    *,
    request_payload: Mapping[str, JsonValue],
    viewer: ViewerContext,
) -> bool:
    if type(viewer) is not ViewerContext:
        raise GameLifecycleError("DecisionRequest redaction requires a ViewerContext.")
    actor_id = _optional_string(request_payload, key="actor_id")
    decision_type = _required_string(request_payload, key="decision_type")
    if decision_type == TACTICAL_SECONDARY_SCORE_DECISION_TYPE:
        return not (viewer.policy.omniscient or viewer.owns_player(actor_id))
    return secret_payload_hidden_from_context(
        actor_id=actor_id,
        payload=request_payload["payload"],
        viewer=viewer,
    )


def secret_payload_hidden_from_context(
    *,
    actor_id: str | None,
    payload: JsonValue,
    viewer: ViewerContext,
) -> bool:
    if type(viewer) is not ViewerContext:
        raise GameLifecycleError("Redaction requires a ViewerContext.")
    if viewer.policy.omniscient or viewer.owns_player(actor_id):
        return False
    if not isinstance(payload, dict):
        return False
    secret = payload.get("secret")
    if secret is None:
        return False
    if type(secret) is not bool:
        raise GameLifecycleError("Secret DecisionRequest payload flag must be a bool.")
    return secret


def decision_request_hidden_from_viewer(
    *,
    request: DecisionRequest,
    viewer_player_id: str | None,
) -> bool:
    return decision_request_hidden_from_context(
        request=request,
        viewer=_legacy_viewer_context(viewer_player_id),
    )


def decision_request_payload_hidden_from_viewer(
    *,
    request_payload: Mapping[str, JsonValue],
    viewer_player_id: str | None,
) -> bool:
    return decision_request_payload_hidden_from_context(
        request_payload=request_payload,
        viewer=_legacy_viewer_context(viewer_player_id),
    )


def redacted_decision_type_for_hidden_viewer() -> str:
    return HIDDEN_DECISION_TYPE


def public_decision_request_payload(
    request: DecisionRequest,
    *,
    viewer: ViewerContext,
) -> dict[str, JsonValue]:
    """Project one request through the shared viewer-safe event/pending path."""

    if type(request) is not DecisionRequest:
        raise GameLifecycleError("DecisionRequest redaction requires a DecisionRequest.")
    payload = _public_decision_request_payload(
        validate_json_value(request.to_payload()),
        viewer=viewer,
    )
    payload = _without_internal_model_destruction_authority(payload)
    if not isinstance(payload, dict):
        raise GameLifecycleError("Public DecisionRequest payload must be an object.")
    return payload


def redacted_lifecycle_status(
    status: LifecycleStatus,
    *,
    viewer: ViewerContext,
) -> RedactedLifecycleStatusPayload:
    if type(status) is not LifecycleStatus:
        raise GameLifecycleError("Lifecycle status redaction requires LifecycleStatus.")
    decision_request = status.decision_request
    hidden_pending = (
        False
        if decision_request is None
        else decision_request_hidden_from_context(request=decision_request, viewer=viewer)
    )
    metadata_payload = (
        status.payload
        if status.status_kind
        in {
            LifecycleStatusKind.TERMINAL,
            LifecycleStatusKind.INVALID,
            LifecycleStatusKind.UNSUPPORTED,
        }
        else None
    )
    if hidden_pending:
        return {
            "stage": status.stage.value,
            "status_kind": status.status_kind.value,
            "message": None,
            "payload": None,
            "pending_request_id": None,
            "decision_type": HIDDEN_DECISION_TYPE,
            "actor_id": None,
        }
    return {
        "stage": status.stage.value,
        "status_kind": status.status_kind.value,
        "message": status.message,
        "payload": _without_internal_model_destruction_authority(metadata_payload),
        "pending_request_id": None if decision_request is None else decision_request.request_id,
        "decision_type": None if decision_request is None else decision_request.decision_type,
        "actor_id": None if decision_request is None else decision_request.actor_id,
    }


def public_event_record_payload(
    *,
    event_id: str,
    event_type: str,
    payload: JsonValue,
    viewer: ViewerContext,
) -> EventRecordPayload | None:
    if _event_record_hidden_from_context(
        event_type=event_type,
        payload=payload,
        viewer=viewer,
    ):
        return None
    public_payload = _public_event_payload(
        event_type=event_type,
        payload=payload,
        viewer=viewer,
    )
    public_payload = _without_internal_model_destruction_authority(public_payload)
    if _is_generic_hidden_event_payload(public_payload):
        return None
    return cast(
        EventRecordPayload,
        {
            "event_id": event_id,
            "event_type": event_type,
            "payload": public_payload,
        },
    )


def _event_record_hidden_from_context(
    *,
    event_type: str,
    payload: JsonValue,
    viewer: ViewerContext,
) -> bool:
    if event_type in {
        MODEL_LOGICAL_DEATH_RECORDED_EVENT,
        MORTAL_WOUND_APPLICATION_STARTED_EVENT,
        MORTAL_WOUND_MODEL_ALLOCATED_EVENT_TYPE,
    }:
        return True
    if _player_owned_secret_event_hidden_from_context(payload=payload, viewer=viewer):
        return True
    if event_type == "decision_requested":
        request_payload = _json_object("decision_requested payload", payload)
        return decision_request_payload_hidden_from_context(
            request_payload=request_payload,
            viewer=viewer,
        )
    if event_type == "decision_recorded":
        record_payload = _json_object("decision_recorded payload", payload)
        request_payload = _json_object(
            "decision_recorded request payload",
            record_payload["request"],
        )
        return decision_request_payload_hidden_from_context(
            request_payload=request_payload,
            viewer=viewer,
        )
    if event_type == "secondary_mission_choice_recorded":
        event_payload = _json_object("secondary_mission_choice_recorded payload", payload)
        return not (
            viewer.policy.omniscient
            or viewer.owns_player(_required_string(event_payload, key="player_id"))
        )
    if event_type in {
        PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT,
        MISSION_ACTION_OPPORTUNITY_DECLINED_EVENT,
    }:
        event_payload = _json_object(
            f"{event_type} payload",
            payload,
        )
        return not (
            viewer.policy.omniscient
            or viewer.owns_player(_required_string(event_payload, key="player_id"))
        )
    if event_type == PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT:
        event_payload = _json_object(f"{event_type} payload", payload)
        checkpoint = PrimaryMissionBoundaryCheckpoint.from_payload(event_payload["checkpoint"])
        return not (viewer.policy.omniscient or viewer.owns_player(checkpoint.player_id))
    if event_type == _TACTICAL_SECONDARY_SCORE_DECLINED_EVENT_TYPE:
        event_payload = _json_object(f"{event_type} payload", payload)
        return not (
            viewer.policy.omniscient
            or viewer.owns_player(_required_string(event_payload, key="player_id"))
        )
    if event_type in {
        "tactical_secondary_missions_drawn",
        "tactical_secondary_mission_discarded",
        "tactical_secondary_missions_discarded",
        "tactical_secondary_when_drawn_kept",
        "tactical_secondary_when_drawn_discarded",
        "tactical_secondary_when_drawn_shuffled",
        "beacon_unit_selected",
        "burden_of_trust_guard_selected",
        "mission_action_started",
    }:
        event_payload = _json_object(f"{event_type} payload", payload)
        hidden = event_payload.get("hidden")
        if hidden is not None and type(hidden) is not bool:
            raise GameLifecycleError("Hidden player event payload flag must be a bool.")
        return bool(
            hidden is True
            and not viewer.policy.omniscient
            and not viewer.owns_player(_required_string(event_payload, key="player_id"))
        )
    return False


def _player_owned_secret_event_hidden_from_context(
    *,
    payload: JsonValue,
    viewer: ViewerContext,
) -> bool:
    if not isinstance(payload, dict):
        return False
    secret = payload.get("secret")
    if secret is None:
        return False
    if type(secret) is not bool:
        raise GameLifecycleError("Secret event payload flag must be a bool.")
    if secret is False:
        return False
    player_id = _required_string(payload, key="player_id")
    visibility_source = _required_string(payload, key="visibility_source")
    if visibility_source != "declare_battle_formations":
        raise GameLifecycleError("Secret event visibility source is unsupported.")
    return not (viewer.policy.omniscient or viewer.owns_player(player_id))


def _public_event_payload(
    *,
    event_type: str,
    payload: JsonValue,
    viewer: ViewerContext,
) -> JsonValue:
    if event_type == PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT:
        return _public_primary_mission_boundary_checkpoint_payload(payload, viewer=viewer)
    if event_type == PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT:
        return _public_primary_scoring_commit_checkpoint_payload(payload, viewer=viewer)
    if event_type == "decision_requested":
        return _public_decision_request_payload(payload, viewer=viewer)
    if event_type == "decision_recorded":
        return _public_decision_record_payload(payload, viewer=viewer)
    if event_type == "secondary_mission_choice_recorded":
        return _public_secondary_mission_choice_recorded_payload(payload, viewer=viewer)
    if event_type == "tactical_secondary_missions_drawn":
        return _public_tactical_secondary_drawn_payload(payload, viewer=viewer)
    if event_type in {
        "tactical_secondary_mission_discarded",
        "tactical_secondary_missions_discarded",
        "tactical_secondary_when_drawn_kept",
        "tactical_secondary_when_drawn_discarded",
        "tactical_secondary_when_drawn_shuffled",
        "beacon_unit_selected",
        "burden_of_trust_guard_selected",
    }:
        return _public_tactical_secondary_discarded_payload(payload, viewer=viewer)
    if event_type == "mission_action_started":
        return _public_hidden_player_event_payload(
            "mission_action_started",
            payload,
            viewer=viewer,
        )
    if event_type == "tactical_secondary_mission_scored":
        return _public_tactical_secondary_mission_scored_payload(payload, viewer=viewer)
    if event_type == _TACTICAL_SECONDARY_SCORE_DECLINED_EVENT_TYPE:
        return _public_tactical_secondary_mission_score_declined_payload(
            payload,
            viewer=viewer,
        )
    if event_type == "model_destroyed":
        return _public_model_destroyed_payload(payload)
    return validate_json_value(payload)


def _public_primary_mission_boundary_checkpoint_payload(
    payload: JsonValue,
    *,
    viewer: ViewerContext,
) -> JsonValue:
    checkpoint = PrimaryMissionBoundaryCheckpoint.from_payload(payload)
    return _viewer_safe_primary_mission_boundary_checkpoint_payload(
        checkpoint,
        viewer=viewer,
    )


def _viewer_safe_primary_mission_boundary_checkpoint_payload(
    checkpoint: PrimaryMissionBoundaryCheckpoint,
    *,
    viewer: ViewerContext,
) -> JsonValue:
    if type(checkpoint) is not PrimaryMissionBoundaryCheckpoint:
        raise GameLifecycleError("Checkpoint redaction requires a typed checkpoint.")
    if viewer.policy.omniscient:
        return checkpoint.to_payload()
    if not viewer.owns_player(checkpoint.player_id):
        raise GameLifecycleError(
            "Primary mission boundary checkpoint viewer does not own the checkpoint."
        )
    public_payload = checkpoint.to_payload()
    public_payload.pop("active_secondary_mission_card_jsons", None)
    public_payload.pop("completed_mission_action_state_jsons", None)
    public_payload.pop("primary_unit_destruction_state_jsons", None)
    public_payload.pop("starting_strength_record_jsons", None)
    public_payload.pop("checkpoint_id")
    public_payload.pop("checkpoint_hash")
    digest = canonical_payload_sha256(public_payload)
    public_payload["checkpoint_id"] = f"primary-mission-boundary:{digest}"
    public_payload["checkpoint_hash"] = digest
    return validate_json_value(public_payload)


def _public_primary_scoring_commit_checkpoint_payload(
    payload: JsonValue,
    *,
    viewer: ViewerContext,
) -> JsonValue:
    event_payload = _json_object("primary scoring-commit checkpoint payload", payload)
    checkpoint = PrimaryMissionBoundaryCheckpoint.from_payload(event_payload["checkpoint"])
    public_payload = dict(event_payload)
    public_payload["checkpoint"] = _viewer_safe_primary_mission_boundary_checkpoint_payload(
        checkpoint,
        viewer=viewer,
    )
    return validate_json_value(public_payload)


def _public_tactical_secondary_mission_scored_payload(
    payload: JsonValue,
    *,
    viewer: ViewerContext,
) -> JsonValue:
    event_payload = _json_object("tactical secondary scored payload", payload)
    player_id = _required_string(event_payload, key="player_id")
    transaction = VictoryPointTransaction.from_payload(
        cast(VictoryPointTransactionPayload, event_payload["victory_point_transaction"])
    )
    card = SecondaryMissionCardState.from_payload(
        cast(SecondaryMissionCardStatePayload, event_payload["secondary_mission_card_state"])
    )
    if transaction.player_id != player_id or card.player_id != player_id:
        raise GameLifecycleError("Tactical secondary scored event player drifted.")
    if viewer.policy.omniscient:
        return validate_json_value(event_payload)
    domain_viewer_player_id = viewer.viewer_player_id or "redacted-viewer"
    public_payload = dict(event_payload)
    public_payload["victory_point_transaction"] = public_victory_point_transaction_payload(
        transaction,
        viewer=viewer,
        domain_viewer_player_id=domain_viewer_player_id,
        secondary_mission_choices_revealed=True,
    )
    public_payload["secondary_mission_card_state"] = card.to_public_payload(
        viewer_player_id=domain_viewer_player_id,
        secondary_mission_choices_revealed=True,
    )
    if viewer.owns_player(player_id):
        public_payload["achievement_context"] = (
            _public_tactical_secondary_achievement_context_payload(
                event_payload["achievement_context"]
            )
        )
    else:
        public_payload.pop("achievement_context", None)
    return validate_json_value(public_payload)


def _public_tactical_secondary_mission_score_declined_payload(
    payload: JsonValue,
    *,
    viewer: ViewerContext,
) -> JsonValue:
    event_payload = _json_object("tactical secondary score-declined payload", payload)
    player_id = _required_string(event_payload, key="player_id")
    if viewer.policy.omniscient:
        return validate_json_value(event_payload)
    if not viewer.owns_player(player_id):
        raise GameLifecycleError("Tactical secondary score-declined viewer does not own the event.")
    card = SecondaryMissionCardState.from_payload(
        cast(SecondaryMissionCardStatePayload, event_payload["secondary_mission_card_state"])
    )
    if card.player_id != player_id:
        raise GameLifecycleError("Tactical secondary score-declined card player drifted.")
    public_payload = dict(event_payload)
    public_payload["achievement_context"] = _public_tactical_secondary_achievement_context_payload(
        event_payload["achievement_context"]
    )
    return validate_json_value(public_payload)


def _public_tactical_secondary_achievement_context_payload(payload: JsonValue) -> JsonValue:
    context = _json_object("tactical secondary achievement context", payload)
    return validate_json_value(_without_internal_secondary_authority_commitments(context))


def _without_internal_secondary_authority_commitments(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return {
            key: _without_internal_secondary_authority_commitments(nested)
            for key, nested in value.items()
            if key not in _INTERNAL_SECONDARY_AUTHORITY_COMMITMENT_KEYS
        }
    if isinstance(value, list):
        return [_without_internal_secondary_authority_commitments(nested) for nested in value]
    return value


def _without_internal_model_destruction_authority(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return {
            key: _without_internal_model_destruction_authority(nested)
            for key, nested in value.items()
            if key not in _INTERNAL_MODEL_DESTRUCTION_AUTHORITY_KEYS
        }
    if isinstance(value, list):
        return [_without_internal_model_destruction_authority(nested) for nested in value]
    return value


def _public_model_destroyed_payload(
    payload: JsonValue,
) -> JsonValue:
    event_payload = _json_object("model_destroyed payload", payload)
    _required_string(event_payload, key="destroying_player_id")
    for field_name in (
        "source_rules_unit_objective_proximity_witness",
        "destroyed_rules_unit_objective_proximity_witness",
    ):
        if field_name not in event_payload:
            raise GameLifecycleError(f"model_destroyed payload is missing {field_name}.")
    raw_source_witness = event_payload["source_rules_unit_objective_proximity_witness"]
    if raw_source_witness is not None:
        RulesUnitObjectiveProximityWitness.from_payload(raw_source_witness)
    raw_destroyed_witness = event_payload["destroyed_rules_unit_objective_proximity_witness"]
    if raw_destroyed_witness is None:
        raise GameLifecycleError(
            "model_destroyed payload requires destroyed objective proximity evidence."
        )
    RulesUnitObjectiveProximityWitness.from_payload(raw_destroyed_witness)
    return validate_json_value(event_payload)


def _public_decision_request_payload(
    payload: JsonValue,
    *,
    viewer: ViewerContext,
) -> JsonValue:
    request_payload = _json_object("decision_requested payload", payload)
    if decision_request_payload_hidden_from_context(
        request_payload=request_payload,
        viewer=viewer,
    ):
        return _redacted_request_payload()
    if (
        not viewer.policy.omniscient
        and _required_string(request_payload, key="decision_type")
        == TACTICAL_SECONDARY_SCORE_DECISION_TYPE
    ):
        return _public_tactical_secondary_score_request_payload(request_payload)
    return validate_json_value(request_payload)


def _public_decision_record_payload(
    payload: JsonValue,
    *,
    viewer: ViewerContext,
) -> JsonValue:
    record_payload = _json_object("decision_recorded payload", payload)
    request_payload = _json_object("decision_recorded request payload", record_payload["request"])
    if decision_request_payload_hidden_from_context(
        request_payload=request_payload,
        viewer=viewer,
    ):
        return {
            "record_id": "hidden-record",
            "request": _redacted_request_payload(),
            "result": _redacted_result_payload(),
        }
    if (
        not viewer.policy.omniscient
        and _required_string(request_payload, key="decision_type")
        == TACTICAL_SECONDARY_SCORE_DECISION_TYPE
    ):
        public_record = dict(record_payload)
        public_record["request"] = _public_tactical_secondary_score_request_payload(request_payload)
        result_payload = _json_object(
            "decision_recorded tactical score result payload",
            record_payload["result"],
        )
        public_result = dict(result_payload)
        public_result["payload"] = _without_internal_secondary_authority_commitments(
            result_payload["payload"]
        )
        public_record["result"] = public_result
        return validate_json_value(public_record)
    return validate_json_value(record_payload)


def _public_tactical_secondary_score_request_payload(
    request_payload: Mapping[str, JsonValue],
) -> JsonValue:
    public_request = dict(request_payload)
    public_request["payload"] = _without_internal_secondary_authority_commitments(
        request_payload["payload"]
    )
    raw_options = request_payload.get("options")
    if not isinstance(raw_options, list):
        raise GameLifecycleError("Tactical secondary score request options must be a list.")
    public_options: list[JsonValue] = []
    for raw_option in raw_options:
        option = _json_object("tactical secondary score option", raw_option)
        if "payload" not in option:
            raise GameLifecycleError("Tactical secondary score option lacks a payload.")
        public_option = dict(option)
        public_option["payload"] = _without_internal_secondary_authority_commitments(
            option["payload"]
        )
        public_options.append(validate_json_value(public_option))
    public_request["options"] = public_options
    return validate_json_value(public_request)


def _public_secondary_mission_choice_recorded_payload(
    payload: JsonValue,
    *,
    viewer: ViewerContext,
) -> JsonValue:
    choice_payload = _json_object("secondary_mission_choice_recorded payload", payload)
    player_id = _required_string(choice_payload, key="player_id")
    if viewer.policy.omniscient or viewer.owns_player(player_id):
        return validate_json_value(choice_payload)
    return {
        "game_id": _required_string(choice_payload, key="game_id"),
        "selected": True,
        "hidden": True,
    }


def _public_tactical_secondary_drawn_payload(
    payload: JsonValue,
    *,
    viewer: ViewerContext,
) -> JsonValue:
    return _public_hidden_player_event_payload(
        "tactical_secondary_missions_drawn",
        payload,
        viewer=viewer,
    )


def _public_tactical_secondary_discarded_payload(
    payload: JsonValue,
    *,
    viewer: ViewerContext,
) -> JsonValue:
    return _public_hidden_player_event_payload(
        "tactical_secondary_mission_discarded",
        payload,
        viewer=viewer,
    )


def _public_hidden_player_event_payload(
    event_name: str,
    payload: JsonValue,
    *,
    viewer: ViewerContext,
) -> JsonValue:
    event_payload = _json_object(f"{event_name} payload", payload)
    player_id = _required_string(event_payload, key="player_id")
    hidden = event_payload.get("hidden")
    if hidden is not None and type(hidden) is not bool:
        raise GameLifecycleError("Hidden player event payload flag must be a bool.")
    if viewer.policy.omniscient or viewer.owns_player(player_id) or hidden is not True:
        return validate_json_value(event_payload)
    return {
        "game_id": _required_string(event_payload, key="game_id"),
        "hidden": True,
        "hidden_event": True,
    }


def _is_generic_hidden_event_payload(payload: JsonValue) -> bool:
    if not isinstance(payload, dict):
        return False
    hidden_event = payload.get("hidden_event")
    if hidden_event is None:
        return False
    if type(hidden_event) is not bool:
        raise GameLifecycleError("Hidden event payload flag must be a bool.")
    return hidden_event


def _redacted_request_payload() -> JsonValue:
    return {
        "request_id": HIDDEN_REQUEST_ID,
        "decision_type": HIDDEN_DECISION_TYPE,
        "actor_id": None,
        "secret": True,
        "hidden": True,
    }


def _redacted_result_payload() -> JsonValue:
    return {
        "result_id": HIDDEN_RESULT_ID,
        "request_id": HIDDEN_REQUEST_ID,
        "decision_type": HIDDEN_DECISION_TYPE,
        "actor_id": None,
        "secret": True,
        "hidden": True,
    }


def _legacy_viewer_context(viewer_player_id: str | None) -> ViewerContext:
    if viewer_player_id is None:
        return ViewerContext.for_player("redacted-viewer")
    return ViewerContext.for_player(viewer_player_id)


def _json_object(field_name: str, value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    return value


def _required_string(payload: Mapping[str, JsonValue], *, key: str) -> str:
    value = payload[key]
    if type(value) is not str:
        raise GameLifecycleError(f"Redacted payload key must be a string: {key}.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Redacted payload key must not be empty: {key}.")
    return stripped


def _optional_string(payload: Mapping[str, JsonValue], *, key: str) -> str | None:
    value = payload[key]
    if value is None:
        return None
    if type(value) is not str:
        raise GameLifecycleError(f"Redacted payload key must be a string or null: {key}.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Redacted payload key must not be empty: {key}.")
    return stripped


def _public_error_string(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Public {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Public {field_name} must not be empty.")
    return stripped
