from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Self, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.mission_action_options import (
    mission_action_opportunity_drift_reason,
)
from warhammer40k_core.engine.mission_terrain import (
    logical_terrain_area_within_player_territory,
    mission_logical_terrain_areas,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
)
from warhammer40k_core.engine.primary_mission_action_battlefield_evidence import (
    MissionActionBattlefieldBoundaryEvidence,
)
from warhammer40k_core.engine.primary_mission_action_lifecycle_evidence import (
    MissionActionPriorUseEvidence,
    MissionActionStartAuthorityEvidence,
    MissionActionStartAuthorityOptionEvidence,
    canonical_identifier_tuple,
    canonical_json_object,
    canonical_mission_action_prior_uses,
)
from warhammer40k_core.engine.primary_mission_action_lifecycle_policy import (
    active_primary_mission_marker_ids,
    active_primary_mission_marker_ids_at_event,
    primary_mission_action_prior_use_evidence,
)
from warhammer40k_core.engine.primary_mission_action_request_authority import (
    validate_recomputed_primary_mission_action_opportunity_authority,
)
from warhammer40k_core.engine.primary_mission_boundary_checkpoint import (
    active_primary_marker_ids_from_checkpoint,
    mission_action_prior_uses_from_checkpoint,
    primary_mission_boundary_checkpoint_for_request,
    validate_primary_mission_action_request_checkpoint,
    validate_primary_mission_boundary_checkpoint_modifier_sources,
)
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PrimaryMissionBoundaryCheckpointReference,
)
from warhammer40k_core.engine.primary_mission_boundary_state import (
    primary_mission_action_boundary_state_from_checkpoint,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import SecondaryMissionCardStatus

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
    from warhammer40k_core.engine.faction_rule_execution import FactionRuleExecutionRegistry
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_rule_ir_authority import RuntimeRuleIRAuthorityIndex


MISSION_ACTION_OPPORTUNITY_DECLINED_EVENT: Final = "mission_action_opportunity_declined"
MISSION_ACTION_OPPORTUNITY_DECLINE_EVIDENCE_KEY: Final = (
    "mission_action_opportunity_decline_evidence"
)
MISSION_ACTION_OPPORTUNITY_DECLINE_EVIDENCE_SCHEMA: Final = (
    "mission-action-opportunity-decline-evidence-v1"
)

_START_MISSION_ACTION_DECISION_TYPE: Final = "start_mission_action"
_DECLINE_OPTION_ID: Final = "continue_to_shooting"
_DECISION_REQUESTED_EVENT: Final = "decision_requested"
_DECISION_RECORDED_EVENT: Final = "decision_recorded"
_MISSION_ACTION_STARTED_EVENT: Final = "mission_action_started"
_MISSION_ACTION_ID_PREFIX: Final = "mission-action:"

_REQUEST_PAYLOAD_KEYS: Final = frozenset(
    {
        "game_id",
        "player_id",
        "battle_round",
        "phase",
        "mission_action_opportunity",
        "legal_mission_action_ids",
        "legal_action_option_ids",
        "legal_option_ids",
    }
)
_RESULT_PAYLOAD_KEYS: Final = frozenset(
    {
        "game_id",
        "player_id",
        "battle_round",
        "phase",
        "mission_action_opportunity",
        "legal_action_option_ids",
    }
)
_DECLINE_EVENT_KEYS: Final = frozenset(
    {
        "game_id",
        "player_id",
        "battle_round",
        "phase",
        "request_id",
        "result_id",
        "selected_option_id",
        MISSION_ACTION_OPPORTUNITY_DECLINE_EVIDENCE_KEY,
    }
)

_validate_identifier = IdentifierValidator(GameLifecycleError)


@dataclass(frozen=True, slots=True)
class MissionActionOpportunityDeclineEvidence:
    schema_version: str
    game_id: str
    player_id: str
    active_player_id: str
    battle_round: int
    phase: str
    ruleset_descriptor_hash: str
    active_primary_mission_marker_ids: tuple[str, ...]
    enemy_territory_logical_terrain_area_ids: tuple[str, ...]
    prior_uses: tuple[MissionActionPriorUseEvidence, ...]
    request_authority: MissionActionStartAuthorityEvidence
    checkpoint_reference: PrimaryMissionBoundaryCheckpointReference

    def __post_init__(self) -> None:
        for field_name in (
            "schema_version",
            "game_id",
            "player_id",
            "active_player_id",
            "phase",
            "ruleset_descriptor_hash",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_identifier(field_name, getattr(self, field_name)),
            )
        if self.schema_version != MISSION_ACTION_OPPORTUNITY_DECLINE_EVIDENCE_SCHEMA:
            raise GameLifecycleError("Mission Action decline evidence schema is unsupported.")
        if type(self.battle_round) is not int or self.battle_round < 1:
            raise GameLifecycleError("Mission Action decline battle_round must be positive.")
        if self.phase != BattlePhase.SHOOTING.value:
            raise GameLifecycleError("Mission Action decline evidence requires SHOOTING phase.")
        object.__setattr__(
            self,
            "active_primary_mission_marker_ids",
            canonical_identifier_tuple(
                "active_primary_mission_marker_ids",
                self.active_primary_mission_marker_ids,
                require_non_empty=False,
            ),
        )
        object.__setattr__(
            self,
            "enemy_territory_logical_terrain_area_ids",
            canonical_identifier_tuple(
                "enemy_territory_logical_terrain_area_ids",
                self.enemy_territory_logical_terrain_area_ids,
                require_non_empty=False,
            ),
        )
        object.__setattr__(
            self,
            "prior_uses",
            canonical_mission_action_prior_uses(self.prior_uses),
        )
        if (
            type(self.request_authority) is not MissionActionStartAuthorityEvidence
            or self.request_authority.request_kind != "opportunity"
        ):
            raise GameLifecycleError("Mission Action decline request authority is invalid.")
        if type(self.checkpoint_reference) is not PrimaryMissionBoundaryCheckpointReference:
            raise GameLifecycleError("Mission Action decline checkpoint reference is invalid.")

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            validate_json_value(
                {
                    "schema_version": self.schema_version,
                    "game_id": self.game_id,
                    "player_id": self.player_id,
                    "active_player_id": self.active_player_id,
                    "battle_round": self.battle_round,
                    "phase": self.phase,
                    "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
                    "active_primary_mission_marker_ids": list(
                        self.active_primary_mission_marker_ids
                    ),
                    "enemy_territory_logical_terrain_area_ids": list(
                        self.enemy_territory_logical_terrain_area_ids
                    ),
                    "prior_uses": [row.to_payload() for row in self.prior_uses],
                    "request_authority": self.request_authority.to_payload(),
                    "checkpoint_reference": self.checkpoint_reference.to_payload(),
                }
            ),
        )

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw = _object(
            payload,
            label="Mission Action decline evidence",
            keys=frozenset(
                {
                    "schema_version",
                    "game_id",
                    "player_id",
                    "active_player_id",
                    "battle_round",
                    "phase",
                    "ruleset_descriptor_hash",
                    "active_primary_mission_marker_ids",
                    "enemy_territory_logical_terrain_area_ids",
                    "prior_uses",
                    "request_authority",
                    "checkpoint_reference",
                }
            ),
        )
        return cls(
            schema_version=_string(raw, "schema_version"),
            game_id=_string(raw, "game_id"),
            player_id=_string(raw, "player_id"),
            active_player_id=_string(raw, "active_player_id"),
            battle_round=_int(raw, "battle_round"),
            phase=_string(raw, "phase"),
            ruleset_descriptor_hash=_string(raw, "ruleset_descriptor_hash"),
            active_primary_mission_marker_ids=_string_tuple(
                raw, "active_primary_mission_marker_ids"
            ),
            enemy_territory_logical_terrain_area_ids=_string_tuple(
                raw, "enemy_territory_logical_terrain_area_ids"
            ),
            prior_uses=tuple(
                MissionActionPriorUseEvidence.from_payload(row) for row in _list(raw, "prior_uses")
            ),
            request_authority=MissionActionStartAuthorityEvidence.from_payload(
                raw["request_authority"]
            ),
            checkpoint_reference=PrimaryMissionBoundaryCheckpointReference.from_payload(
                raw["checkpoint_reference"]
            ),
        )


