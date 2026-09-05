from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldTransitionBatch,
    ModelDisplacementKind,
    ModelDisplacementRecord,
    ModelPlacementRecord,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionRequest,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage, SetupStep
from warhammer40k_core.engine.prebattle import (
    SCOUT_MOVE_PROPOSAL_KIND,
    SCOUT_RESERVE_SETUP_PROPOSAL_KIND,
    SELECT_PREBATTLE_ACTION_DECISION_TYPE,
    SUBMIT_SCOUT_MOVE_DECISION_TYPE,
    SUBMIT_SCOUT_RESERVE_SETUP_DECISION_TYPE,
    PreBattlePlacementProposal,
    PreBattlePlacementProposalPayload,
    PreBattleProposalRequest,
    ScoutMoveProposal,
    ScoutMoveProposalPayload,
    dedicated_transport_scout_move_candidates_for_player,
    scout_move_candidates_for_player,
    scout_reserve_setup_candidates_for_player,
)
from warhammer40k_core.engine.prebattle_alternation import (
    PREBATTLE_ALTERNATION_DECISION_TYPES,
)
from warhammer40k_core.engine.prebattle_records import (
    PreBattleActionKind,
    PreBattleActionRecord,
    PreBattleAlternationCursor,
)
from warhammer40k_core.engine.scout_abilities import CORE_SCOUTS_SOURCE_RULE_ID
from warhammer40k_core.geometry.pathing import PathWitness

_COMPLETION_OPTION_ID = PreBattleActionKind.COMPLETE_PREBATTLE_ACTIONS.value
_UNIT_ACTION_DECISION_TYPE_BY_KIND = {
    PreBattleActionKind.SCOUT_MOVE: SUBMIT_SCOUT_MOVE_DECISION_TYPE,
    PreBattleActionKind.DEDICATED_TRANSPORT_SCOUT_MOVE: SUBMIT_SCOUT_MOVE_DECISION_TYPE,
    PreBattleActionKind.SCOUT_RESERVE_SETUP: SUBMIT_SCOUT_RESERVE_SETUP_DECISION_TYPE,
}
_RESOLUTION_PAYLOAD_KEYS = frozenset(
    {
        "proposal",
        "is_valid",
        "violations",
        "coherency_result",
        "transition_batch",
        "removal_batch",
        "placement_batch",
    }
)
_COMPLETION_RESULT_PAYLOAD_KEYS = frozenset(
    {
        "submission_kind",
        "game_id",
        "setup_step",
        "player_id",
        "action_kind",
        "ruleset_descriptor_hash",
    }
)
_COMPLETION_ACTION_PAYLOAD_KEYS = frozenset({"game_id", "setup_step", "player_id"})
_SELECTION_REQUEST_PAYLOAD_KEYS = frozenset(
    {"game_id", "setup_step", "player_id", "ruleset_descriptor_hash"}
)
_UNIT_SELECTION_RESULT_PAYLOAD_KEYS = frozenset(
    {
        "submission_kind",
        "game_id",
        "player_id",
        "setup_step",
        "unit_instance_id",
        "is_attached_rules_unit",
        "component_unit_instance_ids",
        "model_instance_ids",
        "deployment_zone_ids",
        "mission_pack_id",
        "deployment_map_id",
        "terrain_layout_id",
        "ruleset_descriptor_hash",
        "action_kind",
        "source_rule_id",
        "proposal_kind",
        "scout_distance_inches",
        "scout_ability_instances",
    }
)
_PROPOSAL_REQUEST_PAYLOAD_KEYS = frozenset(
    {
        "request_id",
        "decision_type",
        "actor_id",
        "game_id",
        "setup_step",
        "player_id",
        "unit_instance_id",
        "component_unit_instance_ids",
        "model_instance_ids",
        "proposal_kind",
        "action_kind",
        "source_rule_id",
        "placement_kind",
        "scout_distance_inches",
        "deployment_zone_ids",
        "legal_deployment_zones",
        "mission_setup",
        "ruleset_descriptor_hash",
        "source_decision_request_id",
        "source_decision_result_id",
        "context",
    }
)
_SCOUT_MOVE_PROPOSAL_PAYLOAD_KEYS = frozenset(
    {
        "proposal_request_id",
        "proposal_kind",
        "game_id",
        "ruleset_descriptor_hash",
        "setup_step",
        "player_id",
        "unit_instance_id",
        "action_kind",
        "source_rule_id",
        "scout_distance_inches",
        "witness",
        "context",
    }
)
_SCOUT_RESERVE_PROPOSAL_PAYLOAD_KEYS = frozenset(
    {
        "proposal_request_id",
        "proposal_kind",
        "game_id",
        "ruleset_descriptor_hash",
        "setup_step",
        "player_id",
        "unit_instance_id",
        "action_kind",
        "source_rule_id",
        "placement_kind",
        "model_placements",
        "context",
    }
)


