from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from warhammer40k_core.core.missions import MissionActionDefinition
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    PlacementError,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mission_action_eligibility import (
    mission_action_unit_ineligibility_reason,
)
from warhammer40k_core.engine.mission_action_policies import (
    SUPPORTED_MISSION_ACTION_TARGET_POLICIES as PRIMARY_MISSION_ACTION_TARGET_POLICIES,
)
from warhammer40k_core.engine.mission_action_policies import (
    mission_action_policy_for_id,
)
from warhammer40k_core.engine.mission_terrain import (
    logical_terrain_area_within_player_deployment_zone,
    logical_terrain_area_within_player_territory,
    mission_logical_terrain_area_by_id,
    mission_logical_terrain_areas,
    model_intersects_logical_terrain_area,
)
from warhammer40k_core.engine.missions import mission_pack_for_id
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_mission_action_battlefield_evidence import (
    MissionActionBattlefieldBoundaryEvidence,
)
from warhammer40k_core.engine.primary_mission_action_lifecycle_evidence import (
    MissionActionStartAuthorityEvidence,
    MissionActionStartAuthorityOptionEvidence,
    PrimaryMissionActionStartEvidence,
    canonical_json_object,
)
from warhammer40k_core.engine.primary_mission_action_lifecycle_policy import (
    capture_primary_mission_action_start_evidence,
)
from warhammer40k_core.engine.primary_mission_action_options import (
    primary_mission_action_start_targets,
    primary_mission_action_target_kind,
)
from warhammer40k_core.engine.primary_mission_boundary_checkpoint import (
    terrain_model_inventory_from_checkpoint,
)
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PrimaryMissionBoundaryCheckpoint,
    PrimaryMissionBoundaryCheckpointReference,
)
from warhammer40k_core.engine.primary_mission_boundary_state import (
    primary_mission_action_boundary_state_from_checkpoint,
)
from warhammer40k_core.engine.primary_scoring_conditions import (
    home_objective_ids as _home_objective_ids,
)
from warhammer40k_core.engine.rules_units import (
    rules_unit_display_name,
    rules_unit_id_for_unit_id,
    rules_unit_view_by_id,
    rules_unit_views_from_armies,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import SecondaryMissionCardStatus

_LEGACY_MISSION_ACTION_TARGET_POLICIES = frozenset(
    ("objective_marker", "trappable_terrain_area", "plunderable_terrain_area")
)
SUPPORTED_MISSION_ACTION_TARGET_POLICIES = frozenset(
    (*_LEGACY_MISSION_ACTION_TARGET_POLICIES, *PRIMARY_MISSION_ACTION_TARGET_POLICIES)
)


@dataclass(frozen=True, slots=True)
class MissionActionStartOption:
    action: MissionActionDefinition
    unit_instance_id: str
    target_id: str
    condition_target_id: str | None
    eligible_unit_instance_ids: tuple[str, ...]

    def option_id(self) -> str:
        return f"start:{self.action.mission_action_id}:{self.unit_instance_id}:{self.target_id}"

    def label(self, *, state: GameState) -> str:
        rules_unit = rules_unit_view_by_id(
            state=state,
            unit_instance_id=self.unit_instance_id,
        )
        return (
            f"{self.action.name} — "
            f"{rules_unit_display_name(rules_unit)} ({self.unit_instance_id}) — "
            f"{_target_display_name(state=state, target_id=self.target_id)} ({self.target_id})"
        )

    def payload(
        self,
        *,
        state: GameState,
        player_id: str,
        phase: BattlePhase,
    ) -> dict[str, JsonValue]:
        return {
            "game_id": state.game_id,
            "player_id": player_id,
            "battle_round": state.battle_round,
            "phase": phase.value,
            "mission_action_id": self.action.mission_action_id,
            "mission_id": self.action.mission_id,
            "mission_kind": self.action.mission_kind,
            "unit_instance_id": self.unit_instance_id,
            "target_id": self.target_id,
            "condition_target_id": self.condition_target_id,
            "target_kind": _target_kind_for_policy(self.action.target_policy),
            "target_policy": self.action.target_policy,
            "start_timing": self.action.start_timing,
            "completion_timing": self.action.completion_timing,
            "eligible_unit_instance_ids": list(self.eligible_unit_instance_ids),
            "interruption_conditions": list(self.action.interruption_conditions),
            "scoring_source_id": self.action.scoring_source_id,
            "victory_points": self.action.victory_points,
        }


def mission_action_opportunity_options(
    *,
    state: GameState,
    player_id: str,
    runtime_modifier_registry: RuntimeModifierRegistry,
    relevant_actions: tuple[MissionActionDefinition, ...] | None = None,
) -> tuple[MissionActionStartOption, ...]:
    _require_runtime_modifier_registry(runtime_modifier_registry)
    phase = _current_phase(state)
    actions = (
        available_mission_actions_for_state(state=state, player_id=player_id)
        if relevant_actions is None
        else relevant_actions
    )
    options = tuple(
        option
        for action in actions
        if action.start_phase == phase.value
        and action.target_policy in SUPPORTED_MISSION_ACTION_TARGET_POLICIES
        for option in mission_action_start_options(
            state=state,
            player_id=player_id,
            action=action,
            runtime_modifier_registry=runtime_modifier_registry,
        )
    )
    return tuple(sorted(options, key=lambda option: option.option_id()))


def mission_action_start_options(
    *,
    state: GameState,
    player_id: str,
    action: MissionActionDefinition,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> tuple[MissionActionStartOption, ...]:
    _require_runtime_modifier_registry(runtime_modifier_registry)
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Mission Action start requires battlefield_state.")
    if state.mission_setup is None:
        raise GameLifecycleError("Mission Action start requires MissionSetup.")
    if action.target_policy not in SUPPORTED_MISSION_ACTION_TARGET_POLICIES:
        raise GameLifecycleError("Unsupported Mission Action target policy.")
    if action.target_policy in PRIMARY_MISSION_ACTION_TARGET_POLICIES:
        primary_targets = primary_mission_action_start_targets(
            state=state,
            player_id=player_id,
            action=action,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        eligible_unit_ids = tuple(sorted({target.unit_instance_id for target in primary_targets}))
        return tuple(
            MissionActionStartOption(
                action=action,
                unit_instance_id=target.unit_instance_id,
                target_id=target.target_id,
                condition_target_id=target.condition_target_id,
                eligible_unit_instance_ids=eligible_unit_ids,
            )
            for target in primary_targets
        )
    placed_army = battlefield_state.placed_army_for_player_or_none(player_id)
    if placed_army is None:
        return ()
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=battlefield_state,
    )
    eligible_unit_ids = _eligible_rules_unit_instance_ids_for_action(
        state=state,
        player_id=player_id,
        action=action,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    target_ids_by_unit = _target_ids_by_unit_for_action(
        state=state,
        player_id=player_id,
        action=action,
        scenario=scenario,
        placed_unit_ids=eligible_unit_ids,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    eligible_target_pairs = tuple(
        (unit_id, target_id)
        for unit_id in eligible_unit_ids
        for target_id in target_ids_by_unit.get(unit_id, ())
    )
    if not eligible_target_pairs:
        return ()
    return tuple(
        MissionActionStartOption(
            action=action,
            unit_instance_id=unit_id,
            target_id=target_id,
            condition_target_id=target_id,
            eligible_unit_instance_ids=eligible_unit_ids,
        )
        for unit_id, target_id in eligible_target_pairs
    )


def primary_mission_action_start_evidence_for_selection(
    *,
    state: GameState,
    player_id: str,
    action: MissionActionDefinition,
    unit_instance_id: str,
    target_id: str,
    condition_target_id: str | None,
    opportunity: bool,
    decline_option_id: str,
    boundary_checkpoint: PrimaryMissionBoundaryCheckpointReference,
    boundary_checkpoint_evidence: PrimaryMissionBoundaryCheckpoint,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> PrimaryMissionActionStartEvidence:
    """Recompute the complete legal inventory before capturing selected start evidence."""

    _require_runtime_modifier_registry(runtime_modifier_registry)
    if (
        boundary_checkpoint_evidence.reference(event_id=boundary_checkpoint.checkpoint_event_id)
        != boundary_checkpoint
    ):
        raise GameLifecycleError("Primary Mission Action boundary checkpoint drifted.")
    boundary_state = primary_mission_action_boundary_state_from_checkpoint(
        state=state,
        checkpoint=boundary_checkpoint_evidence,
    )
    boundary_registry = RuntimeModifierRegistry.empty()
    if action.target_policy not in PRIMARY_MISSION_ACTION_TARGET_POLICIES:
        raise GameLifecycleError("Start evidence requires a source-backed Primary Action.")
    battlefield_state = boundary_state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Start evidence requires battlefield_state.")
    phase = _current_phase(boundary_state)
    options = (
        mission_action_opportunity_options(
            state=boundary_state,
            player_id=player_id,
            runtime_modifier_registry=boundary_registry,
        )
        if opportunity
        else mission_action_start_options(
            state=boundary_state,
            player_id=player_id,
            action=action,
            runtime_modifier_registry=boundary_registry,
        )
    )
    matching = tuple(
        option
        for option in options
        if option.action.mission_action_id == action.mission_action_id
        and option.unit_instance_id == unit_instance_id
        and option.target_id == target_id
        and option.condition_target_id == condition_target_id
    )
    if len(matching) != 1:
        raise GameLifecycleError("Selected Primary Mission Action target is not legal.")
    action_option_ids = [option.option_id() for option in options]
    if opportunity:
        request_payload: dict[str, JsonValue] = {
            "game_id": boundary_state.game_id,
            "player_id": player_id,
            "battle_round": boundary_state.battle_round,
            "phase": phase.value,
            "mission_action_opportunity": True,
            "legal_mission_action_ids": cast(
                list[JsonValue],
                sorted({option.action.mission_action_id for option in options}),
            ),
            "legal_action_option_ids": cast(list[JsonValue], action_option_ids),
            "legal_option_ids": cast(
                list[JsonValue],
                sorted((*action_option_ids, decline_option_id)),
            ),
        }
        authority_options = (
            *(
                MissionActionStartAuthorityOptionEvidence(
                    option_id=option.option_id(),
                    label=option.label(state=boundary_state),
                    payload_json=canonical_json_object(
                        {
                            **option.payload(
                                state=boundary_state,
                                player_id=player_id,
                                phase=phase,
                            ),
                            "mission_action_opportunity": True,
                            "legal_action_option_ids": action_option_ids,
                        }
                    ),
                )
                for option in options
            ),
            MissionActionStartAuthorityOptionEvidence(
                option_id=decline_option_id,
                label="Continue to shooting",
                payload_json=canonical_json_object(
                    {
                        "game_id": boundary_state.game_id,
                        "player_id": player_id,
                        "battle_round": boundary_state.battle_round,
                        "phase": phase.value,
                        "mission_action_opportunity": True,
                        "legal_action_option_ids": action_option_ids,
                    }
                ),
            ),
        )
    else:
        request_payload = {
            "game_id": boundary_state.game_id,
            "player_id": player_id,
            "battle_round": boundary_state.battle_round,
            "phase": phase.value,
            "mission_action_id": action.mission_action_id,
            "legal_option_ids": cast(list[JsonValue], action_option_ids),
        }
        authority_options = tuple(
            MissionActionStartAuthorityOptionEvidence(
                option_id=option.option_id(),
                label=option.label(state=boundary_state),
                payload_json=canonical_json_object(
                    option.payload(
                        state=boundary_state,
                        player_id=player_id,
                        phase=phase,
                    )
                ),
            )
            for option in options
        )
    start_authority = MissionActionStartAuthorityEvidence(
        request_kind="opportunity" if opportunity else "direct",
        request_payload_json=canonical_json_object(request_payload),
        battlefield_boundary=MissionActionBattlefieldBoundaryEvidence.from_battlefield_state(
            battlefield_state
        ),
        options=authority_options,
        candidate_units=(),
        terrain_model_inventory=(),
    )
    return capture_primary_mission_action_start_evidence(
        state=boundary_state,
        player_id=player_id,
        action=action,
        policy=mission_action_policy_for_id(action.mission_action_id),
        unit_instance_id=unit_instance_id,
        target_id=target_id,
        condition_target_id=condition_target_id,
        eligible_unit_instance_ids=matching[0].eligible_unit_instance_ids,
        start_authority=start_authority,
        boundary_checkpoint=boundary_checkpoint,
        boundary_terrain_model_inventory=terrain_model_inventory_from_checkpoint(
            boundary_checkpoint_evidence
        ),
        runtime_modifier_registry=boundary_registry,
    )


def mission_action_for_state(
    *,
    state: GameState,
    mission_action_id: str,
) -> MissionActionDefinition:
    if state.mission_setup is None:
        raise GameLifecycleError("Mission Action start requires MissionSetup.")
    mission_pack = mission_pack_for_id(state.mission_setup.mission_pack_id)
    return mission_pack.mission_action(mission_action_id)


def available_mission_actions_for_state(
    *,
    state: GameState,
    player_id: str,
) -> tuple[MissionActionDefinition, ...]:
    if state.mission_setup is None:
        raise GameLifecycleError("Mission Action availability requires MissionSetup.")
    requested_player = _validate_player_id(state=state, player_id=player_id)
    mission_pack = mission_pack_for_id(state.mission_setup.mission_pack_id)
    active_secondary_ids = {
        card.secondary_mission_id
        for card in state.secondary_mission_card_states
        if card.player_id == requested_player and card.status is SecondaryMissionCardStatus.ACTIVE
    }
    available: list[MissionActionDefinition] = []
    assigned_primary_mission_id = state.mission_setup.primary_mission_id_for_player(
        requested_player
    )
    for action in mission_pack.mission_actions:
        if action.mission_kind == "primary":
            if action.mission_id == assigned_primary_mission_id:
                available.append(action)
            continue
        if action.mission_kind == "secondary":
            if action.mission_id in active_secondary_ids:
                available.append(action)
            continue
        raise GameLifecycleError("Mission Action has an unsupported mission_kind.")
    return tuple(sorted(available, key=lambda action: action.mission_action_id))


def mission_action_opportunity_drift_reason(
    *,
    state: GameState,
    payload: dict[str, JsonValue],
    player_id: str,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> str | None:
    shooting_state = state.shooting_phase_state
    if shooting_state is None:
        return "missing_shooting_phase_state"
    if shooting_state.mission_action_opportunity_declined:
        return "mission_action_opportunity_already_declined"
    expected_option_ids = tuple(_payload_string_list(payload, key="legal_action_option_ids"))
    try:
        current_option_ids = tuple(
            option.option_id()
            for option in mission_action_opportunity_options(
                state=state,
                player_id=player_id,
                runtime_modifier_registry=runtime_modifier_registry,
            )
        )
    except PlacementError as exc:
        raise GameLifecycleError("Mission Action opportunity validation failed.") from exc
    if current_option_ids != expected_option_ids:
        return "legal_action_options_drift"
    return None


def _eligible_rules_unit_instance_ids_for_action(
    *,
    state: GameState,
    player_id: str,
    action: MissionActionDefinition,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> tuple[str, ...]:
    eligible_ids: list[str] = []
    for rules_unit in rules_unit_views_from_armies(armies=tuple(state.army_definitions)):
        if rules_unit.owner_player_id != player_id:
            continue
        if (
            mission_action_unit_ineligibility_reason(
                state=state,
                player_id=player_id,
                unit_instance_id=rules_unit.unit_instance_id,
                runtime_modifier_registry=runtime_modifier_registry,
            )
            is not None
        ):
            continue
        if not _unit_matches_eligible_policy(rules_unit.keywords, action.eligible_unit_policy):
            continue
        eligible_ids.append(rules_unit.unit_instance_id)
    return tuple(sorted(eligible_ids))


def _target_ids_by_unit_for_action(
    *,
    state: GameState,
    player_id: str,
    action: MissionActionDefinition,
    scenario: BattlefieldScenario,
    placed_unit_ids: tuple[str, ...],
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> dict[str, tuple[str, ...]]:
    if action.target_policy == "objective_marker":
        return _objective_marker_target_ids_by_unit(
            state=state,
            player_id=player_id,
            action=action,
            runtime_modifier_registry=runtime_modifier_registry,
        )
    if action.target_policy == "trappable_terrain_area":
        return _trappable_terrain_target_ids_by_unit(
            state=state,
            player_id=player_id,
            scenario=scenario,
            placed_unit_ids=placed_unit_ids,
        )
    if action.target_policy == "plunderable_terrain_area":
        return _plunderable_terrain_target_ids_by_unit(
            state=state,
            player_id=player_id,
            scenario=scenario,
            placed_unit_ids=placed_unit_ids,
        )
    raise GameLifecycleError("Unsupported Mission Action target policy.")


def _unit_matches_eligible_policy(
    keywords: tuple[str, ...],
    eligible_unit_policy: str,
) -> bool:
    policy = _validate_identifier("eligible_unit_policy", eligible_unit_policy)
    keyword_set = {_canonical_keyword(keyword) for keyword in keywords}
    if policy == "active_player_unit":
        return True
    if policy == "active_player_infantry_or_battleline_unit":
        return bool(keyword_set.intersection({"INFANTRY", "BATTLELINE"}))
    raise GameLifecycleError("Unsupported Mission Action eligible unit policy.")


def _objective_marker_target_ids_by_unit(
    *,
    state: GameState,
    player_id: str,
    action: MissionActionDefinition,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> dict[str, tuple[str, ...]]:
    mission_setup = state.mission_setup
    if mission_setup is None:
        raise GameLifecycleError("Objective Mission Action requires MissionSetup.")
    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=_current_phase(state),
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            runtime_modifier_registry=runtime_modifier_registry,
        )
    )
    home_objective_ids: frozenset[str]
    already_actioned_objective_ids: set[str]
    if action.mission_action_id == "cleanse-objective":
        home_objective_ids = frozenset(
            _home_objective_ids(
                mission_setup,
                player_id=player_id,
            )
        )
        already_actioned_objective_ids = {
            action_state.target_id
            for action_state in state.mission_action_states
            if action_state.player_id == player_id
            and action_state.mission_id == action.mission_id
            and action_state.battle_round_started == state.battle_round
        }
    else:
        home_objective_ids = frozenset()
        already_actioned_objective_ids = set()
    targets_by_unit: dict[str, set[str]] = {}
    for result in record.results:
        if result.objective_id in home_objective_ids:
            continue
        if result.objective_id in already_actioned_objective_ids:
            continue
        for contribution in result.contributors:
            if contribution.player_id != player_id:
                continue
            rules_unit_id = rules_unit_id_for_unit_id(
                armies=tuple(state.army_definitions),
                unit_instance_id=contribution.unit_instance_id,
            )
            targets_by_unit.setdefault(rules_unit_id, set()).add(result.objective_id)
    return {
        unit_id: tuple(sorted(target_ids))
        for unit_id, target_ids in sorted(targets_by_unit.items(), key=lambda item: item[0])
    }


def _trappable_terrain_target_ids_by_unit(
    *,
    state: GameState,
    player_id: str,
    scenario: BattlefieldScenario,
    placed_unit_ids: tuple[str, ...],
) -> dict[str, tuple[str, ...]]:
    if state.mission_setup is None:
        raise GameLifecycleError("Trappable terrain Mission Action requires MissionSetup.")
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Trappable terrain Mission Action requires battlefield_state.")
    requested_player = _validate_player_id(state=state, player_id=player_id)
    eligible_unit_ids = set(
        _validate_identifier_tuple(
            "placed_unit_ids",
            placed_unit_ids,
            min_length=0,
            sort_values=True,
        )
    )
    trapped_area_ids = {
        trap.terrain_feature_id
        for trap in state.primary_terrain_trap_states
        if trap.player_id == requested_player
    }
    candidate_areas = tuple(
        area
        for area in mission_logical_terrain_areas(state.mission_setup)
        if area.logical_terrain_area_id not in trapped_area_ids
        and not logical_terrain_area_within_player_deployment_zone(
            area,
            mission_setup=state.mission_setup,
            player_id=requested_player,
        )
    )
    if not candidate_areas:
        return {}
    placed_army = battlefield_state.placed_army_for_player_or_none(requested_player)
    if placed_army is None:
        return {}
    targets_by_unit: dict[str, set[str]] = {}
    for unit_placement in placed_army.unit_placements:
        rules_unit_id = rules_unit_id_for_unit_id(
            armies=tuple(state.army_definitions),
            unit_instance_id=unit_placement.unit_instance_id,
        )
        if rules_unit_id not in eligible_unit_ids:
            continue
        for model_placement in unit_placement.model_placements:
            model = geometry_model_for_placement(
                model=scenario.model_instance_for_placement(model_placement),
                placement=model_placement,
            )
            for area in candidate_areas:
                if model_intersects_logical_terrain_area(model, area=area):
                    targets_by_unit.setdefault(rules_unit_id, set()).add(
                        area.logical_terrain_area_id
                    )
    return {
        unit_id: tuple(sorted(target_ids))
        for unit_id, target_ids in sorted(targets_by_unit.items(), key=lambda item: item[0])
    }


def _plunderable_terrain_target_ids_by_unit(
    *,
    state: GameState,
    player_id: str,
    scenario: BattlefieldScenario,
    placed_unit_ids: tuple[str, ...],
) -> dict[str, tuple[str, ...]]:
    if any(
        plunder.player_id == player_id
        and plunder.battle_round == state.battle_round
        and plunder.active_player_id == _active_player_id(state)
        for plunder in state.secondary_terrain_plunder_states
    ):
        return {}
    return _terrain_area_target_ids_by_unit(
        state=state,
        player_id=player_id,
        scenario=scenario,
        placed_unit_ids=placed_unit_ids,
        excluded_logical_terrain_area_ids=(),
    )


def _terrain_area_target_ids_by_unit(
    *,
    state: GameState,
    player_id: str,
    scenario: BattlefieldScenario,
    placed_unit_ids: tuple[str, ...],
    excluded_logical_terrain_area_ids: tuple[str, ...],
) -> dict[str, tuple[str, ...]]:
    if state.mission_setup is None:
        raise GameLifecycleError("Terrain area Mission Action requires MissionSetup.")
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Terrain area Mission Action requires battlefield_state.")
    requested_player = _validate_player_id(state=state, player_id=player_id)
    eligible_unit_ids = set(
        _validate_identifier_tuple(
            "placed_unit_ids",
            placed_unit_ids,
            min_length=0,
            sort_values=True,
        )
    )
    excluded_ids = set(
        _validate_identifier_tuple(
            "excluded_logical_terrain_area_ids",
            excluded_logical_terrain_area_ids,
            min_length=0,
            sort_values=True,
        )
    )
    candidate_areas = tuple(
        area
        for area in mission_logical_terrain_areas(state.mission_setup)
        if area.logical_terrain_area_id not in excluded_ids
        and not logical_terrain_area_within_player_territory(
            area,
            mission_setup=state.mission_setup,
            player_id=requested_player,
        )
    )
    if not candidate_areas:
        return {}
    placed_army = battlefield_state.placed_army_for_player_or_none(requested_player)
    if placed_army is None:
        return {}
    targets_by_unit: dict[str, set[str]] = {}
    for unit_placement in placed_army.unit_placements:
        rules_unit_id = rules_unit_id_for_unit_id(
            armies=tuple(state.army_definitions),
            unit_instance_id=unit_placement.unit_instance_id,
        )
        if rules_unit_id not in eligible_unit_ids:
            continue
        for model_placement in unit_placement.model_placements:
            model = geometry_model_for_placement(
                model=scenario.model_instance_for_placement(model_placement),
                placement=model_placement,
            )
            for area in candidate_areas:
                if model_intersects_logical_terrain_area(model, area=area):
                    targets_by_unit.setdefault(rules_unit_id, set()).add(
                        area.logical_terrain_area_id
                    )
    return {
        unit_id: tuple(sorted(target_ids))
        for unit_id, target_ids in sorted(targets_by_unit.items(), key=lambda item: item[0])
    }


def _target_kind_for_policy(target_policy: str) -> str:
    policy = _validate_identifier("target_policy", target_policy)
    if policy in PRIMARY_MISSION_ACTION_TARGET_POLICIES:
        return primary_mission_action_target_kind(policy)
    if policy == "objective_marker":
        return "objective_marker"
    if policy in {"trappable_terrain_area", "plunderable_terrain_area"}:
        return "terrain_area"
    raise GameLifecycleError("Unsupported Mission Action target policy.")


def _target_display_name(*, state: GameState, target_id: str) -> str:
    if state.mission_setup is None:
        raise GameLifecycleError("Mission Action target display requires MissionSetup.")
    for marker in state.mission_setup.objective_markers:
        if marker.objective_marker_id == target_id:
            return marker.name
    for rules_unit in rules_unit_views_from_armies(armies=tuple(state.army_definitions)):
        if rules_unit.unit_instance_id == target_id:
            return rules_unit_display_name(rules_unit)
    mission_logical_terrain_area_by_id(
        state.mission_setup,
        logical_terrain_area_id=target_id,
    )
    return "Terrain area"


def _canonical_keyword(keyword: str) -> str:
    return _validate_identifier("keyword", keyword).replace("-", " ").replace("_", " ").upper()


def _current_phase(state: GameState) -> BattlePhase:
    phase = state.current_battle_phase
    if phase is None:
        raise GameLifecycleError("Mission Action options require a battle phase.")
    return phase


def _active_player_id(state: GameState) -> str:
    active_player_id = state.active_player_id
    if active_player_id is None:
        raise GameLifecycleError("Mission Action options require an active player.")
    return active_player_id


def _validate_player_id(*, state: GameState, player_id: str) -> str:
    requested_player = _validate_identifier("player_id", player_id)
    if requested_player not in state.player_ids:
        raise GameLifecycleError("Mission Action player_id is not in this game.")
    return requested_player


def _payload_string_list(payload: dict[str, JsonValue], *, key: str) -> list[str]:
    value = payload[key]
    if not isinstance(value, list):
        raise GameLifecycleError(f"Mission Action payload key must be a list: {key}.")
    return [_validate_identifier(f"{key} value", item) for item in cast(list[object], value)]


def _require_runtime_modifier_registry(registry: object) -> None:
    if type(registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError("Mission Action options require a RuntimeModifierRegistry.")


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int,
    sort_values: bool,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    if len(identifiers) < min_length:
        raise GameLifecycleError(f"{field_name} must contain at least {min_length} values.")
    if sort_values:
        return tuple(sorted(identifiers))
    return tuple(identifiers)
