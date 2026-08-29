from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from typing import cast

import pytest
from tests.phase11c_command_phase_helpers import (
    battle_state,
    battle_state_with_center_objective_positions,
    center_marker_definition,
    complete_setup_through_gate,
    default_unit_selection,
    remove_first_models,
    unit_by_id,
    unit_selection,
    with_model_offsets,
)
from tests.setup_completion_helpers import record_completed_command_occurrences_for_fixture

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
    DatasheetDefinition,
    DatasheetKeywordSet,
)
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine import stratagems_generic_metadata, stratagems_selection
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    muster_army,
)
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockTestReason,
    BattleShockTestRequest,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockHookRegistry,
    BattleShockModifierContext,
    BattleShockOutcomeContext,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRuntimeState,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.command_points import (
    CommandPointGainStatus,
    CommandPointSourceKind,
)
from warhammer40k_core.engine.damage_allocation import FeelNoPainSource
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
    army_rule,
    datasheets,
    july_2026_candidate,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
    july_2026_updates as chaos_daemons_july_updates,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.daemonic_incursion import (  # noqa: E501
    rule as daemonic_incursion_rule,
)
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.healing import SELECT_HEALING_MODEL_DECISION_TYPE
from warhammer40k_core.engine.healing_revival import (
    SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.command import CommandPhaseHandler
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.rule_execution import RuleExecutionResult
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.sequencing import (
    SEQUENCING_DECISION_TYPE,
    sequencing_decision_event_from_request,
)
from warhammer40k_core.engine.sticky_objective_control import StickyObjectiveControlState
from warhammer40k_core.engine.stratagem_catalog import eleventh_edition_stratagem_index
from warhammer40k_core.engine.stratagem_cost_choice_hooks import (
    SELECT_STRATAGEM_COST_MODIFIER_OPTION_DECISION_TYPE,
)
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    StratagemCatalogIndex,
    StratagemEligibilityContext,
    StratagemTargetBinding,
    StratagemTargetKind,
    StratagemTargetProposal,
    apply_stratagem_target_proposal,
    create_stratagem_use_decision_request,
    invalid_stratagem_target_proposal_status,
    request_stratagem_target_proposal,
    stratagem_decline_payload,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.rule_ir import RuleConditionKind
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14 as datasheet_keyword_lexicon_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_daemonic_incursion_ir_support_2026_27 as daemonic_incursion_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_execution_2026_27,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_coverage_2026_27 import (
    Phase17ECoverageKind,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionRecord,
)

CHAOS_DAEMONS_TEST_DATASHEET_ID = "phase17g-manifestation-daemon"
SOURCE_KEYWORD_SEQUENCE_PARTS = (
    datasheet_keyword_lexicon_source.canonical_datasheet_keyword_sequence_parts()
)


def test_shadow_of_chaos_marks_no_mans_land_when_daemons_control_half_objectives() -> None:
    state = battle_state_with_center_objective_positions(
        player_a_offsets=((0.0, 0.0), (-1.5, -13.5)),
        player_b_offsets=((8.0, 0.0),),
    )
    _mark_player_as_chaos_daemons(state, player_id="player-a")

    regions = army_rule.shadow_regions_for_player(state=state, player_id="player-a")

    assert army_rule.ShadowRegion.OWN_DEPLOYMENT_ZONE in regions
    assert army_rule.ShadowRegion.NO_MANS_LAND in regions
    assert army_rule.unit_within_shadow_of_chaos(
        state=state,
        player_id="player-a",
        unit_instance_id="army-alpha:intercessor-unit-1",
    )


def test_shadow_of_chaos_marks_and_reaches_controlled_opponent_deployment_zone() -> None:
    state = battle_state()
    _mark_player_as_chaos_daemons(state, player_id="player-a")
    target_unit_id = "army-alpha:intercessor-unit-1"
    opponent_objective_ids = army_rule._opponent_deployment_objective_ids(  # pyright: ignore[reportPrivateUsage]
        state,
        player_id="player-a",
    )
    assert opponent_objective_ids
    assert state.mission_setup is not None
    marker = next(
        marker
        for marker in state.mission_setup.objective_markers
        if marker.objective_marker_id == opponent_objective_ids[0]
    )
    _relocate_unit(
        state=state,
        unit_instance_id=target_unit_id,
        x=marker.x_inches,
        y=marker.y_inches,
    )

    regions = army_rule.shadow_regions_for_player(state=state, player_id="player-a")

    assert army_rule.ShadowRegion.OPPONENT_DEPLOYMENT_ZONE in regions
    assert army_rule.unit_within_shadow_of_chaos(
        state=state,
        player_id="player-a",
        unit_instance_id=target_unit_id,
    )


def test_corrupted_realspace_shadow_routes_owned_controlled_objective_and_round_trips() -> None:
    state = battle_state()
    _mark_player_as_chaos_daemons(state, player_id="player-a")
    target_unit_id = "army-alpha:intercessor-unit-1"
    assert state.mission_setup is not None
    center = center_marker_definition(state)
    other_markers = tuple(
        marker
        for marker in state.mission_setup.objective_markers
        if marker.objective_marker_id != center.objective_marker_id
    )
    assert len(other_markers) >= 3
    _relocate_unit(
        state=state,
        unit_instance_id=target_unit_id,
        x=center.x_inches,
        y=center.y_inches,
    )
    states = (
        _corrupted_realspace_sticky_state(
            state=state,
            state_id="phase17g-corrupted-realspace-foreign",
            player_id="player-b",
            objective_id=other_markers[0].objective_marker_id,
            target_unit_instance_id="army-beta:intercessor-unit-3",
        ),
        replace(
            _corrupted_realspace_sticky_state(
                state=state,
                state_id="phase17g-corrupted-realspace-wrong-kind",
                player_id="player-a",
                objective_id=other_markers[1].objective_marker_id,
                target_unit_instance_id=target_unit_id,
            ),
            replay_payload={"effect_kind": "another_sticky_effect"},
        ),
        _corrupted_realspace_sticky_state(
            state=state,
            state_id="phase17g-corrupted-realspace-uncontrolled",
            player_id="player-a",
            objective_id=other_markers[2].objective_marker_id,
            target_unit_instance_id=target_unit_id,
        ),
        _corrupted_realspace_sticky_state(
            state=state,
            state_id="phase17g-corrupted-realspace-valid",
            player_id="player-a",
            objective_id=center.objective_marker_id,
            target_unit_instance_id=target_unit_id,
        ),
    )
    state.sticky_objective_control_states = list(states)

    assert army_rule._unit_within_corrupted_realspace_shadow(  # pyright: ignore[reportPrivateUsage]
        state=state,
        player_id="player-a",
        unit_instance_id=target_unit_id,
    )
    assert army_rule.unit_within_shadow_of_chaos(
        state=state,
        player_id="player-a",
        unit_instance_id=target_unit_id,
    )
    assert (
        tuple(StickyObjectiveControlState.from_payload(sticky.to_payload()) for sticky in states)
        == states
    )


def test_corrupted_realspace_shadow_rejects_malformed_replay_payload_and_invalid_range() -> None:
    state = battle_state()
    _mark_player_as_chaos_daemons(state, player_id="player-a")
    target_unit_id = "army-alpha:intercessor-unit-1"
    center = center_marker_definition(state)
    _relocate_unit(
        state=state,
        unit_instance_id=target_unit_id,
        x=center.x_inches,
        y=center.y_inches,
    )
    sticky = _corrupted_realspace_sticky_state(
        state=state,
        state_id="phase17g-corrupted-realspace-payload-validation",
        player_id="player-a",
        objective_id=center.objective_marker_id,
        target_unit_instance_id=target_unit_id,
    )
    state_before = state.to_payload()

    state.sticky_objective_control_states = [replace(sticky, replay_payload=[])]
    with pytest.raises(GameLifecycleError, match="sticky payload must be an object"):
        army_rule._unit_within_corrupted_realspace_shadow(  # pyright: ignore[reportPrivateUsage]
            state=state,
            player_id="player-a",
            unit_instance_id=target_unit_id,
        )
    state.sticky_objective_control_states = [
        replace(
            sticky,
            replay_payload={
                "effect_kind": army_rule.CORRUPTED_REALSPACE_STICKY_EFFECT_KIND,
                "shadow_of_chaos_aura_inches": "six",
            },
        )
    ]
    with pytest.raises(GameLifecycleError, match="payload must contain inches"):
        army_rule._unit_within_corrupted_realspace_shadow(  # pyright: ignore[reportPrivateUsage]
            state=state,
            player_id="player-a",
            unit_instance_id=target_unit_id,
        )
    state.sticky_objective_control_states = [
        replace(
            sticky,
            replay_payload={
                "effect_kind": army_rule.CORRUPTED_REALSPACE_STICKY_EFFECT_KIND,
                "shadow_of_chaos_aura_inches": 0,
            },
        )
    ]
    with pytest.raises(GameLifecycleError, match="aura inches must be positive"):
        army_rule._unit_within_corrupted_realspace_shadow(  # pyright: ignore[reportPrivateUsage]
            state=state,
            player_id="player-a",
            unit_instance_id=target_unit_id,
        )
    assert {
        key: value
        for key, value in state.to_payload().items()
        if key != "sticky_objective_control_states"
    } == {
        key: value
        for key, value in state_before.items()
        if key != "sticky_objective_control_states"
    }


def test_corrupted_realspace_shadow_returns_false_outside_controlled_objective_aura() -> None:
    state = battle_state()
    _mark_player_as_chaos_daemons(state, player_id="player-a")
    controlling_unit_id = "army-alpha:intercessor-unit-1"
    target_unit_id = "army-beta:intercessor-unit-3"
    center = center_marker_definition(state)
    _relocate_unit(
        state=state,
        unit_instance_id=controlling_unit_id,
        x=center.x_inches,
        y=center.y_inches,
    )
    assert state.battlefield_state is not None
    far_x, far_y = _farthest_battlefield_point(
        battlefield=state.battlefield_state,
        points=((center.x_inches, center.y_inches),),
    )
    _relocate_unit(
        state=state,
        unit_instance_id=target_unit_id,
        x=far_x,
        y=far_y,
    )
    state.sticky_objective_control_states = [
        _corrupted_realspace_sticky_state(
            state=state,
            state_id="phase17g-corrupted-realspace-outside-aura",
            player_id="player-a",
            objective_id=center.objective_marker_id,
            target_unit_instance_id=controlling_unit_id,
        )
    ]

    assert not army_rule._unit_within_corrupted_realspace_shadow(  # pyright: ignore[reportPrivateUsage]
        state=state,
        player_id="player-a",
        unit_instance_id=target_unit_id,
    )


def test_daemonic_manifestation_modifies_battle_shock_and_heals_one_model() -> None:
    state = battle_state()
    _mark_player_as_chaos_daemons(
        state,
        player_id="player-a",
        remove_battleline=True,
    )
    unit_id = "army-alpha:intercessor-unit-1"
    remove_first_models(state, unit_instance_id=unit_id, count=3)
    wounded_model_id = _placed_model_ids(state, unit_id)[0]
    _replace_model_wounds(state, model_instance_id=wounded_model_id, wounds_remaining=1)
    decisions = DecisionController()
    _record_battle_shock_auto_pass(
        state,
        decisions=decisions,
        unit_instance_id=unit_id,
    )
    handler = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
        battle_shock_hooks=_chaos_daemons_battle_shock_hooks(),
    )

    completed = handler.begin_phase(state=state, decisions=decisions)

    assert completed.status_kind is LifecycleStatusKind.ADVANCED
    resolved_payload = _event_payload(decisions, "battle_shock_test_resolved")
    result_payload = cast(dict[str, JsonValue], resolved_payload["battle_shock_result"])
    modified_roll = cast(dict[str, JsonValue], result_payload["modified_roll"])
    modifiers = cast(list[JsonValue], modified_roll["modifiers"])
    assert result_payload["total"] == 13
    assert cast(dict[str, JsonValue], modifiers[0])["operand"] == 1
    healing_step_payload = _event_payload(decisions, "healing_step_resolved")
    assert healing_step_payload["source_rule_id"] == army_rule.SOURCE_RULE_ID
    step_payload = cast(dict[str, JsonValue], healing_step_payload["step"])
    assert step_payload["model_instance_id"] == wounded_model_id
    assert step_payload["starting_wounds_remaining"] == 1
    assert step_payload["final_wounds_remaining"] == 2
    manifestation_payload = _event_payload(
        decisions,
        "chaos_daemons_daemonic_manifestation_healing_resolved",
    )
    healing_effect = cast(dict[str, JsonValue], manifestation_payload["healing_effect"])
    assert healing_effect["source_rule_id"] == army_rule.SOURCE_RULE_ID
    assert _model_by_id(state, wounded_model_id).wounds_remaining == 2


def test_daemonic_manifestation_uses_semantic_shadow_of_chaos_aura() -> None:
    state = battle_state(
        player_a_units=(
            default_unit_selection("intercessor-unit-1"),
            default_unit_selection("intercessor-unit-2"),
        )
    )
    _mark_player_as_chaos_daemons(state, player_id="player-a", remove_battleline=True)
    source_unit_id = "army-alpha:intercessor-unit-1"
    target_unit_id = "army-alpha:intercessor-unit-2"
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=source_unit_id,
        keywords=("Character", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
        datasheet_abilities=(_semantic_shadow_aura_ability(allegiance="Khorne"),),
    )
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=target_unit_id,
        keywords=("Infantry", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
    )
    _place_unit_near_center(state, unit_instance_id=source_unit_id, offset=(16.0, 0.0))
    _place_unit_near_center(state, unit_instance_id=target_unit_id, offset=(18.0, 0.0))
    remove_first_models(state, unit_instance_id=target_unit_id, count=3)
    wounded_model_id = _placed_model_ids(state, target_unit_id)[0]
    _replace_model_wounds(state, model_instance_id=wounded_model_id, wounds_remaining=1)
    decisions = DecisionController()
    _record_battle_shock_auto_pass(
        state,
        decisions=decisions,
        unit_instance_id=target_unit_id,
    )
    handler = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
        battle_shock_hooks=_chaos_daemons_battle_shock_hooks(),
    )

    completed = handler.begin_phase(state=state, decisions=decisions)

    assert completed.status_kind is LifecycleStatusKind.ADVANCED
    assert _model_by_id(state, wounded_model_id).wounds_remaining == 2
    manifestation_payload = _event_payload(
        decisions,
        "chaos_daemons_daemonic_manifestation_healing_resolved",
    )
    assert manifestation_payload["unit_instance_id"] == target_unit_id
    assert manifestation_payload["source_rule_id"] == army_rule.SOURCE_RULE_ID


