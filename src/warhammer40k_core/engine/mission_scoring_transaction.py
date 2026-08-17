from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.engine.event_log import EventLog, EventRecord
from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlRecord,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_scoring_boundary import (
    score_primary_objective_control_boundary,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
    VictoryPointSourceKind,
    secondary_mission_card_mode_from_token,
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
    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.TURN_END,
            phase=phase,
            ruleset_descriptor=state.ruleset_descriptor_for_runtime_policy(),
        )
    )
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
        phase=phase,
    ):
        return card_state
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
        enemy_unit_ids_in_player_deployment_zone=(
            state.enemy_unit_ids_in_player_deployment_zone(card_state.player_id)
        ),
        starting_strength_records=tuple(state.starting_strength_records),
    )
    if award is None:
        raise GameLifecycleError("State-backed secondary mission requirements are not met.")
    snapshot = _capture_aggregate(state=state, event_log=event_log)
    try:
        if not any(
            stored.record_id == record.record_id for stored in state.objective_control_records
        ):
            state.record_objective_control_record(
                record,
                runtime_modifier_registry=runtime_modifier_registry,
            )
        _emit_objective_control_boundary_event_if_missing(event_log=event_log, record=record)
        score_primary_objective_control_boundary(
            state=state,
            record=record,
            end_of_battle=False,
            event_log=event_log,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        transaction = state.award_victory_points(award)
        if requested_mode is SecondaryMissionCardMode.FIXED:
            result = card_state
        else:
            scored = card_state.score(transaction_id=transaction.transaction_id)
            state.replace_secondary_mission_card_state(scored)
            result = scored
    except GameLifecycleError:
        _restore_aggregate(state=state, event_log=event_log, snapshot=snapshot)
        raise
    else:
        return result


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
    phase: BattlePhase,
) -> bool:
    stored = any(stored.record_id == record.record_id for stored in state.objective_control_records)
    if not stored:
        return False
    primary_closed = any(
        evidence.objective_control_record_id == record.record_id
        for evidence in state.primary_scoring_state_evidence_records
    )
    ledger = state.victory_point_ledger_for_player(card_state.player_id)
    secondary_transactions = tuple(
        transaction
        for transaction in ledger.transactions
        if transaction.source_kind is source_kind
        and transaction.source_id == card_state.secondary_mission_id
        and transaction.battle_round == state.battle_round
        and transaction.phase == phase.value
    )
    if not secondary_transactions:
        return False
    if not primary_closed:
        raise GameLifecycleError(
            "State-backed secondary scoring found a Secondary award without Primary evidence."
        )
    return True


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
