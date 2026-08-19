from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_scoring_boundary import (
    score_primary_objective_control_boundary,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
    TacticalSecondaryAchievementContext,
    VictoryPointSourceKind,
)
from warhammer40k_core.engine.secondary_deployment_zone_evidence import (
    bind_state_backed_secondary_scoring_commit,
)
from warhammer40k_core.engine.secondary_mission_selection import (
    SecondaryMissionSelection,
    secondary_mission_selection_from_json,
)
from warhammer40k_core.engine.secondary_scoring_context import (
    secondary_scoring_condition_context_from_state,
)
from warhammer40k_core.engine.secondary_tactical_achievement import (
    tactical_secondary_achievement_context_from_award,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def score_turn_end_mission_scoring_boundary(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    end_of_battle: bool,
    event_log: EventLog | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> None:
    from warhammer40k_core.engine.game_state import GameState as _GameState

    if type(state) is not _GameState:
        raise GameLifecycleError("Turn-end mission scoring requires GameState.")
    if type(record) is not ObjectiveControlRecord:
        raise GameLifecycleError("Turn-end mission scoring requires an ObjectiveControlRecord.")
    if type(end_of_battle) is not bool:
        raise GameLifecycleError("Turn-end mission scoring end_of_battle must be a bool.")
    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=end_of_battle,
        event_log=event_log,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if end_of_battle or record.timing is not ObjectiveControlTiming.TURN_END:
        return
    _score_secondary_objective_control_boundary(state=state, record=record)


def next_pending_tactical_secondary_achievement(
    state: GameState,
) -> TacticalSecondaryAchievementContext | None:
    from warhammer40k_core.engine.game_state import GameState as _GameState

    if type(state) is not _GameState:
        raise GameLifecycleError("Tactical secondary achievement lookup requires GameState.")
    if not state.tactical_secondary_achievement_contexts:
        return None
    active_player_id = state.active_player_id
    if active_player_id is None:
        raise GameLifecycleError("Tactical secondary achievement lookup requires an active player.")
    ordered_players = (
        active_player_id,
        *(player_id for player_id in state.turn_order if player_id != active_player_id),
    )
    for player_id in ordered_players:
        matches = tuple(
            context
            for context in state.tactical_secondary_achievement_contexts
            if context.player_id == player_id
        )
        if matches:
            return matches[0]
    return None


def _score_secondary_objective_control_boundary(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
) -> None:
    if state.mission_setup is None:
        raise GameLifecycleError("Secondary boundary scoring requires MissionSetup.")
    policies = mission_scoring_policies_from_setup(state.mission_setup)
    active_player_id = record.active_player_id
    ordered_players = (
        active_player_id,
        *(player_id for player_id in state.turn_order if player_id != active_player_id),
    )
    for player_id in ordered_players:
        cards = tuple(
            card
            for card in state.secondary_mission_card_states
            if card.player_id == player_id and card.status is SecondaryMissionCardStatus.ACTIVE
        )
        for card in cards:
            _score_or_record_secondary_card(
                state=state,
                record=record,
                card=card,
                policies=policies,
            )


def _score_or_record_secondary_card(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    card: SecondaryMissionCardState,
    policies: object,
) -> None:
    from warhammer40k_core.engine.mission_scoring_policies import MissionScoringPolicies

    if type(policies) is not MissionScoringPolicies:
        raise GameLifecycleError("Secondary boundary scoring requires MissionScoringPolicies.")
    selection = _selection_for_card(card)
    pending_achievement = any(
        stored.player_id == card.player_id
        and stored.secondary_mission_id == card.secondary_mission_id
        and stored.card_battle_round == card.battle_round
        for stored in state.tactical_secondary_achievement_contexts
    )
    if (
        selection is not None
        and record.record_id in selection.resolved_objective_control_record_ids
        and not pending_achievement
    ):
        return
    source_kind = (
        VictoryPointSourceKind.FIXED_SECONDARY
        if card.mode is SecondaryMissionCardMode.FIXED
        else VictoryPointSourceKind.TACTICAL_SECONDARY
    )
    if _already_awarded_at_record(
        state=state,
        card=card,
        record=record,
        source_kind=source_kind,
    ):
        _mark_card_record_resolved(state=state, card=card, record=record)
        return
    mission_setup = state.mission_setup
    if mission_setup is None:
        raise GameLifecycleError("Secondary boundary scoring requires MissionSetup.")
    context = secondary_scoring_condition_context_from_state(
        state=state,
        player_id=card.player_id,
        record=record,
        selection=selection,
    )
    award = policies.secondary_award_from_mission_state(
        player_id=card.player_id,
        battle_round=record.battle_round,
        phase=record.phase,
        secondary_mission_id=card.secondary_mission_id,
        source_kind=source_kind,
        hidden=False,
        record=record,
        mission_setup=mission_setup,
        unit_destruction_states=tuple(state.secondary_unit_destruction_states),
        objective_cleanse_states=tuple(state.secondary_objective_cleanse_states),
        terrain_plunder_states=tuple(state.secondary_terrain_plunder_states),
        enemy_unit_ids_in_player_deployment_zone=context.enemy_unit_ids_in_player_deployment_zone,
        starting_strength_records=tuple(state.starting_strength_records),
        condition_context=context,
    )
    if award is None:
        return
    if card.mode is SecondaryMissionCardMode.FIXED:
        bound = bind_state_backed_secondary_scoring_commit(award, state=state, record=record)
        state.award_victory_points(bound)
        _mark_card_record_resolved(state=state, card=card, record=record)
        return
    if pending_achievement:
        return
    achievement = tactical_secondary_achievement_context_from_award(
        state=state,
        card=card,
        record=record,
        award=award,
    )
    state.record_tactical_secondary_achievement_context(achievement)
    _mark_card_record_resolved(state=state, card=card, record=record)


def _already_awarded_at_record(
    *,
    state: GameState,
    card: SecondaryMissionCardState,
    record: ObjectiveControlRecord,
    source_kind: VictoryPointSourceKind,
) -> bool:
    from warhammer40k_core.engine.secondary_scoring_inventory import (
        canonical_secondary_mission_id,
    )

    ledger = state.victory_point_ledger_for_player(card.player_id)
    card_source_id = canonical_secondary_mission_id(card.secondary_mission_id)
    for transaction in ledger.transactions:
        if transaction.source_kind is not source_kind:
            continue
        if canonical_secondary_mission_id(transaction.source_id) != card_source_id:
            continue
        metadata = transaction.metadata
        if not isinstance(metadata, dict):
            continue
        record_id = metadata.get("objective_control_record_id")
        if record_id == record.record_id:
            return True
    return False


def _selection_for_card(card: SecondaryMissionCardState) -> SecondaryMissionSelection | None:
    return secondary_mission_selection_from_json(card.selection_payload)


def _mark_card_record_resolved(
    *,
    state: GameState,
    card: SecondaryMissionCardState,
    record: ObjectiveControlRecord,
) -> None:
    selection = _selection_for_card(card) or SecondaryMissionSelection()
    updated = card.with_selection(selection.with_resolved_record(record.record_id))
    state.replace_secondary_mission_card_state(updated)


__all__ = (
    "next_pending_tactical_secondary_achievement",
    "score_turn_end_mission_scoring_boundary",
)