def test_daemonic_manifestation_uses_source_backed_greater_daemon_shadow_aura() -> None:
    state = battle_state(
        player_a_units=(
            default_unit_selection("intercessor-unit-1"),
            default_unit_selection("intercessor-unit-2"),
        )
    )
    _mark_player_as_chaos_daemons(state, player_id="player-a", remove_battleline=True)
    source_unit_id = "army-alpha:intercessor-unit-1"
    target_unit_id = "army-alpha:intercessor-unit-2"
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=source_unit_id,
        keywords=("Character", "Monster", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
        datasheet_abilities=(_datasheet_ability(datasheets.SKARBRAND_GREATER_DAEMON_ABILITY_ID),),
    )
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=target_unit_id,
        keywords=("Infantry", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
    )
    _place_unit_near_center(state, unit_instance_id=source_unit_id, offset=(16.0, 0.0))
    _place_unit_near_center(state, unit_instance_id=target_unit_id, offset=(18.0, 0.0))
    remove_first_models(state, unit_instance_id=target_unit_id, count=3)
    wounded_model_id = _placed_model_ids(state, target_unit_id)[0]
    _replace_model_wounds(state, model_instance_id=wounded_model_id, wounds_remaining=1)
    decisions = DecisionController()
    _record_battle_shock_auto_pass(
        state,
        decisions=decisions,
        unit_instance_id=target_unit_id,
    )
    handler = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
        battle_shock_hooks=_chaos_daemons_battle_shock_hooks(),
    )

    completed = handler.begin_phase(state=state, decisions=decisions)

    assert completed.status_kind is LifecycleStatusKind.ADVANCED
    assert _model_by_id(state, wounded_model_id).wounds_remaining == 2
    manifestation_payload = _event_payload(
        decisions,
        "chaos_daemons_daemonic_manifestation_healing_resolved",
    )
    assert manifestation_payload["unit_instance_id"] == target_unit_id
    assert manifestation_payload["source_rule_id"] == army_rule.SOURCE_RULE_ID


def test_greater_daemon_shadow_aura_filters_ownership_faction_keyword_range_and_source_kind() -> (
    None
):
    state = battle_state(
        player_a_units=(
            default_unit_selection("intercessor-unit-1"),
            default_unit_selection("intercessor-unit-2"),
        )
    )
    _mark_player_as_chaos_daemons(state, player_id="player-a", remove_battleline=True)
    source_unit_id = "army-alpha:intercessor-unit-1"
    target_unit_id = "army-alpha:intercessor-unit-2"
    source = unit_by_id(state, source_unit_id)
    target = unit_by_id(state, target_unit_id)
    wargear_id = source.own_models[0].wargear_ids[0]
    wargear_ability = replace(
        _semantic_shadow_aura_ability(allegiance="Khorne"),
        ability_id="phase17g-shadow-aura-wargear-source-kind",
        source_id="phase17g:test:shadow-aura-wargear-source-kind",
        source_kind=CatalogAbilitySourceKind.WARGEAR,
        source_wargear_id=wargear_id,
    )
    source_ability = _datasheet_ability(datasheets.BLOODTHIRSTER_GREATER_DAEMON_ABILITY_ID)
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=source_unit_id,
        keywords=("Character", "Monster", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
        datasheet_abilities=(wargear_ability, source_ability),
    )
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=target_unit_id,
        keywords=("Infantry", "Khorne"),
        faction_keywords=(),
    )
    assert not army_rule._unit_within_greater_daemon_shadow_aura(  # pyright: ignore[reportPrivateUsage]
        state=state,
        player_id="player-a",
        unit_instance_id=target_unit_id,
    )

    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=target_unit_id,
        keywords=("Infantry", "Tzeentch"),
        faction_keywords=("Legiones Daemonica",),
    )
    assert not army_rule._unit_within_greater_daemon_shadow_aura(  # pyright: ignore[reportPrivateUsage]
        state=state,
        player_id="player-a",
        unit_instance_id=target_unit_id,
    )

    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=target_unit_id,
        keywords=("Infantry", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
    )
    assert state.battlefield_state is not None
    far_x, far_y = _farthest_battlefield_point(
        battlefield=state.battlefield_state,
        points=tuple(
            (
                placement.pose.position.x,
                placement.pose.position.y,
            )
            for placement in state.battlefield_state.unit_placement_by_id(
                source_unit_id
            ).model_placements
        ),
    )
    _relocate_unit(state=state, unit_instance_id=target_unit_id, x=far_x, y=far_y)
    assert not army_rule._unit_within_greater_daemon_shadow_aura(  # pyright: ignore[reportPrivateUsage]
        state=state,
        player_id="player-a",
        unit_instance_id=target_unit_id,
    )

    source_position = (
        state.battlefield_state.unit_placement_by_id(source_unit_id)
        .model_placements[0]
        .pose.position
    )
    near_x, near_y = _nearby_battlefield_point(
        battlefield=state.battlefield_state,
        x=source_position.x,
        y=source_position.y,
    )
    _relocate_unit(state=state, unit_instance_id=target_unit_id, x=near_x, y=near_y)
    assert army_rule._unit_within_greater_daemon_shadow_aura(  # pyright: ignore[reportPrivateUsage]
        state=state,
        player_id="player-a",
        unit_instance_id=target_unit_id,
    )
    assert (
        army_rule._greater_daemon_shadow_aura_keyword(  # pyright: ignore[reportPrivateUsage]
            unit_by_id(state, source_unit_id)
        )
        == "KHORNE"
    )
    assert target.unit_instance_id == target_unit_id


def test_semantic_shadow_aura_executes_rule_ir_and_honours_wargear_bearer_state() -> None:
    state = battle_state(
        player_a_units=(
            default_unit_selection("intercessor-unit-1"),
            default_unit_selection("intercessor-unit-2"),
        )
    )
    _mark_player_as_chaos_daemons(state, player_id="player-a", remove_battleline=True)
    source_unit_id = "army-alpha:intercessor-unit-1"
    target_unit_id = "army-alpha:intercessor-unit-2"
    semantic_ability = _semantic_unit_shadow_aura_ability(allegiance="Khorne")
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=source_unit_id,
        keywords=("Character", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
        datasheet_abilities=(semantic_ability,),
    )
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=target_unit_id,
        keywords=("Infantry", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
    )
    _place_unit_near_center(state, unit_instance_id=source_unit_id, offset=(16.0, 0.0))
    _place_unit_near_center(state, unit_instance_id=target_unit_id, offset=(18.0, 0.0))

    assert army_rule._unit_within_semantic_shadow_aura(  # pyright: ignore[reportPrivateUsage]
        state=state,
        player_id="player-a",
        unit_instance_id=target_unit_id,
    )
    rule_ir = army_rule._semantic_rule_ir_for_ability(  # pyright: ignore[reportPrivateUsage]
        semantic_ability
    )
    assert army_rule._rule_ir_sets_shadow_of_chaos_status(  # pyright: ignore[reportPrivateUsage]
        rule_ir
    )

    source = unit_by_id(state, source_unit_id)
    source_wargear_id = source.own_models[0].wargear_ids[0]
    equipped = replace(
        semantic_ability,
        ability_id="phase17g-semantic-shadow-equipped-wargear",
        source_id="phase17g:test:semantic-shadow-equipped-wargear",
        source_kind=CatalogAbilitySourceKind.WARGEAR,
        source_wargear_id=source_wargear_id,
    )
    unequipped = replace(
        equipped,
        ability_id="phase17g-semantic-shadow-unequipped-wargear",
        source_id="phase17g:test:semantic-shadow-unequipped-wargear",
        source_wargear_id="phase17g-missing-wargear",
    )
    faction_source = replace(
        semantic_ability,
        ability_id="phase17g-semantic-shadow-faction-source",
        source_id="phase17g:test:semantic-shadow-faction-source",
        source_kind=CatalogAbilitySourceKind.FACTION,
    )
    assert army_rule._semantic_shadow_aura_source_model_ids(  # pyright: ignore[reportPrivateUsage]
        unit=source,
        ability=equipped,
    )
    assert not army_rule._semantic_shadow_aura_source_model_ids(  # pyright: ignore[reportPrivateUsage]
        unit=source,
        ability=unequipped,
    )
    assert not army_rule._semantic_shadow_aura_source_model_ids(  # pyright: ignore[reportPrivateUsage]
        unit=source,
        ability=faction_source,
    )
    assert GameState.from_payload(state.to_payload()).to_payload() == state.to_payload()


def test_semantic_shadow_aura_source_does_not_expand_to_attached_bodyguards() -> None:
    source_bodyguard_id = "army-alpha:shadow-bodyguard"
    source_leader_id = "army-alpha:shadow-leader"
    target_unit_id = "army-alpha:shadow-target"
    state = battle_state(
        game_id="phase17g-chaos-daemons-attached-semantic-aura-source",
        player_a_units=(
            default_unit_selection("shadow-bodyguard"),
            unit_selection(
                unit_selection_id="shadow-leader",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
            default_unit_selection("shadow-target"),
        ),
        player_a_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="shadow-leader",
                bodyguard_unit_selection_id="shadow-bodyguard",
            ),
        ),
    )
    _mark_player_as_chaos_daemons(state, player_id="player-a", remove_battleline=True)
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=source_leader_id,
        keywords=("Character", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
        datasheet_abilities=(_semantic_shadow_aura_ability(allegiance="Khorne"),),
    )
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=target_unit_id,
        keywords=("Infantry", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
    )
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    marker = center_marker_definition(state)
    battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(
            state.battlefield_state.unit_placement_by_id(source_leader_id),
            marker,
            offsets=((-15.0, 0.0),),
        )
    )
    battlefield_state = battlefield_state.with_unit_placement(
        with_model_offsets(
            state.battlefield_state.unit_placement_by_id(source_bodyguard_id),
            marker,
            offsets=((0.0, 0.0), (0.4, 0.0), (0.8, 0.0), (1.2, 0.0), (1.6, 0.0)),
        )
    )
    battlefield_state = battlefield_state.with_unit_placement(
        with_model_offsets(
            state.battlefield_state.unit_placement_by_id(target_unit_id),
            marker,
            offsets=((3.0, 0.0), (3.4, 0.0), (3.8, 0.0), (4.2, 0.0), (4.6, 0.0)),
        )
    )
    state.battlefield_state = battlefield_state

    assert not army_rule._unit_within_semantic_shadow_aura(  # pyright: ignore[reportPrivateUsage]
        state=state,
        player_id="player-a",
        unit_instance_id=target_unit_id,
    )


def test_semantic_shadow_aura_skips_self_unplaced_sources_and_non_shadow_rule_ir() -> None:
    state = battle_state(
        player_a_units=(
            default_unit_selection("intercessor-unit-1"),
            default_unit_selection("intercessor-unit-2"),
        )
    )
    _mark_player_as_chaos_daemons(state, player_id="player-a", remove_battleline=True)
    source_unit_id = "army-alpha:intercessor-unit-1"
    target_unit_id = "army-alpha:intercessor-unit-2"
    semantic = _semantic_unit_shadow_aura_ability(allegiance="Khorne")
    semantic_rule = army_rule._semantic_rule_ir_for_ability(  # pyright: ignore[reportPrivateUsage]
        semantic
    )
    clause = semantic_rule.clauses[0]
    effect = clause.effects[0]
    non_shadow_effect = replace(
        effect,
        parameters=tuple(
            replace(parameter, value="opponent_army") if parameter.key == "owner" else parameter
            for parameter in effect.parameters
        ),
    )
    non_shadow_rule = replace(
        semantic_rule,
        clauses=(replace(clause, effects=(non_shadow_effect,)),),
    )
    non_shadow = replace(
        semantic,
        ability_id="phase17g-semantic-non-shadow-status",
        source_id="phase17g:test:semantic-non-shadow-status",
        rule_ir_payload=cast(CatalogJsonObject, non_shadow_rule.to_payload()),
    )
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=source_unit_id,
        keywords=("Character", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
        datasheet_abilities=(non_shadow,),
    )
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=target_unit_id,
        keywords=("Infantry", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
    )
    _place_unit_near_center(state, unit_instance_id=source_unit_id, offset=(16.0, 0.0))
    _place_unit_near_center(state, unit_instance_id=target_unit_id, offset=(18.0, 0.0))

    assert not army_rule._unit_within_semantic_shadow_aura(  # pyright: ignore[reportPrivateUsage]
        state=state,
        player_id="player-a",
        unit_instance_id=source_unit_id,
    )
    assert not army_rule._unit_within_semantic_shadow_aura(  # pyright: ignore[reportPrivateUsage]
        state=state,
        player_id="player-a",
        unit_instance_id=target_unit_id,
    )
    rule_ir = army_rule._semantic_rule_ir_for_ability(non_shadow)  # pyright: ignore[reportPrivateUsage]
    assert not army_rule._rule_ir_sets_shadow_of_chaos_status(  # pyright: ignore[reportPrivateUsage]
        rule_ir
    )

    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.without_unit_placement(source_unit_id)
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=source_unit_id,
        keywords=("Character", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
        datasheet_abilities=(_semantic_unit_shadow_aura_ability(allegiance="Khorne"),),
    )
    assert not army_rule._unit_within_semantic_shadow_aura(  # pyright: ignore[reportPrivateUsage]
        state=state,
        player_id="player-a",
        unit_instance_id=target_unit_id,
    )


def test_semantic_shadow_aura_execution_payload_is_target_scoped_and_fail_closed() -> None:
    ability = _semantic_unit_shadow_aura_ability(allegiance="Khorne")
    rule_ir = army_rule._semantic_rule_ir_for_ability(  # pyright: ignore[reportPrivateUsage]
        ability
    )
    effect = rule_ir.clauses[0].effects[0]
    target_id = "army-alpha:semantic-shadow-target"
    other_id = "army-alpha:semantic-shadow-other"
    matching_payload: dict[str, JsonValue] = {
        "target_unit_instance_ids": [target_id],
        "effect": cast(dict[str, JsonValue], effect.to_payload()),
    }
    matching = RuleExecutionResult.applied(
        rule_ir,
        applied_clause_ids=(rule_ir.clauses[0].clause_id,),
        effect_payloads=(matching_payload,),
    )
    assert army_rule._execution_result_sets_shadow_status_for_unit(  # pyright: ignore[reportPrivateUsage]
        matching,
        unit_instance_id=target_id,
    )

    nonmatching = RuleExecutionResult.applied(
        rule_ir,
        effect_payloads=(
            {
                **matching_payload,
                "target_unit_instance_ids": [other_id],
            },
        ),
    )
    assert not army_rule._execution_result_sets_shadow_status_for_unit(  # pyright: ignore[reportPrivateUsage]
        nonmatching,
        unit_instance_id=target_id,
    )

    non_shadow_effect = replace(
        effect,
        parameters=tuple(
            replace(parameter, value="opponent_army") if parameter.key == "owner" else parameter
            for parameter in effect.parameters
        ),
    )
    non_shadow_result = RuleExecutionResult.applied(
        rule_ir,
        effect_payloads=(
            {
                "target_unit_instance_ids": [target_id],
                "effect": cast(dict[str, JsonValue], non_shadow_effect.to_payload()),
            },
        ),
    )
    assert not army_rule._execution_result_sets_shadow_status_for_unit(  # pyright: ignore[reportPrivateUsage]
        non_shadow_result,
        unit_instance_id=target_id,
    )

    missing_effect = RuleExecutionResult.applied(
        rule_ir,
        effect_payloads=({"target_unit_instance_ids": [target_id]},),
    )
    with pytest.raises(GameLifecycleError, match="payload is missing effect"):
        army_rule._execution_result_sets_shadow_status_for_unit(  # pyright: ignore[reportPrivateUsage]
            missing_effect,
            unit_instance_id=target_id,
        )
    invalid_effect = RuleExecutionResult.applied(
        rule_ir,
        effect_payloads=(
            {
                "target_unit_instance_ids": [target_id],
                "effect": {
                    **cast(dict[str, JsonValue], effect.to_payload()),
                    "kind": "not-a-rule-effect",
                },
            },
        ),
    )
    with pytest.raises(GameLifecycleError, match="effect payload is invalid"):
        army_rule._execution_result_sets_shadow_status_for_unit(  # pyright: ignore[reportPrivateUsage]
            invalid_effect,
            unit_instance_id=target_id,
        )
    with pytest.raises(GameLifecycleError, match="requires target_unit_instance_ids"):
        army_rule._payload_identifier_list({}, key="target_unit_instance_ids")  # pyright: ignore[reportPrivateUsage]


