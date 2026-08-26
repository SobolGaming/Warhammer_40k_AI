from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from warhammer40k_core.core.missions import MissionActionDefinition, ObjectiveMarkerRole
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.actions import MissionActionState
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.mission_action_eligibility import (
    mission_action_unit_ineligibility_reason,
)
from warhammer40k_core.engine.mission_action_policies import (
    MissionActionPolicyDescriptor,
    mission_action_policy_descriptors,
)
from warhammer40k_core.engine.mission_terrain import (
    logical_terrain_area_within_player_territory,
    mission_logical_terrain_areas,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlTiming,
    model_objective_control_characteristic,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_destruction_evidence import (
    rules_unit_objective_proximity_witness,
)
from warhammer40k_core.engine.primary_mission_action_lifecycle_evidence import (
    PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_SCHEMA,
    PRIMARY_MISSION_ACTION_OBJECTIVE_CONTROL_EFFECTS,
    PRIMARY_MISSION_ACTION_START_EVIDENCE_SCHEMA,
    PRIMARY_MISSION_ACTION_SURVEIL_EFFECT,
    PRIMARY_MISSION_ACTION_VANGUARD_EFFECT,
    MissionActionPriorUseEvidence,
    MissionActionStartAuthorityEvidence,
    MissionActionSurveilTargetEvidence,
    MissionActionTerrainIntersectionEvidence,
    MissionActionTerrainModelInventoryEvidence,
    PrimaryMissionActionCompletionEvidence,
    PrimaryMissionActionStartEvidence,
    canonical_identifier_tuple,
    canonical_mission_action_prior_uses,
    require_primary_mission_game_state,
)
from warhammer40k_core.engine.primary_mission_action_start_authority import (
    capture_primary_mission_action_terrain_model_inventory,
    terrain_intersections_from_model_inventory,
    validate_primary_mission_action_start_authority,
    validate_primary_mission_action_terrain_model_inventory,
)
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PrimaryMissionBoundaryCheckpointReference,
)
from warhammer40k_core.engine.primary_mission_state import PrimaryMissionMarkerStatus
from warhammer40k_core.engine.primary_scoring_conditions import home_objective_ids
from warhammer40k_core.engine.primary_scoring_spatial_evidence import objective_control_record_hash
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_identities_share_lineage,
    rules_unit_identity_ids,
    rules_unit_is_battle_shocked,
    rules_unit_view_by_id,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.shooting_selection_range import target_within_shooting_selection_range
from warhammer40k_core.engine.shooting_targets import unit_has_line_of_sight_to_target
from warhammer40k_core.engine.shooting_terrain_visibility import (
    shooting_terrain_areas_for_state,
    shooting_visibility_cache_key,
)
from warhammer40k_core.engine.unit_factory import ModelInstance
from warhammer40k_core.engine.unit_proximity import unit_within_enemy_engagement_range

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


_validate_identifier = IdentifierValidator(GameLifecycleError)


