from __future__ import annotations

import json
from copy import copy
from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.attributes import (
    Characteristic,
    CharacteristicValue,
    CharacteristicValuePayload,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attached_unit_formation import (
    AttachedUnitFormation,
    AttachedUnitFormationPayload,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    ModelPlacement,
    ModelPlacementPayload,
    PlacedArmy,
    UnitPlacement,
)
from warhammer40k_core.engine.effects import GENERIC_RULE_EFFECT_KIND, PersistingEffect
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.phases.movement_model import (
    AdvancedUnitState,
    AdvancedUnitStatePayload,
    FellBackUnitState,
    FellBackUnitStatePayload,
)
from warhammer40k_core.engine.phases.shooting_model import ShootingPhaseState
from warhammer40k_core.engine.primary_mission_action_battlefield_evidence import (
    MissionActionBattlefieldBoundaryEvidence,
)
from warhammer40k_core.engine.primary_mission_action_lifecycle_evidence import (
    MissionActionPriorUseEvidence,
    PrimaryMissionActionStartEvidence,
)
from warhammer40k_core.engine.primary_mission_action_request_authority import (
    validate_recomputed_primary_mission_action_request_authority,
)
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PrimaryMissionBoundaryCheckpoint,
    PrimaryMissionBoundaryModelState,
)
from warhammer40k_core.engine.primary_mission_state import PrimaryMissionMarkerState
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardMode,
    SecondaryMissionCardStatus,
)
from warhammer40k_core.engine.unit_factory import ModelInstance

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def validate_checkpoint_backed_primary_mission_action_start_authority(
    *,
    state: GameState,
    evidence: PrimaryMissionActionStartEvidence,
) -> None:
    authority = evidence.start_authority
    if authority.candidate_units or authority.terrain_model_inventory:
        raise GameLifecycleError(
            "Primary Mission Action checkpoint-backed request authority drifted."
        )
    if any(
        (
            authority.battle_shocked_unit_instance_ids,
            authority.advanced_unit_instance_ids,
            authority.fell_back_unit_instance_ids,
            authority.shot_unit_instance_ids,
            authority.active_secondary_mission_ids,
        )
    ):
        raise GameLifecycleError(
            "Primary Mission Action checkpoint-backed request authority drifted."
        )
    battlefield = state.battlefield_state
    if battlefield is None or authority.battlefield_boundary != (
        MissionActionBattlefieldBoundaryEvidence.from_battlefield_state(battlefield)
    ):
        raise GameLifecycleError(
            "Primary Mission Action checkpoint-backed battlefield authority drifted."
        )
    validate_recomputed_primary_mission_action_request_authority(
        state=state,
        evidence=evidence,
    )
    _validate_selected_option_authority(evidence=evidence)