def test_semantic_shadow_aura_reports_unsupported_multi_effect_execution() -> None:
    state = battle_state(
        player_a_units=(
            default_unit_selection("intercessor-unit-1"),
            default_unit_selection("intercessor-unit-2"),
        )
    )
    _mark_player_as_chaos_daemons(state, player_id="player-a", remove_battleline=True)
    source_unit_id = "army-alpha:intercessor-unit-1"
    target_unit_id = "army-alpha:intercessor-unit-2"
    semantic = _semantic_unit_shadow_aura_ability(allegiance="Khorne")
    rule_ir = army_rule._semantic_rule_ir_for_ability(semantic)  # pyright: ignore[reportPrivateUsage]
    clause = rule_ir.clauses[0]
    keyword_condition = clause.conditions[1]
    unsupported_condition = replace(
        keyword_condition,
        kind=RuleConditionKind.TARGET_CONSTRAINT,
        parameters=(
            replace(
                keyword_condition.parameters[0],
                key="relationship",
                value="phase17g_unknown_relationship",
            ),
        ),
    )
    unsupported_rule = replace(
        rule_ir,
        clauses=(
            replace(
                clause,
                conditions=(
                    clause.conditions[0],
                    unsupported_condition,
                    *clause.conditions[2:],
                ),
            ),
        ),
    )
    unsupported_ability = replace(
        semantic,
        ability_id="phase17g-semantic-shadow-unsupported-multi-effect",
        source_id="phase17g:test:semantic-shadow-unsupported-multi-effect",
        rule_ir_payload=cast(CatalogJsonObject, unsupported_rule.to_payload()),
    )
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=source_unit_id,
        keywords=("Character", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
        datasheet_abilities=(unsupported_ability,),
    )
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=target_unit_id,
        keywords=("Infantry", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
    )
    _place_unit_near_center(state, unit_instance_id=source_unit_id, offset=(16.0, 0.0))
    _place_unit_near_center(state, unit_instance_id=target_unit_id, offset=(18.0, 0.0))

    with pytest.raises(GameLifecycleError, match="semantic aura execution failed"):
        army_rule._unit_within_semantic_shadow_aura(  # pyright: ignore[reportPrivateUsage]
            state=state,
            player_id="player-a",
            unit_instance_id=target_unit_id,
        )


def test_greater_daemon_shadow_aura_host_table_covers_all_datasheet_sources() -> None:
    assert (
        tuple(
            ability_id
            for ability_id, _keyword in army_rule.GREATER_DAEMON_SHADOW_AURA_KEYWORDS_BY_ABILITY_ID
        )
        == datasheets.GREATER_DAEMON_SHADOW_AURA_ABILITY_IDS
    )
    assert tuple(
        keyword
        for _ability_id, keyword in army_rule.GREATER_DAEMON_SHADOW_AURA_KEYWORDS_BY_ABILITY_ID
    ) == (
        "KHORNE",
        "KHORNE",
        "TZEENTCH",
        "TZEENTCH",
        "NURGLE",
        "NURGLE",
        "SLAANESH",
        "SLAANESH",
    )


def test_daemonic_manifestation_caps_non_battleline_healing_before_revival() -> None:
    state = battle_state()
    state.game_id = "phase17g-overheal-seed-2"
    _mark_player_as_chaos_daemons(
        state,
        player_id="player-a",
        remove_battleline=True,
    )
    unit_id = "army-alpha:intercessor-unit-1"
    starting_model_ids = _placed_model_ids(state, unit_id)
    destroyed_model_ids = starting_model_ids[:3]
    remove_first_models(state, unit_instance_id=unit_id, count=3)
    for destroyed_model_id in destroyed_model_ids:
        _replace_model_wounds(
            state,
            model_instance_id=destroyed_model_id,
            wounds_remaining=0,
        )
    wounded_model_id = _placed_model_ids(state, unit_id)[0]
    _replace_model_wounds(state, model_instance_id=wounded_model_id, wounds_remaining=1)
    decisions = DecisionController()
    _record_battle_shock_auto_pass(
        state,
        decisions=decisions,
        unit_instance_id=unit_id,
    )
    handler = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
        battle_shock_hooks=_chaos_daemons_battle_shock_hooks(),
    )

    completed = handler.begin_phase(state=state, decisions=decisions)

    assert completed.status_kind is LifecycleStatusKind.ADVANCED
    assert decisions.queue.pending_requests == ()
    manifestation_payload = _event_payload(
        decisions,
        "chaos_daemons_daemonic_manifestation_healing_resolved",
    )
    d3_result = cast(dict[str, JsonValue], manifestation_payload["d3_result"])
    healing_effect = cast(dict[str, JsonValue], manifestation_payload["healing_effect"])
    resolved_steps = cast(list[JsonValue], healing_effect["resolved_steps"])
    first_step = cast(dict[str, JsonValue], resolved_steps[0])
    assert d3_result["value"] == 3
    assert healing_effect["amount"] == 1
    assert len(resolved_steps) == 1
    assert first_step["step_kind"] == "heal_wound"
    assert first_step["model_instance_id"] == wounded_model_id
    assert first_step["transition_batch"] is None
    assert _event_payloads(decisions, "healing_step_resolved") == (
        _event_payload(decisions, "healing_step_resolved"),
    )
    assert state.battlefield_state is not None
    placed_ids = set(state.battlefield_state.placed_model_ids())
    removed_ids = set(state.battlefield_state.removed_model_ids)
    assert set(destroyed_model_ids).isdisjoint(placed_ids)
    assert set(destroyed_model_ids) <= removed_ids
    assert _model_by_id(state, wounded_model_id).wounds_remaining == 2


def test_staged_july_daemonic_manifestation_revival_uses_adapter_decisions() -> None:
    (
        session,
        state,
        destroyed_model_ids,
        return_placements,
        selection_request,
    ) = _july_manifestation_revival_session()
    default = army_rule.runtime_contribution()
    assert default.battle_shock_hook_bindings[0].source_id == army_rule.SOURCE_RULE_ID
    assert selection_request.decision_type == SELECT_HEALING_MODEL_DECISION_TYPE
    assert selection_request.actor_id == "player-a"
    assert _healing_option_model_ids(selection_request) == tuple(sorted(destroyed_model_ids))
    assert _healing_finish_option_id(selection_request).endswith(":finish")

    owner_view = session.view(viewer_player_id="player-a")
    opponent_view = session.view(viewer_player_id="player-b")
    assert owner_view["pending_decision"] == opponent_view["pending_decision"]
    assert owner_view["pending_decision"] is not None
    assert owner_view["pending_decision"]["request_id"] == selection_request.request_id

    selected_model_id = sorted(destroyed_model_ids)[-1]
    placement_status = session.submit_option(
        request_id=selection_request.request_id,
        option_id=_healing_option_id_for_model(selection_request, selected_model_id),
        result_id="phase17g-july-daemonic-manifestation-select-first",
    )
    placement_request = _required_decision_request(placement_status)
    assert placement_request.decision_type == SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE

    malformed_status = session.submit_parameterized_payload(
        request_id=placement_request.request_id,
        payload={},
        result_id="phase17g-july-daemonic-manifestation-malformed-placement",
    )
    stale_status = session.submit_parameterized_payload(
        request_id=placement_request.request_id,
        payload=_healing_revival_payload(
            request=placement_request,
            placement=return_placements[selected_model_id],
            proposal_request_id="phase17g-stale-daemonic-manifestation-request",
        ),
        result_id="phase17g-july-daemonic-manifestation-stale-placement",
    )
    invalid_status = session.submit_parameterized_payload(
        request_id=placement_request.request_id,
        payload=_healing_revival_payload(
            request=placement_request,
            placement=return_placements[selected_model_id].with_pose(Pose.at(x=500.0, y=500.0)),
        ),
        result_id="phase17g-july-daemonic-manifestation-invalid-placement",
    )
    assert malformed_status.status_kind is LifecycleStatusKind.INVALID
    assert stale_status.status_kind is LifecycleStatusKind.INVALID
    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.decision_controller.queue.peek_next() == placement_request
    assert _model_by_id(state, selected_model_id).wounds_remaining == 0

    next_status = session.submit_parameterized_payload(
        request_id=placement_request.request_id,
        payload=_healing_revival_payload(
            request=placement_request,
            placement=return_placements[selected_model_id],
        ),
        result_id="phase17g-july-daemonic-manifestation-place-first",
    )
    revived_ids = [selected_model_id]
    decision_index = 1
    while (
        next_status.decision_request is not None
        and next_status.decision_request.decision_type
        in {
            SELECT_HEALING_MODEL_DECISION_TYPE,
            SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE,
        }
    ):
        request = next_status.decision_request
        if request.decision_type == SELECT_HEALING_MODEL_DECISION_TYPE:
            assert _healing_finish_option_id(request).endswith(":finish")
            selected_model_id = _healing_option_model_ids(request)[-1]
            next_status = session.submit_option(
                request_id=request.request_id,
                option_id=_healing_option_id_for_model(request, selected_model_id),
                result_id=(f"phase17g-july-daemonic-manifestation-select-{decision_index}"),
            )
            continue
        request_payload = cast(dict[str, JsonValue], request.payload)
        selected_model_id = cast(str, request_payload["model_instance_id"])
        next_status = session.submit_parameterized_payload(
            request_id=request.request_id,
            payload=_healing_revival_payload(
                request=request,
                placement=return_placements[selected_model_id],
            ),
            result_id=(f"phase17g-july-daemonic-manifestation-place-{decision_index}"),
        )
        revived_ids.append(selected_model_id)
        decision_index += 1

    assert tuple(sorted(revived_ids)) == tuple(sorted(destroyed_model_ids))
    assert all(
        _model_by_id(state, model_instance_id).wounds_remaining
        == _model_by_id(state, model_instance_id).starting_wounds
        for model_instance_id in destroyed_model_ids
    )
    healing_events = _event_payloads(
        session.lifecycle.decision_controller,
        "healing_step_resolved",
    )
    assert len(healing_events) == 3
    assert all(
        payload["source_rule_id"] == army_rule.JULY_SOURCE_RULE_ID for payload in healing_events
    )
    pending_payload = _event_payload(
        session.lifecycle.decision_controller,
        "chaos_daemons_daemonic_manifestation_revival_pending",
    )
    assert pending_payload["eligible_destroyed_model_ids"] == sorted(destroyed_model_ids)

    owner_events = session.events_since(EventStreamCursor(), viewer_player_id="player-a")
    opponent_events = session.events_since(EventStreamCursor(), viewer_player_id="player-b")
    owner_manifestation_events = tuple(
        event
        for event in owner_events["events"]
        if event["event_type"].startswith("chaos_daemons_daemonic_manifestation")
        or event["event_type"] == "healing_step_resolved"
    )
    opponent_manifestation_events = tuple(
        event
        for event in opponent_events["events"]
        if event["event_type"].startswith("chaos_daemons_daemonic_manifestation")
        or event["event_type"] == "healing_step_resolved"
    )
    assert owner_manifestation_events == opponent_manifestation_events
    replay_payload = session.lifecycle.decision_controller.to_payload()
    assert DecisionController.from_payload(replay_payload).to_payload() == replay_payload
    assert "<" not in json.dumps(replay_payload, sort_keys=True)


def test_daemonic_manifestation_effect_kind_drift_rejects_before_lifecycle_mutation() -> None:
    session, state, destroyed_model_ids, _return_placements, request = (
        _july_manifestation_revival_session()
    )
    lifecycle = session.lifecycle
    bundle = _runtime_content_bundle(lifecycle)
    decisions = lifecycle.decision_controller
    request_payload = cast(dict[str, object], deepcopy(request.payload))
    effect_payload = cast(dict[str, object], request_payload["effect"])
    source_context = cast(dict[str, object], effect_payload["source_context"])
    source_context["effect_kind"] = "phase17g:forged-daemonic-manifestation-effect"
    forged_options = tuple(
        replace(
            option,
            payload=validate_json_value(
                {
                    **cast(dict[str, JsonValue], deepcopy(option.payload)),
                    "source_context": {
                        **cast(
                            dict[str, JsonValue],
                            deepcopy(cast(dict[str, JsonValue], option.payload)["source_context"]),
                        ),
                        "effect_kind": "phase17g:forged-daemonic-manifestation-effect",
                    },
                }
            ),
        )
        for option in request.options
    )
    forged_request = replace(
        request,
        payload=validate_json_value(request_payload),
        options=forged_options,
    )
    decisions.queue._pending_requests[0] = forged_request  # pyright: ignore[reportPrivateUsage]

    original_request_payload = request.to_payload()
    forged_request_payload = forged_request.to_payload()
    changed_request_event = False
    drifted_events: list[EventRecord] = []
    for event in decisions.event_log.records:
        if event.event_type == "decision_requested" and event.payload == original_request_payload:
            drifted_events.append(
                replace(event, payload=validate_json_value(forged_request_payload))
            )
            changed_request_event = True
            continue
        drifted_events.append(event)
    assert changed_request_event
    decisions.event_log.replace_records(tuple(drifted_events))

    with pytest.raises(GameLifecycleError, match="provider identity drifted"):
        GameLifecycle.from_payload(
            deepcopy(lifecycle.to_payload()),
            runtime_content_bundle=bundle,
        )

    selected_model_id = destroyed_model_ids[-1]
    result = DecisionResult.for_request(
        result_id="phase17g-daemonic-manifestation-effect-kind-drift:select",
        request=forged_request,
        selected_option_id=_healing_option_id_for_model(forged_request, selected_model_id),
    )
    before_state = state.to_payload()
    before_queue = decisions.queue.pending_requests
    before_records = decisions.records
    before_events = decisions.event_log.records
    before_dice_events = sum(event.event_type == "dice_rolled" for event in before_events)

    with pytest.raises(GameLifecycleError, match="provider identity drifted"):
        lifecycle.submit_decision(result)

    assert state.to_payload() == before_state
    assert decisions.queue.pending_requests == before_queue
    assert decisions.records == before_records
    assert decisions.event_log.records == before_events
    assert (
        sum(event.event_type == "dice_rolled" for event in decisions.event_log.records)
        == before_dice_events
    )
    assert all(
        _model_by_id(state, model_instance_id).wounds_remaining == 0
        for model_instance_id in destroyed_model_ids
    )


