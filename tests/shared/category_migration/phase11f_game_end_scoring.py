from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from tests.setup_completion_helpers import enter_battle_for_fixture
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.final_scoring import (
    FinalScoreLine,
    FinalScoringResult,
    FinalScoringResultPayload,
)
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    GameStatePayload,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup
from warhammer40k_core.engine.objective_control import ObjectiveControlTiming
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.primary_scoring_boundary_lifecycle import (
    resolve_primary_scoring_boundary_lifecycle,
)
from warhammer40k_core.engine.primary_scoring_state_evidence import (
    build_primary_scoring_state_evidence,
    record_primary_scoring_state_evidence,
)
from warhammer40k_core.engine.primary_turn_start_evidence import record_primary_turn_start_evidence
from warhammer40k_core.engine.scoring import (
    VictoryPointAward,
    VictoryPointSourceKind,
    VictoryPointTransaction,
)
from warhammer40k_core.engine.scoring_cap_audit import metadata_with_vp_cap_audit
from warhammer40k_core.engine.secondary_scoring_provider import SecondaryScoringProviderKind
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import (
    chapter_approved_2026_27_mission_pack,
    warhammer_event_companion_2026_07_mission_pack,
)

PHASE16A_MISSION_POOL_ENTRY_ID = "mission-take-and-hold-vs-purge-the-foe-layout-3"


def _immovable_object_primary_award_fixture() -> tuple[GameState, VictoryPointAward]:
    state = _battle_state()
    mission_setup = state.mission_setup
    if mission_setup is None:
        raise AssertionError("Immovable Object award fixture requires MissionSetup.")
    policy = mission_scoring_policies_from_setup(mission_setup).policy_for_player("player-a")
    state.battle_round = 2
    battlefield = state.battlefield_state
    if battlefield is None:
        raise AssertionError("Immovable Object award fixture requires battlefield state.")
    controlled_marker = mission_setup.objective_markers[0]
    player_a_unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-a"
        for unit in army.units
    )
    placement = battlefield.unit_placement_by_id(player_a_unit.unit_instance_id)
    offsets = ((0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (0.0, 1.0), (1.0, 1.0))
    state.battlefield_state = battlefield.with_unit_placement(
        replace(
            placement,
            model_placements=tuple(
                replace(
                    model_placement,
                    pose=Pose.at(
                        controlled_marker.x_inches + x_offset,
                        controlled_marker.y_inches + y_offset,
                        model_placement.pose.position.z,
                        facing_degrees=model_placement.pose.facing.degrees,
                    ),
                )
                for model_placement, (x_offset, y_offset) in zip(
                    placement.model_placements,
                    offsets,
                    strict=True,
                )
            ),
        )
    )
    record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.COMMAND,
        timing=ObjectiveControlTiming.PHASE_END,
        runtime_modifier_registry=None,
    )
    state_evidence = build_primary_scoring_state_evidence(
        scoring_player_id=record.active_player_id,
        state=state,
        record=record,
        end_of_battle=False,
    )
    awards = policy.primary_awards_from_objective_control(
        record=record,
        mission_setup=mission_setup,
        turn_order=state.turn_order,
        turn_start_states=tuple(state.primary_objective_turn_start_states),
        terrain_trap_states=tuple(state.primary_terrain_trap_states),
        unit_destruction_states=tuple(state.primary_unit_destruction_states),
        state_evidence=state_evidence,
    )
    if len(awards) != 1 or awards[0].amount != 5:
        raise AssertionError("Immovable Object fixture requires one 5VP Primary award.")
    metadata = awards[0].metadata
    if not isinstance(metadata, dict) or metadata.get("score_count") != 1:
        raise AssertionError("Immovable Object fixture requires score_count 1 evidence.")
    record_primary_scoring_state_evidence(state=state, evidence=state_evidence)
    return state, awards[0]


def _assert_final_payload_rejected(payload: dict[str, object], message: str) -> None:
    with pytest.raises(GameLifecycleError, match=message):
        FinalScoringResult.from_payload(cast(FinalScoringResultPayload, payload))


def _cap_reasons(transaction: VictoryPointTransaction) -> list[str]:
    payload = transaction.metadata
    assert isinstance(payload, dict)
    audit = payload["vp_cap_audit"]
    assert isinstance(audit, dict)
    reasons = audit["capped_reasons"]
    assert isinstance(reasons, list)
    return [str(reason) for reason in reasons]


def _set_round_five_going_second_fight(state: GameState) -> None:
    state.battle_round = 5
    state.active_player_id = "player-b"
    record_primary_turn_start_evidence(state=state)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)


