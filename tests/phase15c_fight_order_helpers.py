from __future__ import annotations

from typing import cast

from warhammer40k_core.adapters.contracts import ParameterizedSubmission
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.missions import ObjectiveMarkerDefinition, ObjectiveMarkerRole
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    RulesetDescriptor,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.attack_sequence import (
    ATTACK_ALLOCATION_DECISION_TYPES,
    ATTACK_RESOLUTION_SELECTION_DECISION_TYPES,
)
from warhammer40k_core.engine.battlefield_state import ModelPlacement, UnitPlacement
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.fight_order import (
    CHARGE_FIGHTS_FIRST_EFFECT_KIND,
    FIGHT_INTERRUPT_EFFECT_KIND,
    FIGHTS_FIRST_EFFECT_KIND,
)
from warhammer40k_core.engine.fight_resolution import (
    MeleeDeclarationProposalRequest,
)
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack

_ATTACK_SEQUENCE_DECISION_TYPES = frozenset(
    (*ATTACK_RESOLUTION_SELECTION_DECISION_TYPES, *ATTACK_ALLOCATION_DECISION_TYPES)
)


def fight_lifecycle(
    *,
    alpha_unit_ids: tuple[str, ...],
    enemy_unit_ids: tuple[str, ...],
    origins: dict[str, Pose],
    game_id: str,
    fights_first_unit_keys: tuple[str, ...] = (),
    charge_fights_first_unit_keys: tuple[str, ...] = (),
    fight_interrupt_unit_keys: tuple[str, ...] = (),
    datasheet_id: str = "core-intercessor-like-infantry",
    model_profile_id: str = "core-intercessor-like",
    model_count: int = 5,
    alpha_unit_specs: dict[str, tuple[str, str, int]] | None = None,
    enemy_unit_specs: dict[str, tuple[str, str, int]] | None = None,
    catalog: ArmyCatalog | None = None,
) -> tuple[GameLifecycle, dict[str, UnitInstance]]:
    config = fight_config(
        game_id=game_id,
        alpha_unit_ids=alpha_unit_ids,
        enemy_unit_ids=enemy_unit_ids,
        datasheet_id=datasheet_id,
        model_profile_id=model_profile_id,
        model_count=model_count,
        alpha_unit_specs=alpha_unit_specs,
        enemy_unit_specs=enemy_unit_specs,
        catalog=catalog,
    )
    armies = mustered_armies(config)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id=f"{game_id}-battlefield",
        armies=armies,
    )
    units = {
        unit.unit_instance_id.split(":", maxsplit=1)[1]: unit
        for army in armies
        for unit in army.units
    }
    battlefield = scenario.battlefield_state
    for key, unit in units.items():
        army_id = unit.unit_instance_id.split(":", maxsplit=1)[0]
        player_id = "player-a" if army_id == "army-alpha" else "player-b"
        battlefield = battlefield.with_unit_placement(
            unit_placement_at(
                unit,
                army_id=army_id,
                player_id=player_id,
                poses=compact_test_unit_poses(
                    origin=origins[key],
                    model_count=len(unit.own_models),
                ),
            )
        )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    state.record_battlefield_state(battlefield)
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.battle_round = 1
    state.active_player_id = "player-a"
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    for key in fights_first_unit_keys:
        record_fights_first_effect(
            state=state,
            unit=units[key],
            effect_kind=FIGHTS_FIRST_EFFECT_KIND,
        )
    for key in charge_fights_first_unit_keys:
        record_fights_first_effect(
            state=state,
            unit=units[key],
            effect_kind=CHARGE_FIGHTS_FIRST_EFFECT_KIND,
        )
    for key in fight_interrupt_unit_keys:
        record_fight_interrupt_effect(state=state, unit=units[key])
    payload = cast(
        GameLifecyclePayload,
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": GameLifecycle().decision_controller.to_payload(),
            "reaction_queue": {"frames": []},
        },
    )
    return GameLifecycle.from_payload(payload), units