def capture_mission_action_opportunity_decline_evidence(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    checkpoint_reference: PrimaryMissionBoundaryCheckpointReference,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> MissionActionOpportunityDeclineEvidence:
    """Capture the exact opportunity and its historical state boundary before mutation."""

    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Mission Action decline evidence requires GameState.")
    if type(request) is not DecisionRequest or type(result) is not DecisionResult:
        raise GameLifecycleError("Mission Action decline evidence requires typed decisions.")
    if type(runtime_modifier_registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError("Mission Action decline evidence requires runtime modifiers.")
    player_id, battle_round, phase = _validate_decline_decision(
        state=state,
        decision=DecisionRecord(
            record_id="mission-action-decline-capture",
            request=request,
            result=result,
        ),
    )
    authority = _capture_request_authority(
        state=state,
        player_id=player_id,
        request=request,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if state.active_player_id is None:
        raise GameLifecycleError("Mission Action decline requires an active player.")
    evidence = MissionActionOpportunityDeclineEvidence(
        schema_version=MISSION_ACTION_OPPORTUNITY_DECLINE_EVIDENCE_SCHEMA,
        game_id=state.game_id,
        player_id=player_id,
        active_player_id=state.active_player_id,
        battle_round=battle_round,
        phase=phase,
        ruleset_descriptor_hash=state.ruleset_descriptor_hash,
        active_primary_mission_marker_ids=active_primary_mission_marker_ids(state=state),
        enemy_territory_logical_terrain_area_ids=_enemy_territory_area_ids(
            state=state,
            player_id=player_id,
        ),
        prior_uses=primary_mission_action_prior_use_evidence(
            state=state,
            actions=tuple(state.mission_action_states),
        ),
        request_authority=authority,
        checkpoint_reference=checkpoint_reference,
    )
    _validate_evidence_context(state=state, evidence=evidence)
    return evidence


def apply_mission_action_opportunity_decline_mutation(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
    runtime_modifier_registry: RuntimeModifierRegistry,
    rule_ir_authority_index: RuntimeRuleIRAuthorityIndex | None = None,
    faction_rule_execution_registry: FactionRuleExecutionRegistry | None = None,
    runtime_content_activation: RuntimeContentActivation | None = None,
) -> None:
    """Validate and apply one live Mission Action opportunity decline."""

    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Mission Action decline mutation requires GameState.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Mission Action decline mutation requires DecisionController.")
    player_id, battle_round, phase = _validate_decline_decision(
        state=state,
        decision=DecisionRecord(
            record_id="mission-action-decline-live-apply",
            request=request,
            result=result,
        ),
    )
    if (
        state.stage is not GameLifecycleStage.BATTLE
        or state.active_player_id != player_id
        or state.battle_round != battle_round
        or state.current_battle_phase is not BattlePhase.SHOOTING
        or phase != BattlePhase.SHOOTING.value
    ):
        raise GameLifecycleError("Mission Action decline live context drifted.")
    payload = _object(
        result.payload,
        label="Mission Action decline result payload",
        keys=_RESULT_PAYLOAD_KEYS,
    )
    drift_reason = mission_action_opportunity_drift_reason(
        state=state,
        payload=payload,
        player_id=player_id,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if drift_reason is not None:
        raise GameLifecycleError(f"Mission Action opportunity drifted: {drift_reason}.")
    boundary_reference, checkpoint, _checkpoint_index = (
        primary_mission_boundary_checkpoint_for_request(
            event_records=decisions.event_log.records,
            request_id=result.request_id,
        )
    )
    decline_evidence = capture_mission_action_opportunity_decline_evidence(
        state=state,
        request=request,
        result=result,
        checkpoint_reference=boundary_reference,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    validate_primary_mission_action_request_checkpoint(
        state=state,
        event_records=decisions.event_log.records,
        decision_records=decisions.records,
        request_id=result.request_id,
        reference=boundary_reference,
        player_id=decline_evidence.player_id,
        battle_round=decline_evidence.battle_round,
        phase=decline_evidence.phase,
        rule_ir_authority_index=rule_ir_authority_index,
        faction_rule_execution_registry=faction_rule_execution_registry,
        runtime_content_activation=runtime_content_activation,
    )
    validate_primary_mission_boundary_checkpoint_modifier_sources(
        state=state,
        checkpoint=checkpoint,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    shooting_state = state.shooting_phase_state
    if shooting_state is None:
        raise GameLifecycleError("Mission Action decline requires ShootingPhaseState.")
    state.replace_shooting_phase_state(shooting_state.with_mission_action_opportunity_declined())
    decisions.event_log.append(
        MISSION_ACTION_OPPORTUNITY_DECLINED_EVENT,
        {
            "game_id": decline_evidence.game_id,
            "player_id": decline_evidence.player_id,
            "battle_round": decline_evidence.battle_round,
            "phase": decline_evidence.phase,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "selected_option_id": result.selected_option_id,
            MISSION_ACTION_OPPORTUNITY_DECLINE_EVIDENCE_KEY: decline_evidence.to_payload(),
        },
    )


def validate_mission_action_opportunity_decline_integrity(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    rule_ir_authority_index: RuntimeRuleIRAuthorityIndex | None = None,
    faction_rule_execution_registry: FactionRuleExecutionRegistry | None = None,
    runtime_content_activation: RuntimeContentActivation | None = None,
) -> None:
    """Require bidirectional closure for every accepted Mission Action decline."""

    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Mission Action decline integrity requires GameState.")
    events = _event_records(event_records)
    decisions = _decision_records(decision_records)
    event_index_by_id = {event.event_id: index for index, event in enumerate(events)}
    if len(event_index_by_id) != len(events):
        raise GameLifecycleError("Mission Action decline event identities are duplicated.")

    decline_decisions = tuple(
        decision
        for decision in decisions
        if decision.result.decision_type == _START_MISSION_ACTION_DECISION_TYPE
        and decision.result.selected_option_id == _DECLINE_OPTION_ID
    )
    decline_events = tuple(
        event for event in events if event.event_type == MISSION_ACTION_OPPORTUNITY_DECLINED_EVENT
    )
    if len({decision.result.result_id for decision in decline_decisions}) != len(decline_decisions):
        raise GameLifecycleError("Mission Action decline result identities are duplicated.")

    authenticated_event_ids: set[str] = set()
    phase_keys: set[tuple[str, str, int, str]] = set()
    context_by_result_id: dict[str, tuple[str, int, str]] = {}
    for decision in decline_decisions:
        player_id, battle_round, phase = _validate_decline_decision(
            state=state,
            decision=decision,
        )
        phase_key = (state.game_id, player_id, battle_round, phase)
        if phase_key in phase_keys:
            raise GameLifecycleError("Mission Action opportunity was declined more than once.")
        phase_keys.add(phase_key)
        context_by_result_id[decision.result.result_id] = (
            player_id,
            battle_round,
            phase,
        )
    _validate_current_shooting_flag(state=state, phase_keys=phase_keys)

    for decision in decline_decisions:
        player_id, battle_round, phase = context_by_result_id[decision.result.result_id]
        mutation_event = _unique_decline_event(
            events=decline_events,
            request_id=decision.request.request_id,
            result_id=decision.result.result_id,
        )
        evidence = _validate_decline_event(
            state=state,
            event=mutation_event,
            decision=decision,
            player_id=player_id,
            battle_round=battle_round,
            phase=phase,
        )
        request_event, recorded_event = _validate_decision_event_closure(
            decision=decision,
            mutation_event=mutation_event,
            event_records=events,
            event_index_by_id=event_index_by_id,
        )
        _reject_resulting_action(
            state=state,
            event_records=events,
            result_id=decision.result.result_id,
        )
        _validate_evidence_at_request(
            state=state,
            evidence=evidence,
            request=decision.request,
            request_event=request_event,
            event_records=events,
            decision_records=decisions,
            event_index_by_id=event_index_by_id,
            rule_ir_authority_index=rule_ir_authority_index,
            faction_rule_execution_registry=faction_rule_execution_registry,
            runtime_content_activation=runtime_content_activation,
        )
        authenticated_event_ids.add(mutation_event.event_id)
        del recorded_event

    if authenticated_event_ids != {event.event_id for event in decline_events}:
        raise GameLifecycleError("Mission Action decline event lacks an exact DecisionRecord.")


def _capture_request_authority(
    *,
    state: GameState,
    player_id: str,
    request: DecisionRequest,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> MissionActionStartAuthorityEvidence:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Mission Action decline requires battlefield state.")
    del runtime_modifier_registry
    return MissionActionStartAuthorityEvidence(
        request_kind="opportunity",
        request_payload_json=canonical_json_object(request.payload),
        battlefield_boundary=MissionActionBattlefieldBoundaryEvidence.from_battlefield_state(
            battlefield
        ),
        options=tuple(
            MissionActionStartAuthorityOptionEvidence(
                option_id=option.option_id,
                label=option.label,
                payload_json=canonical_json_object(option.payload),
            )
            for option in request.options
        ),
        candidate_units=(),
        terrain_model_inventory=(),
        active_secondary_mission_ids=tuple(
            card.secondary_mission_id
            for card in state.secondary_mission_card_states
            if card.player_id == player_id and card.status is SecondaryMissionCardStatus.ACTIVE
        ),
    )


def _validate_decline_decision(
    *,
    state: GameState,
    decision: DecisionRecord,
) -> tuple[str, int, str]:
    request = decision.request
    result = decision.result
    request_payload = _object(
        request.payload,
        label="Mission Action decline request payload",
        keys=_REQUEST_PAYLOAD_KEYS,
    )
    result_payload = _object(
        result.payload,
        label="Mission Action decline result payload",
        keys=_RESULT_PAYLOAD_KEYS,
    )
    player_id = _string(result_payload, "player_id")
    battle_round = _int(result_payload, "battle_round")
    phase = _string(result_payload, "phase")
    if (
        request.decision_type != _START_MISSION_ACTION_DECISION_TYPE
        or result.decision_type != _START_MISSION_ACTION_DECISION_TYPE
        or request.actor_id != player_id
        or result.actor_id != player_id
        or result.request_id != request.request_id
        or result.selected_option_id != _DECLINE_OPTION_ID
        or result_payload.get("game_id") != state.game_id
        or request_payload.get("game_id") != state.game_id
        or request_payload.get("player_id") != player_id
        or request_payload.get("battle_round") != battle_round
        or request_payload.get("phase") != phase
        or request_payload.get("mission_action_opportunity") is not True
        or result_payload.get("mission_action_opportunity") is not True
        or phase != BattlePhase.SHOOTING.value
    ):
        raise GameLifecycleError("Mission Action decline DecisionRecord context drifted.")
    _validate_decline_boundary_has_occurred(
        state=state,
        player_id=player_id,
        battle_round=battle_round,
    )

    option_ids = [option.option_id for option in request.options]
    action_options = tuple(
        option for option in request.options if option.option_id != _DECLINE_OPTION_ID
    )
    decline_options = tuple(
        option for option in request.options if option.option_id == _DECLINE_OPTION_ID
    )
    if len(decline_options) != 1 or not action_options:
        raise GameLifecycleError("Mission Action decline option inventory drifted.")
    mission_action_ids = sorted(
        {
            _string(
                _object_any_keys(
                    option.payload,
                    label="Mission Action opportunity option payload",
                ),
                "mission_action_id",
            )
            for option in action_options
        }
    )
    action_option_ids = [option.option_id for option in action_options]
    if (
        request_payload.get("legal_mission_action_ids") != mission_action_ids
        or request_payload.get("legal_action_option_ids") != action_option_ids
        or request_payload.get("legal_option_ids") != sorted(option_ids)
        or result_payload.get("legal_action_option_ids") != action_option_ids
        or decline_options[0].payload != result.payload
    ):
        raise GameLifecycleError("Mission Action decline complete option inventory drifted.")
    return player_id, battle_round, phase


def _validate_decline_boundary_has_occurred(
    *,
    state: GameState,
    player_id: str,
    battle_round: int,
) -> None:
    if player_id not in state.turn_order or battle_round < 1 or battle_round > state.battle_round:
        raise GameLifecycleError("Mission Action decline battle context has not occurred.")
    if state.stage is GameLifecycleStage.COMPLETE:
        return
    if (
        state.stage is not GameLifecycleStage.BATTLE
        or state.active_player_id is None
        or state.current_battle_phase is None
    ):
        raise GameLifecycleError("Mission Action decline battle context has not occurred.")
    if battle_round < state.battle_round:
        return
    requested_turn_index = state.turn_order.index(player_id)
    active_turn_index = state.turn_order.index(state.active_player_id)
    if requested_turn_index > active_turn_index or (
        requested_turn_index == active_turn_index
        and state.battle_phase_sequence.index(state.current_battle_phase)
        < state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    ):
        raise GameLifecycleError("Mission Action decline battle context has not occurred.")


def _validate_decline_event(
    *,
    state: GameState,
    event: EventRecord,
    decision: DecisionRecord,
    player_id: str,
    battle_round: int,
    phase: str,
) -> MissionActionOpportunityDeclineEvidence:
    payload = _object(
        event.payload,
        label="Mission Action decline event",
        keys=_DECLINE_EVENT_KEYS,
    )
    evidence = MissionActionOpportunityDeclineEvidence.from_payload(
        payload[MISSION_ACTION_OPPORTUNITY_DECLINE_EVIDENCE_KEY]
    )
    expected: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "player_id": player_id,
        "battle_round": battle_round,
        "phase": phase,
        "request_id": decision.request.request_id,
        "result_id": decision.result.result_id,
        "selected_option_id": _DECLINE_OPTION_ID,
        MISSION_ACTION_OPPORTUNITY_DECLINE_EVIDENCE_KEY: evidence.to_payload(),
    }
    if payload != expected:
        raise GameLifecycleError("Mission Action decline mutation event drifted.")
    _validate_evidence_context(state=state, evidence=evidence)
    if (
        evidence.player_id != player_id
        or evidence.battle_round != battle_round
        or evidence.phase != phase
    ):
        raise GameLifecycleError("Mission Action decline evidence context drifted.")
    return evidence


def _validate_evidence_context(
    *, state: GameState, evidence: MissionActionOpportunityDeclineEvidence
) -> None:
    if (
        evidence.game_id != state.game_id
        or evidence.player_id != evidence.active_player_id
        or evidence.player_id not in state.player_ids
        or evidence.ruleset_descriptor_hash != state.ruleset_descriptor_hash
        or evidence.enemy_territory_logical_terrain_area_ids
        != _enemy_territory_area_ids(state=state, player_id=evidence.player_id)
    ):
        raise GameLifecycleError("Mission Action decline evidence boundary drifted.")


def _validate_evidence_at_request(
    *,
    state: GameState,
    evidence: MissionActionOpportunityDeclineEvidence,
    request: DecisionRequest,
    request_event: EventRecord,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    event_index_by_id: dict[str, int],
    rule_ir_authority_index: RuntimeRuleIRAuthorityIndex | None,
    faction_rule_execution_registry: FactionRuleExecutionRegistry | None,
    runtime_content_activation: RuntimeContentActivation | None,
) -> None:
    if evidence.active_primary_mission_marker_ids != active_primary_mission_marker_ids_at_event(
        state=state,
        event=request_event,
        event_index_by_id=event_index_by_id,
    ):
        raise GameLifecycleError("Mission Action decline marker inventory drifted.")
    prior_actions = tuple(
        action
        for action in state.mission_action_states
        if _mission_action_start_index(
            action_id=action.action_id,
            event_records=event_records,
            event_index_by_id=event_index_by_id,
        )
        < event_index_by_id[request_event.event_id]
    )
    expected_prior = primary_mission_action_prior_use_evidence(
        state=state,
        actions=prior_actions,
    )
    if evidence.prior_uses != expected_prior:
        raise GameLifecycleError("Mission Action decline prior-use inventory drifted.")

    if canonical_json_object(
        request.payload
    ) != evidence.request_authority.request_payload_json or _request_option_rows(
        request
    ) != _authority_option_rows(evidence.request_authority):
        raise GameLifecycleError("Mission Action decline request inventory drifted.")

    checkpoint = validate_primary_mission_action_request_checkpoint(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        request_id=request.request_id,
        reference=evidence.checkpoint_reference,
        player_id=evidence.player_id,
        battle_round=evidence.battle_round,
        phase=evidence.phase,
        rule_ir_authority_index=rule_ir_authority_index,
        faction_rule_execution_registry=faction_rule_execution_registry,
        runtime_content_activation=runtime_content_activation,
    )
    if (
        evidence.active_primary_mission_marker_ids
        != active_primary_marker_ids_from_checkpoint(checkpoint)
        or evidence.prior_uses != mission_action_prior_uses_from_checkpoint(checkpoint)
        or evidence.request_authority.active_secondary_mission_ids
        != checkpoint.active_secondary_mission_ids
    ):
        raise GameLifecycleError(
            "Mission Action decline evidence drifted from its boundary checkpoint."
        )
    boundary_state = primary_mission_action_boundary_state_from_checkpoint(
        state=state,
        checkpoint=checkpoint,
    )
    validate_recomputed_primary_mission_action_opportunity_authority(
        state=boundary_state,
        player_id=evidence.player_id,
        battle_round=evidence.battle_round,
        authority=evidence.request_authority,
    )


def _validate_decision_event_closure(
    *,
    decision: DecisionRecord,
    mutation_event: EventRecord,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
) -> tuple[EventRecord, EventRecord]:
    requested = tuple(
        event
        for event in event_records
        if event.event_type == _DECISION_REQUESTED_EVENT
        and event.payload == decision.request.to_payload()
    )
    recorded = tuple(
        event
        for event in event_records
        if event.event_type == _DECISION_RECORDED_EVENT and event.payload == decision.to_payload()
    )
    if len(requested) != 1 or len(recorded) != 1:
        raise GameLifecycleError(
            "Mission Action decline requires exact requested and recorded decision events."
        )
    if not (
        event_index_by_id[requested[0].event_id]
        < event_index_by_id[recorded[0].event_id]
        < event_index_by_id[mutation_event.event_id]
    ):
        raise GameLifecycleError("Mission Action decline decision/mutation ordering drifted.")
    return requested[0], recorded[0]


def _unique_decline_event(
    *, events: tuple[EventRecord, ...], request_id: str, result_id: str
) -> EventRecord:
    matches = tuple(
        event
        for event in events
        if isinstance(event.payload, dict)
        and event.payload.get("request_id") == request_id
        and event.payload.get("result_id") == result_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Mission Action decline requires one mutation event.")
    return matches[0]


def _validate_current_shooting_flag(
    *, state: GameState, phase_keys: set[tuple[str, str, int, str]]
) -> None:
    shooting_state = state.shooting_phase_state
    if shooting_state is None:
        return
    current_key = (
        state.game_id,
        shooting_state.active_player_id,
        shooting_state.battle_round,
        BattlePhase.SHOOTING.value,
    )
    authoritative_decline = current_key in phase_keys
    if shooting_state.mission_action_opportunity_declined is not authoritative_decline:
        raise GameLifecycleError(
            "ShootingPhaseState Mission Action decline flag lacks exact decision authority."
        )


def _reject_resulting_action(
    *, state: GameState, event_records: tuple[EventRecord, ...], result_id: str
) -> None:
    action_id = f"{_MISSION_ACTION_ID_PREFIX}{result_id}"
    if any(action.action_id == action_id for action in state.mission_action_states):
        raise GameLifecycleError("Mission Action decline produced persisted Action state.")
    for event in event_records:
        if event.event_type != _MISSION_ACTION_STARTED_EVENT:
            continue
        payload = _object_any_keys(event.payload, label="Mission Action start event")
        nested = _object_any_keys(
            payload.get("mission_action_state"),
            label="Mission Action start event state",
        )
        if nested.get("action_id") == action_id:
            raise GameLifecycleError("Mission Action decline produced a start mutation event.")


def _mission_action_start_index(
    *,
    action_id: str,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
) -> int:
    matches = tuple(
        event
        for event in event_records
        if event.event_type == _MISSION_ACTION_STARTED_EVENT
        and isinstance(event.payload, dict)
        and isinstance(event.payload.get("mission_action_state"), dict)
        and cast(dict[str, object], event.payload["mission_action_state"]).get("action_id")
        == action_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Mission Action prior use requires one start event.")
    return event_index_by_id[matches[0].event_id]


def _request_option_rows(request: DecisionRequest) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        sorted(
            (
                option.option_id,
                option.label,
                canonical_json_object(option.payload),
            )
            for option in request.options
        )
    )


def _authority_option_rows(
    authority: MissionActionStartAuthorityEvidence,
) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        sorted(
            (option.option_id, option.label, option.payload_json) for option in authority.options
        )
    )


def _enemy_territory_area_ids(*, state: GameState, player_id: str) -> tuple[str, ...]:
    setup = state.mission_setup
    if setup is None:
        raise GameLifecycleError("Mission Action decline requires MissionSetup.")
    opponents = tuple(candidate for candidate in state.player_ids if candidate != player_id)
    if len(opponents) != 1:
        raise GameLifecycleError("Mission Action decline requires exactly one opponent.")
    return tuple(
        sorted(
            area.logical_terrain_area_id
            for area in mission_logical_terrain_areas(setup)
            if logical_terrain_area_within_player_territory(
                area,
                mission_setup=setup,
                player_id=opponents[0],
            )
        )
    )


def _event_records(value: object) -> tuple[EventRecord, ...]:
    if type(value) is not tuple or any(
        type(event) is not EventRecord for event in cast(tuple[object, ...], value)
    ):
        raise GameLifecycleError("Mission Action decline integrity requires EventRecords.")
    return cast(tuple[EventRecord, ...], value)


def _decision_records(value: object) -> tuple[DecisionRecord, ...]:
    if type(value) is not tuple or any(
        type(record) is not DecisionRecord for record in cast(tuple[object, ...], value)
    ):
        raise GameLifecycleError("Mission Action decline integrity requires DecisionRecords.")
    return cast(tuple[DecisionRecord, ...], value)


def _object(value: object, *, label: str, keys: frozenset[str]) -> dict[str, JsonValue]:
    raw = _object_any_keys(value, label=label)
    if frozenset(raw) != keys:
        raise GameLifecycleError(f"{label} fields drifted.")
    return raw


def _object_any_keys(value: object, *, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{label} must be a JSON object.")
    untyped = cast(dict[object, object], value)
    if any(type(key) is not str for key in untyped):
        raise GameLifecycleError(f"{label} must be a JSON object.")
    raw = cast(dict[str, object], value)
    return cast(dict[str, JsonValue], validate_json_value(raw))


def _string(raw: dict[str, JsonValue], key: str) -> str:
    value = raw.get(key)
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"Mission Action decline {key} must be an identifier.")
    return value


def _int(raw: dict[str, JsonValue], key: str) -> int:
    value = raw.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"Mission Action decline {key} must be an int.")
    return value


def _list(raw: dict[str, JsonValue], key: str) -> list[JsonValue]:
    value = raw.get(key)
    if not isinstance(value, list):
        raise GameLifecycleError(f"Mission Action decline {key} must be a list.")
    return value


def _string_tuple(raw: dict[str, JsonValue], key: str) -> tuple[str, ...]:
    values = _list(raw, key)
    if any(type(value) is not str for value in values):
        raise GameLifecycleError(f"Mission Action decline {key} must contain strings.")
    return cast(tuple[str, ...], tuple(values))


__all__ = (
    "MISSION_ACTION_OPPORTUNITY_DECLINED_EVENT",
    "MISSION_ACTION_OPPORTUNITY_DECLINE_EVIDENCE_KEY",
    "MISSION_ACTION_OPPORTUNITY_DECLINE_EVIDENCE_SCHEMA",
    "MissionActionOpportunityDeclineEvidence",
    "capture_mission_action_opportunity_decline_evidence",
    "validate_mission_action_opportunity_decline_integrity",
)