def _battle_state(
    *,
    mission_pool_entry_id: str = PHASE16A_MISSION_POOL_ENTRY_ID,
    mission_setup: MissionSetup | None = None,
) -> GameState:
    config = _config(
        mission_pool_entry_id=mission_pool_entry_id,
        mission_setup=mission_setup,
    )
    state = GameState.from_config(config)
    assert config.mission_setup is not None
    for army in _mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase11f-battlefield",
        armies=tuple(state.army_definitions),
        battlefield_width_inches=config.mission_setup.battlefield_width_inches,
        battlefield_depth_inches=config.mission_setup.battlefield_depth_inches,
        terrain_features=config.mission_setup.terrain_features,
    )
    state.record_battlefield_state(scenario.battlefield_state)
    state.record_secondary_mission_choice(
        SecondaryMissionChoice(
            player_id="player-a",
            mode=SecondaryMissionMode.FIXED,
            fixed_mission_ids=("assassination", "bring-it-down"),
        )
    )
    state.record_secondary_mission_choice(
        SecondaryMissionChoice(
            player_id="player-b",
            mode=SecondaryMissionMode.FIXED,
            fixed_mission_ids=("assassination", "bring-it-down"),
        )
    )
    enter_battle_for_fixture(state)
    assert state.stage is GameLifecycleStage.BATTLE
    return GameState.from_payload(state.to_payload())


def _config(
    *,
    mission_pool_entry_id: str = PHASE16A_MISSION_POOL_ENTRY_ID,
    mission_setup: MissionSetup | None = None,
) -> GameConfig:
    source_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    catalog = replace(
        source_catalog,
        detachments=tuple(
            replace(
                detachment,
                force_disposition_ids=("disruption", "purge-the-foe", "take-and-hold"),
            )
            if detachment.detachment_id == "core-combined-arms"
            else detachment
            for detachment in source_catalog.detachments
        ),
    )
    resolved_mission_setup = (
        MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2026_27_mission_pack(),
            mission_pool_entry_id=mission_pool_entry_id,
            terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
            attacker_player_id="player-a",
            attacker_force_disposition_id="take-and-hold",
            defender_player_id="player-b",
            defender_force_disposition_id="purge-the-foe",
        )
        if mission_setup is None
        else mission_setup
    )
    return GameConfig(
        game_id="phase11f-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=("intercessor-unit-1",),
                force_disposition_id=resolved_mission_setup.force_disposition_id_for_player(
                    "player-a"
                ),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("intercessor-unit-3",),
                force_disposition_id=resolved_mission_setup.force_disposition_id_for_player(
                    "player-b"
                ),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
        mission_setup=resolved_mission_setup,
    )


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
        descriptor_version="core-v2-phase11f-test"
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_ids: tuple[str, ...],
    force_disposition_id: str,
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
        force_disposition_id=force_disposition_id,
        unit_selections=tuple(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            )
            for unit_selection_id in unit_selection_ids
        ),
    )


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


def _event_death_trap_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-disruption-layout-1",
        terrain_layout_id="take-and-hold-vs-disruption-layout-1",
        attacker_player_id="player-a",
        attacker_force_disposition_id="disruption",
        defender_player_id="player-b",
        defender_force_disposition_id="take-and-hold",
    )


__all__: list[str] = []
__all__ += ["ArmyCatalog", "ArmyDefinition", "ArmyMusterRequest", "BattlePhase"]
__all__ += ["DetachmentSelection", "FinalScoreLine", "FinalScoringResult"]
__all__ += ["FinalScoringResultPayload", "GameConfig", "GameLifecycleError", "GameLifecycleStage"]
__all__ += ["GameState", "GameStatePayload", "JsonValue", "MissionSetup", "ModelProfileSelection"]
__all__ += ["PHASE16A_MISSION_POOL_ENTRY_ID", "ObjectiveControlTiming", "Pose"]
__all__ += ["RulesetDescriptor", "SecondaryMissionChoice", "SecondaryMissionMode"]
__all__ += ["SecondaryScoringProviderKind", "UnitMusterSelection", "VictoryPointAward"]
__all__ += ["VictoryPointSourceKind", "VictoryPointTransaction", "_army_muster_request"]
__all__ += ["_assert_final_payload_rejected", "_battle_state", "_cap_reasons", "_config"]
__all__ += ["_event_death_trap_setup", "_immovable_object_primary_award_fixture"]
__all__ += ["_mustered_armies", "_ruleset", "_set_round_five_going_second_fight"]
__all__ += ["build_primary_scoring_state_evidence", "cast"]
__all__ += ["chapter_approved_2026_27_mission_pack", "create_deterministic_battlefield_scenario"]
__all__ += ["enter_battle_for_fixture", "json", "metadata_with_vp_cap_audit"]
__all__ += ["mission_scoring_policies_from_setup", "muster_army", "pytest"]
__all__ += ["record_primary_scoring_state_evidence", "record_primary_turn_start_evidence"]
__all__ += ["replace", "resolve_primary_scoring_boundary_lifecycle"]
__all__ += ["warhammer_event_companion_2026_07_mission_pack"]
