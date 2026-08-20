from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.missions import MissionActionDefinition
from warhammer40k_core.engine.actions import MissionActionState, MissionActionStatus
from warhammer40k_core.engine.mission_scoring_evidence_validation import (
    validate_secondary_objective_cleanse_action_link,
    validate_secondary_terrain_plunder_action_link,
)
from warhammer40k_core.engine.missions import (
    mission_pack_for_id,
    mission_scoring_policies_from_setup,
)
from warhammer40k_core.engine.objective_control import ObjectiveControlRecord
from warhammer40k_core.engine.objective_control_record_authority import (
    ObjectiveControlRecordAuthority,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_destruction_evidence import (
    PrimaryUnattributedDestructionCause,
)
from warhammer40k_core.engine.primary_mission_boundary_checkpoint import (
    active_secondary_mission_card_states_from_checkpoint,
    completed_mission_action_states_from_checkpoint,
    primary_unit_destruction_states_from_checkpoint,
    starting_strength_records_from_checkpoint,
)
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PrimaryMissionBoundaryCheckpoint,
)
from warhammer40k_core.engine.primary_mission_boundary_state import (
    primary_mission_boundary_state_from_checkpoint,
)
from warhammer40k_core.engine.primary_scoring_history_evidence import (
    primary_unit_destruction_state_ids_for_boundary,
    primary_unit_destruction_states_for_evidence,
)
from warhammer40k_core.engine.reserves import ReserveStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies
from warhammer40k_core.engine.scoring import (
    PrimaryUnitDestructionState,
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryObjectiveCleanseState,
    SecondaryTerrainPlunderState,
    VictoryPointSourceKind,
)
from warhammer40k_core.engine.secondary_deployment_zone_evidence import (
    enemy_unit_ids_in_player_deployment_zone_from_model_placements,
)
from warhammer40k_core.engine.secondary_mission_selection import (
    secondary_mission_selection_from_json,
)
from warhammer40k_core.engine.secondary_scoring_conditions import (
    SecondaryScoringConditionContext,
)
from warhammer40k_core.engine.secondary_scoring_occupancy import (
    build_secondary_battlefield_occupancy,
)
from warhammer40k_core.engine.secondary_scoring_state_evidence import (
    SecondaryScoringStateEvidence,
    build_secondary_scoring_state_evidence,
)
from warhammer40k_core.engine.secondary_unit_destruction_tracking import (
    secondary_unit_destruction_from_primary,
)
from warhammer40k_core.engine.unit_state import StartingStrengthRecord

if TYPE_CHECKING:
    from warhammer40k_core.engine.battlefield_state import ModelPlacement
    from warhammer40k_core.engine.game_state import GameState


_CLEANSE_TARGET_POLICY = "objective_marker"
_PLUNDER_TARGET_POLICY = "plunderable_terrain_area"