def fight_config(
    *,
    game_id: str,
    alpha_unit_ids: tuple[str, ...],
    enemy_unit_ids: tuple[str, ...],
    datasheet_id: str,
    model_profile_id: str,
    model_count: int,
    alpha_unit_specs: dict[str, tuple[str, str, int]] | None = None,
    enemy_unit_specs: dict[str, tuple[str, str, int]] | None = None,
    catalog: ArmyCatalog | None = None,
) -> GameConfig:
    resolved_catalog = ArmyCatalog.phase9a_canonical_content_pack() if catalog is None else catalog
    return GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase15c-test"
        ),
        army_catalog=resolved_catalog,
        army_muster_requests=(
            army_muster_request(
                catalog=resolved_catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=alpha_unit_ids,
                datasheet_id=datasheet_id,
                model_profile_id=model_profile_id,
                model_count=model_count,
                unit_specs=alpha_unit_specs,
            ),
            army_muster_request(
                catalog=resolved_catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=enemy_unit_ids,
                datasheet_id=datasheet_id,
                model_profile_id=model_profile_id,
                model_count=model_count,
                unit_specs=enemy_unit_specs,
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=mission_setup(),
    )


def mission_setup() -> MissionSetup:
    mission_pack = chapter_approved_2026_27_mission_pack()
    return MissionSetup(
        mission_pack_id=mission_pack.mission_pack_id,
        source_version=mission_pack.source_version,
        source_id=mission_pack.source_id,
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        primary_mission_id="take-and-hold",
        battlefield_layout_id=None,
        deployment_map_id="phase15c-open-map",
        terrain_layout_id="phase15c-open-layout",
        attacker_player_id="player-a",
        defender_player_id="player-b",
        battlefield_width_inches=100.0,
        battlefield_depth_inches=100.0,
        objective_markers=(
            ObjectiveMarkerDefinition(
                objective_marker_id="phase15c-remote-objective",
                name="Phase 15C Remote Objective",
                objective_role=ObjectiveMarkerRole.CENTRAL,
                x_inches=95.0,
                y_inches=95.0,
                source_id="phase15c-test",
            ),
        ),
        deployment_zones=(),
        battlefield_regions=(),
        terrain_areas=(),
        terrain_features=(),
    )


def army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_ids: tuple[str, ...],
    datasheet_id: str,
    model_profile_id: str,
    model_count: int,
    unit_specs: dict[str, tuple[str, str, int]] | None = None,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        unit_selections=tuple(
            unit_selection_for_id(
                unit_id,
                unit_specs=unit_specs,
                default_datasheet_id=datasheet_id,
                default_model_profile_id=model_profile_id,
                default_model_count=model_count,
            )
            for unit_id in unit_selection_ids
        ),
    )


def unit_selection_for_id(
    unit_id: str,
    *,
    unit_specs: dict[str, tuple[str, str, int]] | None,
    default_datasheet_id: str,
    default_model_profile_id: str,
    default_model_count: int,
) -> UnitMusterSelection:
    datasheet_id, model_profile_id, model_count = unit_selection_spec(
        unit_id=unit_id,
        unit_specs=unit_specs,
        default_datasheet_id=default_datasheet_id,
        default_model_profile_id=default_model_profile_id,
        default_model_count=default_model_count,
    )
    return unit_selection(
        unit_id,
        datasheet_id=datasheet_id,
        model_profile_id=model_profile_id,
        model_count=model_count,
    )


def unit_selection_spec(
    *,
    unit_id: str,
    unit_specs: dict[str, tuple[str, str, int]] | None,
    default_datasheet_id: str,
    default_model_profile_id: str,
    default_model_count: int,
) -> tuple[str, str, int]:
    if unit_specs is not None and unit_id in unit_specs:
        return unit_specs[unit_id]
    return (default_datasheet_id, default_model_profile_id, default_model_count)


def unit_selection(
    unit_selection_id: str,
    *,
    datasheet_id: str,
    model_profile_id: str,
    model_count: int,
) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id=model_profile_id,
                model_count=model_count,
            ),
        ),
    )


def mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


def compact_test_unit_poses(*, origin: Pose, model_count: int) -> tuple[Pose, ...]:
    return tuple(
        Pose.at(
            origin.position.x + ((index % 5) * 1.4),
            origin.position.y + ((index // 5) * 1.4),
            origin.position.z,
            facing_degrees=origin.facing.degrees,
        )
        for index in range(model_count)
    )


def unit_placement_at(
    unit: UnitInstance,
    *,
    army_id: str,
    player_id: str,
    poses: tuple[Pose, ...],
) -> UnitPlacement:
    return UnitPlacement(
        army_id=army_id,
        player_id=player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army_id,
                player_id=player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=pose,
            )
            for model, pose in zip(unit.own_models, poses, strict=True)
        ),
    )