def capture_primary_mission_action_start_evidence(
    *,
    state: GameState,
    player_id: str,
    action: MissionActionDefinition,
    policy: MissionActionPolicyDescriptor,
    unit_instance_id: str,
    target_id: str,
    condition_target_id: str | None,
    eligible_unit_instance_ids: tuple[str, ...],
    start_authority: MissionActionStartAuthorityEvidence,
    boundary_checkpoint: PrimaryMissionBoundaryCheckpointReference,
    boundary_terrain_model_inventory: tuple[MissionActionTerrainModelInventoryEvidence, ...],
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> PrimaryMissionActionStartEvidence:
    require_primary_mission_game_state(state)
    if state.active_player_id is None or state.current_battle_phase is None:
        raise GameLifecycleError("Primary Mission Action start evidence requires battle context.")
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    component_ids = tuple(sorted(rules_unit.component_unit_instance_ids))
    identity_ids = tuple(
        sorted(rules_unit_identity_ids(state=state, unit_instance_id=unit_instance_id))
    )
    placed_models = _placed_alive_models(state=state, rules_unit=rules_unit)
    placed_model_ids = tuple(sorted(model.model_instance_id for _unit_id, model in placed_models))
    positive_oc_ids = tuple(
        sorted(
            model.model_instance_id
            for component_unit_id, model in placed_models
            if (
                characteristic := model_objective_control_characteristic(
                    model,
                    battle_shocked=False,
                    state=state,
                    unit_instance_id=component_unit_id,
                    runtime_modifier_registry=runtime_modifier_registry,
                    model_instance_id=model.model_instance_id,
                )
            ).is_numeric
            and characteristic.final > 0
        )
    )
    state_unit_ids = tuple(sorted({rules_unit.unit_instance_id, *component_ids}))
    phase = state.current_battle_phase
    shooting_state = state.shooting_phase_state
    prior_uses = primary_mission_action_prior_use_evidence(
        state=state,
        actions=tuple(state.mission_action_states),
    )
    target_kind = _target_kind(policy.target_policy)
    objective_witness = (
        rules_unit_objective_proximity_witness(
            state=state,
            rules_unit_instance_id=rules_unit.unit_instance_id,
        )
        if target_kind == "objective_marker"
        else None
    )
    terrain_intersections = (
        terrain_intersections_from_model_inventory(
            tuple(
                row
                for row in boundary_terrain_model_inventory
                if row.owner_player_id == player_id
                and row.rules_unit_instance_id == rules_unit.unit_instance_id
                and row.component_unit_instance_id in component_ids
            )
        )
        if target_kind == "terrain_area"
        else ()
    )
    surveil_evidence = (
        _capture_surveil_evidence(
            state=state,
            player_id=player_id,
            observer=rules_unit,
            target_unit_id=target_id,
        )
        if target_kind == "enemy_rules_unit"
        else None
    )
    enemy_territory_ids = _enemy_territory_area_ids(state=state, player_id=player_id)
    evidence = PrimaryMissionActionStartEvidence(
        schema_version=PRIMARY_MISSION_ACTION_START_EVIDENCE_SCHEMA,
        game_id=state.game_id,
        player_id=player_id,
        active_player_id=state.active_player_id,
        battle_round=state.battle_round,
        phase=phase.value,
        mission_action_id=action.mission_action_id,
        mission_id=action.mission_id,
        source_id=policy.source_id,
        eligible_unit_policy=policy.eligible_unit_policy,
        target_policy=policy.target_policy,
        use_limit=policy.use_limit,
        effect_descriptor=policy.effect_descriptor,
        unit_instance_id=rules_unit.unit_instance_id,
        unit_identity_ids=identity_ids,
        component_unit_instance_ids=component_ids,
        eligible_unit_instance_ids=eligible_unit_instance_ids,
        target_id=target_id,
        condition_target_id=condition_target_id,
        ruleset_descriptor_hash=state.ruleset_descriptor_hash,
        unit_owner_player_id=rules_unit.owner_player_id,
        placed_alive_model_instance_ids=placed_model_ids,
        positive_objective_control_model_instance_ids=positive_oc_ids,
        keyword_tokens=tuple(sorted(_canonical_keyword(value) for value in rules_unit.keywords)),
        battle_shocked=rules_unit_is_battle_shocked(
            state=state, unit_instance_id=rules_unit.unit_instance_id
        ),
        within_enemy_engagement_range=(
            bool(placed_model_ids)
            and unit_within_enemy_engagement_range(
                state=state, unit_instance_id=rules_unit.unit_instance_id
            )
        ),
        advanced_unit_instance_ids=tuple(
            unit_id
            for unit_id in state_unit_ids
            if state.advanced_unit_state_for_unit(
                player_id=player_id,
                battle_round=state.battle_round,
                unit_instance_id=unit_id,
            )
            is not None
        ),
        fell_back_unit_instance_ids=tuple(
            unit_id
            for unit_id in state_unit_ids
            if state.fell_back_unit_state_for_unit(
                player_id=player_id,
                battle_round=state.battle_round,
                unit_instance_id=unit_id,
            )
            is not None
        ),
        shot_unit_instance_ids=(
            ()
            if phase is not BattlePhase.SHOOTING or shooting_state is None
            else tuple(sorted(set(state_unit_ids).intersection(shooting_state.shot_unit_ids)))
        ),
        unit_ineligibility_reason=mission_action_unit_ineligibility_reason(
            state=state,
            player_id=player_id,
            unit_instance_id=rules_unit.unit_instance_id,
            runtime_modifier_registry=runtime_modifier_registry,
        ),
        objective_proximity_witness=objective_witness,
        active_primary_mission_marker_ids=active_primary_mission_marker_ids(state=state),
        enemy_territory_logical_terrain_area_ids=enemy_territory_ids,
        terrain_intersections=terrain_intersections,
        surveil_target_evidence=surveil_evidence,
        prior_uses=prior_uses,
        start_authority=start_authority,
        boundary_checkpoint=boundary_checkpoint,
    )
    validate_primary_mission_action_start_evidence(
        state=state,
        action=action,
        policy=policy,
        evidence=evidence,
        expected_active_marker_ids=evidence.active_primary_mission_marker_ids,
        expected_prior_uses=prior_uses,
        validate_current_visibility_cache=True,
        validate_request_authority=False,
    )
    return evidence


def validate_primary_mission_action_start_evidence(
    *,
    state: GameState,
    action: MissionActionDefinition,
    policy: MissionActionPolicyDescriptor,
    evidence: PrimaryMissionActionStartEvidence,
    expected_active_marker_ids: tuple[str, ...],
    expected_prior_uses: tuple[MissionActionPriorUseEvidence, ...],
    validate_current_visibility_cache: bool = False,
    validate_request_authority: bool = True,
) -> None:
    require_primary_mission_game_state(state)
    if (
        type(action) is not MissionActionDefinition
        or type(policy) is not MissionActionPolicyDescriptor
    ):
        raise GameLifecycleError("Primary Mission Action start evidence requires typed policy.")
    if type(evidence) is not PrimaryMissionActionStartEvidence:
        raise GameLifecycleError("Primary Mission Action start evidence is invalid.")
    expected_policy = (
        action.mission_action_id,
        action.mission_id,
        policy.source_id,
        policy.eligible_unit_policy,
        policy.target_policy,
        policy.use_limit,
        policy.effect_descriptor,
    )
    actual_policy = (
        evidence.mission_action_id,
        evidence.mission_id,
        evidence.source_id,
        evidence.eligible_unit_policy,
        evidence.target_policy,
        evidence.use_limit,
        evidence.effect_descriptor,
    )
    if actual_policy != expected_policy:
        raise GameLifecycleError("Primary Mission Action start evidence policy drifted.")
    if (
        evidence.game_id != state.game_id
        or evidence.player_id != evidence.active_player_id
        or evidence.player_id not in state.player_ids
        or evidence.phase != BattlePhase.SHOOTING.value
        or evidence.ruleset_descriptor_hash != state.ruleset_descriptor_hash
    ):
        raise GameLifecycleError("Primary Mission Action start evidence boundary drifted.")
    if policy.start_timing == "shooting_phase_action_start_from_battle_round_two" and (
        evidence.battle_round < 2
    ):
        raise GameLifecycleError("Primary Mission Action started before battle round two.")
    if evidence.unit_owner_player_id != evidence.player_id:
        raise GameLifecycleError("Primary Mission Action start unit owner drifted.")
    expected_identity_ids = tuple(
        sorted(
            rules_unit_identity_ids(
                state=state,
                unit_instance_id=evidence.unit_instance_id,
            )
        )
    )
    expected_component_ids = tuple(
        value for value in expected_identity_ids if value != evidence.unit_instance_id
    ) or (evidence.unit_instance_id,)
    if (
        evidence.unit_identity_ids != expected_identity_ids
        or evidence.component_unit_instance_ids != expected_component_ids
    ):
        raise GameLifecycleError("Primary Mission Action start unit identity drifted.")
    component_units = tuple(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id in evidence.component_unit_instance_ids
    )
    if {unit.unit_instance_id for unit in component_units} != set(
        evidence.component_unit_instance_ids
    ):
        raise GameLifecycleError("Primary Mission Action component inventory drifted.")
    actor_model_ids_by_component = {
        unit.unit_instance_id: frozenset(model.model_instance_id for model in unit.own_models)
        for unit in component_units
    }
    placed_model_ids = set(evidence.placed_alive_model_instance_ids)
    actor_model_ids: set[str] = {
        model_id
        for component_model_ids in actor_model_ids_by_component.values()
        for model_id in component_model_ids
    }
    if not placed_model_ids <= actor_model_ids or any(
        placed_model_ids.isdisjoint(model_ids)
        for model_ids in actor_model_ids_by_component.values()
    ):
        raise GameLifecycleError("Primary Mission Action start model inventory drifted.")
    expected_keywords = tuple(
        sorted(
            {_canonical_keyword(keyword) for unit in component_units for keyword in unit.keywords}
        )
    )
    if evidence.keyword_tokens != expected_keywords:
        raise GameLifecycleError("Primary Mission Action start keyword inventory drifted.")
    if evidence.unit_instance_id not in evidence.eligible_unit_instance_ids:
        raise GameLifecycleError("Primary Mission Action start unit is not in eligible inventory.")
    if evidence.unit_ineligibility_reason is not None:
        raise GameLifecycleError("Primary Mission Action started with an ineligible unit.")
    if not evidence.placed_alive_model_instance_ids:
        raise GameLifecycleError("Primary Mission Action unit was not alive and placed.")
    if not evidence.positive_objective_control_model_instance_ids or not set(
        evidence.positive_objective_control_model_instance_ids
    ) <= set(evidence.placed_alive_model_instance_ids):
        raise GameLifecycleError("Primary Mission Action unit lacked positive Objective Control.")
    if {"AIRCRAFT", "FORTIFICATION"}.intersection(evidence.keyword_tokens):
        raise GameLifecycleError("Primary Mission Action unit has an ineligible keyword.")
    if evidence.battle_shocked:
        raise GameLifecycleError("Battle-shocked unit started a Primary Mission Action.")
    if evidence.within_enemy_engagement_range and "TITANIC" not in evidence.keyword_tokens:
        raise GameLifecycleError("Engaged non-Titanic unit started a Primary Mission Action.")
    if (
        evidence.advanced_unit_instance_ids
        or evidence.fell_back_unit_instance_ids
        or evidence.shot_unit_instance_ids
    ):
        raise GameLifecycleError("Primary Mission Action unit had already acted this turn.")
    if evidence.active_primary_mission_marker_ids != canonical_identifier_tuple(
        "expected_active_marker_ids", expected_active_marker_ids, require_non_empty=False
    ):
        raise GameLifecycleError("Primary Mission Action start marker inventory drifted.")
    expected_prior = canonical_mission_action_prior_uses(expected_prior_uses)
    if evidence.prior_uses != expected_prior:
        raise GameLifecycleError("Primary Mission Action prior-use inventory drifted.")
    if validate_request_authority:
        validate_primary_mission_action_start_authority(
            state=state,
            evidence=evidence,
        )
    expected_enemy_territory_ids = _enemy_territory_area_ids(
        state=state,
        player_id=evidence.player_id,
    )
    if evidence.enemy_territory_logical_terrain_area_ids != expected_enemy_territory_ids:
        raise GameLifecycleError("Primary Mission Action enemy-territory inventory drifted.")
    if any(
        prior.player_id == evidence.player_id
        and prior.battle_round_started == evidence.battle_round
        and not set(prior.unit_identity_ids).isdisjoint(evidence.unit_identity_ids)
        for prior in evidence.prior_uses
    ):
        raise GameLifecycleError("Primary Mission Action unit already started an Action this turn.")
    _validate_eligible_unit_policy(state=state, evidence=evidence, policy=policy)
    _validate_start_target(
        state=state,
        evidence=evidence,
        policy=policy,
        validate_current_visibility_cache=validate_current_visibility_cache,
    )
    _validate_use_limit_from_prior_uses(evidence=evidence, policy=policy)


def capture_primary_mission_action_completion_evidence(
    *,
    state: GameState,
    action: MissionActionState,
    policy: MissionActionPolicyDescriptor,
    completed_phase: BattlePhase,
    objective_control_record: ObjectiveControlRecord | None,
    runtime_modifier_registry: RuntimeModifierRegistry,
    boundary_checkpoint: PrimaryMissionBoundaryCheckpointReference | None = None,
) -> PrimaryMissionActionCompletionEvidence:
    require_primary_mission_game_state(state)
    if state.active_player_id is None:
        raise GameLifecycleError(
            "Primary Mission Action completion evidence requires active player."
        )
    identity_ids = tuple(
        sorted(rules_unit_identity_ids(state=state, unit_instance_id=action.unit_instance_id))
    )
    result: ObjectiveControlResult | None = None
    contributor_unit_ids: tuple[str, ...] = ()
    contributor_model_ids: tuple[str, ...] = ()
    if policy.effect_descriptor in PRIMARY_MISSION_ACTION_OBJECTIVE_CONTROL_EFFECTS:
        if objective_control_record is None or action.condition_target_id is None:
            raise GameLifecycleError("Objective Primary Action completion evidence is incomplete.")
        result = _objective_result(
            objective_control_record, objective_id=action.condition_target_id
        )
        contributors = tuple(
            contribution
            for contribution in result.contributors
            if contribution.player_id == action.player_id
            and rules_unit_identities_share_lineage(
                state=state,
                first_unit_instance_id=action.unit_instance_id,
                second_unit_instance_id=contribution.unit_instance_id,
            )
        )
        contributor_unit_ids = tuple(
            sorted({contribution.unit_instance_id for contribution in contributors})
        )
        contributor_model_ids = tuple(
            sorted({contribution.model_instance_id for contribution in contributors})
        )
    terrain_model_inventory = (
        capture_primary_mission_action_terrain_model_inventory(
            state=state,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        if policy.effect_descriptor == PRIMARY_MISSION_ACTION_VANGUARD_EFFECT
        else ()
    )
    terrain_intersections = (
        terrain_intersections_from_model_inventory(terrain_model_inventory)
        if policy.effect_descriptor == PRIMARY_MISSION_ACTION_VANGUARD_EFFECT
        else ()
    )
    evidence = PrimaryMissionActionCompletionEvidence(
        schema_version=PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_SCHEMA,
        boundary_kind=(
            "immediate_completion"
            if policy.completion_timing == "immediate"
            else "turn_end_completion"
        ),
        game_id=state.game_id,
        player_id=action.player_id,
        active_player_id=state.active_player_id,
        battle_round=state.battle_round,
        phase=completed_phase.value,
        action_id=action.action_id,
        mission_action_id=action.mission_action_id,
        source_id=policy.source_id,
        effect_descriptor=policy.effect_descriptor,
        condition_target_id=action.condition_target_id,
        action_unit_identity_ids=identity_ids,
        action_unit_battle_shocked=rules_unit_is_battle_shocked(
            state=state, unit_instance_id=action.unit_instance_id
        ),
        objective_control_record_id=(
            None if objective_control_record is None else objective_control_record.record_id
        ),
        objective_control_record_hash=(
            None
            if objective_control_record is None
            else objective_control_record_hash(objective_control_record)
        ),
        objective_control_result=result,
        action_unit_contributor_unit_instance_ids=contributor_unit_ids,
        action_unit_contributor_model_instance_ids=contributor_model_ids,
        terrain_intersections=terrain_intersections,
        terrain_model_inventory=terrain_model_inventory,
        boundary_checkpoint=boundary_checkpoint,
        completion_condition_met=False,
    )
    met = evaluate_primary_mission_action_completion_evidence(
        evidence=evidence,
        policy=policy,
    )
    evidence = replace(evidence, completion_condition_met=met)
    validate_primary_mission_action_completion_evidence(
        state=state,
        action=action,
        policy=policy,
        evidence=evidence,
        objective_control_record=objective_control_record,
    )
    return evidence


def validate_primary_mission_action_completion_evidence(
    *,
    state: GameState,
    action: MissionActionState,
    policy: MissionActionPolicyDescriptor,
    evidence: PrimaryMissionActionCompletionEvidence,
    objective_control_record: ObjectiveControlRecord | None,
) -> bool:
    require_primary_mission_game_state(state)
    if type(evidence) is not PrimaryMissionActionCompletionEvidence:
        raise GameLifecycleError("Primary Mission Action completion evidence is invalid.")
    if (
        evidence.game_id != state.game_id
        or evidence.player_id != action.player_id
        or evidence.active_player_id != action.player_id
        or evidence.action_id != action.action_id
        or evidence.mission_action_id != action.mission_action_id
        or evidence.source_id != policy.source_id
        or evidence.effect_descriptor != policy.effect_descriptor
        or evidence.condition_target_id != action.condition_target_id
    ):
        raise GameLifecycleError("Primary Mission Action completion evidence identity drifted.")
    if evidence.action_unit_identity_ids != tuple(
        sorted(
            rules_unit_identity_ids(
                state=state,
                unit_instance_id=action.unit_instance_id,
            )
        )
    ):
        raise GameLifecycleError("Primary Mission Action completion unit identity drifted.")
    expected_boundary = (
        "immediate_completion" if policy.completion_timing == "immediate" else "turn_end_completion"
    )
    if evidence.boundary_kind != expected_boundary:
        raise GameLifecycleError("Primary Mission Action completion boundary drifted.")
    if policy.completion_timing == "turn_end":
        if objective_control_record is None:
            raise GameLifecycleError("Turn-end Primary Mission Action lacks objective boundary.")
        battlefield = state.battlefield_state
        setup = state.mission_setup
        if battlefield is None or setup is None:
            raise GameLifecycleError(
                "Turn-end Primary Mission Action lacks mission battlefield state."
            )
        expected_objective_ids = tuple(
            sorted(marker.objective_marker_id for marker in setup.objective_markers)
        )
        if (
            objective_control_record.record_id != evidence.objective_control_record_id
            or objective_control_record_hash(objective_control_record)
            != evidence.objective_control_record_hash
            or objective_control_record.game_id != evidence.game_id
            or objective_control_record.battle_round != evidence.battle_round
            or objective_control_record.active_player_id != evidence.active_player_id
            or objective_control_record.phase != evidence.phase
            or objective_control_record.timing is not ObjectiveControlTiming.TURN_END
            or objective_control_record.battlefield_id != battlefield.battlefield_id
            or tuple(sorted(result.objective_id for result in objective_control_record.results))
            != expected_objective_ids
        ):
            raise GameLifecycleError(
                "Primary Mission Action completion objective boundary drifted."
            )
    elif (
        evidence.objective_control_record_id is not None
        or evidence.objective_control_record_hash is not None
        or evidence.objective_control_result is not None
    ):
        raise GameLifecycleError("Immediate Primary Mission Action has turn-end evidence.")
    if policy.effect_descriptor in PRIMARY_MISSION_ACTION_OBJECTIVE_CONTROL_EFFECTS:
        if objective_control_record is None or action.condition_target_id is None:
            raise GameLifecycleError("Objective Primary Mission Action evidence is incomplete.")
        result = _objective_result(
            objective_control_record, objective_id=action.condition_target_id
        )
        if evidence.objective_control_result != result:
            raise GameLifecycleError("Primary Mission Action objective result drifted.")
        contributors = tuple(
            contribution
            for contribution in result.contributors
            if contribution.player_id == action.player_id
            and rules_unit_identities_share_lineage(
                state=state,
                first_unit_instance_id=action.unit_instance_id,
                second_unit_instance_id=contribution.unit_instance_id,
            )
        )
        if any(
            contribution.battle_shocked is not evidence.action_unit_battle_shocked
            for contribution in contributors
        ):
            raise GameLifecycleError(
                "Primary Mission Action Battle-shock evidence contradicts objective control."
            )
        expected_contributor_unit_ids = tuple(
            sorted({contribution.unit_instance_id for contribution in contributors})
        )
        expected_contributor_model_ids = tuple(
            sorted({contribution.model_instance_id for contribution in contributors})
        )
        if (
            evidence.action_unit_contributor_unit_instance_ids != expected_contributor_unit_ids
            or evidence.action_unit_contributor_model_instance_ids != expected_contributor_model_ids
        ):
            raise GameLifecycleError(
                "Primary Mission Action objective contributor inventory drifted."
            )
    elif (
        evidence.objective_control_result is not None
        or evidence.action_unit_contributor_unit_instance_ids
        or evidence.action_unit_contributor_model_instance_ids
    ):
        raise GameLifecycleError("Non-objective Primary Mission Action has objective evidence.")
    if policy.effect_descriptor == PRIMARY_MISSION_ACTION_VANGUARD_EFFECT:
        if evidence.boundary_checkpoint is None:
            raise GameLifecycleError(
                "Vanguard Primary Mission Action lacks an end-turn boundary checkpoint."
            )
        if not evidence.terrain_model_inventory:
            raise GameLifecycleError(
                "Vanguard Primary Mission Action lacks terrain-model inventory."
            )
        validate_primary_mission_action_terrain_model_inventory(
            state=state,
            values=evidence.terrain_model_inventory,
        )
        if evidence.terrain_intersections != terrain_intersections_from_model_inventory(
            evidence.terrain_model_inventory
        ):
            raise GameLifecycleError("Vanguard terrain boundary inventory drifted.")
        _validate_terrain_intersection_identities(
            state=state,
            values=evidence.terrain_intersections,
        )
    elif (
        evidence.terrain_intersections
        or evidence.terrain_model_inventory
        or evidence.boundary_checkpoint is not None
    ):
        raise GameLifecycleError("Non-Vanguard Primary Mission Action has terrain evidence.")
    completion_condition_met = evaluate_primary_mission_action_completion_evidence(
        evidence=evidence,
        policy=policy,
    )
    if evidence.completion_condition_met is not completion_condition_met:
        raise GameLifecycleError(
            "Primary Mission Action completion result drifted from its evidence."
        )
    return completion_condition_met


def evaluate_primary_mission_action_completion_evidence(
    *,
    evidence: PrimaryMissionActionCompletionEvidence,
    policy: MissionActionPolicyDescriptor,
) -> bool:
    if evidence.action_unit_battle_shocked:
        return False
    effect = policy.effect_descriptor
    if effect == PRIMARY_MISSION_ACTION_SURVEIL_EFFECT:
        return True
    if effect in PRIMARY_MISSION_ACTION_OBJECTIVE_CONTROL_EFFECTS:
        result = evidence.objective_control_result
        return bool(
            result is not None
            and result.controlled_by_player_id == evidence.player_id
            and evidence.action_unit_contributor_model_instance_ids
        )
    if effect == PRIMARY_MISSION_ACTION_VANGUARD_EFFECT:
        target_id = evidence.condition_target_id
        if target_id is None:
            raise GameLifecycleError(
                "Vanguard Primary Mission Action is missing its terrain target."
            )
        action_identities = set(evidence.action_unit_identity_ids)
        actor_present = any(
            row.logical_terrain_area_id == target_id
            and row.owner_player_id == evidence.player_id
            and row.rules_unit_instance_id in action_identities
            and row.component_unit_instance_id in action_identities
            for row in evidence.terrain_intersections
        )
        enemy_present = any(
            row.logical_terrain_area_id == target_id and row.owner_player_id != evidence.player_id
            for row in evidence.terrain_intersections
        )
        return actor_present and not enemy_present
    raise GameLifecycleError("Primary Mission Action completion effect is unsupported.")


def validate_primary_mission_action_use_limits(
    *,
    state: GameState,
    ordered_actions: tuple[MissionActionState, ...],
    policies: dict[str, MissionActionPolicyDescriptor],
) -> None:
    require_primary_mission_game_state(state)
    once_per_turn: set[tuple[str, int, str]] = set()
    per_phase_identities: dict[tuple[str, int, str, str], set[str]] = {}
    per_phase_targets: dict[tuple[str, int, str, str], set[str]] = {}
    for action in ordered_actions:
        policy = policies.get(action.mission_action_id)
        if policy is None:
            continue
        if policy.use_limit == "unlimited":
            continue
        if policy.use_limit == "once_per_turn":
            once_key = (
                action.player_id,
                action.battle_round_started,
                action.mission_action_id,
            )
            if once_key in once_per_turn:
                raise GameLifecycleError("Primary Mission Action once-per-turn use limit exceeded.")
            once_per_turn.add(once_key)
            continue
        if policy.use_limit != "unlimited_different_objective_per_unit_this_phase":
            raise GameLifecycleError("Primary Mission Action use limit is unsupported.")
        phase_key = (
            action.player_id,
            action.battle_round_started,
            action.phase_started,
            action.mission_action_id,
        )
        identity_ids = set(
            rules_unit_identity_ids(
                state=state,
                unit_instance_id=action.unit_instance_id,
            )
        )
        used_identity_ids = per_phase_identities.setdefault(phase_key, set())
        used_targets = per_phase_targets.setdefault(phase_key, set())
        if not identity_ids.isdisjoint(used_identity_ids) or action.target_id in used_targets:
            raise GameLifecycleError(
                "Primary Mission Action per-phase unit/objective use limit exceeded."
            )
        used_identity_ids.update(identity_ids)
        used_targets.add(action.target_id)


def primary_mission_action_prior_use_evidence(
    *,
    state: GameState,
    actions: tuple[MissionActionState, ...],
) -> tuple[MissionActionPriorUseEvidence, ...]:
    require_primary_mission_game_state(state)
    primary_policies = {
        policy.mission_action_id: policy for policy in mission_action_policy_descriptors()
    }
    rows: list[MissionActionPriorUseEvidence] = []
    for action in actions:
        policy = primary_policies.get(action.mission_action_id)
        target_identity_ids: tuple[str, ...] = ()
        if policy is not None and _target_kind(policy.target_policy) == "enemy_rules_unit":
            target_identity_ids = tuple(
                sorted(rules_unit_identity_ids(state=state, unit_instance_id=action.target_id))
            )
        rows.append(
            MissionActionPriorUseEvidence(
                action_id=action.action_id,
                mission_action_id=action.mission_action_id,
                player_id=action.player_id,
                battle_round_started=action.battle_round_started,
                phase_started=action.phase_started,
                unit_instance_id=action.unit_instance_id,
                unit_identity_ids=tuple(
                    sorted(
                        rules_unit_identity_ids(
                            state=state, unit_instance_id=action.unit_instance_id
                        )
                    )
                ),
                target_id=action.target_id,
                target_rules_unit_identity_ids=target_identity_ids,
            )
        )
    return tuple(sorted(rows, key=lambda row: row.action_id))


def active_primary_mission_marker_ids(*, state: GameState) -> tuple[str, ...]:
    return tuple(
        sorted(
            marker.marker_id
            for marker in state.primary_mission_progress_state.markers
            if marker.status is PrimaryMissionMarkerStatus.ACTIVE
        )
    )


def active_primary_mission_marker_ids_at_event(
    *,
    state: GameState,
    event: EventRecord,
    event_index_by_id: dict[str, int],
) -> tuple[str, ...]:
    event_order = event_index_by_id[event.event_id]
    active: list[str] = []
    for marker in state.primary_mission_progress_state.markers:
        creation_order = event_index_by_id.get(marker.source_event_id)
        if creation_order is None:
            raise GameLifecycleError("Primary Mission Action marker creation event is unknown.")
        removal_order = (
            None
            if marker.removal_event_id is None
            else event_index_by_id.get(marker.removal_event_id)
        )
        if marker.removal_event_id is not None and removal_order is None:
            raise GameLifecycleError("Primary Mission Action marker removal event is unknown.")
        if creation_order >= event_order or (
            removal_order is not None and removal_order <= event_order
        ):
            continue
        active.append(marker.marker_id)
    return tuple(sorted(active))


def objective_control_record_for_completion_evidence(
    *,
    state: GameState,
    evidence: PrimaryMissionActionCompletionEvidence,
) -> ObjectiveControlRecord | None:
    if evidence.objective_control_record_id is None:
        return None
    matches = tuple(
        record
        for record in state.objective_control_records
        if record.record_id == evidence.objective_control_record_id
    )
    if len(matches) != 1:
        raise GameLifecycleError(
            "Primary Mission Action completion objective record is not authoritative."
        )
    return matches[0]


def _validate_eligible_unit_policy(
    *,
    state: GameState,
    evidence: PrimaryMissionActionStartEvidence,
    policy: MissionActionPolicyDescriptor,
) -> None:
    eligible_policy = policy.eligible_unit_policy
    if eligible_policy == "active_player_unit":
        return
    setup = state.mission_setup
    if setup is None:
        raise GameLifecycleError("Primary Mission Action eligibility requires MissionSetup.")
    if eligible_policy in {
        "active_player_unit_within_range_of_central_objective",
        "active_player_unit_within_range_of_non_home_objective",
    }:
        witness = evidence.objective_proximity_witness
        if witness is None:
            raise GameLifecycleError(
                "Primary Mission Action eligibility lacks objective proximity evidence."
            )
        witnessed_objective_ids = set(witness.objective_marker_ids)
        if eligible_policy == "active_player_unit_within_range_of_central_objective":
            eligible_objective_ids = {
                marker.objective_marker_id
                for marker in setup.objective_markers
                if marker.objective_role is ObjectiveMarkerRole.CENTRAL
            }
        else:
            eligible_objective_ids = {
                marker.objective_marker_id for marker in setup.objective_markers
            } - set(home_objective_ids(setup, player_id=evidence.player_id))
        if witnessed_objective_ids.isdisjoint(eligible_objective_ids):
            raise GameLifecycleError(
                "Primary Mission Action unit does not satisfy its objective eligibility policy."
            )
        return
    if eligible_policy == "active_player_unit_within_terrain_area_in_enemy_territory":
        enemy_territory_ids = set(evidence.enemy_territory_logical_terrain_area_ids)
        if not any(
            row.logical_terrain_area_id in enemy_territory_ids
            and row.owner_player_id == evidence.player_id
            and row.rules_unit_instance_id == evidence.unit_instance_id
            and row.component_unit_instance_id in evidence.component_unit_instance_ids
            for row in evidence.terrain_intersections
        ):
            raise GameLifecycleError(
                "Primary Mission Action unit does not satisfy its terrain eligibility policy."
            )
        return
    raise GameLifecycleError("Primary Mission Action eligible-unit policy is unsupported.")


def _validate_start_target(
    *,
    state: GameState,
    evidence: PrimaryMissionActionStartEvidence,
    policy: MissionActionPolicyDescriptor,
    validate_current_visibility_cache: bool,
) -> None:
    setup = state.mission_setup
    if setup is None:
        raise GameLifecycleError("Primary Mission Action start evidence requires MissionSetup.")
    target_kind = _target_kind(policy.target_policy)
    marker_by_id = {
        marker.marker_id: marker for marker in state.primary_mission_progress_state.markers
    }
    active_markers = tuple(
        marker_by_id[marker_id]
        for marker_id in evidence.active_primary_mission_marker_ids
        if marker_id in marker_by_id
    )
    if len(active_markers) != len(evidence.active_primary_mission_marker_ids):
        raise GameLifecycleError("Primary Mission Action start marker inventory is unknown.")
    if target_kind == "objective_marker":
        if evidence.condition_target_id != evidence.target_id:
            raise GameLifecycleError("Primary Mission Action objective condition target drifted.")
        objective = next(
            (
                marker
                for marker in setup.objective_markers
                if marker.objective_marker_id == evidence.target_id
            ),
            None,
        )
        witness = evidence.objective_proximity_witness
        if objective is None or witness is None:
            raise GameLifecycleError("Primary Mission Action objective evidence is missing.")
        if (
            witness.rules_unit_instance_id != evidence.unit_instance_id
            or tuple(sorted(witness.component_unit_instance_ids))
            != evidence.component_unit_instance_ids
            or evidence.target_id not in witness.objective_marker_ids
        ):
            raise GameLifecycleError("Primary Mission Action objective proximity drifted.")
        selected_witnesses = tuple(
            item
            for item in witness.objective_marker_witnesses
            if item.objective_marker_id == evidence.target_id
        )
        if len(selected_witnesses) != 1 or not set(selected_witnesses[0].model_instance_ids) <= set(
            evidence.placed_alive_model_instance_ids
        ):
            raise GameLifecycleError("Primary Mission Action objective model witness drifted.")
        if policy.target_policy.startswith("central_objective") and (
            objective.objective_role is not ObjectiveMarkerRole.CENTRAL
        ):
            raise GameLifecycleError("Primary Mission Action central target drifted.")
        if policy.target_policy.startswith("objective_marker_excluding_home") and (
            evidence.target_id in home_objective_ids(setup, player_id=evidence.player_id)
        ):
            raise GameLifecycleError("Primary Mission Action home objective target is invalid.")
        if policy.target_policy == "objective_marker_excluding_home_not_decoy" and any(
            marker.owner_player_id == evidence.player_id
            and marker.mission_id == policy.primary_mission_id
            and marker.objective_marker_id == evidence.target_id
            for marker in active_markers
        ):
            raise GameLifecycleError("Primary Mission Action selected an existing Decoy.")
        if (
            policy.target_policy
            == "objective_marker_excluding_home_without_friendly_operation_marker"
            and any(
                marker.owner_player_id == evidence.player_id
                and marker.marker_kind == "operation"
                and marker.objective_marker_id == evidence.target_id
                for marker in active_markers
            )
        ):
            raise GameLifecycleError(
                "Primary Mission Action target already has a friendly Operation marker."
            )
        if "friendly_operation_marker_requires_more_than_one" in policy.target_policy and (
            sum(
                marker.owner_player_id == evidence.player_id and marker.marker_kind == "operation"
                for marker in active_markers
            )
            <= 1
        ):
            raise GameLifecycleError(
                "Primary Mission Action lacks required friendly Operation markers."
            )
        if "opponent_operation_marker_requires_more_than_one" in policy.target_policy and (
            sum(
                marker.owner_player_id != evidence.player_id and marker.marker_kind == "operation"
                for marker in active_markers
            )
            <= 1
        ):
            raise GameLifecycleError(
                "Primary Mission Action lacks required opponent Operation markers."
            )
        if evidence.terrain_intersections or evidence.surveil_target_evidence is not None:
            raise GameLifecycleError("Objective Primary Mission Action has unrelated evidence.")
        return
    if target_kind == "terrain_area":
        if evidence.condition_target_id != evidence.target_id:
            raise GameLifecycleError("Primary Mission Action terrain condition target drifted.")
        if evidence.target_id not in evidence.enemy_territory_logical_terrain_area_ids:
            raise GameLifecycleError(
                "Primary Mission Action terrain target is not enemy territory."
            )
        if not any(
            row.logical_terrain_area_id == evidence.target_id
            and row.owner_player_id == evidence.player_id
            and row.rules_unit_instance_id == evidence.unit_instance_id
            and row.component_unit_instance_id in evidence.component_unit_instance_ids
            for row in evidence.terrain_intersections
        ):
            raise GameLifecycleError("Primary Mission Action unit was not in selected terrain.")
        if evidence.objective_proximity_witness is not None or evidence.surveil_target_evidence:
            raise GameLifecycleError("Terrain Primary Mission Action has unrelated evidence.")
        _validate_terrain_intersection_identities(
            state=state, values=evidence.terrain_intersections
        )
        if any(
            row.owner_player_id != evidence.player_id
            or row.rules_unit_instance_id != evidence.unit_instance_id
            or row.component_unit_instance_id not in evidence.component_unit_instance_ids
            for row in evidence.terrain_intersections
        ):
            raise GameLifecycleError("Primary Mission Action start terrain inventory drifted.")
        return
    if target_kind != "enemy_rules_unit":
        raise GameLifecycleError("Primary Mission Action target kind is unsupported.")
    surveil = evidence.surveil_target_evidence
    if evidence.condition_target_id is not None or surveil is None:
        raise GameLifecycleError("Surveil Primary Mission Action evidence is incomplete.")
    expected_target_identity_ids = tuple(
        sorted(
            rules_unit_identity_ids(
                state=state,
                unit_instance_id=evidence.target_id,
            )
        )
    )
    target_component_ids = set(expected_target_identity_ids) - {
        surveil.target_rules_unit_instance_id
    }
    if not target_component_ids:
        target_component_ids = {surveil.target_rules_unit_instance_id}
    target_units = tuple(
        (army.player_id, unit)
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id in target_component_ids
    )
    target_owner_ids = {owner_player_id for owner_player_id, _unit in target_units}
    target_model_ids = {
        model.model_instance_id
        for _owner_player_id, unit in target_units
        for model in unit.own_models
    }
    if (
        surveil.target_rules_unit_instance_id != evidence.target_id
        or surveil.target_rules_unit_identity_ids != expected_target_identity_ids
        or target_owner_ids != {surveil.target_owner_player_id}
        or surveil.target_owner_player_id == evidence.player_id
        or not surveil.placed_alive_target_model_instance_ids
        or not set(surveil.placed_alive_target_model_instance_ids) <= target_model_ids
        or not surveil.observer_component_unit_instance_ids_within_18
        or not surveil.observer_component_unit_instance_ids_with_line_of_sight
        or not set(surveil.observer_component_unit_instance_ids_within_18)
        <= set(evidence.component_unit_instance_ids)
        or not set(surveil.observer_component_unit_instance_ids_with_line_of_sight)
        <= set(evidence.component_unit_instance_ids)
    ):
        raise GameLifecycleError("Surveil Primary Mission Action geometry drifted.")
    if validate_current_visibility_cache:
        battlefield = state.battlefield_state
        if battlefield is None:
            raise GameLifecycleError("Surveil evidence requires battlefield state.")
        scenario = BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=battlefield,
        )
        expected_visibility_cache_key = shooting_visibility_cache_key(
            scenario=scenario,
            terrain_features=battlefield.terrain_features,
            terrain_areas=shooting_terrain_areas_for_state(state),
        )
        if surveil.visibility_cache_key != expected_visibility_cache_key:
            raise GameLifecycleError("Surveil visibility cache identity drifted.")
    if any(
        prior.player_id == evidence.player_id
        and prior.mission_action_id == evidence.mission_action_id
        and prior.battle_round_started == evidence.battle_round
        and not set(prior.target_rules_unit_identity_ids).isdisjoint(
            surveil.target_rules_unit_identity_ids
        )
        for prior in evidence.prior_uses
    ):
        raise GameLifecycleError("Surveil target was already surveilled this turn.")
    if evidence.objective_proximity_witness is not None or evidence.terrain_intersections:
        raise GameLifecycleError("Surveil Primary Mission Action has unrelated evidence.")


def _validate_use_limit_from_prior_uses(
    *, evidence: PrimaryMissionActionStartEvidence, policy: MissionActionPolicyDescriptor
) -> None:
    matching = tuple(
        prior
        for prior in evidence.prior_uses
        if prior.player_id == evidence.player_id
        and prior.mission_action_id == evidence.mission_action_id
        and prior.battle_round_started == evidence.battle_round
    )
    if policy.use_limit == "unlimited":
        return
    if policy.use_limit == "once_per_turn":
        if matching:
            raise GameLifecycleError("Primary Mission Action once-per-turn use limit exceeded.")
        return
    if policy.use_limit != "unlimited_different_objective_per_unit_this_phase":
        raise GameLifecycleError("Primary Mission Action use limit is unsupported.")
    if any(
        prior.phase_started == evidence.phase
        and (
            not set(prior.unit_identity_ids).isdisjoint(evidence.unit_identity_ids)
            or prior.target_id == evidence.target_id
        )
        for prior in matching
    ):
        raise GameLifecycleError(
            "Primary Mission Action per-phase unit/objective use limit exceeded."
        )


def _capture_surveil_evidence(
    *,
    state: GameState,
    player_id: str,
    observer: RulesUnitView,
    target_unit_id: str,
) -> MissionActionSurveilTargetEvidence:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Surveil evidence requires battlefield state.")
    target = rules_unit_view_by_id(state=state, unit_instance_id=target_unit_id)
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions), battlefield_state=battlefield
    )
    ruleset = state.runtime_ruleset_descriptor()
    terrain_areas = shooting_terrain_areas_for_state(state)
    range_components: list[str] = []
    los_components: list[str] = []
    for component in observer.components:
        if (
            any(model.is_alive for model in component.unit.own_models)
            and battlefield.unit_placement_or_none(component.unit.unit_instance_id) is not None
        ):
            if target_within_shooting_selection_range(
                scenario=scenario,
                attacking_unit_instance_id=component.unit.unit_instance_id,
                target_unit_instance_id=target.unit_instance_id,
                max_range_inches=18,
                placed_alive_attacker_models_only=True,
                placed_alive_target_models_only=True,
            ):
                range_components.append(component.unit.unit_instance_id)
            if unit_has_line_of_sight_to_target(
                state=state,
                scenario=scenario,
                ruleset_descriptor=ruleset,
                observing_unit=component.unit,
                target_unit_id=target.unit_instance_id,
                placed_alive_models_only=True,
                terrain_features=battlefield.terrain_features,
                terrain_areas=terrain_areas,
            ):
                los_components.append(component.unit.unit_instance_id)
    placed_ids = set(battlefield.placed_model_ids())
    return MissionActionSurveilTargetEvidence(
        target_rules_unit_instance_id=target.unit_instance_id,
        target_rules_unit_identity_ids=tuple(
            sorted(rules_unit_identity_ids(state=state, unit_instance_id=target.unit_instance_id))
        ),
        target_owner_player_id=target.owner_player_id,
        placed_alive_target_model_instance_ids=tuple(
            sorted(
                model.model_instance_id
                for model in target.own_models
                if model.is_alive and model.model_instance_id in placed_ids
            )
        ),
        observer_component_unit_instance_ids_within_18=tuple(sorted(range_components)),
        observer_component_unit_instance_ids_with_line_of_sight=tuple(sorted(los_components)),
        visibility_cache_key=shooting_visibility_cache_key(
            scenario=scenario,
            terrain_features=battlefield.terrain_features,
            terrain_areas=terrain_areas,
        ),
    )