def validate_secondary_scoring_state_evidence_authority(
    evidence: SecondaryScoringStateEvidence,
    *,
    state: GameState,
) -> None:
    """Rebuild every rule-relevant Secondary fact from independent boundary authority."""

    from warhammer40k_core.engine.game_state import GameState

    if type(evidence) is not SecondaryScoringStateEvidence:
        raise GameLifecycleError("Secondary scoring authority requires typed evidence.")
    if type(state) is not GameState:
        raise GameLifecycleError("Secondary scoring authority requires GameState.")
    if state.mission_setup is None:
        raise GameLifecycleError("Secondary scoring authority requires MissionSetup.")

    record = _objective_control_record_for_evidence(evidence=evidence, state=state)
    authority = _objective_control_record_authority(record=record, state=state)
    if not authority.boundary_checkpoint.has_secondary_scoring_authority_witnesses:
        raise GameLifecycleError(
            "Secondary scoring evidence lacks complete boundary authority witnesses."
        )
    boundary_state = primary_mission_boundary_state_from_checkpoint(
        state=state,
        checkpoint=authority.boundary_checkpoint,
    )
    card = _active_card_for_evidence(
        evidence=evidence,
        authority=authority,
    )
    selection = secondary_mission_selection_from_json(card.selection_payload)
    placements = _model_placements(boundary_state)
    occupancy = build_secondary_battlefield_occupancy(
        state=boundary_state,
        player_id=card.player_id,
        record=record,
        selection=selection,
        model_placements=placements,
    )
    player_zones = tuple(
        zone for zone in state.mission_setup.deployment_zones if zone.player_id == card.player_id
    )
    enemy_zone_ids = (
        ()
        if not player_zones
        else enemy_unit_ids_in_player_deployment_zone_from_model_placements(
            state=boundary_state,
            player_id=card.player_id,
            model_placements=placements,
        )
    )
    ordinary_destruction_ids = primary_unit_destruction_state_ids_for_boundary(
        state=state,
        record=record,
        end_of_battle=False,
    )
    checkpoint_primary_destructions = primary_unit_destruction_states_from_checkpoint(
        authority.boundary_checkpoint
    )
    checkpoint_destruction_ids = tuple(
        destruction.destruction_id for destruction in checkpoint_primary_destructions
    )
    current_checkpoint_destructions = primary_unit_destruction_states_for_evidence(
        state=state,
        destruction_state_ids=checkpoint_destruction_ids,
    )
    if checkpoint_primary_destructions != current_checkpoint_destructions:
        raise GameLifecycleError(
            "Secondary scoring state evidence drifted from authoritative boundary state."
        )
    all_destruction_ids = primary_unit_destruction_state_ids_for_boundary(
        state=state,
        record=record,
        end_of_battle=True,
    )
    all_current_primary_destructions = primary_unit_destruction_states_for_evidence(
        state=state,
        destruction_state_ids=all_destruction_ids,
    )
    if not set(checkpoint_destruction_ids) <= set(all_destruction_ids):
        raise GameLifecycleError(
            "Secondary scoring state evidence drifted from authoritative boundary state."
        )
    current_ordinary_destructions = primary_unit_destruction_states_for_evidence(
        state=state,
        destruction_state_ids=ordinary_destruction_ids,
    )
    ordinary_destruction_id_set = set(ordinary_destruction_ids)
    checkpoint_ordinary_destructions = tuple(
        destruction
        for destruction in checkpoint_primary_destructions
        if destruction.destruction_id in ordinary_destruction_id_set
    )
    if checkpoint_ordinary_destructions != current_ordinary_destructions:
        raise GameLifecycleError(
            "Secondary scoring state evidence drifted from authoritative boundary state."
        )
    same_boundary_reserve_destructions = tuple(
        destruction
        for destruction in all_current_primary_destructions
        if destruction.destruction_id not in ordinary_destruction_id_set
    )
    _validate_same_boundary_reserve_destructions(
        state=state,
        record=record,
        checkpoint=authority.boundary_checkpoint,
        checkpoint_destruction_ids=checkpoint_destruction_ids,
        destructions=same_boundary_reserve_destructions,
    )
    authoritative_primary_destructions = checkpoint_primary_destructions
    destructions = tuple(
        sorted(
            (
                secondary_unit_destruction_from_primary(
                    state=boundary_state,
                    primary_destruction=primary,
                )
                for primary in authoritative_primary_destructions
            ),
            key=lambda row: row.destruction_id,
        )
    )
    authoritative_primary_ids = {
        destruction.destruction_id for destruction in authoritative_primary_destructions
    }
    current_secondary_projections = tuple(
        sorted(
            (
                destruction
                for destruction in state.secondary_unit_destruction_states
                if destruction.source_primary_destruction_id in authoritative_primary_ids
            ),
            key=lambda row: row.destruction_id,
        )
    )
    if destructions != current_secondary_projections:
        raise GameLifecycleError(
            "Secondary scoring state evidence drifted from authoritative boundary state."
        )
    cleanses, plunders = _secondary_mission_action_projections_for_boundary(
        state=state,
        record=record,
        checkpoint=authority.boundary_checkpoint,
    )
    starting_strength_records = _starting_strength_records_for_boundary(
        boundary_state=boundary_state,
        checkpoint=authority.boundary_checkpoint,
    )
    policies = mission_scoring_policies_from_setup(state.mission_setup)
    player_policy = policies.policy_for_player(card.player_id)
    context = SecondaryScoringConditionContext(
        record=record,
        mission_setup=state.mission_setup,
        player_id=card.player_id,
        unit_destruction_states=destructions,
        objective_cleanse_states=cleanses,
        terrain_plunder_states=plunders,
        enemy_unit_ids_in_player_deployment_zone=enemy_zone_ids,
        starting_strength_records=starting_strength_records,
        occupancy=occupancy,
        game_length_battle_rounds=player_policy.game_length_battle_rounds,
    )
    award = policies.secondary_award_from_mission_state(
        player_id=card.player_id,
        battle_round=record.battle_round,
        phase=record.phase,
        secondary_mission_id=card.secondary_mission_id,
        source_kind=_source_kind(card.mode),
        hidden=False,
        record=record,
        mission_setup=state.mission_setup,
        unit_destruction_states=destructions,
        objective_cleanse_states=cleanses,
        terrain_plunder_states=plunders,
        enemy_unit_ids_in_player_deployment_zone=enemy_zone_ids,
        starting_strength_records=starting_strength_records,
        condition_context=context,
    )
    if award is None:
        raise GameLifecycleError(
            "Secondary scoring state evidence drifted from authoritative boundary state."
        )
    expected = build_secondary_scoring_state_evidence(
        state=state,
        card=card,
        record=record,
        context=context,
        award=award,
    )
    if evidence != expected:
        raise GameLifecycleError(
            "Secondary scoring state evidence drifted from authoritative boundary state."
        )