def primary_mission_action_boundary_state_from_checkpoint(
    *,
    state: GameState,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> GameState:
    """Rebuild the Action-opportunity state from an engine boundary checkpoint."""

    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError(
            "Primary Mission Action checkpoint reconstruction requires GameState."
        )
    if type(checkpoint) is not PrimaryMissionBoundaryCheckpoint:
        raise GameLifecycleError("Primary Mission Action checkpoint reconstruction is invalid.")
    if checkpoint.boundary_kind != "action_request" or checkpoint.phase != (
        BattlePhase.SHOOTING.value
    ):
        raise GameLifecycleError(
            "Primary Mission Action checkpoint reconstruction requires an Action request."
        )
    battlefield = state.battlefield_state
    if battlefield is None or battlefield.battlefield_id != checkpoint.battlefield_id:
        raise GameLifecycleError(
            "Primary Mission Action checkpoint reconstruction battlefield drifted."
        )

    current_model_ids = {
        model.model_instance_id
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    rows_by_model_id = {row.model_instance_id: row for row in checkpoint.model_states}
    if set(rows_by_model_id) != current_model_ids:
        raise GameLifecycleError(
            "Primary Mission Action checkpoint reconstruction model inventory drifted."
        )

    formations = tuple(
        AttachedUnitFormation.from_payload(cast(AttachedUnitFormationPayload, _json_object(value)))
        for value in checkpoint.attached_unit_formation_jsons
    )
    owner_by_component_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    formations_by_player: dict[str, list[AttachedUnitFormation]] = {
        player_id: [] for player_id in state.player_ids
    }
    for formation in formations:
        owners = {
            owner_by_component_id.get(component_id)
            for component_id in formation.component_unit_instance_ids
        }
        if len(owners) != 1 or None in owners:
            raise GameLifecycleError(
                "Primary Mission Action checkpoint reconstruction attachment drifted."
            )
        owner = next(iter(owners))
        if owner is None:
            raise GameLifecycleError(
                "Primary Mission Action checkpoint reconstruction attachment drifted."
            )
        formations_by_player[owner].append(formation)

    rebuilt_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        rebuilt_armies.append(
            replace(
                army,
                units=tuple(
                    replace(
                        unit,
                        own_models=tuple(
                            _checkpoint_boundary_model(
                                model=model,
                                row=rows_by_model_id[model.model_instance_id],
                            )
                            for model in unit.own_models
                        ),
                    )
                    for unit in army.units
                ),
                attached_units=tuple(
                    sorted(
                        formations_by_player[army.player_id],
                        key=lambda row: row.attached_unit_instance_id,
                    )
                ),
            )
        )

    placements_by_unit: dict[tuple[str, str, str], list[ModelPlacement]] = {}
    for row in checkpoint.model_states:
        if row.model_placement_json is None:
            continue
        placement = ModelPlacement.from_payload(
            cast(ModelPlacementPayload, _json_object(row.model_placement_json))
        )
        placements_by_unit.setdefault(
            (placement.army_id, placement.player_id, placement.unit_instance_id), []
        ).append(placement)
    placed_armies: list[PlacedArmy] = []
    for army in rebuilt_armies:
        unit_placements = tuple(
            UnitPlacement(
                army_id=army_id,
                player_id=player_id,
                unit_instance_id=unit_id,
                model_placements=tuple(sorted(placements, key=lambda row: row.model_instance_id)),
            )
            for (army_id, player_id, unit_id), placements in sorted(placements_by_unit.items())
            if army_id == army.army_id
        )
        if unit_placements:
            placed_armies.append(
                PlacedArmy(
                    army_id=army.army_id,
                    player_id=army.player_id,
                    unit_placements=unit_placements,
                )
            )

    clone = copy(state)
    clone.army_definitions = rebuilt_armies
    clone.battlefield_state = BattlefieldRuntimeState(
        battlefield_id=battlefield.battlefield_id,
        battlefield_width_inches=battlefield.battlefield_width_inches,
        battlefield_depth_inches=battlefield.battlefield_depth_inches,
        placed_armies=tuple(placed_armies),
        terrain_features=battlefield.terrain_features,
        removed_model_ids=tuple(
            sorted(
                row.model_instance_id
                for row in checkpoint.model_states
                if row.presence == "destroyed"
            )
        ),
    )
    clone.primary_mission_progress_state = replace(
        clone.primary_mission_progress_state,
        markers=tuple(
            PrimaryMissionMarkerState.from_payload(_json_object(value))
            for value in checkpoint.active_primary_marker_jsons
        ),
    )
    clone.battle_shocked_unit_ids = list(checkpoint.battle_shocked_unit_instance_ids)
    clone.active_player_id = checkpoint.active_player_id
    clone.battle_round = checkpoint.battle_round
    clone.battle_phase_index = clone.battle_phase_sequence.index(BattlePhase.SHOOTING)
    clone.advanced_unit_states = [
        AdvancedUnitState.from_payload(cast(AdvancedUnitStatePayload, _json_object(value)))
        for value in checkpoint.advanced_unit_state_jsons
    ]
    clone.fell_back_unit_states = [
        FellBackUnitState.from_payload(cast(FellBackUnitStatePayload, _json_object(value)))
        for value in checkpoint.fell_back_unit_state_jsons
    ]
    clone.shooting_phase_state = ShootingPhaseState(
        battle_round=checkpoint.battle_round,
        active_player_id=checkpoint.active_player_id,
        shot_unit_ids=checkpoint.shot_unit_instance_ids,
    )
    clone.persisting_effects = [
        effect
        for effect in clone.persisting_effects
        if not _is_generic_objective_control_effect(effect)
    ]

    active_secondary_matches = {
        secondary_id: tuple(
            card
            for card in state.secondary_mission_card_states
            if card.player_id == checkpoint.player_id
            and card.secondary_mission_id == secondary_id
            and (
                card.mode is SecondaryMissionCardMode.FIXED
                or card.battle_round == checkpoint.battle_round
            )
        )
        for secondary_id in checkpoint.active_secondary_mission_ids
    }
    if any(len(matches) != 1 for matches in active_secondary_matches.values()):
        raise GameLifecycleError("Primary Mission Action checkpoint secondary inventory drifted.")
    clone.secondary_mission_card_states = [
        card
        for card in state.secondary_mission_card_states
        if card.player_id != checkpoint.player_id
    ] + [
        replace(
            active_secondary_matches[secondary_id][0],
            status=SecondaryMissionCardStatus.ACTIVE,
            scored_transaction_id=None,
            discarded_result_id=None,
        )
        for secondary_id in checkpoint.active_secondary_mission_ids
    ]

    prior_uses = tuple(
        MissionActionPriorUseEvidence.from_payload(_json_object(value))
        for value in checkpoint.mission_action_prior_use_jsons
    )
    current_action_by_id = {action.action_id: action for action in state.mission_action_states}
    if not {row.action_id for row in prior_uses} <= set(current_action_by_id):
        raise GameLifecycleError("Primary Mission Action checkpoint prior-use inventory drifted.")
    clone.mission_action_states = [
        replace(
            current_action_by_id[row.action_id],
            mission_action_id=row.mission_action_id,
            player_id=row.player_id,
            battle_round_started=row.battle_round_started,
            phase_started=row.phase_started,
            unit_instance_id=row.unit_instance_id,
            target_id=row.target_id,
        )
        for row in prior_uses
    ]
    prior_action_ids = {row.action_id for row in prior_uses}
    clone.primary_terrain_trap_states = [
        row for row in state.primary_terrain_trap_states if row.action_id in prior_action_ids
    ]
    clone.secondary_terrain_plunder_states = [
        row for row in state.secondary_terrain_plunder_states if row.action_id in prior_action_ids
    ]
    return clone


def _validate_selected_option_authority(*, evidence: PrimaryMissionActionStartEvidence) -> None:
    expected_option_id = (
        f"start:{evidence.mission_action_id}:{evidence.unit_instance_id}:{evidence.target_id}"
    )
    matches = tuple(
        option
        for option in evidence.start_authority.options
        if option.option_id == expected_option_id
    )
    if len(matches) != 1:
        raise GameLifecycleError(
            "Primary Mission Action selected checkpoint option authority drifted."
        )
    payload = _json_object(matches[0].payload_json)
    if (
        payload.get("mission_action_id") != evidence.mission_action_id
        or payload.get("unit_instance_id") != evidence.unit_instance_id
        or payload.get("target_id") != evidence.target_id
        or payload.get("condition_target_id") != evidence.condition_target_id
        or _json_string_tuple(payload, key="eligible_unit_instance_ids")
        != evidence.eligible_unit_instance_ids
    ):
        raise GameLifecycleError(
            "Primary Mission Action selected checkpoint option authority drifted."
        )


def _json_string_tuple(payload: dict[str, object], *, key: str) -> tuple[str, ...]:
    values = payload.get(key)
    if type(values) is not list:
        raise GameLifecycleError(
            "Primary Mission Action selected checkpoint option authority drifted."
        )
    raw_values = cast(list[object], values)
    if any(type(value) is not str for value in raw_values):
        raise GameLifecycleError(
            "Primary Mission Action selected checkpoint option authority drifted."
        )
    return tuple(sorted(cast(list[str], raw_values)))


def _checkpoint_boundary_model(
    *, model: ModelInstance, row: PrimaryMissionBoundaryModelState
) -> ModelInstance:
    resolved = CharacteristicValue.from_payload(
        cast(
            CharacteristicValuePayload,
            _json_object(row.resolved_objective_control_json),
        )
    )
    return replace(
        model,
        wounds_remaining=row.wounds_remaining,
        characteristics=tuple(
            resolved if value.characteristic is Characteristic.OBJECTIVE_CONTROL else value
            for value in model.characteristics
        ),
    )


def _is_generic_objective_control_effect(effect: PersistingEffect) -> bool:
    payload = effect.effect_payload
    if not isinstance(payload, dict) or payload.get("effect_kind") != GENERIC_RULE_EFFECT_KIND:
        return False
    raw_effect = payload.get("effect")
    if not isinstance(raw_effect, dict) or raw_effect.get("kind") != "modify_characteristic":
        return False
    parameters = raw_effect.get("parameters")
    if not isinstance(parameters, list):
        raise GameLifecycleError("Generic Objective Control effect parameters are invalid.")
    return any(
        isinstance(parameter, dict)
        and parameter.get("key") == "characteristic"
        and parameter.get("value") == "objective_control"
        for parameter in parameters
    )


def _json_object(value: str) -> dict[str, object]:
    decoded: object = json.loads(value)
    if type(decoded) is not dict:
        raise GameLifecycleError("Primary Mission Action boundary payload is invalid.")
    mapping = cast(dict[object, object], decoded)
    if any(type(key) is not str for key in mapping):
        raise GameLifecycleError("Primary Mission Action boundary payload is invalid.")
    return cast(dict[str, object], mapping)


__all__ = (
    "primary_mission_action_boundary_state_from_checkpoint",
    "validate_checkpoint_backed_primary_mission_action_start_authority",
)