@dataclass(frozen=True, slots=True)
class _VerifiedPreBattleAction:
    action: PreBattleActionRecord
    decision_index: int


def validate_prebattle_alternation_restore(
    *,
    state: GameState,
    army_catalog: ArmyCatalog | None,
    decision_records: tuple[DecisionRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> None:
    cursor = state.prebattle_alternation_cursor
    action_records = tuple(
        record
        for record in state.prebattle_action_records
        if record.setup_step is SetupStep.RESOLVE_PREBATTLE_ACTIONS
    )
    pending_requests = tuple(
        request
        for request in pending_decision_requests
        if request.decision_type in PREBATTLE_ALTERNATION_DECISION_TYPES
    )
    if cursor is None:
        if action_records or pending_requests:
            raise GameLifecycleError("Restored pre-battle state requires an alternation cursor.")
        return
    if army_catalog is not None and type(army_catalog) is not ArmyCatalog:
        raise GameLifecycleError(
            "Restored pre-battle alternation integrity requires an ArmyCatalog."
        )
    if army_catalog is None and pending_requests:
        raise GameLifecycleError(
            "Restored pending pre-battle alternation integrity requires an ArmyCatalog."
        )
    if len(pending_requests) > 1:
        raise GameLifecycleError(
            "Restored pre-battle alternation has multiple authoritative pending requests."
        )
    if pending_requests and pending_requests[0].actor_id != cursor.next_player_id:
        raise GameLifecycleError(
            "Restored pending decision actor drifted from the pre-battle alternation cursor."
        )

    verified = _verified_action_records(
        state=state,
        action_records=action_records,
        decision_records=decision_records,
    )
    _validate_terminal_decision_ownership(
        verified=verified,
        decision_records=decision_records,
    )
    _validate_derived_cursor(
        state=state,
        army_catalog=army_catalog,
        cursor=cursor,
        verified=verified,
        pending_request=None if not pending_requests else pending_requests[0],
    )


def _verified_action_records(
    *,
    state: GameState,
    action_records: tuple[PreBattleActionRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> tuple[_VerifiedPreBattleAction, ...]:
    verified: list[_VerifiedPreBattleAction] = []
    claimed_decision_indexes: set[int] = set()
    claimed_selection_indexes: set[int] = set()
    for action in action_records:
        decision_index, decision = _unique_decision_for_identity(
            decision_records=decision_records,
            request_id=action.request_id,
            result_id=action.result_id,
            identity_name="pre-battle action",
        )
        if decision_index in claimed_decision_indexes:
            raise GameLifecycleError(
                "Restored pre-battle actions must have one-to-one authoritative decisions."
            )
        claimed_decision_indexes.add(decision_index)
        if (
            decision.request.actor_id != action.player_id
            or decision.result.actor_id != action.player_id
        ):
            _raise_semantic_drift("action actor does not match its authoritative decision")
        if action.action_kind is PreBattleActionKind.COMPLETE_PREBATTLE_ACTIONS:
            _validate_completion_action(state=state, action=action, decision=decision)
            selection_decision_index = decision_index
        elif action.action_kind in _UNIT_ACTION_DECISION_TYPE_BY_KIND:
            selection_decision_index = _validate_unit_action(
                state=state,
                action=action,
                action_decision=decision,
                action_decision_index=decision_index,
                decision_records=decision_records,
            )
        else:
            _raise_semantic_drift("action kind is not a supported Scout pre-battle action")
        if selection_decision_index in claimed_selection_indexes:
            raise GameLifecycleError(
                "Restored pre-battle actions must have one-to-one unit selections."
            )
        claimed_selection_indexes.add(selection_decision_index)
        verified.append(
            _VerifiedPreBattleAction(
                action=action,
                decision_index=decision_index,
            )
        )
    return tuple(verified)


def _validate_completion_action(
    *,
    state: GameState,
    action: PreBattleActionRecord,
    decision: DecisionRecord,
) -> None:
    request_payload = _closed_json_object(
        decision.request.payload,
        field_name="pre-battle completion request payload",
        expected_keys=_SELECTION_REQUEST_PAYLOAD_KEYS,
    )
    result_payload = _closed_json_object(
        decision.result.payload,
        field_name="pre-battle completion result payload",
        expected_keys=_COMPLETION_RESULT_PAYLOAD_KEYS,
    )
    action_payload = _closed_json_object(
        action.payload,
        field_name="pre-battle completion action payload",
        expected_keys=_COMPLETION_ACTION_PAYLOAD_KEYS,
    )
    non_completion_options = tuple(
        option for option in decision.request.options if option.option_id != _COMPLETION_OPTION_ID
    )
    expected_result_payload: dict[str, JsonValue] = {
        "submission_kind": SELECT_PREBATTLE_ACTION_DECISION_TYPE,
        "game_id": state.game_id,
        "setup_step": SetupStep.RESOLVE_PREBATTLE_ACTIONS.value,
        "player_id": action.player_id,
        "action_kind": PreBattleActionKind.COMPLETE_PREBATTLE_ACTIONS.value,
        "ruleset_descriptor_hash": request_payload.get("ruleset_descriptor_hash"),
    }
    expected_action_payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "setup_step": SetupStep.RESOLVE_PREBATTLE_ACTIONS.value,
        "player_id": action.player_id,
    }
    expected_request_payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "setup_step": SetupStep.RESOLVE_PREBATTLE_ACTIONS.value,
        "player_id": action.player_id,
        "ruleset_descriptor_hash": request_payload["ruleset_descriptor_hash"],
    }
    if (
        decision.request.decision_type != SELECT_PREBATTLE_ACTION_DECISION_TYPE
        or decision.result.selected_option_id != _COMPLETION_OPTION_ID
        or not non_completion_options
        or request_payload != expected_request_payload
        or result_payload != expected_result_payload
        or action.unit_instance_id is not None
        or action.source_rule_id != CORE_SCOUTS_SOURCE_RULE_ID
        or action_payload != expected_action_payload
    ):
        _raise_semantic_drift("completion action does not match its selected completion option")


def _validate_unit_action(
    *,
    state: GameState,
    action: PreBattleActionRecord,
    action_decision: DecisionRecord,
    action_decision_index: int,
    decision_records: tuple[DecisionRecord, ...],
) -> int:
    expected_decision_type = _UNIT_ACTION_DECISION_TYPE_BY_KIND[action.action_kind]
    if (
        action_decision.request.decision_type != expected_decision_type
        or action_decision.result.selected_option_id != PARAMETERIZED_DECISION_OPTION_ID
    ):
        _raise_semantic_drift("unit action does not match its proposal decision type")
    request_envelope = _closed_json_object(
        action_decision.request.payload,
        field_name="pre-battle proposal DecisionRequest payload",
        expected_keys=frozenset({"proposal_request"}),
    )
    _closed_json_object(
        request_envelope["proposal_request"],
        field_name="pre-battle proposal request context",
        expected_keys=_PROPOSAL_REQUEST_PAYLOAD_KEYS,
    )
    try:
        request_context = PreBattleProposalRequest.from_decision_request_payload(
            action_decision.request.payload
        )
    except (KeyError, TypeError) as exc:
        raise GameLifecycleError(
            "Restored pre-battle action semantic drift: malformed proposal request."
        ) from exc
    result_payload = _closed_json_object(
        action_decision.result.payload,
        field_name="pre-battle proposal result payload",
        expected_keys=(
            _SCOUT_MOVE_PROPOSAL_PAYLOAD_KEYS
            if expected_decision_type == SUBMIT_SCOUT_MOVE_DECISION_TYPE
            else _SCOUT_RESERVE_PROPOSAL_PAYLOAD_KEYS
        ),
    )
    try:
        proposal: ScoutMoveProposal | PreBattlePlacementProposal
        if expected_decision_type == SUBMIT_SCOUT_MOVE_DECISION_TYPE:
            proposal = ScoutMoveProposal.from_payload(
                cast(ScoutMoveProposalPayload, result_payload)
            )
        else:
            proposal = PreBattlePlacementProposal.from_payload(
                cast(PreBattlePlacementProposalPayload, result_payload)
            )
    except (KeyError, TypeError) as exc:
        raise GameLifecycleError(
            "Restored pre-battle action semantic drift: malformed proposal result."
        ) from exc
    if proposal.request_drift_violations(request_context):
        _raise_semantic_drift("proposal result drifted from its authoritative proposal request")
    if (
        request_context.request_id != action_decision.request.request_id
        or request_context.decision_type != action_decision.request.decision_type
        or request_context.actor_id != action_decision.request.actor_id
        or request_context.game_id != state.game_id
        or request_context.setup_step is not SetupStep.RESOLVE_PREBATTLE_ACTIONS
        or request_context.player_id != action.player_id
        or request_context.action_kind is not action.action_kind
        or request_context.unit_instance_id != action.unit_instance_id
        or request_context.source_rule_id != action.source_rule_id
        or proposal.context != request_context.context
    ):
        _raise_semantic_drift("action identity drifted from its proposal request")

    selection_index, selection_decision = _unique_decision_for_identity(
        decision_records=decision_records,
        request_id=request_context.source_decision_request_id,
        result_id=request_context.source_decision_result_id,
        identity_name="pre-battle unit selection",
    )
    if selection_index >= action_decision_index:
        _raise_semantic_drift("proposal decision does not follow its unit selection")
    _validate_unit_selection(
        request_context=request_context,
        selection_decision=selection_decision,
    )
    _validate_resolution_payload(
        action=action,
        proposal=proposal,
    )
    return selection_index


def _validate_unit_selection(
    *,
    request_context: PreBattleProposalRequest,
    selection_decision: DecisionRecord,
) -> None:
    selection_request_payload = _closed_json_object(
        selection_decision.request.payload,
        field_name="pre-battle unit selection request payload",
        expected_keys=_SELECTION_REQUEST_PAYLOAD_KEYS,
    )
    selection_payload = _closed_json_object(
        selection_decision.result.payload,
        field_name="pre-battle unit selection result payload",
        expected_keys=_UNIT_SELECTION_RESULT_PAYLOAD_KEYS,
    )
    expected_option_id = f"{request_context.action_kind.value}:{request_context.unit_instance_id}"
    expected_proposal_kind = (
        SCOUT_RESERVE_SETUP_PROPOSAL_KIND
        if request_context.action_kind is PreBattleActionKind.SCOUT_RESERVE_SETUP
        else SCOUT_MOVE_PROPOSAL_KIND
    )
    expected_values: dict[str, JsonValue] = {
        "submission_kind": SELECT_PREBATTLE_ACTION_DECISION_TYPE,
        "game_id": request_context.game_id,
        "setup_step": request_context.setup_step.value,
        "player_id": request_context.player_id,
        "unit_instance_id": request_context.unit_instance_id,
        "component_unit_instance_ids": list(request_context.component_unit_instance_ids),
        "model_instance_ids": list(request_context.model_instance_ids),
        "deployment_zone_ids": [
            zone.deployment_zone_id for zone in request_context.deployment_zones
        ],
        "mission_pack_id": request_context.mission_setup.mission_pack_id,
        "deployment_map_id": request_context.mission_setup.deployment_map_id,
        "terrain_layout_id": request_context.mission_setup.terrain_layout_id,
        "ruleset_descriptor_hash": request_context.ruleset_descriptor_hash,
        "action_kind": request_context.action_kind.value,
        "source_rule_id": request_context.source_rule_id,
        "proposal_kind": expected_proposal_kind,
        "is_attached_rules_unit": (request_context.context or {}).get("is_attached_rules_unit"),
    }
    if request_context.action_kind is not PreBattleActionKind.SCOUT_RESERVE_SETUP:
        expected_values["scout_distance_inches"] = request_context.scout_distance_inches
    expected_request_values: dict[str, JsonValue] = {
        "game_id": request_context.game_id,
        "setup_step": request_context.setup_step.value,
        "player_id": request_context.player_id,
        "ruleset_descriptor_hash": request_context.ruleset_descriptor_hash,
    }
    if (
        selection_decision.request.decision_type != SELECT_PREBATTLE_ACTION_DECISION_TYPE
        or selection_decision.request.actor_id != request_context.player_id
        or selection_decision.result.actor_id != request_context.player_id
        or selection_decision.result.selected_option_id != expected_option_id
        or selection_request_payload != expected_request_values
        or any(selection_payload.get(key) != value for key, value in expected_values.items())
    ):
        _raise_semantic_drift("proposal does not match its selected Scout unit option")


def _validate_resolution_payload(
    *,
    action: PreBattleActionRecord,
    proposal: ScoutMoveProposal | PreBattlePlacementProposal,
) -> None:
    resolution_payload = _closed_json_object(
        action.payload,
        field_name="pre-battle unit action resolution payload",
        expected_keys=_RESOLUTION_PAYLOAD_KEYS,
    )
    if (
        resolution_payload.get("proposal") != proposal.to_payload()
        or resolution_payload.get("is_valid") is not True
        or resolution_payload.get("violations") != []
        or resolution_payload.get("transition_batch")
        != _expected_transition_batch(action=action, proposal=proposal).to_payload()
        or resolution_payload.get("removal_batch") is not None
        or resolution_payload.get("placement_batch") is not None
    ):
        _raise_semantic_drift("unit action payload does not match its accepted proposal result")


def _expected_transition_batch(
    *,
    action: PreBattleActionRecord,
    proposal: ScoutMoveProposal | PreBattlePlacementProposal,
) -> BattlefieldTransitionBatch:
    if type(proposal) is ScoutMoveProposal:
        return BattlefieldTransitionBatch(
            displacements=tuple(
                ModelDisplacementRecord(
                    model_instance_id=model_instance_id,
                    displacement_kind=ModelDisplacementKind.SCOUT_MOVE,
                    start_pose=proposal.witness.poses_for_model(model_instance_id)[0],
                    end_pose=proposal.witness.final_pose_for_model(model_instance_id),
                    path_witness=PathWitness.for_paths(
                        (
                            (
                                model_instance_id,
                                proposal.witness.poses_for_model(model_instance_id),
                            ),
                        )
                    ),
                    source_phase=None,
                    source_step=SetupStep.RESOLVE_PREBATTLE_ACTIONS.value,
                    source_rule_id=action.source_rule_id,
                    source_event_id=action.result_id,
                )
                for model_instance_id in proposal.witness.model_ids()
                if proposal.witness.poses_for_model(model_instance_id)[0]
                != proposal.witness.final_pose_for_model(model_instance_id)
            )
        )
    placement_proposal = cast(PreBattlePlacementProposal, proposal)
    return BattlefieldTransitionBatch(
        placements=tuple(
            ModelPlacementRecord(
                model_instance_id=placement.model_instance_id,
                placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
                pose=placement.pose,
                source_phase=None,
                source_step=SetupStep.RESOLVE_PREBATTLE_ACTIONS.value,
                source_rule_id=action.source_rule_id,
                source_event_id=action.result_id,
            )
            for placement in placement_proposal.model_placements
        )
    )


def _validate_terminal_decision_ownership(
    *,
    verified: tuple[_VerifiedPreBattleAction, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    claimed_indexes = {record.decision_index for record in verified}
    terminal_indexes = {
        index
        for index, decision in enumerate(decision_records)
        if decision.request.decision_type
        in {SUBMIT_SCOUT_MOVE_DECISION_TYPE, SUBMIT_SCOUT_RESERVE_SETUP_DECISION_TYPE}
        or (
            decision.request.decision_type == SELECT_PREBATTLE_ACTION_DECISION_TYPE
            and decision.result.selected_option_id == _COMPLETION_OPTION_ID
        )
    }
    if claimed_indexes != terminal_indexes:
        raise GameLifecycleError(
            "Restored pre-battle actions must own every terminal Scout decision one-to-one."
        )


def _validate_derived_cursor(
    *,
    state: GameState,
    army_catalog: ArmyCatalog | None,
    cursor: PreBattleAlternationCursor,
    verified: tuple[_VerifiedPreBattleAction, ...],
    pending_request: DecisionRequest | None,
) -> None:
    unresolved_player_ids: set[str]
    if army_catalog is not None and _is_live_prebattle_window(state):
        live_prebattle_window = True
        unresolved_player_ids = _current_unresolved_player_ids(
            state=state,
            army_catalog=army_catalog,
        )
    else:
        live_prebattle_window = False
        unresolved_player_ids = set()
    derived = PreBattleAlternationCursor.start(
        game_id=state.game_id,
        ordered_player_ids=state.turn_order,
    )
    completed_player_ids: set[str] = set()
    previous_decision_index = -1
    for action_index, verified_action in enumerate(verified):
        action = verified_action.action
        if verified_action.decision_index <= previous_decision_index:
            raise GameLifecycleError(
                "Restored pre-battle action order drifted from authoritative decision order."
            )
        previous_decision_index = verified_action.decision_index
        if action.player_id in completed_player_ids:
            raise GameLifecycleError(
                "Restored pre-battle action follows that player's completion decision."
            )
        remaining_player_ids = {
            later.action.player_id for later in verified[action_index:]
        } | unresolved_player_ids
        expected_player_id = _next_unresolved_player_id(
            cursor=derived,
            unresolved_player_ids=remaining_player_ids - completed_player_ids,
        )
        if action.player_id != expected_player_id:
            raise GameLifecycleError(
                "Restored pre-battle cursor transition drifted from verified action order."
            )
        derived = derived.aligned_to(expected_player_id).after_action(action)
        if action.action_kind is PreBattleActionKind.COMPLETE_PREBATTLE_ACTIONS:
            completed_player_ids.add(action.player_id)

    final_player_id: str | None = None
    if live_prebattle_window:
        final_player_id = _next_unresolved_player_id(
            cursor=derived,
            unresolved_player_ids=unresolved_player_ids - completed_player_ids,
        )
        if final_player_id is not None and pending_request is None:
            raise GameLifecycleError(
                "Restored pre-battle cursor has an unresolved player without a pending decision."
            )
        if pending_request is not None and pending_request.actor_id != final_player_id:
            raise GameLifecycleError(
                "Restored pending decision actor drifted from the derived pre-battle cursor."
            )
    elif pending_request is not None:
        raise GameLifecycleError(
            "Completed pre-battle alternation must not retain a pending Scout decision."
        )
    derived = derived.aligned_to(final_player_id)
    if cursor != derived:
        raise GameLifecycleError(
            "Restored pre-battle cursor drifted from its verified action transitions."
        )


def _current_unresolved_player_ids(
    *,
    state: GameState,
    army_catalog: ArmyCatalog,
) -> set[str]:
    unresolved: set[str] = set()
    for player_id in state.player_ids:
        if (
            scout_reserve_setup_candidates_for_player(
                state=state,
                army_catalog=army_catalog,
                player_id=player_id,
            )
            or scout_move_candidates_for_player(
                state=state,
                army_catalog=army_catalog,
                player_id=player_id,
            )
            or dedicated_transport_scout_move_candidates_for_player(
                state=state,
                army_catalog=army_catalog,
                player_id=player_id,
            )
        ):
            unresolved.add(player_id)
    return unresolved


def _is_live_prebattle_window(state: GameState) -> bool:
    return (
        state.stage is GameLifecycleStage.SETUP
        and state.current_setup_step is SetupStep.RESOLVE_PREBATTLE_ACTIONS
    )


def _next_unresolved_player_id(
    *,
    cursor: PreBattleAlternationCursor,
    unresolved_player_ids: set[str],
) -> str | None:
    if cursor.next_player_id is None:
        return None
    start_index = cursor.ordered_player_ids.index(cursor.next_player_id)
    for offset in range(len(cursor.ordered_player_ids)):
        player_id = cursor.ordered_player_ids[
            (start_index + offset) % len(cursor.ordered_player_ids)
        ]
        if player_id in unresolved_player_ids:
            return player_id
    return None


def _unique_decision_for_identity(
    *,
    decision_records: tuple[DecisionRecord, ...],
    request_id: str,
    result_id: str,
    identity_name: str,
) -> tuple[int, DecisionRecord]:
    request_matches = tuple(
        (index, decision)
        for index, decision in enumerate(decision_records)
        if decision.request.request_id == request_id
    )
    result_matches = tuple(
        (index, decision)
        for index, decision in enumerate(decision_records)
        if decision.result.result_id == result_id
    )
    if len(request_matches) != 1 or len(result_matches) != 1:
        raise GameLifecycleError(
            f"Restored {identity_name} requires unique authoritative request/result ownership."
        )
    if request_matches[0][0] != result_matches[0][0]:
        raise GameLifecycleError(
            f"Restored {identity_name} request/result identities belong to different decisions."
        )
    return request_matches[0]


def _json_object(value: JsonValue, *, field_name: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        _raise_semantic_drift(f"{field_name} is not an object")
    return value


def _closed_json_object(
    value: JsonValue,
    *,
    field_name: str,
    expected_keys: frozenset[str],
) -> dict[str, JsonValue]:
    payload = _json_object(value, field_name=field_name)
    if frozenset(payload) != expected_keys:
        _raise_semantic_drift(f"{field_name} key inventory drifted")
    return payload


def _raise_semantic_drift(detail: str) -> NoReturn:
    raise GameLifecycleError(f"Restored pre-battle action semantic drift: {detail}.")


__all__ = ("validate_prebattle_alternation_restore",)