def test_daemonic_manifestation_dual_identity_drift_keeps_provider_ownership() -> None:
    session, state, destroyed_model_ids, _return_placements, request = (
        _july_manifestation_revival_session()
    )
    lifecycle = session.lifecycle
    bundle = _runtime_content_bundle(lifecycle)
    decisions = lifecycle.decision_controller
    request_payload = cast(dict[str, object], deepcopy(request.payload))
    effect_payload = cast(dict[str, object], request_payload["effect"])
    effect_payload["source_rule_id"] = "phase17g:forged-daemonic-manifestation-source"
    source_context = cast(dict[str, object], effect_payload["source_context"])
    source_context["effect_kind"] = "phase17g:forged-daemonic-manifestation-effect"
    forged_options = tuple(
        replace(
            option,
            payload=validate_json_value(
                {
                    **cast(dict[str, JsonValue], deepcopy(option.payload)),
                    "source_rule_id": "phase17g:forged-daemonic-manifestation-source",
                    "source_context": {
                        **cast(
                            dict[str, JsonValue],
                            deepcopy(cast(dict[str, JsonValue], option.payload)["source_context"]),
                        ),
                        "effect_kind": "phase17g:forged-daemonic-manifestation-effect",
                    },
                }
            ),
        )
        for option in request.options
    )
    forged_request = replace(
        request,
        payload=validate_json_value(request_payload),
        options=forged_options,
    )
    decisions.queue._pending_requests[0] = forged_request  # pyright: ignore[reportPrivateUsage]

    original_request_payload = request.to_payload()
    forged_request_payload = forged_request.to_payload()
    changed_request_event = False
    drifted_events: list[EventRecord] = []
    for event in decisions.event_log.records:
        if event.event_type == "decision_requested" and event.payload == original_request_payload:
            drifted_events.append(
                replace(event, payload=validate_json_value(forged_request_payload))
            )
            changed_request_event = True
            continue
        drifted_events.append(event)
    assert changed_request_event
    decisions.event_log.replace_records(tuple(drifted_events))

    pending_marker = _event_payload(
        decisions,
        "chaos_daemons_daemonic_manifestation_revival_pending",
    )
    assert pending_marker["source_rule_id"] == army_rule.JULY_SOURCE_RULE_ID
    assert pending_marker["decision_request_id"] == request.request_id
    assert cast(dict[str, JsonValue], request.payload)["effect"] != effect_payload

    with pytest.raises(GameLifecycleError, match="provider identity drifted"):
        GameLifecycle.from_payload(
            deepcopy(lifecycle.to_payload()),
            runtime_content_bundle=bundle,
        )

    selected_model_id = destroyed_model_ids[-1]
    result = DecisionResult.for_request(
        result_id="phase17g-daemonic-manifestation-dual-identity-drift:select",
        request=forged_request,
        selected_option_id=_healing_option_id_for_model(forged_request, selected_model_id),
    )
    before_state = state.to_payload()
    before_queue = decisions.queue.pending_requests
    before_records = decisions.records
    before_events = decisions.event_log.records
    before_dice_events = sum(event.event_type == "dice_rolled" for event in before_events)

    with pytest.raises(GameLifecycleError, match="provider identity drifted"):
        lifecycle.submit_decision(result)

    assert state.to_payload() == before_state
    assert decisions.queue.pending_requests == before_queue
    assert decisions.records == before_records
    assert decisions.event_log.records == before_events
    assert (
        sum(event.event_type == "dice_rolled" for event in decisions.event_log.records)
        == before_dice_events
    )
    assert all(
        _model_by_id(state, model_instance_id).wounds_remaining == 0
        for model_instance_id in destroyed_model_ids
    )


@pytest.mark.parametrize(
    ("erase_selection_lineage", "rewrite_request_id"),
    [(False, False), (True, False), (True, True)],
    ids=(
        "selection-lineage-preserved",
        "selection-lineage-erased",
        "request-id-and-selection-lineage-erased",
    ),
)
def test_daemonic_manifestation_placement_identity_drift_retains_provider_ownership(
    erase_selection_lineage: bool,
    rewrite_request_id: bool,
) -> None:
    session, state, destroyed_model_ids, return_placements, selection_request = (
        _july_manifestation_revival_session()
    )
    lifecycle = session.lifecycle
    bundle = _runtime_content_bundle(lifecycle)
    selected_model_id = destroyed_model_ids[-1]
    placement_status = session.submit_option(
        request_id=selection_request.request_id,
        option_id=_healing_option_id_for_model(selection_request, selected_model_id),
        result_id="phase17g-daemonic-manifestation-lineage-drift:selection",
    )
    placement_request = _required_decision_request(placement_status)
    assert placement_request.decision_type == SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE
    restored = GameLifecycle.from_payload(
        deepcopy(lifecycle.to_payload()),
        runtime_content_bundle=bundle,
    )
    assert restored.decision_controller.queue.peek_next() == placement_request

    decisions = lifecycle.decision_controller
    placement_payload = cast(dict[str, object], deepcopy(placement_request.payload))
    selection_request_id = cast(str, placement_payload["source_selection_request_id"])
    selection_result_id = cast(str, placement_payload["source_selection_result_id"])
    selection_records = tuple(
        record
        for record in decisions.records
        if record.request.request_id == selection_request_id
        and record.result.result_id == selection_result_id
    )
    assert len(selection_records) == 1
    assert selection_records[0].request == selection_request
    pending_marker = _event_payload(
        decisions,
        "chaos_daemons_daemonic_manifestation_revival_pending",
    )
    assert pending_marker["decision_request_id"] == selection_request_id
    assert pending_marker["source_rule_id"] == army_rule.JULY_SOURCE_RULE_ID

    effect_payload = cast(dict[str, object], placement_payload["effect"])
    forged_effect_id = "phase17g:forged-daemonic-manifestation-effect"
    effect_payload["effect_id"] = forged_effect_id
    effect_payload["source_rule_id"] = "phase17g:forged-daemonic-manifestation-source"
    source_context = cast(dict[str, object], effect_payload["source_context"])
    source_context["effect_kind"] = "phase17g:forged-daemonic-manifestation-kind"
    source_context["hook_id"] = "phase17g:forged-daemonic-manifestation-hook"
    if erase_selection_lineage:
        placement_payload["source_selection_request_id"] = None
        placement_payload["source_selection_result_id"] = None
    forged_request = replace(
        placement_request,
        request_id=(
            f"{forged_effect_id}:healing-step-"
            f"{cast(int, placement_payload['step_index']):03d}:placement"
            if rewrite_request_id
            else placement_request.request_id
        ),
        payload=validate_json_value(placement_payload),
    )
    assert (forged_request.request_id == placement_request.request_id) is not rewrite_request_id
    assert (
        forged_request.request_id.startswith(
            f"{army_rule.JULY_HOOK_ID}:daemonic-manifestation-battleline:"
        )
        is not rewrite_request_id
    )
    decisions.queue._pending_requests[0] = forged_request  # pyright: ignore[reportPrivateUsage]

    original_request_payload = placement_request.to_payload()
    forged_request_payload = forged_request.to_payload()
    changed_request_event = False
    drifted_events: list[EventRecord] = []
    for event in decisions.event_log.records:
        if event.event_type == "decision_requested" and event.payload == original_request_payload:
            drifted_events.append(
                replace(event, payload=validate_json_value(forged_request_payload))
            )
            changed_request_event = True
            continue
        drifted_events.append(event)
    assert changed_request_event
    decisions.event_log.replace_records(tuple(drifted_events))
    expected_selection_request_id = None if erase_selection_lineage else selection_request_id
    expected_selection_result_id = None if erase_selection_lineage else selection_result_id
    assert placement_payload["source_selection_request_id"] == expected_selection_request_id
    assert placement_payload["source_selection_result_id"] == expected_selection_result_id

    with pytest.raises(GameLifecycleError, match="provider identity drifted"):
        GameLifecycle.from_payload(
            deepcopy(lifecycle.to_payload()),
            runtime_content_bundle=bundle,
        )

    result = DecisionResult(
        result_id="phase17g-daemonic-manifestation-lineage-drift:placement",
        request_id=forged_request.request_id,
        decision_type=forged_request.decision_type,
        actor_id=forged_request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=_healing_revival_payload(
            request=forged_request,
            placement=return_placements[selected_model_id],
        ),
    )
    before_state = state.to_payload()
    before_queue = decisions.queue.pending_requests
    before_records = decisions.records
    before_events = decisions.event_log.records

    if rewrite_request_id:
        with pytest.raises(GameLifecycleError, match="provider identity drifted"):
            lifecycle.submit_decision(result)
    else:
        invalid_status = lifecycle.submit_decision(result)
        assert invalid_status.status_kind is LifecycleStatusKind.INVALID

    assert state.to_payload() == before_state
    assert decisions.queue.pending_requests == before_queue
    assert decisions.records == before_records
    assert decisions.event_log.records == before_events
    assert _model_by_id(state, selected_model_id).wounds_remaining == 0
    assert state.battlefield_state is not None
    assert selected_model_id not in state.battlefield_state.placed_model_ids()


def test_staged_july_daemonic_manifestation_can_finish_before_first_revival() -> None:
    session, state, destroyed_model_ids, _return_placements, request = (
        _july_manifestation_revival_session()
    )
    finish_option_id = _healing_finish_option_id(request)
    valid_result = DecisionResult.for_request(
        result_id="phase17g-july-manifestation-finish-zero",
        request=request,
        selected_option_id=finish_option_id,
    )
    valid_payload = cast(dict[str, JsonValue], valid_result.payload)
    malformed_result = replace(
        valid_result,
        result_id="phase17g-july-manifestation-malformed-finish",
        payload={**valid_payload, "legal_model_ids": []},
    )
    before_records = session.lifecycle.decision_controller.records

    malformed_status = session.lifecycle.submit_decision(malformed_result)
    stale_status = session.lifecycle.submit_decision(
        replace(
            valid_result,
            result_id="phase17g-july-manifestation-stale-finish",
            request_id="phase17g-july-manifestation-stale-request",
        )
    )

    assert malformed_status.status_kind is LifecycleStatusKind.INVALID
    assert malformed_status.payload == {
        "invalid_reason": "invalid_healing_model_selection_result",
        "field": "payload",
    }
    assert stale_status.status_kind is LifecycleStatusKind.INVALID
    assert stale_status.payload == {
        "invalid_reason": "invalid_healing_model_selection_result",
        "field": "request_id",
    }
    assert session.lifecycle.decision_controller.queue.peek_next() == request
    assert session.lifecycle.decision_controller.records == before_records

    completed = session.submit_option(
        request_id=request.request_id,
        option_id=finish_option_id,
        result_id=valid_result.result_id,
    )

    assert completed.status_kind is not LifecycleStatusKind.INVALID
    assert all(
        _model_by_id(state, model_id).wounds_remaining == 0 for model_id in destroyed_model_ids
    )
    finish_event = _event_payloads(
        session.lifecycle.decision_controller,
        "healing_step_resolved",
    )[-1]
    finish_step = cast(dict[str, JsonValue], finish_event["step"])
    assert finish_step["step_kind"] == "finish"
    assert finish_step["model_instance_id"] is None
    assert finish_step["request_id"] == request.request_id
    assert finish_step["result_id"] == valid_result.result_id
    replay_payload = session.lifecycle.decision_controller.to_payload()
    assert DecisionController.from_payload(replay_payload).to_payload() == replay_payload


def test_staged_july_daemonic_manifestation_can_finish_after_partial_revival() -> None:
    session, state, destroyed_model_ids, return_placements, request = (
        _july_manifestation_revival_session()
    )
    selected_model_id = _healing_option_model_ids(request)[-1]
    placement_status = session.submit_option(
        request_id=request.request_id,
        option_id=_healing_option_id_for_model(request, selected_model_id),
        result_id="phase17g-july-manifestation-partial-select",
    )
    placement_request = _required_decision_request(placement_status)
    next_status = session.submit_parameterized_payload(
        request_id=placement_request.request_id,
        payload=_healing_revival_payload(
            request=placement_request,
            placement=return_placements[selected_model_id],
        ),
        result_id="phase17g-july-manifestation-partial-place",
    )
    finish_request = _required_decision_request(next_status)

    assert finish_request.decision_type == SELECT_HEALING_MODEL_DECISION_TYPE
    assert len(_healing_option_model_ids(finish_request)) == 2
    completed = session.submit_option(
        request_id=finish_request.request_id,
        option_id=_healing_finish_option_id(finish_request),
        result_id="phase17g-july-manifestation-partial-finish",
    )

    assert completed.status_kind is not LifecycleStatusKind.INVALID
    assert (
        _model_by_id(state, selected_model_id).wounds_remaining
        == _model_by_id(
            state,
            selected_model_id,
        ).starting_wounds
    )
    assert all(
        _model_by_id(state, model_id).wounds_remaining == 0
        for model_id in destroyed_model_ids
        if model_id != selected_model_id
    )
    step_kinds = tuple(
        cast(dict[str, JsonValue], event["step"])["step_kind"]
        for event in _event_payloads(
            session.lifecycle.decision_controller,
            "healing_step_resolved",
        )
    )
    assert step_kinds == ("revive_model", "finish")