def validate_secondary_scoring_state_evidence_records_authority(
    records: object,
    *,
    state: GameState,
) -> None:
    if not isinstance(records, list):
        raise GameLifecycleError("Secondary scoring authority records must be a list.")
    for evidence in cast(list[object], records):
        if type(evidence) is not SecondaryScoringStateEvidence:
            raise GameLifecycleError(
                "Secondary scoring authority records must contain typed evidence."
            )
        validate_secondary_scoring_state_evidence_authority(evidence, state=state)


def _objective_control_record_for_evidence(
    *,
    evidence: SecondaryScoringStateEvidence,
    state: GameState,
) -> ObjectiveControlRecord:
    matches = tuple(
        record
        for record in state.objective_control_records
        if record.record_id == evidence.objective_control_record_id
    )
    if len(matches) != 1:
        raise GameLifecycleError(
            "Secondary scoring evidence requires one authoritative ObjectiveControlRecord."
        )
    return matches[0]


def _objective_control_record_authority(
    *,
    record: ObjectiveControlRecord,
    state: GameState,
) -> ObjectiveControlRecordAuthority:
    matches = tuple(
        authority
        for authority in state.objective_control_record_authorities
        if authority.objective_control_record_id == record.record_id
    )
    if len(matches) != 1:
        raise GameLifecycleError(
            "Secondary scoring evidence requires one ObjectiveControlRecord authority."
        )
    authority = matches[0]
    if type(authority) is not ObjectiveControlRecordAuthority:
        raise GameLifecycleError(
            "Secondary scoring evidence requires typed ObjectiveControlRecord authority."
        )
    return authority


def _active_card_for_evidence(
    *,
    evidence: SecondaryScoringStateEvidence,
    authority: ObjectiveControlRecordAuthority,
) -> SecondaryMissionCardState:
    cards = active_secondary_mission_card_states_from_checkpoint(authority.boundary_checkpoint)
    player_cards = tuple(card for card in cards if card.player_id == evidence.scoring_player_id)
    mission_cards = tuple(
        card for card in player_cards if card.secondary_mission_id == evidence.secondary_mission_id
    )
    if not mission_cards:
        raise GameLifecycleError("Secondary scoring evidence mission identity drifted.")
    mode_cards = tuple(card for card in mission_cards if card.mode is evidence.card_mode)
    if not mode_cards:
        raise GameLifecycleError("Secondary scoring evidence card mode drifted.")
    matches = tuple(card for card in mode_cards if card.battle_round == evidence.card_battle_round)
    if not matches:
        raise GameLifecycleError("Secondary scoring evidence card battle round drifted.")
    if len(matches) != 1:
        raise GameLifecycleError(
            "Secondary scoring evidence lacks immutable active-card boundary authority."
        )
    return matches[0]