def _enemy_territory_area_ids(*, state: GameState, player_id: str) -> tuple[str, ...]:
    setup = state.mission_setup
    if setup is None:
        raise GameLifecycleError("Primary Mission Action terrain evidence requires MissionSetup.")
    opponents = tuple(candidate for candidate in state.player_ids if candidate != player_id)
    if len(opponents) != 1:
        raise GameLifecycleError("Primary Mission Action requires exactly one opponent.")
    return tuple(
        sorted(
            area.logical_terrain_area_id
            for area in mission_logical_terrain_areas(setup)
            if logical_terrain_area_within_player_territory(
                area, mission_setup=setup, player_id=opponents[0]
            )
        )
    )


def _placed_alive_models(
    *, state: GameState, rules_unit: RulesUnitView
) -> tuple[tuple[str, ModelInstance], ...]:
    battlefield = state.battlefield_state
    if battlefield is None:
        return ()
    placed_ids = set(battlefield.placed_model_ids())
    return tuple(
        (component.unit.unit_instance_id, model)
        for component in rules_unit.components
        for model in component.unit.own_models
        if model.is_alive and model.model_instance_id in placed_ids
    )


def _validate_terrain_intersection_identities(
    *, state: GameState, values: tuple[MissionActionTerrainIntersectionEvidence, ...]
) -> None:
    setup = state.mission_setup
    if setup is None:
        raise GameLifecycleError("Primary Mission Action terrain evidence requires MissionSetup.")
    area_ids = {area.logical_terrain_area_id for area in mission_logical_terrain_areas(setup)}
    model_owner: dict[str, tuple[str, str]] = {}
    for army in state.army_definitions:
        for unit in army.units:
            for model in unit.own_models:
                model_owner[model.model_instance_id] = (army.player_id, unit.unit_instance_id)
    for row in values:
        if row.logical_terrain_area_id not in area_ids:
            raise GameLifecycleError("Primary Mission Action terrain evidence area is unknown.")
        owner = model_owner.get(row.model_instance_id)
        if owner != (row.owner_player_id, row.component_unit_instance_id):
            raise GameLifecycleError("Primary Mission Action terrain model identity drifted.")


def _objective_result(
    record: ObjectiveControlRecord, *, objective_id: str
) -> ObjectiveControlResult:
    matches = tuple(result for result in record.results if result.objective_id == objective_id)
    if len(matches) != 1:
        raise GameLifecycleError("Primary Mission Action objective result is missing.")
    return matches[0]


def _target_kind(target_policy: str) -> str:
    if target_policy == "terrain_area_in_enemy_territory":
        return "terrain_area"
    if target_policy == "visible_enemy_unit_within_18_not_surveilled_this_turn":
        return "enemy_rules_unit"
    return "objective_marker"


def _canonical_keyword(value: str) -> str:
    return _validate_identifier("keyword", value).replace("-", " ").replace("_", " ").upper()