def test_kairos_lifecycle_checks_primary_and_companion_range_targets() -> None:
    cases = (
        (False, True, True),
        (True, False, True),
        (False, False, False),
    )
    for primary_inside, companion_inside, expects_choice in cases:
        lifecycle, primary_id, companion_id = _kairos_realm_lifecycle(
            primary_inside=primary_inside,
            companion_inside=companion_inside,
        )

        status = _submit_realm_of_chaos_pair(
            lifecycle=lifecycle,
            primary_unit_id=primary_id,
            companion_unit_id=companion_id,
            result_id=(f"phase17g-kairos-realm:{primary_inside}:{companion_inside}:source-result"),
        )

        if not expects_choice:
            assert status.decision_request is None or (
                status.decision_request.decision_type
                != SELECT_STRATAGEM_COST_MODIFIER_OPTION_DECISION_TYPE
            )
            assert not any(
                event.event_type == "catalog_ir_stratagem_cost_choice_resolved"
                for event in lifecycle.decision_controller.event_log.records
            )
            continue
        request = _required_decision_request(status)
        assert request.decision_type == SELECT_STRATAGEM_COST_MODIFIER_OPTION_DECISION_TYPE
        request_payload = cast(dict[str, JsonValue], request.payload)
        assert request_payload["target_unit_instance_ids"] == sorted((primary_id, companion_id))
        assert all(
            cast(dict[str, JsonValue], option.payload)["target_unit_instance_ids"]
            == sorted((primary_id, companion_id))
            for option in request.options
        )


def test_kairos_lifecycle_canonicalizes_attached_target_and_restores_choice() -> None:
    lifecycle, primary_id, companion_id = _kairos_realm_lifecycle(
        primary_inside=True,
        companion_inside=False,
        attached_primary=True,
    )
    source_status = _submit_realm_of_chaos_pair(
        lifecycle=lifecycle,
        primary_unit_id=primary_id,
        companion_unit_id=companion_id,
        result_id="phase17g-kairos-attached-source-result",
    )
    request = _required_decision_request(source_status)
    bundle = _runtime_content_bundle(lifecycle)
    restored = GameLifecycle.from_payload(
        lifecycle.to_payload(),
        runtime_content_bundle=bundle,
    )
    restored_request = restored.decision_controller.queue.peek_next()

    assert restored_request == request
    request_payload = cast(dict[str, JsonValue], restored_request.payload)
    assert request_payload["target_unit_instance_ids"] == sorted((primary_id, companion_id))
    decline_option = next(
        option
        for option in restored_request.options
        if cast(dict[str, JsonValue], option.payload)["use_ability"] is False
    )
    valid_result = DecisionResult.for_request(
        result_id="phase17g-kairos-attached-decline",
        request=restored_request,
        selected_option_id=decline_option.option_id,
    )
    valid_payload = cast(dict[str, JsonValue], valid_result.payload)
    before_cp = restored.state.command_point_total("player-b") if restored.state else -1
    before_records = restored.decision_controller.records
    malformed_status = restored.submit_decision(
        replace(
            valid_result,
            result_id="phase17g-kairos-attached-malformed",
            payload={
                **valid_payload,
                "target_unit_instance_ids": [companion_id],
            },
        )
    )

    assert malformed_status.status_kind is LifecycleStatusKind.INVALID
    assert malformed_status.payload == {
        "invalid_reason": "invalid_stratagem_cost_modifier_option_result",
        "field": "payload",
    }
    assert restored.decision_controller.queue.peek_next() == restored_request
    assert restored.decision_controller.records == before_records
    assert restored.state is not None
    assert restored.state.command_point_total("player-b") == before_cp

    completed = restored.submit_decision(valid_result)

    assert completed.status_kind is not LifecycleStatusKind.INVALID
    choice_event = _event_payload(
        restored.decision_controller,
        "catalog_ir_stratagem_cost_choice_resolved",
    )
    assert choice_event["target_unit_instance_ids"] == sorted((primary_id, companion_id))
    assert choice_event["use_ability"] is False


def test_staged_july_daemonic_manifestation_has_no_effect_without_eligible_models() -> None:
    state = battle_state()
    _mark_player_as_chaos_daemons(state, player_id="player-a")
    unit_id = "army-alpha:intercessor-unit-1"
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=unit_id,
        keywords=("Battleline", "Character", "Infantry"),
        faction_keywords=("Legiones Daemonica",),
    )
    destroyed_model_ids = _placed_model_ids(state, unit_id)[:3]
    remove_first_models(state, unit_instance_id=unit_id, count=3)
    for model_instance_id in destroyed_model_ids:
        _replace_model_wounds(
            state,
            model_instance_id=model_instance_id,
            wounds_remaining=0,
        )
    decisions = DecisionController()
    _record_battle_shock_auto_pass(
        state,
        decisions=decisions,
        unit_instance_id=unit_id,
    )
    handler = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
        battle_shock_hooks=BattleShockHookRegistry.from_bindings(
            july_2026_candidate.runtime_contribution().battle_shock_hook_bindings
        ),
    )

    completed = handler.begin_phase(state=state, decisions=decisions)

    assert completed.status_kind is LifecycleStatusKind.ADVANCED
    assert decisions.queue.pending_requests == ()
    no_effect = _event_payload(
        decisions,
        "chaos_daemons_daemonic_manifestation_no_effect",
    )
    assert no_effect["source_rule_id"] == army_rule.JULY_SOURCE_RULE_ID
    assert no_effect["no_effect_reason"] == "battleline_unit_has_no_destroyed_models"


def test_staged_july_daemonic_manifestation_uses_attached_rules_unit_models() -> None:
    config = _chaos_daemons_lifecycle_config(attached=True)
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    state = _record_lifecycle_battle_state(lifecycle=lifecycle, config=config)
    _mark_player_as_chaos_daemons(state, player_id="player-a")
    daemon_army = state.army_definition_for_player("player-a")
    assert daemon_army is not None
    formation = daemon_army.attached_units[0]
    bodyguard = unit_by_id(state, formation.bodyguard_unit_instance_id)
    leader = unit_by_id(state, formation.leader_unit_instance_ids[0])
    bodyguard_destroyed_ids = _placed_model_ids(state, bodyguard.unit_instance_id)[:3]
    leader_model_id = leader.own_models[0].model_instance_id
    remove_first_models(
        state,
        unit_instance_id=bodyguard.unit_instance_id,
        count=3,
    )
    remove_first_models(
        state,
        unit_instance_id=leader.unit_instance_id,
        count=1,
    )
    for model_instance_id in (*bodyguard_destroyed_ids, leader_model_id):
        _replace_model_wounds(
            state,
            model_instance_id=model_instance_id,
            wounds_remaining=0,
        )
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=formation.attached_unit_instance_id,
    )
    below_half_context = BelowHalfStrengthContext.from_rules_unit(
        rules_unit=rules_unit,
        starting_strength=state.starting_strength_record_for_unit(
            formation.attached_unit_instance_id
        ),
        current_model_ids=tuple(model.model_instance_id for model in rules_unit.alive_models()),
    )
    request = BattleShockTestRequest.for_unit(
        request_id="phase17g-july-attached-battle-shock",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-a",
        unit_instance_id=formation.attached_unit_instance_id,
        reason=BattleShockTestReason.BELOW_HALF_STRENGTH,
        leadership_target=7,
        below_half_strength_context=below_half_context,
    )
    modifiers = BattleShockHookRegistry.from_bindings(
        july_2026_candidate.runtime_contribution().battle_shock_hook_bindings
    ).modifiers_for(
        BattleShockModifierContext(
            state=state,
            request=request,
            active_player_id="player-a",
            phase=BattlePhase.COMMAND,
            phase_start_battle_shocked_unit_ids=(),
        )
    )
    assert tuple(modifier.operand for modifier in modifiers) == (1,)
    decisions = DecisionController()
    dice_manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    roll_state = dice_manager.roll_fixed(request.spec, (6, 6))
    result = BattleShockResult.from_roll_state(
        result_id="phase17g-july-attached-battle-shock-result",
        request=request,
        roll_state=roll_state,
    )

    army_rule.resolve_july_battle_shock_outcome(
        BattleShockOutcomeContext(
            state=state,
            decisions=decisions,
            dice_manager=dice_manager,
            result=result,
            active_player_id="player-a",
            phase=BattlePhase.COMMAND,
            auto_passed=True,
            phase_start_battle_shocked_unit_ids=(),
        )
    )

    pending = decisions.queue.peek_next()
    assert pending.decision_type == SELECT_HEALING_MODEL_DECISION_TYPE
    assert _healing_option_model_ids(pending) == tuple(sorted(bodyguard_destroyed_ids))
    assert leader_model_id not in _healing_option_model_ids(pending)
    payload = cast(dict[str, JsonValue], pending.payload)
    effect = cast(dict[str, JsonValue], payload["effect"])
    assert effect["target_unit_instance_id"] == formation.attached_unit_instance_id
    source_context = cast(dict[str, JsonValue], effect["source_context"])
    assert source_context["eligible_revival_model_ids"] == sorted(bodyguard_destroyed_ids)


def test_default_june_daemonic_manifestation_battleline_branch_remains_unsupported() -> None:
    state = battle_state()
    _mark_player_as_chaos_daemons(state, player_id="player-a")
    unit_id = "army-alpha:intercessor-unit-1"
    destroyed_model_ids = _placed_model_ids(state, unit_id)[:3]
    remove_first_models(state, unit_instance_id=unit_id, count=3)
    for model_instance_id in destroyed_model_ids:
        _replace_model_wounds(
            state,
            model_instance_id=model_instance_id,
            wounds_remaining=0,
        )
    decisions = DecisionController()
    _record_battle_shock_auto_pass(
        state,
        decisions=decisions,
        unit_instance_id=unit_id,
    )
    handler = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
        battle_shock_hooks=_chaos_daemons_battle_shock_hooks(),
    )

    completed = handler.begin_phase(state=state, decisions=decisions)

    assert completed.status_kind is LifecycleStatusKind.ADVANCED
    assert decisions.queue.pending_requests == ()
    unsupported = _event_payload(
        decisions,
        "chaos_daemons_daemonic_manifestation_unsupported",
    )
    assert unsupported["source_rule_id"] == army_rule.SOURCE_RULE_ID
    assert (
        unsupported["unsupported_reason"] == "battleline_model_return_requires_placement_decision"
    )


def test_chaos_daemons_army_rule_hook_uses_phase17f_execution_source_id() -> None:
    record = _chaos_daemons_army_rule_execution_record()
    contribution = army_rule.staged_july_runtime_contribution()
    binding = contribution.battle_shock_hook_bindings[0]

    assert record.execution_id == army_rule.JULY_SOURCE_RULE_ID
    assert record.handler_id == army_rule.JULY_HOOK_ID
    assert binding.source_id == record.execution_id
    assert binding.hook_id == record.handler_id


def test_lifecycle_loads_chaos_daemons_battle_shock_hook_from_runtime_manifest() -> None:
    config = _chaos_daemons_lifecycle_config()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    state = _record_lifecycle_battle_state(lifecycle=lifecycle, config=config)
    unit_id = "army-alpha:manifestation-daemon"
    remove_first_models(state, unit_instance_id=unit_id, count=3)
    wounded_model_id = _placed_model_ids(state, unit_id)[0]
    _replace_model_wounds(state, model_instance_id=wounded_model_id, wounds_remaining=1)
    _record_battle_shock_auto_pass(
        state,
        decisions=lifecycle.decision_controller,
        unit_instance_id=unit_id,
    )
    bundle = _runtime_content_bundle(lifecycle)
    summary = bundle.to_summary_payload()

    assert army_rule.JULY_HOOK_ID in summary["battle_shock_hook_ids"]
    assert army_rule.JULY_SOURCE_RULE_ID in summary["selected_execution_record_ids"]
    assert army_rule.SOURCE_RULE_ID not in summary["selected_execution_record_ids"]
    assert any(
        path.endswith(".chaos_daemons.july_2026") for path in summary["selected_module_paths"]
    )

    status = lifecycle.advance_until_decision_or_terminal()
    _decline_stratagem_target_proposal_if_pending(
        lifecycle=lifecycle,
        status=status,
        result_id="phase17g-chaos-daemons-decline-insane-bravery",
    )
    lifecycle.advance_until_decision_or_terminal()

    manifestation_payload = _event_payload(
        lifecycle.decision_controller,
        "chaos_daemons_daemonic_manifestation_healing_resolved",
    )
    assert manifestation_payload["source_rule_id"] == army_rule.JULY_SOURCE_RULE_ID
    assert _model_by_id(state, wounded_model_id).wounds_remaining == 2


def test_shadow_of_chaos_uses_phase_start_control_snapshot_for_all_tests() -> None:
    state = battle_state(
        player_a_units=(
            default_unit_selection("intercessor-unit-1"),
            default_unit_selection("intercessor-unit-2"),
        )
    )
    _mark_player_as_chaos_daemons(state, player_id="player-a")
    unit_ids = ("army-alpha:intercessor-unit-1", "army-alpha:intercessor-unit-2")
    for unit_id in unit_ids:
        remove_first_models(state, unit_instance_id=unit_id, count=3)
        _replace_unit_leadership(state, unit_instance_id=unit_id, leadership=99)
    _place_unit_near_center(state, unit_instance_id=unit_ids[0], offset=(0.0, 0.0))
    _place_unit_near_center(state, unit_instance_id=unit_ids[1], offset=(-1.5, -13.5))
    decisions = DecisionController()
    handler = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
        battle_shock_hooks=_chaos_daemons_battle_shock_hooks(),
    )

    waiting = handler.begin_phase(state=state, decisions=decisions)
    sequencing_request = _required_decision_request(waiting)
    assert sequencing_request.decision_type == SEQUENCING_DECISION_TYPE
    sequencing_result = DecisionResult.for_request(
        result_id="phase17g-shadow-command-battle-shock-order",
        request=sequencing_request,
        selected_option_id=sequencing_request.options[0].option_id,
    )
    sequencing_record = decisions.submit_result(sequencing_result)
    sequencing_event_type, sequencing_event_payload = sequencing_decision_event_from_request(
        request=sequencing_record.request,
        result=sequencing_record.result,
    )
    decisions.event_log.append(
        sequencing_event_type,
        sequencing_event_payload,
    )

    completed = handler.begin_phase(state=state, decisions=decisions)

    assert completed.status_kind is LifecycleStatusKind.ADVANCED
    results_by_unit_id: dict[str, dict[str, JsonValue]] = {}
    for payload in _event_payloads(decisions, "battle_shock_test_resolved"):
        result_payload = cast(dict[str, JsonValue], payload["battle_shock_result"])
        request_payload = cast(dict[str, JsonValue], result_payload["request"])
        unit_instance_id = cast(str, request_payload["unit_instance_id"])
        results_by_unit_id[unit_instance_id] = result_payload
    for unit_id in unit_ids:
        result_payload = results_by_unit_id[unit_id]
        modified_roll = cast(dict[str, JsonValue], result_payload["modified_roll"])
        modifiers = cast(list[JsonValue], modified_roll["modifiers"])
        assert result_payload["passed"] is False
        assert any(cast(dict[str, JsonValue], modifier)["operand"] == 1 for modifier in modifiers)