def _model_placements(state: GameState) -> tuple[ModelPlacement, ...]:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Secondary scoring authority requires battlefield state.")
    return tuple(
        placement
        for army in battlefield.placed_armies
        for unit in army.unit_placements
        for placement in unit.model_placements
    )


def _starting_strength_records_for_boundary(
    *,
    boundary_state: GameState,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> tuple[StartingStrengthRecord, ...]:
    from warhammer40k_core.engine.game_state import starting_strength_records_for_army

    static_records = starting_strength_records_from_checkpoint(checkpoint)
    registered_records = tuple(
        sorted(
            boundary_state.starting_strength_records,
            key=lambda record: record.unit_instance_id,
        )
    )
    if static_records != registered_records:
        raise GameLifecycleError(
            "Secondary scoring state evidence drifted from authoritative boundary state."
        )
    static_source_by_unit_id = {
        record.unit_instance_id: record.source_id for record in static_records
    }
    derived_records = tuple(
        sorted(
            (
                replace(
                    record,
                    source_id=static_source_by_unit_id.get(
                        record.unit_instance_id,
                        record.source_id,
                    ),
                )
                for army in boundary_state.army_definitions
                for record in starting_strength_records_for_army(army)
            ),
            key=lambda record: record.unit_instance_id,
        )
    )
    if static_records != derived_records:
        raise GameLifecycleError(
            "Secondary scoring state evidence drifted from authoritative boundary state."
        )
    return static_records


def _validate_same_boundary_reserve_destructions(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
    checkpoint_destruction_ids: tuple[str, ...],
    destructions: tuple[PrimaryUnitDestructionState, ...],
) -> None:
    presence_by_model_id = {
        model.model_instance_id: model.presence for model in checkpoint.model_states
    }
    checkpoint_destruction_id_set = set(checkpoint_destruction_ids)
    checkpoint_destroyed_unit_ids = {
        destruction.destroyed_unit_instance_id
        for destruction in destructions
        if destruction.destruction_id in checkpoint_destruction_id_set
    }
    route_authorities_by_unit_id: dict[str, list[tuple[str, str]]] = {}
    for reserve in state.reserve_states:
        if (
            reserve.status is not ReserveStatus.DESTROYED
            or reserve.destroyed_battle_round != record.battle_round
        ):
            continue
        policy = reserve.destruction_deadline_policy
        if policy.applies_at(battle_round=record.battle_round, end_of_battle=False):
            boundary_kind = "round-boundary"
        elif policy.applies_at(battle_round=record.battle_round, end_of_battle=True):
            boundary_kind = "end-of-battle"
        else:
            continue
        mutation_id = f"{policy.source_id}:round-{record.battle_round:02d}:{boundary_kind}"
        reserve_view = rules_unit_view_from_armies(
            armies=tuple(state.army_definitions),
            unit_instance_id=reserve.unit_instance_id,
        )
        route_views = (
            reserve_view,
            *(
                rules_unit_view_from_armies(
                    armies=tuple(state.army_definitions),
                    unit_instance_id=unit_id,
                )
                for unit_id in reserve.embarked_unit_instance_ids
            ),
        )
        for index, view in enumerate(route_views):
            # Reserve-deadline destruction retires the route without rewriting model wounds,
            # so a checkpoint captured afterward records living models as off-battlefield.
            expected_presence = (
                "off_battlefield"
                if view.unit_instance_id in checkpoint_destroyed_unit_ids
                else ("reserves" if index == 0 else "embarked")
            )
            if view.owner_player_id != reserve.player_id or any(
                presence_by_model_id.get(model.model_instance_id) != expected_presence
                for model in view.own_models
            ):
                raise GameLifecycleError(
                    "Secondary scoring state evidence drifted from authoritative boundary state."
                )
            route_authorities_by_unit_id.setdefault(view.unit_instance_id, []).append(
                (reserve.player_id, mutation_id)
            )
    if len({row.destroyed_unit_instance_id for row in destructions}) != len(destructions):
        raise GameLifecycleError(
            "Secondary scoring state evidence drifted from authoritative boundary state."
        )
    for destruction in destructions:
        unit_id = destruction.destroyed_unit_instance_id
        candidates = route_authorities_by_unit_id.get(unit_id, [])
        if len(candidates) != 1:
            raise GameLifecycleError(
                "Secondary scoring state evidence drifted from authoritative boundary state."
            )
        destroyed_player_id, mutation_id = candidates[0]
        if (
            destruction.unattributed_cause
            is not PrimaryUnattributedDestructionCause.RESERVE_DEADLINE
            or destruction.source_mutation_id != mutation_id
            or destruction.source_id != f"{mutation_id}:{unit_id}"
            or destruction.destroyed_player_id != destroyed_player_id
            or destruction.active_player_id != record.active_player_id
            or destruction.battle_round != record.battle_round
            or destruction.phase != record.phase
            or destruction.started_turn_terrain_feature_ids
            or destruction.started_turn_objective_marker_ids
        ):
            raise GameLifecycleError(
                "Secondary scoring state evidence drifted from authoritative boundary state."
            )


def _secondary_mission_action_projections_for_boundary(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> tuple[
    tuple[SecondaryObjectiveCleanseState, ...],
    tuple[SecondaryTerrainPlunderState, ...],
]:
    mission_setup = state.mission_setup
    if mission_setup is None:
        raise GameLifecycleError("Secondary scoring Action authority requires MissionSetup.")
    mission_pack = mission_pack_for_id(mission_setup.mission_pack_id)
    source_by_action_id = {
        source.mission_action_id: source
        for source in mission_pack.mission_actions
        if source.mission_kind == "secondary"
        and (
            (source.target_policy, source.scoring_source_id)
            in {
                (_CLEANSE_TARGET_POLICY, "cleanse"),
                (_PLUNDER_TARGET_POLICY, "plunder"),
            }
        )
    }
    record_key = _boundary_key(
        label="Secondary scoring ObjectiveControlRecord",
        battle_round=record.battle_round,
        active_player_id=record.active_player_id,
        phase=record.phase,
        state=state,
    )
    completed_at_boundary = completed_mission_action_states_from_checkpoint(checkpoint)
    relevant_at_boundary = tuple(
        action
        for action in completed_at_boundary
        if action.mission_action_id in source_by_action_id
    )
    current_relevant = tuple(
        sorted(
            (
                action
                for action in state.mission_action_states
                if action.mission_action_id in source_by_action_id
                and action.status is MissionActionStatus.COMPLETED
                and _completed_action_boundary_key(action=action, state=state) <= record_key
            ),
            key=lambda action: action.action_id,
        )
    )
    if relevant_at_boundary != current_relevant:
        raise GameLifecycleError(
            "Secondary scoring state evidence drifted from authoritative boundary state."
        )
    cleanses: list[SecondaryObjectiveCleanseState] = []
    plunders: list[SecondaryTerrainPlunderState] = []
    for action in relevant_at_boundary:
        source = source_by_action_id.get(action.mission_action_id)
        if source is None:
            raise GameLifecycleError("Secondary scoring Action source authority is incomplete.")
        completed_round = action.completed_battle_round
        completed_phase = action.completed_phase
        if completed_round is None or completed_phase is None:
            raise GameLifecycleError(
                "Secondary scoring Action authority requires completed timing."
            )
        if _completed_action_boundary_key(action=action, state=state) > record_key:
            raise GameLifecycleError(
                "Secondary scoring Action witness comes from a future boundary."
            )
        _validate_completed_action_source(action=action, source=source)
        if source.target_policy == _CLEANSE_TARGET_POLICY:
            cleanse = SecondaryObjectiveCleanseState(
                cleanse_id=(
                    f"secondary-objective-cleanse:{state.game_id}:"
                    f"round-{completed_round:02d}:{action.player_id}:{action.target_id}"
                ),
                game_id=state.game_id,
                player_id=action.player_id,
                active_player_id=action.player_id,
                battle_round=completed_round,
                phase=completed_phase,
                objective_marker_id=action.target_id,
                action_id=action.action_id,
                source_id=source.source_id,
            )
            validate_secondary_objective_cleanse_action_link(
                cleanse,
                mission_setup=mission_setup,
                mission_action_states=state.mission_action_states,
            )
            cleanses.append(cleanse)
            continue
        plunder = SecondaryTerrainPlunderState(
            plunder_id=(
                f"secondary-terrain-plunder:{state.game_id}:"
                f"round-{completed_round:02d}:{action.player_id}:{action.target_id}"
            ),
            game_id=state.game_id,
            player_id=action.player_id,
            active_player_id=action.player_id,
            battle_round=completed_round,
            phase=completed_phase,
            terrain_feature_id=action.target_id,
            action_id=action.action_id,
            source_id=source.source_id,
        )
        validate_secondary_terrain_plunder_action_link(
            plunder,
            mission_setup=mission_setup,
            mission_action_states=state.mission_action_states,
        )
        plunders.append(plunder)
    return (
        tuple(sorted(cleanses, key=lambda row: row.cleanse_id)),
        tuple(sorted(plunders, key=lambda row: row.plunder_id)),
    )


def _completed_action_boundary_key(
    *,
    action: MissionActionState,
    state: GameState,
) -> tuple[int, int, int]:
    if type(action) is not MissionActionState:
        raise GameLifecycleError("Secondary scoring Action authority requires typed states.")
    if (
        action.status is not MissionActionStatus.COMPLETED
        or action.completed_battle_round is None
        or action.completed_phase is None
    ):
        raise GameLifecycleError("Secondary scoring Action authority requires completed timing.")
    return _boundary_key(
        label="Secondary scoring completed Mission Action",
        battle_round=action.completed_battle_round,
        active_player_id=action.player_id,
        phase=action.completed_phase,
        state=state,
    )


def _validate_completed_action_source(
    *,
    action: MissionActionState,
    source: MissionActionDefinition,
) -> None:
    if (
        action.mission_id != source.mission_id
        or action.phase_started != source.start_phase
        or action.start_timing != source.start_timing
        or action.completion_timing != source.completion_timing
        or action.interruption_conditions != source.interruption_conditions
        or action.scoring_source_id != source.scoring_source_id
        or action.victory_points != source.victory_points
        or action.victory_points != 0
        or action.score_transaction_id is not None
    ):
        raise GameLifecycleError(
            "Secondary scoring completed Action drifted from source authority."
        )


def _boundary_key(
    *,
    label: str,
    battle_round: int,
    active_player_id: str,
    phase: str,
    state: GameState,
) -> tuple[int, int, int]:
    if type(battle_round) is not int or battle_round < 1:
        raise GameLifecycleError(f"{label} battle_round must be positive.")
    if active_player_id not in state.turn_order:
        raise GameLifecycleError(f"{label} active player is unknown.")
    phases = tuple(value.value for value in state.battle_phase_sequence)
    if phase not in phases:
        raise GameLifecycleError(f"{label} battle phase is unknown.")
    return (
        battle_round,
        state.turn_order.index(active_player_id),
        phases.index(phase),
    )


def _source_kind(mode: SecondaryMissionCardMode) -> VictoryPointSourceKind:
    if mode is SecondaryMissionCardMode.FIXED:
        return VictoryPointSourceKind.FIXED_SECONDARY
    if mode is SecondaryMissionCardMode.TACTICAL:
        return VictoryPointSourceKind.TACTICAL_SECONDARY
    raise GameLifecycleError("Secondary scoring card mode is unsupported.")


__all__ = (
    "validate_secondary_scoring_state_evidence_authority",
    "validate_secondary_scoring_state_evidence_records_authority",
)
