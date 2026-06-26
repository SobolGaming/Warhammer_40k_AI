from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.unit.test_phase11c_command_phase import (
    _battle_state,  # pyright: ignore[reportPrivateUsage]
    _battle_state_with_center_objective_positions,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import DatasheetDefinition, DatasheetKeywordSet
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponProfile,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest
from warhammer40k_core.engine.command_phase_start_hooks import (
    CommandPhaseStartContext,
    CommandPhaseStartHookRegistry,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.runtime import build_runtime_content_bundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.leagues_of_votann import (
    army_rule,
)
from warhammer40k_core.engine.faction_resources import FactionResourceStatus
from warhammer40k_core.engine.game_state import GameConfig, GameState, GameStatePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.phases.command import CommandPhaseHandler
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierContext,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.stratagems import StratagemCatalogIndex
from warhammer40k_core.engine.unit_factory import UnitInstance

VOTANN_DATASHEET_ID = "phase17g-leagues-of-votann-hearthkyn"
VOTANN_DETACHMENT_ID = "hearthband"
VOTANN_UNIT_ID = "army-alpha:intercessor-unit-1"
ENEMY_UNIT_ID = "army-beta:intercessor-unit-3"


def test_runtime_contribution_exposes_prioritised_efficiency_hooks() -> None:
    contribution = army_rule.runtime_contribution()

    assert contribution.contribution_id == army_rule.CONTRIBUTION_ID
    assert not contribution.contribution_id.endswith(":scaffold")
    assert [binding.hook_id for binding in contribution.command_phase_start_hook_bindings] == [
        army_rule.COMMAND_PHASE_START_HOOK_ID
    ]
    assert [binding.modifier_id for binding in contribution.hit_roll_modifier_bindings] == [
        army_rule.PRIORITISED_EFFICIENCY_HIT_MODIFIER_ID
    ]
    assert [binding.modifier_id for binding in contribution.wound_roll_modifier_bindings] == [
        army_rule.PRIORITISED_EFFICIENCY_WOUND_MODIFIER_ID
    ]


def test_runtime_bundle_loads_leagues_of_votann_manifest_contribution() -> None:
    bundle = build_runtime_content_bundle(_votann_runtime_config())
    summary = bundle.to_summary_payload()

    assert army_rule.COMMAND_PHASE_START_HOOK_ID in summary["command_phase_start_hook_ids"]
    assert army_rule.PRIORITISED_EFFICIENCY_HIT_MODIFIER_ID in summary["hit_roll_modifier_ids"]
    assert army_rule.PRIORITISED_EFFICIENCY_WOUND_MODIFIER_ID in summary["wound_roll_modifier_ids"]


def test_command_start_gains_yield_points_from_objective_control() -> None:
    state = _votann_center_objective_state(
        player_a_offsets=((0.0, 0.0),),
        player_b_offsets=(),
    )
    state.battle_round = 2
    decisions = DecisionController()
    registry = CommandPhaseStartHookRegistry.from_bindings(
        army_rule.runtime_contribution().command_phase_start_hook_bindings
    )

    summary = army_rule.prioritised_efficiency_objective_summary(
        state,
        player_id="player-a",
    )
    assert summary.yield_points == 2

    registry.resolve(
        CommandPhaseStartContext(
            state=state,
            decisions=decisions,
            active_player_id="player-a",
        )
    )

    assert army_rule.yield_points_available(state, player_id="player-a") == 2
    assert (
        army_rule.prioritised_efficiency_mode_for_player(state, player_id="player-a")
        is army_rule.PrioritisedEfficiencyMode.HOSTILE_ACQUISITION
    )
    payload = _last_event_payload(
        decisions,
        "leagues_of_votann_prioritised_efficiency_resolved",
    )
    assert payload["yield_points_gained"] == 2
    assert payload["yield_points_total"] == 2
    assert payload["mode_before"] == "hostile_acquisition"
    assert payload["mode_after"] == "hostile_acquisition"
    assert payload["faction_resource_result"] is not None
    restored = cast(GameStatePayload, json.loads(json.dumps(state.to_payload(), sort_keys=True)))
    assert restored == state.to_payload()


def test_command_start_records_zero_yield_without_resource_gain() -> None:
    state = _votann_center_objective_state(
        player_a_offsets=(),
        player_b_offsets=(),
    )
    state.battle_round = 2
    decisions = DecisionController()
    registry = CommandPhaseStartHookRegistry.from_bindings(
        army_rule.runtime_contribution().command_phase_start_hook_bindings
    )

    registry.resolve(
        CommandPhaseStartContext(
            state=state,
            decisions=decisions,
            active_player_id="player-a",
        )
    )

    assert army_rule.yield_points_available(state, player_id="player-a") == 0
    payload = _last_event_payload(
        decisions,
        "leagues_of_votann_prioritised_efficiency_resolved",
    )
    assert payload["yield_points_gained"] == 0
    assert payload["yield_points_total"] == 0
    assert payload["faction_resource_result"] is None


def test_command_phase_handler_with_bundle_hook_transitions_to_fortify_takeover() -> None:
    state = _votann_center_objective_state(
        player_a_offsets=((0.0, 0.0),),
        player_b_offsets=(),
    )
    state.battle_round = 2
    gain = state.gain_faction_resource(
        player_id="player-a",
        resource_kind=army_rule.YIELD_POINT_RESOURCE_KIND,
        amount=6,
        source_id="phase17g:leagues-of-votann:test-starting-yield-points",
    )
    assert gain.status is FactionResourceStatus.APPLIED
    assert (
        army_rule.prioritised_efficiency_mode_for_player(state, player_id="player-a")
        is army_rule.PrioritisedEfficiencyMode.HOSTILE_ACQUISITION
    )
    bundle = build_runtime_content_bundle(_votann_runtime_config())
    decisions = DecisionController()
    handler = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
        command_phase_start_hooks=bundle.command_phase_start_hook_registry,
    )

    completed = handler.begin_phase(state=state, decisions=decisions)

    assert completed.status_kind is LifecycleStatusKind.ADVANCED
    assert army_rule.yield_points_available(state, player_id="player-a") == 8
    assert (
        army_rule.prioritised_efficiency_mode_for_player(state, player_id="player-a")
        is army_rule.PrioritisedEfficiencyMode.FORTIFY_TAKEOVER
    )
    payload = _last_event_payload(
        decisions,
        "leagues_of_votann_prioritised_efficiency_resolved",
    )
    assert payload["yield_points_gained"] == 2
    assert payload["yield_points_total"] == 8
    assert payload["mode_before"] == "hostile_acquisition"
    assert payload["mode_after"] == "fortify_takeover"
    event_types = tuple(record.event_type for record in decisions.event_log.records)
    assert event_types.index("command_points_gained") < event_types.index(
        "leagues_of_votann_prioritised_efficiency_resolved"
    )
    assert event_types.index("leagues_of_votann_prioritised_efficiency_resolved") < (
        event_types.index("command_step_started")
    )


def test_non_votann_detachment_with_votann_keyword_unit_does_not_gain_yield_points() -> None:
    state = _battle_state_with_center_objective_positions(
        player_a_offsets=((0.0, 0.0),),
        player_b_offsets=(),
    )
    state.battle_round = 2
    _mark_player_units_as_votann(state, player_id="player-a")
    decisions = DecisionController()
    registry = CommandPhaseStartHookRegistry.from_bindings(
        army_rule.runtime_contribution().command_phase_start_hook_bindings
    )

    registry.resolve(
        CommandPhaseStartContext(
            state=state,
            decisions=decisions,
            active_player_id="player-a",
        )
    )

    assert army_rule.yield_points_available(state, player_id="player-a") == 0
    assert all(
        record.event_type != "leagues_of_votann_prioritised_efficiency_resolved"
        for record in decisions.event_log.records
    )


def test_prioritised_efficiency_mode_requires_votann_detachment_selection() -> None:
    state = _battle_state_with_center_objective_positions(
        player_a_offsets=((0.0, 0.0),),
        player_b_offsets=(),
    )
    _mark_player_units_as_votann(state, player_id="player-a")
    gain = state.gain_faction_resource(
        player_id="player-a",
        resource_kind=army_rule.YIELD_POINT_RESOURCE_KIND,
        amount=7,
        source_id="phase17g:leagues-of-votann:test-non-owner-yield-points",
    )
    assert gain.status is FactionResourceStatus.APPLIED

    with pytest.raises(GameLifecycleError, match="requires a Leagues of Votann detachment"):
        army_rule.prioritised_efficiency_mode_for_player(state, player_id="player-a")


def test_prioritised_efficiency_requires_typed_runtime_contexts() -> None:
    with pytest.raises(GameLifecycleError, match="requires command-phase context"):
        army_rule.resolve_command_phase_start(cast(CommandPhaseStartContext, object()))

    with pytest.raises(GameLifecycleError, match="hit modifier requires context"):
        army_rule.prioritised_efficiency_hit_roll_modifier(cast(HitRollModifierContext, object()))

    with pytest.raises(GameLifecycleError, match="wound modifier requires context"):
        army_rule.prioritised_efficiency_wound_roll_modifier(
            cast(WoundRollModifierContext, object())
        )


def test_yield_points_from_objectives_gates_round_one_and_round_two_scoring() -> None:
    assert (
        _yield_points_from_objectives(
            battle_round=1,
            own_deployment=("home",),
            outside=("outside-1", "outside-2"),
            controlled_count=3,
            opponent_max=0,
        )
        == 1
    )
    assert (
        _yield_points_from_objectives(
            battle_round=2,
            own_deployment=(),
            outside=("outside-1",),
            controlled_count=1,
            opponent_max=1,
        )
        == 1
    )
    assert (
        _yield_points_from_objectives(
            battle_round=2,
            own_deployment=(),
            outside=("outside-1", "outside-2"),
            controlled_count=2,
            opponent_max=2,
        )
        == 2
    )
    assert (
        _yield_points_from_objectives(
            battle_round=2,
            own_deployment=("home",),
            outside=(),
            controlled_count=1,
            opponent_max=0,
        )
        == 2
    )


def test_yield_points_from_objectives_do_not_score_control_more_when_tied_or_behind() -> None:
    assert (
        _yield_points_from_objectives(
            battle_round=2,
            own_deployment=("home",),
            outside=(),
            controlled_count=1,
            opponent_max=1,
        )
        == 1
    )
    assert (
        _yield_points_from_objectives(
            battle_round=2,
            own_deployment=("home",),
            outside=(),
            controlled_count=1,
            opponent_max=2,
        )
        == 1
    )


@pytest.mark.parametrize(
    ("battle_round", "message"),
    [
        (cast(int, "2"), "battle_round must be an int"),
        (0, "requires an active battle round"),
    ],
)
def test_yield_points_from_objectives_reject_invalid_battle_round(
    battle_round: int,
    message: str,
) -> None:
    with pytest.raises(GameLifecycleError, match=message):
        army_rule._yield_points_from_objectives(  # pyright: ignore[reportPrivateUsage]
            battle_round=battle_round,
            own_deployment_controlled_objective_ids=(),
            outside_own_deployment_controlled_objective_ids=(),
            controlled_objective_count=0,
            opponent_max_controlled_objective_count=0,
        )


def test_yield_points_from_objectives_reject_malformed_counts_and_identifier_sets() -> None:
    with pytest.raises(GameLifecycleError, match="must be a tuple"):
        army_rule._yield_points_from_objectives(  # pyright: ignore[reportPrivateUsage]
            battle_round=2,
            own_deployment_controlled_objective_ids=cast(tuple[str, ...], ["home"]),
            outside_own_deployment_controlled_objective_ids=(),
            controlled_objective_count=0,
            opponent_max_controlled_objective_count=0,
        )

    with pytest.raises(GameLifecycleError, match="controlled_objective_count must be an int"):
        army_rule._yield_points_from_objectives(  # pyright: ignore[reportPrivateUsage]
            battle_round=2,
            own_deployment_controlled_objective_ids=(),
            outside_own_deployment_controlled_objective_ids=(),
            controlled_objective_count=cast(int, "1"),
            opponent_max_controlled_objective_count=0,
        )

    with pytest.raises(GameLifecycleError, match="must be non-negative"):
        army_rule._yield_points_from_objectives(  # pyright: ignore[reportPrivateUsage]
            battle_round=2,
            own_deployment_controlled_objective_ids=(),
            outside_own_deployment_controlled_objective_ids=(),
            controlled_objective_count=0,
            opponent_max_controlled_objective_count=-1,
        )


def test_own_deployment_objectives_use_official_layout_home_markers() -> None:
    state = _battle_state()

    assert army_rule._own_deployment_objective_ids(  # pyright: ignore[reportPrivateUsage]
        state,
        player_id="player-a",
    ) == ("take-and-hold-vs-purge-the-foe-layout-3-left-home",)
    assert army_rule._own_deployment_objective_ids(  # pyright: ignore[reportPrivateUsage]
        state,
        player_id="player-b",
    ) == ("take-and-hold-vs-purge-the-foe-layout-3-right-home",)


def test_own_deployment_objective_lookup_requires_mission_setup_and_zone() -> None:
    state = _battle_state()
    state.mission_setup = None
    with pytest.raises(GameLifecycleError, match="requires MissionSetup"):
        army_rule._own_deployment_objective_ids(  # pyright: ignore[reportPrivateUsage]
            state,
            player_id="player-a",
        )

    state = _battle_state()
    with pytest.raises(GameLifecycleError, match="requires the player's deployment zone"):
        army_rule._own_deployment_objective_ids(  # pyright: ignore[reportPrivateUsage]
            state,
            player_id="player-c",
        )


def test_hostile_acquisition_hit_bonus_targets_units_on_objectives() -> None:
    state = _votann_center_objective_state(
        player_a_offsets=(),
        player_b_offsets=((0.0, 0.0),),
    )

    assert (
        army_rule.prioritised_efficiency_hit_roll_modifier(
            _hit_context(
                state=state,
                attacking_unit_id=VOTANN_UNIT_ID,
                target_unit_id=ENEMY_UNIT_ID,
            )
        )
        == 1
    )
    assert (
        army_rule.prioritised_efficiency_hit_roll_modifier(
            _hit_context(
                state=state,
                attacking_unit_id=VOTANN_UNIT_ID,
                target_unit_id=ENEMY_UNIT_ID,
                source_phase=BattlePhase.MOVEMENT,
            )
        )
        == 0
    )

    empty_state = _votann_center_objective_state(
        player_a_offsets=(),
        player_b_offsets=(),
    )
    assert (
        army_rule.prioritised_efficiency_hit_roll_modifier(
            _hit_context(
                state=empty_state,
                attacking_unit_id=VOTANN_UNIT_ID,
                target_unit_id=ENEMY_UNIT_ID,
            )
        )
        == 0
    )


def test_fortify_takeover_hit_bonus_and_wound_penalty() -> None:
    state = _votann_center_objective_state(
        player_a_offsets=((0.0, 0.0),),
        player_b_offsets=(),
    )
    gain = state.gain_faction_resource(
        player_id="player-a",
        resource_kind=army_rule.YIELD_POINT_RESOURCE_KIND,
        amount=7,
        source_id="phase17g:leagues-of-votann:test-yield-points",
    )
    assert gain.status is FactionResourceStatus.APPLIED
    assert (
        army_rule.prioritised_efficiency_mode_for_player(state, player_id="player-a")
        is army_rule.PrioritisedEfficiencyMode.FORTIFY_TAKEOVER
    )

    assert (
        army_rule.prioritised_efficiency_hit_roll_modifier(
            _hit_context(
                state=state,
                attacking_unit_id=VOTANN_UNIT_ID,
                target_unit_id=ENEMY_UNIT_ID,
            )
        )
        == 1
    )
    assert (
        army_rule.prioritised_efficiency_wound_roll_modifier(
            _wound_context(
                state=state,
                attacking_unit_id=ENEMY_UNIT_ID,
                target_unit_id=VOTANN_UNIT_ID,
                strength=5,
                toughness=4,
            )
        )
        == -1
    )
    assert (
        army_rule.prioritised_efficiency_wound_roll_modifier(
            _wound_context(
                state=state,
                attacking_unit_id=ENEMY_UNIT_ID,
                target_unit_id=VOTANN_UNIT_ID,
                strength=4,
                toughness=4,
            )
        )
        == 0
    )

    no_objective_state = _votann_center_objective_state(
        player_a_offsets=(),
        player_b_offsets=(),
    )
    gain = no_objective_state.gain_faction_resource(
        player_id="player-a",
        resource_kind=army_rule.YIELD_POINT_RESOURCE_KIND,
        amount=7,
        source_id="phase17g:leagues-of-votann:test-yield-points-no-objective",
    )
    assert gain.status is FactionResourceStatus.APPLIED
    assert (
        army_rule.prioritised_efficiency_hit_roll_modifier(
            _hit_context(
                state=no_objective_state,
                attacking_unit_id=VOTANN_UNIT_ID,
                target_unit_id=ENEMY_UNIT_ID,
            )
        )
        == 0
    )

    _add_unit_keyword(state, unit_instance_id=VOTANN_UNIT_ID, keyword="Vehicle")
    assert (
        army_rule.prioritised_efficiency_wound_roll_modifier(
            _wound_context(
                state=state,
                attacking_unit_id=ENEMY_UNIT_ID,
                target_unit_id=VOTANN_UNIT_ID,
                strength=5,
                toughness=4,
            )
        )
        == 0
    )


def test_unit_scoped_modifiers_reject_non_owner_and_unknown_units() -> None:
    state = _battle_state_with_center_objective_positions(
        player_a_offsets=((0.0, 0.0),),
        player_b_offsets=((0.0, 0.0),),
    )
    _mark_player_units_as_votann(state, player_id="player-a")

    assert (
        army_rule.prioritised_efficiency_hit_roll_modifier(
            _hit_context(
                state=state,
                attacking_unit_id=VOTANN_UNIT_ID,
                target_unit_id=ENEMY_UNIT_ID,
            )
        )
        == 0
    )
    assert (
        army_rule.prioritised_efficiency_wound_roll_modifier(
            _wound_context(
                state=state,
                attacking_unit_id=ENEMY_UNIT_ID,
                target_unit_id=VOTANN_UNIT_ID,
                strength=5,
                toughness=4,
            )
        )
        == 0
    )

    owned_state = _votann_center_objective_state(
        player_a_offsets=((0.0, 0.0),),
        player_b_offsets=(),
    )
    with pytest.raises(GameLifecycleError, match="attacking unit is unknown"):
        army_rule.prioritised_efficiency_hit_roll_modifier(
            _hit_context(
                state=owned_state,
                attacking_unit_id="unknown-attacker",
                target_unit_id=ENEMY_UNIT_ID,
            )
        )
    with pytest.raises(GameLifecycleError, match="target unit is unknown"):
        army_rule.prioritised_efficiency_wound_roll_modifier(
            _wound_context(
                state=owned_state,
                attacking_unit_id=ENEMY_UNIT_ID,
                target_unit_id="unknown-target",
                strength=5,
                toughness=4,
            )
        )


def test_wound_modifier_requires_fortify_takeover_and_supported_phase() -> None:
    state = _votann_center_objective_state(
        player_a_offsets=((0.0, 0.0),),
        player_b_offsets=(),
    )

    assert (
        army_rule.prioritised_efficiency_wound_roll_modifier(
            _wound_context(
                state=state,
                attacking_unit_id=ENEMY_UNIT_ID,
                target_unit_id=VOTANN_UNIT_ID,
                strength=5,
                toughness=4,
            )
        )
        == 0
    )
    assert (
        army_rule.prioritised_efficiency_wound_roll_modifier(
            _wound_context(
                state=state,
                attacking_unit_id=ENEMY_UNIT_ID,
                target_unit_id=VOTANN_UNIT_ID,
                strength=5,
                toughness=4,
                source_phase=BattlePhase.MOVEMENT,
            )
        )
        == 0
    )


def _votann_center_objective_state(
    *,
    player_a_offsets: tuple[tuple[float, float], ...],
    player_b_offsets: tuple[tuple[float, float], ...],
) -> GameState:
    state = _battle_state_with_center_objective_positions(
        player_a_offsets=player_a_offsets,
        player_b_offsets=player_b_offsets,
    )
    _mark_player_as_votann(state, player_id="player-a")
    return state


def _mark_player_as_votann(state: GameState, *, player_id: str) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != player_id:
            updated_armies.append(army)
            continue
        updated_armies.append(
            replace(
                army,
                detachment_selection=replace(
                    army.detachment_selection,
                    faction_id=army_rule.LEAGUES_OF_VOTANN_FACTION_ID,
                ),
                units=tuple(_with_votann_keyword(unit) for unit in army.units),
            )
        )
    state.army_definitions = updated_armies


def _mark_player_units_as_votann(state: GameState, *, player_id: str) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != player_id:
            updated_armies.append(army)
            continue
        updated_armies.append(
            replace(army, units=tuple(_with_votann_keyword(unit) for unit in army.units))
        )
    state.army_definitions = updated_armies


def _with_votann_keyword(unit: UnitInstance) -> UnitInstance:
    return replace(
        unit,
        faction_keywords=tuple(
            dict.fromkeys((*unit.faction_keywords, army_rule.LEAGUES_OF_VOTANN_FACTION_KEYWORD))
        ),
    )


def _add_unit_keyword(state: GameState, *, unit_instance_id: str, keyword: str) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            if unit.unit_instance_id != unit_instance_id:
                updated_units.append(unit)
                continue
            updated_units.append(
                replace(unit, keywords=tuple(dict.fromkeys((*unit.keywords, keyword))))
            )
        updated_armies.append(replace(army, units=tuple(updated_units)))
    state.army_definitions = updated_armies


def _yield_points_from_objectives(
    *,
    battle_round: int,
    own_deployment: tuple[str, ...],
    outside: tuple[str, ...],
    controlled_count: int,
    opponent_max: int,
) -> int:
    return army_rule._yield_points_from_objectives(  # pyright: ignore[reportPrivateUsage]
        battle_round=battle_round,
        own_deployment_controlled_objective_ids=own_deployment,
        outside_own_deployment_controlled_objective_ids=outside,
        controlled_objective_count=controlled_count,
        opponent_max_controlled_objective_count=opponent_max,
    )


def _hit_context(
    *,
    state: GameState,
    attacking_unit_id: str,
    target_unit_id: str,
    source_phase: BattlePhase = BattlePhase.SHOOTING,
) -> HitRollModifierContext:
    return HitRollModifierContext(
        state=state,
        attacking_unit_instance_id=attacking_unit_id,
        attacker_model_instance_id=f"{attacking_unit_id}:core-intercessor-like:001",
        target_unit_instance_id=target_unit_id,
        weapon_profile=_weapon_profile(),
        source_phase=source_phase,
    )


def _wound_context(
    *,
    state: GameState,
    attacking_unit_id: str,
    target_unit_id: str,
    strength: int,
    toughness: int,
    source_phase: BattlePhase = BattlePhase.SHOOTING,
) -> WoundRollModifierContext:
    return WoundRollModifierContext(
        state=state,
        source_phase=source_phase,
        attacking_unit_instance_id=attacking_unit_id,
        attacker_model_instance_id=f"{attacking_unit_id}:core-intercessor-like:001",
        target_unit_instance_id=target_unit_id,
        weapon_profile=_weapon_profile(),
        strength=strength,
        toughness=toughness,
    )


def _weapon_profile() -> WeaponProfile:
    return WeaponProfile(
        profile_id="phase17g-leagues-of-votann-test-weapon",
        name="Autoch-pattern bolt pistol",
        range_profile=RangeProfile.distance(12),
        attack_profile=AttackProfile.fixed(1),
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 3),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(1),
        source_ids=("phase17g:leagues-of-votann:test-weapon",),
    )