def test_daemonic_terror_modifies_enemy_battle_shock_and_applies_mortal_wounds() -> None:
    state = battle_state()
    _mark_player_as_chaos_daemons(
        state,
        player_id="player-a",
        unit_name="Renamed Greater Daemon Source",
    )
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        keywords=("Character", "Monster", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
        datasheet_abilities=(
            _datasheet_ability(datasheets.BLOODTHIRSTER_GREATER_DAEMON_ABILITY_ID),
        ),
    )
    state.active_player_id = "player-b"
    state.command_step_state = None
    target_unit_id = "army-beta:intercessor-unit-3"
    remove_first_models(state, unit_instance_id=target_unit_id, count=3)
    _replace_unit_leadership(state, unit_instance_id=target_unit_id, leadership=13)
    _place_units_near_center(
        state,
        source_unit_id="army-alpha:intercessor-unit-1",
        target_unit_id=target_unit_id,
    )
    starting_wounds = sum(
        model.wounds_remaining for model in unit_by_id(state, target_unit_id).own_models
    )
    decisions = DecisionController()
    handler = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
        battle_shock_hooks=_chaos_daemons_battle_shock_hooks(),
    )

    completed = handler.begin_phase(state=state, decisions=decisions)

    assert completed.status_kind is LifecycleStatusKind.ADVANCED
    resolved_payload = _event_payload(decisions, "battle_shock_test_resolved")
    result_payload = cast(dict[str, JsonValue], resolved_payload["battle_shock_result"])
    modified_roll = cast(dict[str, JsonValue], result_payload["modified_roll"])
    modifiers = cast(list[JsonValue], modified_roll["modifiers"])
    assert result_payload["passed"] is False
    assert cast(dict[str, JsonValue], modifiers[0])["operand"] == -1
    terror_payload = _event_payload(
        decisions,
        "chaos_daemons_daemonic_terror_mortal_wounds_applied",
    )
    application = cast(dict[str, JsonValue], terror_payload["mortal_wound_application"])
    assert application["mortal_wounds"] in (1, 2, 3)
    final_wounds = sum(
        model.wounds_remaining for model in unit_by_id(state, target_unit_id).own_models
    )
    assert final_wounds < starting_wounds


def test_daemonic_manifestation_records_no_effect_and_multiple_wound_choice_boundaries() -> None:
    no_effect_state = battle_state()
    _mark_player_as_chaos_daemons(
        no_effect_state,
        player_id="player-a",
        remove_battleline=True,
    )
    unit_id = "army-alpha:intercessor-unit-1"
    no_effect_decisions = DecisionController()
    army_rule.resolve_battle_shock_outcome(
        _battle_shock_outcome_context(
            state=no_effect_state,
            decisions=no_effect_decisions,
            player_id="player-a",
            unit_instance_id=unit_id,
            passed=True,
            result_id="phase17g-manifestation-no-wounded-models",
        )
    )

    no_effect = _event_payload(
        no_effect_decisions,
        "chaos_daemons_daemonic_manifestation_no_effect",
    )
    assert no_effect["no_effect_reason"] == "unit_has_no_wounded_models"
    assert no_effect["unit_instance_id"] == unit_id
    assert DecisionController.from_payload(no_effect_decisions.to_payload()) == no_effect_decisions

    choice_state = battle_state()
    _mark_player_as_chaos_daemons(
        choice_state,
        player_id="player-a",
        remove_battleline=True,
    )
    wounded_ids = _placed_model_ids(choice_state, unit_id)[:2]
    for model_id in wounded_ids:
        _replace_model_wounds(choice_state, model_instance_id=model_id, wounds_remaining=1)
    choice_decisions = DecisionController()
    army_rule.resolve_battle_shock_outcome(
        _battle_shock_outcome_context(
            state=choice_state,
            decisions=choice_decisions,
            player_id="player-a",
            unit_instance_id=unit_id,
            passed=True,
            result_id="phase17g-manifestation-multiple-wounded-models",
        )
    )

    unsupported = _event_payload(
        choice_decisions,
        "chaos_daemons_daemonic_manifestation_unsupported",
    )
    assert unsupported["unsupported_reason"] == "multiple_wounded_models_require_decision"
    assert _event_payloads(choice_decisions, "healing_step_resolved") == ()
    assert (
        GameState.from_payload(choice_state.to_payload()).to_payload() == choice_state.to_payload()
    )


def test_daemonic_terror_noops_for_pass_or_ineligible_target_and_reports_fnp_choice() -> None:
    state = battle_state()
    _mark_player_as_chaos_daemons(state, player_id="player-a")
    source_unit_id = "army-alpha:intercessor-unit-1"
    target_unit_id = "army-beta:intercessor-unit-3"
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=source_unit_id,
        keywords=("Character", "Monster", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
        datasheet_abilities=(
            _datasheet_ability(datasheets.BLOODTHIRSTER_GREATER_DAEMON_ABILITY_ID),
        ),
    )
    _place_units_near_center(
        state,
        source_unit_id=source_unit_id,
        target_unit_id=target_unit_id,
    )
    target_model_id = _placed_model_ids(state, target_unit_id)[0]
    state.record_model_feel_no_pain_sources(
        model_instance_id=target_model_id,
        sources=(FeelNoPainSource(source_id="phase17g-terror-fnp", threshold=5),),
        decline_allowed=True,
    )
    decisions = DecisionController()

    army_rule.resolve_battle_shock_outcome(
        _battle_shock_outcome_context(
            state=state,
            decisions=decisions,
            player_id="player-b",
            unit_instance_id=target_unit_id,
            passed=True,
            result_id="phase17g-terror-passed-noop",
        )
    )
    assert _event_payloads(decisions, "chaos_daemons_daemonic_terror_unsupported") == ()

    army_rule.resolve_battle_shock_outcome(
        _battle_shock_outcome_context(
            state=state,
            decisions=decisions,
            player_id="player-b",
            unit_instance_id=target_unit_id,
            passed=False,
            result_id="phase17g-terror-fnp-unsupported",
        )
    )
    unsupported = _event_payload(decisions, "chaos_daemons_daemonic_terror_unsupported")
    assert unsupported["unsupported_reason"] == "mortal_wound_feel_no_pain_requires_decision"
    assert unsupported["target_unit_instance_id"] == target_unit_id
    assert _event_payloads(decisions, "chaos_daemons_daemonic_terror_mortal_wounds_applied") == ()

    ineligible_state = battle_state()
    _mark_player_as_chaos_daemons(ineligible_state, player_id="player-a")
    ineligible_decisions = DecisionController()
    target_rules_unit = rules_unit_view_by_id(
        state=ineligible_state,
        unit_instance_id=target_unit_id,
    )
    daemon_army = ineligible_state.army_definition_for_player("player-a")
    assert daemon_army is not None
    assert not army_rule._daemonic_terror_applies(  # pyright: ignore[reportPrivateUsage]
        state=ineligible_state,
        daemon_army=daemon_army,
        target_rules_unit=target_rules_unit,
        battle_shocked_unit_ids=(),
    )
    army_rule.resolve_battle_shock_outcome(
        _battle_shock_outcome_context(
            state=ineligible_state,
            decisions=ineligible_decisions,
            player_id="player-b",
            unit_instance_id=target_unit_id,
            passed=False,
            result_id="phase17g-terror-ineligible-noop",
        )
    )
    assert (
        _event_payloads(
            ineligible_decisions,
            "chaos_daemons_daemonic_terror_mortal_wounds_applied",
        )
        == ()
    )


def _chaos_daemons_battle_shock_hooks() -> BattleShockHookRegistry:
    contribution = army_rule.runtime_contribution()
    return BattleShockHookRegistry.from_bindings(contribution.battle_shock_hook_bindings)


def _chaos_daemons_army_rule_execution_record() -> Phase17FExecutionRecord:
    records = tuple(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.faction_id == army_rule.CHAOS_DAEMONS_FACTION_ID
        and record.coverage_kind is Phase17ECoverageKind.FACTION_ARMY_RULE
    )
    if len(records) != 1:
        raise AssertionError("expected one Chaos Daemons army-rule execution record")
    return records[0]


def _record_lifecycle_battle_state(
    *,
    lifecycle: GameLifecycle,
    config: GameConfig,
) -> GameState:
    state = lifecycle.state
    if state is None:
        raise AssertionError("lifecycle must be started")
    for army in _mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase17g-chaos-daemons-battlefield",
        armies=tuple(state.army_definitions),
    )
    state.record_battlefield_state(scenario.battlefield_state)
    state.record_secondary_mission_choice(
        _fixed_secondary_choice(player_id="player-a"),
    )
    state.record_secondary_mission_choice(
        _fixed_secondary_choice(player_id="player-b"),
    )
    complete_setup_through_gate(
        state=state,
        decisions=lifecycle.decision_controller,
        config=config,
    )
    return state


def _runtime_content_bundle(lifecycle: GameLifecycle) -> RuntimeContentBundle:
    require_runtime_content_bundle = cast(
        Callable[[], RuntimeContentBundle],
        object.__getattribute__(lifecycle, "_require_runtime_content_bundle"),
    )
    return require_runtime_content_bundle()


def _decline_stratagem_target_proposal_if_pending(
    *,
    lifecycle: GameLifecycle,
    status: LifecycleStatus,
    result_id: str,
) -> None:
    request = status.decision_request
    if request is None:
        return
    if request.decision_type != STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
        return
    declined = lifecycle.submit_decision(
        DecisionResult(
            result_id=result_id,
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=stratagem_decline_payload(),
        )
    )
    if declined.status_kind is LifecycleStatusKind.INVALID:
        raise AssertionError("expected Stratagem proposal decline to be valid")


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


def _fixed_secondary_choice(*, player_id: str) -> SecondaryMissionChoice:
    return SecondaryMissionChoice(
        player_id=player_id,
        mode=SecondaryMissionMode.FIXED,
        fixed_mission_ids=("assassination", "bring_it_down"),
    )


def _chaos_daemons_lifecycle_config(
    *,
    battleline: bool = False,
    attached: bool = False,
) -> GameConfig:
    catalog = _chaos_daemons_lifecycle_catalog(
        battleline=battleline,
        attached=attached,
    )
    alpha_unit_selections = (
        (
            UnitMusterSelection(
                unit_selection_id="bodyguard-unit",
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
            UnitMusterSelection(
                unit_selection_id="leader-unit",
                datasheet_id="core-character-leader",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-character-leader",
                        model_count=1,
                    ),
                ),
            ),
        )
        if attached
        else (
            UnitMusterSelection(
                unit_selection_id="manifestation-daemon",
                datasheet_id=CHAOS_DAEMONS_TEST_DATASHEET_ID,
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
        )
    )
    return GameConfig(
        game_id="phase17g-chaos-daemons-lifecycle-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
            descriptor_version="core-v2-phase17g-chaos-daemons-test",
        ),
        army_catalog=catalog,
        army_muster_requests=(
            ArmyMusterRequest(
                army_id="army-alpha",
                player_id="player-a",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id=army_rule.CHAOS_DAEMONS_FACTION_ID,
                    detachment_ids=("warptide",),
                ),
                force_disposition_id="take-and-hold",
                unit_selections=alpha_unit_selections,
                attachment_declarations=(
                    (
                        AttachmentDeclaration(
                            source_unit_selection_id="leader-unit",
                            bodyguard_unit_selection_id="bodyguard-unit",
                        ),
                    )
                    if attached
                    else ()
                ),
            ),
            ArmyMusterRequest(
                army_id="army-beta",
                player_id="player-b",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_ids=("core-combined-arms",),
                ),
                force_disposition_id="purge-the-foe",
                unit_selections=(
                    UnitMusterSelection(
                        unit_selection_id="enemy-unit",
                        datasheet_id="core-intercessor-like-infantry",
                        model_profile_selections=(
                            ModelProfileSelection(
                                model_profile_id="core-intercessor-like",
                                model_count=5,
                            ),
                        ),
                    ),
                ),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2026_27_mission_pack(),
            mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
            terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
            attacker_player_id="player-a",
            attacker_force_disposition_id="take-and-hold",
            defender_player_id="player-b",
            defender_force_disposition_id="purge-the-foe",
        ),
    )


def _chaos_daemons_lifecycle_catalog(
    *,
    battleline: bool = False,
    attached: bool = False,
) -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    daemon_datasheet = _chaos_daemons_datasheet(
        base_datasheet,
        battleline=battleline,
    )
    catalog_datasheets = tuple(
        (
            replace(
                datasheet,
                keywords=replace(
                    datasheet.keywords,
                    faction_keywords=("CORE MARINES", "LEGIONES DAEMONICA"),
                ),
            )
            if attached
            and datasheet.datasheet_id
            in {
                "core-character-leader",
                "core-intercessor-like-infantry",
            }
            else datasheet
        )
        for datasheet in base_catalog.datasheets
    )
    return replace(
        base_catalog,
        datasheets=(*catalog_datasheets, daemon_datasheet),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id=army_rule.CHAOS_DAEMONS_FACTION_ID,
                name="Chaos Daemons",
                faction_keywords=("Legiones Daemonica",),
                source_ids=("gw-11e-faction-detachments-2026-27:faction:chaos-daemons",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                detachment_id="warptide",
                name="Warptide",
                faction_id=army_rule.CHAOS_DAEMONS_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(
                    CHAOS_DAEMONS_TEST_DATASHEET_ID,
                    "core-character-leader",
                    "core-intercessor-like-infantry",
                ),
                force_disposition_ids=("phase17g-force", "take-and-hold"),
                source_ids=(
                    "gw-11e-faction-detachments-2026-27:detachment:chaos-daemons:warptide",
                ),
            ),
        ),
    )


def _chaos_daemons_datasheet(
    base_datasheet: DatasheetDefinition,
    *,
    battleline: bool,
) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=CHAOS_DAEMONS_TEST_DATASHEET_ID,
        name="Manifestation Daemon",
        keywords=DatasheetKeywordSet(
            keywords=(
                ("Battleline", "Infantry", "Khorne") if battleline else ("Infantry", "Khorne")
            ),
            faction_keywords=("Legiones Daemonica",),
        ),
        attachment_eligibilities=(),
        source_ids=("phase17g:test:chaos-daemons:manifestation-daemon",),
    )


def _mark_player_as_chaos_daemons(
    state: GameState,
    *,
    player_id: str,
    unit_name: str | None = None,
    remove_battleline: bool = False,
) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != player_id:
            updated_armies.append(army)
            continue
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            keywords = set(unit.keywords)
            if remove_battleline:
                keywords.discard("Battleline")
                keywords.discard("BATTLELINE")
            updated_units.append(
                replace(
                    unit,
                    name=unit.name if unit_name is None else unit_name,
                    keywords=tuple(sorted(keywords)),
                    faction_keywords=("Legiones Daemonica",),
                )
            )
        updated_armies.append(
            replace(
                army,
                detachment_selection=replace(
                    army.detachment_selection,
                    faction_id="chaos-daemons",
                ),
                units=tuple(updated_units),
            )
        )
    state.army_definitions = updated_armies


