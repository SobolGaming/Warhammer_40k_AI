from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.engine.event_log import EventLog, EventRecord
from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.objective_control_boundary_proposal import (
    commit_canonical_objective_control_proposal,
    propose_canonical_objective_control_boundary,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_scoring_boundary import (
    score_primary_objective_control_boundary,
)
from warhammer40k_core.engine.primary_scoring_boundary_inventory import (
    required_primary_scoring_boundary_kinds,
)
from warhammer40k_core.engine.primary_scoring_boundary_lifecycle import (
    PrimaryScoringBoundaryStatus,
)
from warhammer40k_core.engine.primary_scoring_state_evidence import PrimaryScoringBoundaryKind
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
    VictoryPointAward,
    VictoryPointSourceKind,
    secondary_mission_card_mode_from_token,
)
from warhammer40k_core.engine.secondary_deployment_zone_evidence import (
    bind_state_backed_secondary_scoring_commit,
)
from warhammer40k_core.engine.secondary_scoring_state_evidence import (
    bind_secondary_scoring_state_evidence,
    capture_secondary_scoring_state_evidence,
)
from warhammer40k_core.engine.secondary_tactical_achievement import (
    require_positive_tactical_secondary_score_transaction,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.objective_control_record_authority import (
        ObjectiveControlRecordAuthority,
    )
    from warhammer40k_core.engine.primary_scoring_boundary_lifecycle import (
        PrimaryScoringBoundaryLifecycle,
    )
    from warhammer40k_core.engine.primary_scoring_state_evidence import PrimaryScoringStateEvidence
    from warhammer40k_core.engine.scoring import VictoryPointLedger
    from warhammer40k_core.engine.secondary_scoring_state_evidence import (
        SecondaryScoringStateEvidence,
    )
    from warhammer40k_core.engine.sticky_objective_control import StickyObjectiveControlState

_OBJECTIVE_CONTROL_BOUNDARY_EVENT_TYPE = "end_boundary_objective_control_determined"
_OBJECTIVE_CONTROL_SOURCE_RULE_ID = (
    "gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:14.02.01-control-first"
)


@dataclass(frozen=True, slots=True)
class MissionScoringAggregateSnapshot:
    objective_control_records: tuple[ObjectiveControlRecord, ...]
    objective_control_record_authorities: tuple[ObjectiveControlRecordAuthority, ...]
    sticky_objective_control_states: tuple[StickyObjectiveControlState, ...]
    primary_scoring_state_evidence_records: tuple[PrimaryScoringStateEvidence, ...]
    secondary_scoring_state_evidence_records: tuple[SecondaryScoringStateEvidence, ...]
    victory_point_ledgers: tuple[VictoryPointLedger, ...]
    secondary_mission_card_states: tuple[SecondaryMissionCardState, ...]
    primary_scoring_boundary_lifecycles: tuple[PrimaryScoringBoundaryLifecycle, ...]
    event_records: tuple[EventRecord, ...]


def score_secondary_mission_from_state(
    *,
    state: GameState,
    event_log: EventLog,
    player_id: str,
    secondary_mission_id: str,
    mode: SecondaryMissionCardMode,
    phase: BattlePhase,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> SecondaryMissionCardState:
    """Prove then atomically commit state-backed Secondary scoring and its Primary boundary."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("State-backed secondary scoring requires GameState.")
    if type(event_log) is not EventLog:
        raise GameLifecycleError("State-backed secondary scoring requires EventLog.")
    if state.mission_setup is None:
        raise GameLifecycleError("State-backed secondary scoring requires MissionSetup.")
    if type(phase) is not BattlePhase:
        raise GameLifecycleError("State-backed secondary scoring phase must be a BattlePhase.")
    requested_mode = secondary_mission_card_mode_from_token(mode)
    card_state = _card_for_state_backed_scoring(
        state=state,
        player_id=player_id,
        secondary_mission_id=secondary_mission_id,
        mode=requested_mode,
    )
    proposal = propose_canonical_objective_control_boundary(
        state=state,
        completed_phase=phase,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    record = proposal.retained_record
    policy = mission_scoring_policies_from_setup(state.mission_setup)
    source_kind = (
        VictoryPointSourceKind.FIXED_SECONDARY
        if requested_mode is SecondaryMissionCardMode.FIXED
        else VictoryPointSourceKind.TACTICAL_SECONDARY
    )
    if _already_scored_at_boundary(
        state=state,
        card_state=card_state,
        record=record,
        source_kind=source_kind,
        policies=policy,
    ):
        return card_state
    snapshot = _capture_aggregate(state=state, event_log=event_log)
    try:
        commit_canonical_objective_control_proposal(
            state=state,
            proposal=proposal,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        _emit_objective_control_boundary_event_if_missing(event_log=event_log, record=record)
        if _already_scored_at_boundary(
            state=state,
            card_state=card_state,
            record=record,
            source_kind=source_kind,
            policies=policy,
        ):
            return card_state
        from warhammer40k_core.engine.secondary_scoring_context import (
            secondary_mission_selection_for_card,
            secondary_scoring_condition_context_from_state,
        )

        score_primary_objective_control_boundary(
            state=state,
            record=record,
            end_of_battle=False,
            event_log=event_log,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        condition_context = secondary_scoring_condition_context_from_state(
            state=state,
            player_id=card_state.player_id,
            record=record,
            selection=secondary_mission_selection_for_card(card_state),
        )
        award = policy.secondary_award_from_mission_state(
            player_id=card_state.player_id,
            battle_round=state.battle_round,
            phase=phase.value,
            secondary_mission_id=card_state.secondary_mission_id,
            source_kind=source_kind,
            hidden=False,
            record=record,
            mission_setup=state.mission_setup,
            unit_destruction_states=tuple(state.secondary_unit_destruction_states),
            objective_cleanse_states=tuple(state.secondary_objective_cleanse_states),
            terrain_plunder_states=tuple(state.secondary_terrain_plunder_states),
            enemy_unit_ids_in_player_deployment_zone=condition_context.enemy_unit_ids_in_player_deployment_zone,
            starting_strength_records=tuple(state.starting_strength_records),
            condition_context=condition_context,
        )
        required_award = _require_state_backed_secondary_award(award)
        evidence = capture_secondary_scoring_state_evidence(
            state=state,
            card=card_state,
            record=record,
            context=condition_context,
            award=required_award,
        )
        award = bind_state_backed_secondary_scoring_commit(
            bind_secondary_scoring_state_evidence(required_award, evidence),
            state=state,
            record=record,
        )
        transaction = state.award_victory_points(award)
        if requested_mode is SecondaryMissionCardMode.FIXED:
            result = card_state
        else:
            require_positive_tactical_secondary_score_transaction(transaction)
            scored = card_state.score(transaction_id=transaction.transaction_id)
            state.replace_secondary_mission_card_state(scored)
            result = scored
            _consume_tactical_achievements_for_card(state=state, card_state=card_state)
    except GameLifecycleError:
        _restore_aggregate(state=state, event_log=event_log, snapshot=snapshot)
        raise
    else:
        return result


def _require_state_backed_secondary_award(award: VictoryPointAward | None) -> VictoryPointAward:
    if award is None:
        raise GameLifecycleError("State-backed secondary mission requirements are not met.")
    return award


def _consume_tactical_achievements_for_card(
    *,
    state: GameState,
    card_state: SecondaryMissionCardState,
) -> None:
    matching_ids = tuple(
        context.achievement_id
        for context in state.tactical_secondary_achievement_contexts
        if context.player_id == card_state.player_id
        and context.secondary_mission_id == card_state.secondary_mission_id
        and context.card_battle_round == card_state.battle_round
    )
    for achievement_id in matching_ids:
        state.consume_tactical_secondary_achievement_context(achievement_id)


def _card_for_state_backed_scoring(
    *,
    state: GameState,
    player_id: str,
    secondary_mission_id: str,
    mode: SecondaryMissionCardMode,
) -> SecondaryMissionCardState:
    active = state.secondary_mission_card_state(
        player_id=player_id,
        secondary_mission_id=secondary_mission_id,
        mode=mode,
    )
    if active is not None:
        return active
    matches = tuple(
        card
        for card in state.secondary_mission_card_states
        if card.player_id == player_id
        and card.secondary_mission_id == secondary_mission_id
        and card.mode is mode
        and card.status is SecondaryMissionCardStatus.SCORED
        and card.battle_round == state.battle_round
    )
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise GameLifecycleError("Multiple scored secondary card states found.")
    raise GameLifecycleError("Secondary mission card is not active.")


def _already_scored_at_boundary(
    *,
    state: GameState,
    card_state: SecondaryMissionCardState,
    record: ObjectiveControlRecord,
    source_kind: VictoryPointSourceKind,
    policies: object,
) -> bool:
    stored = any(stored.record_id == record.record_id for stored in state.objective_control_records)
    if not stored:
        return False
    ledger = state.victory_point_ledger_for_player(card_state.player_id)
    secondary_transactions = tuple(
        transaction
        for transaction in ledger.transactions
        if transaction.source_kind is source_kind
        and transaction.source_id == card_state.secondary_mission_id
        and _transaction_objective_control_record_id(transaction) == record.record_id
    )
    if not secondary_transactions:
        return False
    _validate_secondary_primary_closure(
        state=state,
        record=record,
        policies=policies,
    )
    return True


def _transaction_objective_control_record_id(transaction: object) -> str:
    from warhammer40k_core.engine.scoring import VictoryPointTransaction

    if type(transaction) is not VictoryPointTransaction:
        raise GameLifecycleError("Secondary scoring retry requires a VictoryPointTransaction.")
    metadata = transaction.metadata
    if not isinstance(metadata, dict):
        raise GameLifecycleError(
            "Secondary scoring transaction metadata must include objective_control_record_id."
        )
    record_id = metadata.get("objective_control_record_id")
    if type(record_id) is not str or not record_id:
        raise GameLifecycleError(
            "Secondary scoring transaction metadata must include objective_control_record_id."
        )
    return record_id


def _validate_secondary_primary_closure(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    policies: object,
) -> None:
    from warhammer40k_core.engine.mission_scoring_policies import MissionScoringPolicies

    if type(policies) is not MissionScoringPolicies:
        raise GameLifecycleError("Secondary scoring Primary closure requires scoring policies.")
    required = required_primary_scoring_boundary_kinds(
        policies=policies,
        record=record,
        turn_order=state.turn_order,
    )
    ordinary_required = PrimaryScoringBoundaryKind.ORDINARY in required
    ordinary_evidence = tuple(
        evidence
        for evidence in state.primary_scoring_state_evidence_records
        if evidence.objective_control_record_id == record.record_id
        and evidence.scoring_boundary_kind is PrimaryScoringBoundaryKind.ORDINARY
    )
    if not ordinary_required:
        if ordinary_evidence:
            raise GameLifecycleError(
                "State-backed secondary scoring found unexpected Primary evidence."
            )
        return
    if len(ordinary_evidence) != 1:
        raise GameLifecycleError(
            "State-backed secondary scoring found a Secondary award without Primary evidence."
        )
    evidence = ordinary_evidence[0]
    resolved = tuple(
        row
        for row in state.primary_scoring_boundary_lifecycles
        if row.objective_control_record_id == record.record_id
        and row.scoring_boundary_kind is PrimaryScoringBoundaryKind.ORDINARY
        and row.status is PrimaryScoringBoundaryStatus.RESOLVED
        and row.evidence_id == evidence.evidence_id
    )
    if len(resolved) != 1:
        raise GameLifecycleError(
            "State-backed secondary scoring found a Secondary award without "
            "a resolved Primary lifecycle."
        )


def _emit_objective_control_boundary_event_if_missing(
    *,
    event_log: EventLog,
    record: ObjectiveControlRecord,
) -> None:
    if any(
        event.event_type == _OBJECTIVE_CONTROL_BOUNDARY_EVENT_TYPE
        and isinstance(event.payload, dict)
        and event.payload.get("record_ids") == [record.record_id]
        for event in event_log.records
    ):
        return
    event_log.append(
        _OBJECTIVE_CONTROL_BOUNDARY_EVENT_TYPE,
        {
            "game_id": record.game_id,
            "battle_round": record.battle_round,
            "phase": record.phase,
            "record_ids": [record.record_id],
            "source_rule_id": _OBJECTIVE_CONTROL_SOURCE_RULE_ID,
        },
    )


def _capture_aggregate(
    *,
    state: GameState,
    event_log: EventLog,
) -> MissionScoringAggregateSnapshot:
    return MissionScoringAggregateSnapshot(
        objective_control_records=tuple(state.objective_control_records),
        objective_control_record_authorities=tuple(state.objective_control_record_authorities),
        sticky_objective_control_states=tuple(state.sticky_objective_control_states),
        primary_scoring_state_evidence_records=tuple(state.primary_scoring_state_evidence_records),
        secondary_scoring_state_evidence_records=tuple(
            state.secondary_scoring_state_evidence_records
        ),
        victory_point_ledgers=tuple(state.victory_point_ledgers),
        secondary_mission_card_states=tuple(state.secondary_mission_card_states),
        primary_scoring_boundary_lifecycles=tuple(state.primary_scoring_boundary_lifecycles),
        event_records=event_log.records,
    )


def _restore_aggregate(
    *,
    state: GameState,
    event_log: EventLog,
    snapshot: MissionScoringAggregateSnapshot,
) -> None:
    state.restore_mission_scoring_aggregate(snapshot)
    event_log.replace_records(snapshot.event_records)


__all__ = ("MissionScoringAggregateSnapshot", "score_secondary_mission_from_state")