def record_fights_first_effect(
    *,
    state: GameState,
    unit: UnitInstance,
    effect_kind: str,
) -> None:
    player_id = player_id_for_unit(unit)
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=f"{unit.unit_instance_id}:{effect_kind}",
            source_rule_id=f"phase15c:{effect_kind}",
            owner_player_id=player_id,
            target_unit_instance_ids=(unit.unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.CHARGE,
            expiration=EffectExpiration.end_turn(
                battle_round=state.battle_round,
                player_id=player_id,
            ),
            effect_payload={"effect_kind": effect_kind},
        )
    )


def record_fight_interrupt_effect(*, state: GameState, unit: UnitInstance) -> None:
    player_id = player_id_for_unit(unit)
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=f"{unit.unit_instance_id}:fight-interrupt",
            source_rule_id="phase15c:counter-offensive",
            owner_player_id=player_id,
            target_unit_instance_ids=(unit.unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.FIGHT,
            expiration=EffectExpiration.end_phase(
                battle_round=state.battle_round,
                phase=BattlePhaseKind.FIGHT,
                player_id=player_id,
            ),
            effect_payload={
                "effect_kind": FIGHT_INTERRUPT_EFFECT_KIND,
                "source_rule_id": "phase15c:counter-offensive",
            },
        )
    )


def player_id_for_unit(unit: UnitInstance) -> str:
    army_id = unit.unit_instance_id.split(":", maxsplit=1)[0]
    return "player-a" if army_id == "army-alpha" else "player-b"


def advance_to_fight_order_request(lifecycle: GameLifecycle) -> DecisionRequest:
    return decision_request(
        drain_fight_movement_requests(
            lifecycle,
            lifecycle.advance_until_decision_or_terminal(),
        )
    )


def drain_fight_movement_requests(
    lifecycle: GameLifecycle,
    status: LifecycleStatus,
) -> LifecycleStatus:
    current = status
    while (
        current.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
        and current.decision_request is not None
        and current.decision_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    ):
        request = current.decision_request
        proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
        assert proposal_request.proposal_kind in {
            ProposalKind.PILE_IN,
            ProposalKind.CONSOLIDATE,
        }
        context = cast(dict[str, JsonValue], proposal_request.context)
        current = lifecycle.submit_decision(
            ParameterizedSubmission(
                request_id=request.request_id,
                result_id=f"{request.request_id}:phase15c-no-move",
                payload=cast(
                    JsonValue,
                    {
                        "proposal_request_id": proposal_request.request_id,
                        "proposal_kind": proposal_request.proposal_kind.value,
                        "unit_instance_id": proposal_request.unit_instance_id,
                        "movement_phase_action": proposal_request.movement_phase_action,
                        "movement_mode": context["movement_mode"],
                    },
                ),
            ).to_result(request)
        )
    return current


def submit_minimal_melee_declaration(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    result_id: str,
) -> LifecycleStatus:
    proposal_request = MeleeDeclarationProposalRequest.from_decision_request(request)
    declarations: list[dict[str, object]] = []
    primary_model_ids: set[str] = set()
    for weapon in proposal_request.available_weapons:
        weapon_payload = cast(dict[str, object], weapon)
        model_id = cast(str, weapon_payload["model_instance_id"])
        if model_id in primary_model_ids:
            continue
        if weapon_payload["is_extra_attacks"] is True:
            continue
        engaged_target_ids = cast(
            list[str],
            weapon_payload["engaged_target_unit_instance_ids"],
        )
        if not engaged_target_ids:
            continue
        primary_model_ids.add(model_id)
        declarations.append(
            {
                "attacker_model_instance_id": model_id,
                "wargear_id": weapon_payload["wargear_id"],
                "weapon_profile_id": weapon_payload["weapon_profile_id"],
                "target_allocations": [
                    {"target_unit_instance_id": engaged_target_ids[0]},
                ],
            }
        )
    return lifecycle.submit_decision(
        ParameterizedSubmission(
            request_id=request.request_id,
            result_id=result_id,
            payload=cast(
                JsonValue,
                {
                    "proposal_request_id": proposal_request.request_id,
                    "proposal_kind": proposal_request.proposal_kind,
                    "player_id": proposal_request.actor_id,
                    "battle_round": proposal_request.battle_round,
                    "unit_instance_id": proposal_request.unit_instance_id,
                    "source_decision_request_id": (proposal_request.source_decision_request_id),
                    "source_decision_result_id": proposal_request.source_decision_result_id,
                    "declarations": declarations,
                },
            ),
        ).to_result(request)
    )


def decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request