def _replace_unit_keywords_and_abilities(
    state: GameState,
    *,
    unit_instance_id: str,
    keywords: tuple[str, ...],
    faction_keywords: tuple[str, ...],
    datasheet_abilities: tuple[DatasheetAbilityDescriptor, ...] | None = None,
) -> None:
    updated_armies: list[ArmyDefinition] = []
    replaced = False
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            if unit.unit_instance_id != unit_instance_id:
                updated_units.append(unit)
                continue
            replaced = True
            updated_units.append(
                replace(
                    unit,
                    keywords=keywords,
                    faction_keywords=faction_keywords,
                    datasheet_abilities=(
                        unit.datasheet_abilities
                        if datasheet_abilities is None
                        else datasheet_abilities
                    ),
                )
            )
        updated_armies.append(replace(army, units=tuple(updated_units)))
    if not replaced:
        raise AssertionError(f"missing unit {unit_instance_id}")
    state.army_definitions = updated_armies


def _datasheet_ability(ability_id: str) -> DatasheetAbilityDescriptor:
    return DatasheetAbilityDescriptor(
        ability_id=ability_id,
        name="Source Backed Datasheet Ability",
        source_id=f"data-package:core-v2:phase17g-chaos-army-rule-test:{ability_id}",
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description="source-backed datasheet test ability",
    )


def _semantic_shadow_aura_ability(*, allegiance: str) -> DatasheetAbilityDescriptor:
    compiled = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id=f"phase17g:test:semantic-shadow-aura:{allegiance.lower()}",
            raw_text=(
                f"Daemonic Shadow (Aura): While a friendly {allegiance} Legiones Daemonica "
                'unit is within 6" of this model, that unit is within your army\u2019s Shadow '
                "of Chaos."
            ),
        ),
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    )
    if not compiled.rule_ir.is_supported:
        raise AssertionError("semantic Shadow of Chaos aura must compile")
    return DatasheetAbilityDescriptor(
        ability_id=f"phase17g-semantic-shadow-aura-{allegiance.lower()}",
        name="Daemonic Shadow",
        source_id=f"phase17g:test:semantic-shadow-aura:{allegiance.lower()}",
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description="semantic Shadow of Chaos aura",
        rule_ir_payload=cast(CatalogJsonObject, compiled.rule_ir.to_payload()),
        timing_tags=("passive_query",),
        parameter_tokens=(allegiance.lower(), "shadow_of_chaos"),
    )


def _semantic_unit_shadow_aura_ability(*, allegiance: str) -> DatasheetAbilityDescriptor:
    ability = _semantic_shadow_aura_ability(allegiance=allegiance)
    rule_ir = army_rule._semantic_rule_ir_for_ability(  # pyright: ignore[reportPrivateUsage]
        ability
    )
    clause = rule_ir.clauses[0]
    conditions = tuple(
        replace(
            condition,
            parameters=tuple(
                replace(parameter, value="unit") if parameter.key == "object_kind" else parameter
                for parameter in condition.parameters
            ),
        )
        for condition in clause.conditions
    )
    unit_anchor_rule = replace(rule_ir, clauses=(replace(clause, conditions=conditions),))
    return replace(
        ability,
        ability_id=f"{ability.ability_id}-unit-anchor",
        source_id=f"{ability.source_id}:unit-anchor",
        rule_ir_payload=cast(CatalogJsonObject, unit_anchor_rule.to_payload()),
    )


def _battle_shock_outcome_context(
    *,
    state: GameState,
    decisions: DecisionController,
    player_id: str,
    unit_instance_id: str,
    passed: bool,
    result_id: str,
    phase_start_battle_shocked_unit_ids: tuple[str, ...] = (),
) -> BattleShockOutcomeContext:
    unit = unit_by_id(state, unit_instance_id)
    current_model_count = sum(model.is_alive for model in unit.own_models)
    request = BattleShockTestRequest.for_unit(
        request_id=f"{result_id}:request",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=player_id,
        unit_instance_id=unit_instance_id,
        reason=BattleShockTestReason.FORCED_BY_ARMY_RULE,
        leadership_target=7,
        below_half_strength_context=BelowHalfStrengthContext(
            player_id=player_id,
            unit_instance_id=unit_instance_id,
            starting_model_count=len(unit.own_models),
            current_model_count=current_model_count,
            single_model_starting_wounds=None,
            single_model_wounds_remaining=None,
        ),
    )
    dice_manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    roll_state = dice_manager.roll_fixed(request.spec, (6, 6) if passed else (1, 1))
    result = BattleShockResult.from_roll_state(
        result_id=result_id,
        request=request,
        roll_state=roll_state,
    )
    assert result.passed is passed
    active_player_id = state.active_player_id
    if active_player_id is None:
        raise AssertionError("Battle-shock outcome fixture requires an active player.")
    return BattleShockOutcomeContext(
        state=state,
        decisions=decisions,
        dice_manager=dice_manager,
        result=result,
        active_player_id=active_player_id,
        phase=BattlePhase.COMMAND,
        auto_passed=passed,
        phase_start_battle_shocked_unit_ids=phase_start_battle_shocked_unit_ids,
    )


def _corrupted_realspace_sticky_state(
    *,
    state: GameState,
    state_id: str,
    player_id: str,
    objective_id: str,
    target_unit_instance_id: str,
) -> StickyObjectiveControlState:
    active_player_id = state.active_player_id
    if active_player_id is None:
        raise AssertionError("Corrupted Realspace fixture requires an active player.")
    return StickyObjectiveControlState(
        state_id=state_id,
        game_id=state.game_id,
        player_id=player_id,
        objective_id=objective_id,
        source_rule_id="phase17g:test:corrupted-realspace",
        source_event_id=f"{state_id}:event",
        battle_round=state.battle_round,
        phase=(state.current_battle_phase or BattlePhase.COMMAND).value,
        active_player_id=active_player_id,
        originating_unit_instance_id=target_unit_instance_id,
        destroyed_unit_instance_id=target_unit_instance_id,
        replay_payload={
            "effect_kind": army_rule.CORRUPTED_REALSPACE_STICKY_EFFECT_KIND,
            "shadow_of_chaos_aura_inches": army_rule.CORRUPTED_REALSPACE_SHADOW_AURA_INCHES,
            "target_unit_instance_id": target_unit_instance_id,
        },
    )


def _record_battle_shock_auto_pass(
    state: GameState,
    *,
    decisions: DecisionController,
    unit_instance_id: str,
) -> None:
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=unit_instance_id,
    )
    player_id = rules_unit.owner_player_id
    if state.active_player_id != player_id:
        raise AssertionError("Insane Bravery fixture requires the target player's turn.")
    catalog_record = next(
        record
        for record in eleventh_edition_stratagem_index().all_records()
        if record.definition.stratagem_id == "insane-bravery"
    )
    gain = state.gain_command_points(
        player_id=player_id,
        amount=1,
        source_id=f"phase17g-insane-bravery-fixture:{player_id}",
        source_kind=CommandPointSourceKind.OTHER,
    )
    if gain.status is not CommandPointGainStatus.APPLIED:
        raise AssertionError("Insane Bravery fixture CP grant must apply.")
    decisions.event_log.append("command_points_gained", gain.to_payload())
    proposal_request = StratagemTargetProposal.for_request(
        context=StratagemEligibilityContext.from_state(
            state=state,
            player_id=player_id,
            trigger_kind=TimingTriggerKind.START_PHASE,
            timing_window_id=(
                f"insane-bravery-battle-shock-round-{state.battle_round}-player-{player_id}"
            ),
        ),
        catalog_record=catalog_record,
    )
    waiting = request_stratagem_target_proposal(
        state=state,
        decisions=decisions,
        proposal_request=proposal_request,
    )
    request = waiting.decision_request
    if waiting.status_kind is not LifecycleStatusKind.WAITING_FOR_DECISION or request is None:
        raise AssertionError("Insane Bravery fixture must request a target proposal.")
    submitted = proposal_request.with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id=player_id,
            target_unit_instance_id=unit_instance_id,
        )
    )
    result = DecisionResult(
        result_id=f"{request.request_id}:phase17g-insane-bravery-result",
        request_id=request.request_id,
        decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
        actor_id=request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=validate_json_value({"proposal": submitted.to_payload()}),
    )
    invalid = invalid_stratagem_target_proposal_status(
        state=state,
        request=request,
        result=result,
        ruleset_descriptor=state.ruleset_descriptor_for_runtime_policy(),
        army_catalog=ArmyCatalog.phase9a_canonical_content_pack(),
        decisions=decisions,
    )
    if invalid is not None:
        raise AssertionError(f"Insane Bravery fixture proposal was invalid: {invalid}.")
    decisions.submit_result(result)
    use_record = apply_stratagem_target_proposal(
        state=state,
        result=result,
        decisions=decisions,
        ruleset_descriptor=state.ruleset_descriptor_for_runtime_policy(),
        army_catalog=ArmyCatalog.phase9a_canonical_content_pack(),
    )
    if (
        use_record.command_point_cost != 1
        or use_record.command_point_transaction_id is None
        or state.command_point_total(player_id) != 0
    ):
        raise AssertionError("Insane Bravery fixture must spend exactly 1CP.")


def _placed_model_ids(state: GameState, unit_instance_id: str) -> tuple[str, ...]:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    return tuple(
        placement.model_instance_id
        for placement in state.battlefield_state.unit_placement_by_id(
            unit_instance_id
        ).model_placements
    )


def _place_units_near_center(
    state: GameState,
    *,
    source_unit_id: str,
    target_unit_id: str,
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    marker = center_marker_definition(state)
    source = state.battlefield_state.unit_placement_by_id(source_unit_id)
    target = state.battlefield_state.unit_placement_by_id(target_unit_id)
    battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(source, marker, offsets=((0.0, 0.0),))
    )
    battlefield_state = battlefield_state.with_unit_placement(
        with_model_offsets(target, marker, offsets=((1.0, 0.0),))
    )
    state.battlefield_state = battlefield_state


def _place_unit_near_center(
    state: GameState,
    *,
    unit_instance_id: str,
    offset: tuple[float, float],
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    marker = center_marker_definition(state)
    unit = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(unit, marker, offsets=(offset,))
    )


def _replace_unit_leadership(
    state: GameState,
    *,
    unit_instance_id: str,
    leadership: int,
) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            if unit.unit_instance_id != unit_instance_id:
                updated_units.append(unit)
                continue
            updated_units.append(
                replace(
                    unit,
                    own_models=tuple(
                        _replace_model_leadership(model, leadership=leadership)
                        for model in unit.own_models
                    ),
                )
            )
        updated_armies.append(replace(army, units=tuple(updated_units)))
    state.army_definitions = updated_armies


def _replace_model_leadership(
    model: ModelInstance,
    *,
    leadership: int,
) -> ModelInstance:
    return replace(
        model,
        characteristics=tuple(
            CharacteristicValue.from_raw(Characteristic.LEADERSHIP, leadership)
            if value.characteristic is Characteristic.LEADERSHIP
            else value
            for value in model.characteristics
        ),
    )


def _replace_model_wounds(
    state: GameState,
    *,
    model_instance_id: str,
    wounds_remaining: int,
) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            updated_units.append(
                replace(
                    unit,
                    own_models=tuple(
                        replace(model, wounds_remaining=wounds_remaining)
                        if model.model_instance_id == model_instance_id
                        else model
                        for model in unit.own_models
                    ),
                )
            )
        updated_armies.append(replace(army, units=tuple(updated_units)))
    state.army_definitions = updated_armies


def _model_by_id(state: GameState, model_instance_id: str) -> ModelInstance:
    for army in state.army_definitions:
        for unit in army.units:
            for model in unit.own_models:
                if model.model_instance_id == model_instance_id:
                    return model
    raise AssertionError(f"missing model {model_instance_id}")


def _event_payload(decisions: DecisionController, event_type: str) -> dict[str, JsonValue]:
    for event in decisions.event_log.records:
        if event.event_type == event_type:
            return cast(dict[str, JsonValue], event.payload)
    raise AssertionError(f"missing event {event_type}")


def _event_payloads(
    decisions: DecisionController,
    event_type: str,
) -> tuple[dict[str, JsonValue], ...]:
    return tuple(
        cast(dict[str, JsonValue], event.payload)
        for event in decisions.event_log.records
        if event.event_type == event_type
    )


def _required_decision_request(status: LifecycleStatus) -> DecisionRequest:
    request = status.decision_request
    if request is None:
        raise AssertionError("expected a pending DecisionRequest")
    return request


def _healing_option_model_ids(request: DecisionRequest) -> tuple[str, ...]:
    return tuple(
        sorted(
            model_id
            for option in request.options
            for model_id in (cast(dict[str, JsonValue], option.payload)["model_instance_id"],)
            if isinstance(model_id, str)
        )
    )


def _healing_finish_option_id(request: DecisionRequest) -> str:
    return next(
        option.option_id
        for option in request.options
        if cast(dict[str, JsonValue], option.payload)["selection_kind"] == "finish"
    )


def _healing_option_id_for_model(
    request: DecisionRequest,
    model_instance_id: str,
) -> str:
    for option in request.options:
        payload = cast(dict[str, JsonValue], option.payload)
        if payload["model_instance_id"] == model_instance_id:
            return option.option_id
    raise AssertionError(f"missing healing option for {model_instance_id}")


def _healing_revival_payload(
    *,
    request: DecisionRequest,
    placement: ModelPlacement,
    proposal_request_id: str | None = None,
) -> JsonValue:
    return validate_json_value(
        {
            "proposal_request_id": (
                request.request_id if proposal_request_id is None else proposal_request_id
            ),
            "proposal_kind": "healing_revival_placement",
            "unit_instance_id": placement.unit_instance_id,
            "placement_kind": BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD.value,
            "attempted_placement": UnitPlacement(
                army_id=placement.army_id,
                player_id=placement.player_id,
                unit_instance_id=placement.unit_instance_id,
                model_placements=(placement,),
            ).to_payload(),
        }
    )