def _votann_runtime_config() -> GameConfig:
    catalog = _votann_runtime_catalog()
    return GameConfig(
        game_id="phase17g-leagues-of-votann-runtime-bundle",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
            descriptor_version="core-v2-phase17g-leagues-of-votann-test",
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
                    faction_id=army_rule.LEAGUES_OF_VOTANN_FACTION_ID,
                    detachment_ids=(VOTANN_DETACHMENT_ID,),
                ),
                unit_selections=(
                    UnitMusterSelection(
                        unit_selection_id="hearthkyn",
                        datasheet_id=VOTANN_DATASHEET_ID,
                        model_profile_selections=(
                            ModelProfileSelection(
                                model_profile_id="core-intercessor-like",
                                model_count=5,
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
                    faction_id="core-marine-force",
                    detachment_ids=("core-combined-arms",),
                ),
                unit_selections=(
                    UnitMusterSelection(
                        unit_selection_id="intercessors",
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
    )


def _votann_runtime_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    return replace(
        base_catalog,
        datasheets=(
            *base_catalog.datasheets,
            _datasheet(
                base_datasheet,
                datasheet_id=VOTANN_DATASHEET_ID,
                name="Hearthkyn Warriors",
                keywords=("Infantry", "Battleline"),
                faction_keywords=(army_rule.LEAGUES_OF_VOTANN_FACTION_KEYWORD,),
            ),
        ),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id=army_rule.LEAGUES_OF_VOTANN_FACTION_ID,
                name="Leagues of Votann",
                faction_keywords=(army_rule.LEAGUES_OF_VOTANN_FACTION_KEYWORD,),
                source_ids=("phase17g:leagues-of-votann:faction",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                detachment_id=VOTANN_DETACHMENT_ID,
                name="Hearthband",
                faction_id=army_rule.LEAGUES_OF_VOTANN_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(VOTANN_DATASHEET_ID,),
                force_disposition_ids=("phase17g-leagues-of-votann-force",),
                source_ids=("phase17g:leagues-of-votann:detachment:hearthband",),
            ),
        ),
    )


def _datasheet(
    base_datasheet: DatasheetDefinition,
    *,
    datasheet_id: str,
    name: str,
    keywords: tuple[str, ...],
    faction_keywords: tuple[str, ...],
) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=datasheet_id,
        name=name,
        keywords=DatasheetKeywordSet(keywords=keywords, faction_keywords=faction_keywords),
        source_ids=(f"phase17g:leagues-of-votann:datasheet:{datasheet_id}",),
    )


def _last_event_payload(decisions: DecisionController, event_type: str) -> dict[str, JsonValue]:
    for record in reversed(decisions.event_log.records):
        if record.event_type != event_type:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            raise TypeError(f"{event_type} payload is not an object.")
        return payload
    raise AssertionError(f"Missing event {event_type}.")
