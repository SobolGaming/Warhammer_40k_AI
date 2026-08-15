from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.mission_terrain import (
    logical_terrain_area_within_player_deployment_zone,
    mission_logical_terrain_areas,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlResult,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_turn_start_evidence import (
    PrimaryRulesUnitTurnStartMembership,
    PrimaryRulesUnitTurnStartSnapshot,
)
from warhammer40k_core.engine.rules_units import rules_unit_views_from_armies
from warhammer40k_core.engine.scoring import PrimaryObjectiveTurnStartState

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


PunishmentCandidatePresenceContext = Literal["live_request", "historical_restore"]


@dataclass(frozen=True, slots=True)
class LocateAndDenyChoicePolicy:
    eligible_terrain_area_ids: tuple[str, ...]
    evidence_terrain_area_ids: tuple[str, ...]
    selection_count: int


@dataclass(frozen=True, slots=True)
class PunishmentChoicePolicy:
    candidate_rules_unit_instance_ids: tuple[str, ...]
    candidate_evidence_ids: tuple[str, ...]
    used_fallback_candidates: bool


def resolve_locate_and_deny_choice_policy(
    *,
    mission_setup: MissionSetup,
    player_id: str,
    maximum_selections: int,
) -> LocateAndDenyChoicePolicy:
    if type(mission_setup) is not MissionSetup:
        raise GameLifecycleError("Locate and Deny policy requires MissionSetup.")
    if player_id not in {
        mission_setup.attacker_player_id,
        mission_setup.defender_player_id,
    }:
        raise GameLifecycleError("Locate and Deny policy player is not in MissionSetup.")
    if type(maximum_selections) is not int or maximum_selections < 1:
        raise GameLifecycleError("Locate and Deny maximum selections must be positive.")
    eligible_ids = tuple(
        area.logical_terrain_area_id
        for area in mission_logical_terrain_areas(mission_setup)
        if not logical_terrain_area_within_player_deployment_zone(
            area,
            mission_setup=mission_setup,
            player_id=player_id,
        )
    )
    return LocateAndDenyChoicePolicy(
        eligible_terrain_area_ids=eligible_ids,
        evidence_terrain_area_ids=tuple(
            area.terrain_area_id for area in mission_setup.terrain_areas
        ),
        selection_count=min(maximum_selections, len(eligible_ids)),
    )


def resolve_punishment_choice_policy(
    *,
    state: GameState,
    player_id: str,
    battle_round: int,
    candidate_presence_context: PunishmentCandidatePresenceContext,
) -> PunishmentChoicePolicy:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Punishment policy requires GameState.")
    if player_id not in state.player_ids:
        raise GameLifecycleError("Punishment policy player is not in this game.")
    if type(battle_round) is not int or battle_round < 1:
        raise GameLifecycleError("Punishment policy battle round must be positive.")
    if candidate_presence_context not in {"live_request", "historical_restore"}:
        raise GameLifecycleError("Punishment candidate presence context is unsupported.")
    turn_start_state = _turn_start_objective_state(
        state=state,
        player_id=player_id,
        battle_round=battle_round,
    )
    turn_start_snapshot = _turn_start_position_snapshot(
        state=state,
        player_id=player_id,
        battle_round=battle_round,
    )
    battlefield_enemy_ids = _battlefield_enemy_rules_unit_ids(
        state=state,
        player_id=player_id,
        snapshot=turn_start_snapshot,
    )
    if candidate_presence_context == "live_request":
        battlefield_enemy_ids = _currently_present_rules_unit_ids(
            state=state,
            candidate_ids=battlefield_enemy_ids,
            snapshot=turn_start_snapshot,
        )
    objective_candidate_ids = _objective_range_enemy_ids(
        state=state,
        player_id=player_id,
        enemy_ids=battlefield_enemy_ids,
        record=turn_start_state.source_objective_control_record,
        snapshot=turn_start_snapshot,
    )
    destruction_ids_by_candidate = _previous_turn_destroyer_evidence(
        state=state,
        player_id=player_id,
        battle_round=battle_round,
        enemy_ids=battlefield_enemy_ids,
        snapshot=turn_start_snapshot,
    )
    preferred_ids = tuple(sorted(set(objective_candidate_ids).union(destruction_ids_by_candidate)))
    used_fallback = not preferred_ids and bool(battlefield_enemy_ids)
    candidate_ids = battlefield_enemy_ids if used_fallback else preferred_ids
    evidence_ids = tuple(
        sorted(
            {
                turn_start_state.state_id,
                turn_start_state.source_objective_control_record.record_id,
                turn_start_snapshot.snapshot_id,
                *(
                    destruction_id
                    for ids in destruction_ids_by_candidate.values()
                    for destruction_id in ids
                ),
            }
        )
    )
    return PunishmentChoicePolicy(
        candidate_rules_unit_instance_ids=candidate_ids,
        candidate_evidence_ids=evidence_ids,
        used_fallback_candidates=used_fallback,
    )


def _turn_start_objective_state(
    *,
    state: GameState,
    player_id: str,
    battle_round: int,
) -> PrimaryObjectiveTurnStartState:
    matches = tuple(
        evidence
        for evidence in state.primary_objective_turn_start_states
        if evidence.player_id == player_id
        and evidence.active_player_id == player_id
        and evidence.battle_round == battle_round
    )
    if len(matches) != 1:
        raise GameLifecycleError(
            "Punishment requires exactly one owner turn-start objective-control record."
        )
    return matches[0]


def _turn_start_position_snapshot(
    *,
    state: GameState,
    player_id: str,
    battle_round: int,
) -> PrimaryRulesUnitTurnStartSnapshot:
    matches = tuple(
        snapshot
        for snapshot in state.primary_rules_unit_turn_start_snapshots
        if snapshot.game_id == state.game_id
        and snapshot.active_player_id == player_id
        and snapshot.battle_round == battle_round
    )
    if len(matches) != 1:
        raise GameLifecycleError(
            "Punishment requires exactly one owner turn-start rules-unit snapshot."
        )
    return matches[0]


def _battlefield_enemy_rules_unit_ids(
    *,
    state: GameState,
    player_id: str,
    snapshot: PrimaryRulesUnitTurnStartSnapshot,
) -> tuple[str, ...]:
    owner_by_component_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    return tuple(
        sorted(
            membership.rules_unit_instance_id
            for membership in snapshot.rules_unit_memberships
            if _membership_owner(
                membership=membership,
                owner_by_component_id=owner_by_component_id,
            )
            != player_id
            and membership.evaluated_model_instance_ids
        )
    )


def _membership_owner(
    *,
    membership: PrimaryRulesUnitTurnStartMembership,
    owner_by_component_id: dict[str, str],
) -> str:
    if any(
        component_id not in owner_by_component_id
        for component_id in membership.component_unit_instance_ids
    ):
        raise GameLifecycleError("Punishment turn-start membership ownership drifted.")
    owners = {
        owner_by_component_id[component_id]
        for component_id in membership.component_unit_instance_ids
    }
    if len(owners) != 1:
        raise GameLifecycleError("Punishment turn-start membership ownership drifted.")
    return next(iter(owners))


def _currently_present_rules_unit_ids(
    *,
    state: GameState,
    candidate_ids: tuple[str, ...],
    snapshot: PrimaryRulesUnitTurnStartSnapshot,
) -> tuple[str, ...]:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Live Punishment policy requires battlefield state.")
    membership_by_id = {
        membership.rules_unit_instance_id: membership
        for membership in snapshot.rules_unit_memberships
    }
    current_view_by_id = {
        view.unit_instance_id: view
        for view in rules_unit_views_from_armies(armies=tuple(state.army_definitions))
    }
    placed_model_ids = set(battlefield.placed_model_ids())
    present_ids: list[str] = []
    for candidate_id in candidate_ids:
        membership = membership_by_id.get(candidate_id)
        if membership is None:
            raise GameLifecycleError("Live Punishment candidate has no turn-start membership.")
        current_view = current_view_by_id.get(candidate_id)
        if (
            current_view is not None
            and current_view.component_unit_instance_ids == membership.component_unit_instance_ids
            and any(
                model.is_alive and model.model_instance_id in placed_model_ids
                for model in current_view.own_models
            )
        ):
            present_ids.append(candidate_id)
    return tuple(present_ids)


def _objective_range_enemy_ids(
    *,
    state: GameState,
    player_id: str,
    enemy_ids: tuple[str, ...],
    record: ObjectiveControlRecord,
    snapshot: PrimaryRulesUnitTurnStartSnapshot,
) -> tuple[str, ...]:
    enemy_id_set = set(enemy_ids)
    owner_by_component_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    candidates = {
        membership.rules_unit_instance_id
        for membership in snapshot.rules_unit_memberships
        if membership.rules_unit_instance_id in enemy_id_set
        and (
            owner := _membership_owner(
                membership=membership,
                owner_by_component_id=owner_by_component_id,
            )
        )
        != player_id
        and any(
            _result_has_rules_unit(
                result=result,
                membership=membership,
                owner_player_id=owner,
            )
            for result in record.results
        )
    }
    return tuple(sorted(candidates))


def _result_has_rules_unit(
    *,
    result: ObjectiveControlResult,
    membership: PrimaryRulesUnitTurnStartMembership,
    owner_player_id: str,
) -> bool:
    component_ids = set(membership.component_unit_instance_ids)
    model_ids = set(membership.evaluated_model_instance_ids)
    return any(
        contribution.player_id == owner_player_id
        and contribution.unit_instance_id in component_ids
        and contribution.model_instance_id in model_ids
        for contribution in result.contributors
    )


def _previous_turn_destroyer_evidence(
    *,
    state: GameState,
    player_id: str,
    battle_round: int,
    enemy_ids: tuple[str, ...],
    snapshot: PrimaryRulesUnitTurnStartSnapshot,
) -> dict[str, tuple[str, ...]]:
    previous_key = _previous_turn_key_or_none(
        turn_order=state.turn_order,
        player_id=player_id,
        battle_round=battle_round,
    )
    if previous_key is None:
        return {}
    enemy_id_set = set(enemy_ids)
    component_ids_by_identity = _component_ids_by_rules_unit_identity(state)
    evidence: dict[str, set[str]] = {}
    for destruction in state.primary_unit_destruction_states:
        attribution = destruction.destruction_attribution
        if (
            (destruction.battle_round, destruction.active_player_id) != previous_key
            or destruction.destroyed_player_id != player_id
            or destruction.destroying_player_id in {None, player_id}
            or attribution is None
            or attribution.source_rules_unit_instance_id is None
        ):
            continue
        source_component_ids = component_ids_by_identity.get(
            attribution.source_rules_unit_instance_id
        )
        if source_component_ids is None:
            raise GameLifecycleError(
                "Punishment destruction source has no known rules-unit lineage."
            )
        for membership in snapshot.rules_unit_memberships:
            if membership.rules_unit_instance_id in enemy_id_set and set(
                membership.component_unit_instance_ids
            ).intersection(source_component_ids):
                evidence.setdefault(membership.rules_unit_instance_id, set()).add(
                    destruction.destruction_id
                )
    return {
        unit_id: tuple(sorted(ids))
        for unit_id, ids in sorted(evidence.items(), key=lambda item: item[0])
    }


def _component_ids_by_rules_unit_identity(state: GameState) -> dict[str, frozenset[str]]:
    result = {
        unit.unit_instance_id: frozenset({unit.unit_instance_id})
        for army in state.army_definitions
        for unit in army.units
    }
    for army in state.army_definitions:
        for formation in army.attached_units:
            result[formation.attached_unit_instance_id] = frozenset(
                formation.component_unit_instance_ids
            )
    for record in state.starting_attached_unit_records:
        result[record.attached_unit_instance_id] = frozenset(record.component_unit_instance_ids)
    return result


def _previous_turn_key_or_none(
    *,
    turn_order: tuple[str, ...],
    player_id: str,
    battle_round: int,
) -> tuple[int, str] | None:
    player_index = turn_order.index(player_id)
    if player_index > 0:
        return battle_round, turn_order[player_index - 1]
    if battle_round == 1:
        return None
    return battle_round - 1, turn_order[-1]


__all__ = (
    "LocateAndDenyChoicePolicy",
    "PunishmentCandidatePresenceContext",
    "PunishmentChoicePolicy",
    "resolve_locate_and_deny_choice_policy",
    "resolve_punishment_choice_policy",
)