def _july_manifestation_revival_session() -> tuple[
    LocalGameSession,
    GameState,
    tuple[str, ...],
    dict[str, ModelPlacement],
    DecisionRequest,
]:
    config = replace(
        _chaos_daemons_lifecycle_config(battleline=True),
        game_id="phase17g-config-canonical-seed-2",
    )
    session = LocalGameSession()
    session.start(config)
    state = _record_lifecycle_battle_state(lifecycle=session.lifecycle, config=config)
    unit_id = "army-alpha:manifestation-daemon"
    if state.battlefield_state is None:
        raise AssertionError("Manifestation test requires battlefield state.")
    starting_placements = {
        placement.model_instance_id: placement
        for placement in state.battlefield_state.unit_placement_by_id(unit_id).model_placements
    }
    destroyed_model_ids = tuple(starting_placements)[:3]
    survivor_anchor = starting_placements[tuple(starting_placements)[3]]
    anchor_position = survivor_anchor.pose.position
    return_placements = {
        destroyed_model_ids[2]: starting_placements[destroyed_model_ids[2]],
        destroyed_model_ids[1]: starting_placements[destroyed_model_ids[1]].with_pose(
            Pose.at(
                x=anchor_position.x,
                y=anchor_position.y + 2.0,
                z=anchor_position.z,
            )
        ),
        destroyed_model_ids[0]: starting_placements[destroyed_model_ids[0]].with_pose(
            Pose.at(
                x=anchor_position.x,
                y=anchor_position.y - 2.0,
                z=anchor_position.z,
            )
        ),
    }
    remove_first_models(state, unit_instance_id=unit_id, count=3)
    for model_instance_id in destroyed_model_ids:
        _replace_model_wounds(
            state,
            model_instance_id=model_instance_id,
            wounds_remaining=0,
        )
    _record_battle_shock_auto_pass(
        state,
        decisions=session.lifecycle.decision_controller,
        unit_instance_id=unit_id,
    )
    candidate = july_2026_candidate.runtime_contribution()
    handler = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
        battle_shock_hooks=BattleShockHookRegistry.from_bindings(
            candidate.battle_shock_hook_bindings
        ),
    )
    completed = handler.begin_phase(
        state=state,
        decisions=session.lifecycle.decision_controller,
    )
    selection_request = _required_decision_request(completed)
    if candidate.battle_shock_hook_bindings[0].source_id != army_rule.JULY_SOURCE_RULE_ID:
        raise AssertionError("Manifestation test did not load the July source.")
    return (
        session,
        state,
        destroyed_model_ids,
        return_placements,
        selection_request,
    )


def _kairos_realm_lifecycle(
    *,
    primary_inside: bool,
    companion_inside: bool,
    attached_primary: bool = False,
) -> tuple[GameLifecycle, str, str]:
    config = _kairos_lifecycle_config(attached_primary=attached_primary)
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    state = _record_lifecycle_battle_state(lifecycle=lifecycle, config=config)
    state.active_player_id = "player-a"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    record_completed_command_occurrences_for_fixture(
        state,
        decisions=lifecycle.decision_controller,
        config=config,
    )
    state.gain_command_points(
        player_id="player-b",
        amount=3,
        source_id="phase17g-kairos-test-command-points",
        source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
        cap_exempt=True,
    )
    target_army = state.army_definition_for_player("player-b")
    if target_army is None:
        raise AssertionError("Kairos test requires the target army.")
    companion_id = "army-beta:target-companion"
    if attached_primary:
        formation = target_army.attached_units[0]
        primary_id = formation.attached_unit_instance_id
        primary_component_id = formation.bodyguard_unit_instance_id
        primary_leader_id = formation.leader_unit_instance_ids[0]
    else:
        primary_id = "army-beta:target-primary"
        primary_component_id = primary_id
        primary_leader_id = None
    battlefield = state.battlefield_state
    if battlefield is None:
        raise AssertionError("Kairos test requires battlefield state.")
    primary_position = (
        battlefield.unit_placement_by_id(primary_component_id).model_placements[0].pose.position
    )
    if primary_leader_id is not None:
        _relocate_unit(
            state=state,
            unit_instance_id=primary_leader_id,
            x=primary_position.x,
            y=primary_position.y + 2.0,
        )
    companion_y = (
        primary_position.y + 20.0
        if primary_position.y <= battlefield.battlefield_depth_inches / 2.0
        else primary_position.y - 20.0
    )
    _relocate_unit(
        state=state,
        unit_instance_id=companion_id,
        x=primary_position.x,
        y=companion_y,
    )
    updated_battlefield = state.battlefield_state
    if updated_battlefield is None:
        raise AssertionError("Kairos test lost battlefield state.")
    companion_position = (
        updated_battlefield.unit_placement_by_id(companion_id).model_placements[0].pose.position
    )
    kairos_id = "army-alpha:kairos"
    if primary_inside:
        source_x, source_y = _nearby_battlefield_point(
            battlefield=updated_battlefield,
            x=primary_position.x,
            y=primary_position.y,
        )
    elif companion_inside:
        source_x, source_y = _nearby_battlefield_point(
            battlefield=updated_battlefield,
            x=companion_position.x,
            y=companion_position.y,
        )
    else:
        source_x, source_y = _farthest_battlefield_point(
            battlefield=updated_battlefield,
            points=(
                (primary_position.x, primary_position.y),
                (companion_position.x, companion_position.y),
            ),
        )
    _relocate_unit(
        state=state,
        unit_instance_id=kairos_id,
        x=source_x,
        y=source_y,
    )
    _runtime_content_bundle(lifecycle)
    return lifecycle, primary_id, companion_id


def _submit_realm_of_chaos_pair(
    *,
    lifecycle: GameLifecycle,
    primary_unit_id: str,
    companion_unit_id: str,
    result_id: str,
) -> LifecycleStatus:
    state = lifecycle.state
    if state is None:
        raise AssertionError("Kairos test lifecycle requires state.")
    bundle = _runtime_content_bundle(lifecycle)
    context = StratagemEligibilityContext.from_state(
        state=state,
        player_id="player-b",
        trigger_kind=TimingTriggerKind.END_TURN,
    )
    realm_pair_record = next(
        record
        for record in bundle.stratagem_indexes_by_player_id["player-b"].all_records()
        if record.definition.stratagem_id == daemonic_incursion_ir.THE_REALM_OF_CHAOS_STRATAGEM_ID
        and isinstance(record.definition.effect_payload, dict)
        and record.definition.effect_payload.get("effect_selection_kind")
        == stratagems_generic_metadata.SELECTED_FRIENDLY_COMPANION_UNIT_EFFECT_SELECTION_KIND
    )
    binding_unit_id = primary_unit_id
    if primary_unit_id.startswith("attached-unit:"):
        target_army = state.army_definition_for_player("player-b")
        if target_army is None:
            raise AssertionError("Kairos attached test requires target army.")
        formation = next(
            formation
            for formation in target_army.attached_units
            if formation.attached_unit_instance_id == primary_unit_id
        )
        binding_unit_id = formation.bodyguard_unit_instance_id
    target_binding = StratagemTargetBinding(
        target_kind=StratagemTargetKind.FRIENDLY_UNIT,
        target_player_id="player-b",
        target_unit_instance_id=binding_unit_id,
    )
    companion_selection = stratagems_generic_metadata.companion_unit_effect_selection(
        companion_unit_id
    )
    request = create_stratagem_use_decision_request(
        state=state,
        context=context,
        options=(
            stratagems_selection._stratagem_decision_option(
                record=realm_pair_record,
                context=context,
                target_binding=target_binding,
                effect_selection=companion_selection,
            ),
        ),
    )
    lifecycle.decision_controller.request_decision(request)
    selected_option = next(
        option
        for option in request.options
        if _stratagem_option_matches_realm_pair(
            option_payload=option.payload,
            primary_unit_id=binding_unit_id,
            companion_selection=companion_selection,
        )
    )
    return lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=result_id,
            request=request,
            selected_option_id=selected_option.option_id,
        )
    )


def _stratagem_option_matches_realm_pair(
    *,
    option_payload: JsonValue,
    primary_unit_id: str,
    companion_selection: JsonValue,
) -> bool:
    if not isinstance(option_payload, dict):
        return False
    record_payload = option_payload.get("catalog_record")
    binding_payload = option_payload.get("target_binding")
    if not isinstance(record_payload, dict) or not isinstance(binding_payload, dict):
        return False
    definition_payload = record_payload.get("definition")
    if not isinstance(definition_payload, dict):
        return False
    return (
        definition_payload.get("stratagem_id")
        == daemonic_incursion_ir.THE_REALM_OF_CHAOS_STRATAGEM_ID
        and binding_payload.get("target_unit_instance_id") == primary_unit_id
        and option_payload.get("effect_selection") == companion_selection
    )


def _kairos_lifecycle_config(*, attached_primary: bool) -> GameConfig:
    catalog = _kairos_lifecycle_catalog()
    target_selections = (
        (
            UnitMusterSelection(
                unit_selection_id="target-bodyguard",
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
            UnitMusterSelection(
                unit_selection_id="target-leader",
                datasheet_id="core-character-leader",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-character-leader",
                        model_count=1,
                    ),
                ),
            ),
            UnitMusterSelection(
                unit_selection_id="target-companion",
                datasheet_id="phase17g-kairos-target-daemon",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
        )
        if attached_primary
        else (
            UnitMusterSelection(
                unit_selection_id="target-primary",
                datasheet_id="phase17g-kairos-target-daemon",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
            UnitMusterSelection(
                unit_selection_id="target-companion",
                datasheet_id="phase17g-kairos-target-daemon",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
        )
    )
    detachment_id = daemonic_incursion_rule.DAEMONIC_INCURSION_DETACHMENT_ID
    return GameConfig(
        game_id=(
            "phase17g-kairos-attached-lifecycle"
            if attached_primary
            else "phase17g-kairos-pair-lifecycle"
        ),
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
            descriptor_version="core-v2-phase17g-kairos-review",
        ),
        army_catalog=catalog,
        army_muster_requests=(
            ArmyMusterRequest(
                army_id="army-alpha",
                player_id="player-a",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id=army_rule.CHAOS_DAEMONS_FACTION_ID,
                    detachment_ids=(detachment_id,),
                ),
                force_disposition_id="take-and-hold",
                unit_selections=(
                    UnitMusterSelection(
                        unit_selection_id="kairos",
                        datasheet_id=chaos_daemons_july_updates.KAIROS_DATASHEET_ID,
                        model_profile_selections=(
                            ModelProfileSelection(
                                model_profile_id="core-intercessor-like",
                                model_count=1,
                            ),
                        ),
                    ),
                ),
            ),
            ArmyMusterRequest(
                army_id="army-beta",
                player_id="player-b",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id=army_rule.CHAOS_DAEMONS_FACTION_ID,
                    detachment_ids=(detachment_id,),
                ),
                force_disposition_id="purge-the-foe",
                unit_selections=target_selections,
                attachment_declarations=(
                    (
                        AttachmentDeclaration(
                            source_unit_selection_id="target-leader",
                            bodyguard_unit_selection_id="target-bodyguard",
                        ),
                    )
                    if attached_primary
                    else ()
                ),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2026_27_mission_pack(),
            mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
            terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
            attacker_player_id="player-a",
            attacker_force_disposition_id="take-and-hold",
            defender_player_id="player-b",
            defender_force_disposition_id="purge-the-foe",
        ),
    )


def _kairos_lifecycle_catalog() -> ArmyCatalog:
    base = ArmyCatalog.phase9a_canonical_content_pack()
    base_infantry = base.datasheet_by_id("core-intercessor-like-infantry")
    kairos = replace(
        base_infantry,
        datasheet_id=chaos_daemons_july_updates.KAIROS_DATASHEET_ID,
        name="Kairos Fateweaver",
        keywords=DatasheetKeywordSet(
            keywords=("Character", "Monster", "Psyker", "Fly"),
            faction_keywords=("Legiones Daemonica",),
        ),
        composition=tuple(
            replace(composition, min_models=1, max_models=1)
            for composition in base_infantry.composition
        ),
        max_unit_models=1,
        attachment_eligibilities=(),
        source_ids=("phase17g:test:kairos-fateweaver",),
    )
    target_daemon = replace(
        base_infantry,
        datasheet_id="phase17g-kairos-target-daemon",
        name="Kairos Range Target",
        keywords=DatasheetKeywordSet(
            keywords=("Infantry",),
            faction_keywords=("Legiones Daemonica",),
        ),
        attachment_eligibilities=(),
        source_ids=("phase17g:test:kairos-range-target",),
    )
    catalog_datasheets = tuple(
        (
            replace(
                datasheet,
                keywords=replace(
                    datasheet.keywords,
                    faction_keywords=("LEGIONES DAEMONICA",),
                ),
            )
            if datasheet.datasheet_id in {"core-character-leader", "core-intercessor-like-infantry"}
            else datasheet
        )
        for datasheet in base.datasheets
    )
    detachment_id = daemonic_incursion_rule.DAEMONIC_INCURSION_DETACHMENT_ID
    return replace(
        base,
        datasheets=(*catalog_datasheets, kairos, target_daemon),
        factions=(
            *base.factions,
            FactionDefinition(
                faction_id=army_rule.CHAOS_DAEMONS_FACTION_ID,
                name="Chaos Daemons",
                faction_keywords=("Legiones Daemonica",),
                source_ids=("phase17g:test:chaos-daemons",),
            ),
        ),
        detachments=(
            *base.detachments,
            DetachmentDefinition(
                detachment_id=detachment_id,
                name="Daemonic Incursion",
                faction_id=army_rule.CHAOS_DAEMONS_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(
                    chaos_daemons_july_updates.KAIROS_DATASHEET_ID,
                    "phase17g-kairos-target-daemon",
                    "core-character-leader",
                    "core-intercessor-like-infantry",
                ),
                force_disposition_ids=("phase17g-force", "purge-the-foe", "take-and-hold"),
                source_ids=("phase17g:test:daemonic-incursion",),
            ),
        ),
    )


def _relocate_unit(
    *,
    state: GameState,
    unit_instance_id: str,
    x: float,
    y: float,
) -> None:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise AssertionError("Unit relocation requires battlefield state.")
    unit_placement = battlefield.unit_placement_by_id(unit_instance_id)
    anchor = unit_placement.model_placements[0].pose.position
    placements = tuple(
        placement.with_pose(
            Pose.at(
                x=x + placement.pose.position.x - anchor.x,
                y=y + placement.pose.position.y - anchor.y,
                z=placement.pose.position.z,
            )
        )
        for placement in unit_placement.model_placements
    )
    state.battlefield_state = battlefield.with_unit_placement(
        replace(unit_placement, model_placements=placements)
    )


def _nearby_battlefield_point(
    *,
    battlefield: BattlefieldRuntimeState,
    x: float,
    y: float,
) -> tuple[float, float]:
    depth = battlefield.battlefield_depth_inches
    return (x, y + 6.0) if y + 7.0 < depth else (x, y - 6.0)


def _farthest_battlefield_point(
    *,
    battlefield: BattlefieldRuntimeState,
    points: tuple[tuple[float, float], ...],
) -> tuple[float, float]:
    width = battlefield.battlefield_width_inches
    depth = battlefield.battlefield_depth_inches
    candidates = ((2.0, 2.0), (2.0, depth - 2.0), (width - 2.0, 2.0), (width - 2.0, depth - 2.0))
    return max(
        candidates,
        key=lambda candidate: min(
            (candidate[0] - point[0]) ** 2 + (candidate[1] - point[1]) ** 2 for point in points
        ),
    )
