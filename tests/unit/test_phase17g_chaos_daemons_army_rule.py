from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import cast

from tests.unit.test_phase11c_command_phase import (
    _battle_state,  # pyright: ignore[reportPrivateUsage]
    _battle_state_with_center_objective_positions,  # pyright: ignore[reportPrivateUsage]
    _center_marker_definition,  # pyright: ignore[reportPrivateUsage]
    _complete_setup_through_gate,  # pyright: ignore[reportPrivateUsage]
    _default_unit_selection,  # pyright: ignore[reportPrivateUsage]
    _remove_first_models,  # pyright: ignore[reportPrivateUsage]
    _unit_by_id,  # pyright: ignore[reportPrivateUsage]
    _with_model_offsets,  # pyright: ignore[reportPrivateUsage]
)

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
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    muster_army,
)
from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookRegistry
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import PARAMETERIZED_DECISION_OPTION_ID
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
    army_rule,
)
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.phases.command import CommandPhaseHandler
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    StratagemCatalogIndex,
    stratagem_decline_payload,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14 as datasheet_keyword_lexicon_source,
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
    state = _battle_state_with_center_objective_positions(
        player_a_offsets=((0.0, 0.0), (-1.5, -13.5)),
        player_b_offsets=((8.0, 0.0),),
    )
    _mark_player_as_chaos_daemons(state, player_id="player-a")

    regions = army_rule.shadow_regions_for_player(state=state, player_id="player-a")

    assert army_rule.ShadowRegion.OWN_DEPLOYMENT_ZONE in regions
    assert army_rule.ShadowRegion.NO_MANS_LAND in regions


def test_daemonic_manifestation_modifies_battle_shock_and_heals_one_model() -> None:
    state = _battle_state()
    _mark_player_as_chaos_daemons(
        state,
        player_id="player-a",
        remove_battleline=True,
    )
    unit_id = "army-alpha:intercessor-unit-1"
    _remove_first_models(state, unit_instance_id=unit_id, count=3)
    wounded_model_id = _placed_model_ids(state, unit_id)[0]
    _replace_model_wounds(state, model_instance_id=wounded_model_id, wounds_remaining=1)
    _record_battle_shock_auto_pass(state, unit_instance_id=unit_id)
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
    state = _battle_state(
        player_a_units=(
            _default_unit_selection("intercessor-unit-1"),
            _default_unit_selection("intercessor-unit-2"),
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
    _remove_first_models(state, unit_instance_id=target_unit_id, count=3)
    wounded_model_id = _placed_model_ids(state, target_unit_id)[0]
    _replace_model_wounds(state, model_instance_id=wounded_model_id, wounds_remaining=1)
    _record_battle_shock_auto_pass(state, unit_instance_id=target_unit_id)
    decisions = DecisionController()
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


def test_daemonic_manifestation_caps_non_battleline_healing_before_revival() -> None:
    state = _battle_state()
    state.game_id = "phase17g-overheal-seed-1"
    _mark_player_as_chaos_daemons(
        state,
        player_id="player-a",
        remove_battleline=True,
    )
    unit_id = "army-alpha:intercessor-unit-1"
    starting_model_ids = _placed_model_ids(state, unit_id)
    destroyed_model_ids = starting_model_ids[:3]
    _remove_first_models(state, unit_instance_id=unit_id, count=3)
    for destroyed_model_id in destroyed_model_ids:
        _replace_model_wounds(
            state,
            model_instance_id=destroyed_model_id,
            wounds_remaining=0,
        )
    wounded_model_id = _placed_model_ids(state, unit_id)[0]
    _replace_model_wounds(state, model_instance_id=wounded_model_id, wounds_remaining=1)
    _record_battle_shock_auto_pass(state, unit_instance_id=unit_id)
    decisions = DecisionController()
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


def test_chaos_daemons_army_rule_hook_uses_phase17f_execution_source_id() -> None:
    record = _chaos_daemons_army_rule_execution_record()
    contribution = army_rule.runtime_contribution()
    binding = contribution.battle_shock_hook_bindings[0]

    assert record.execution_id == army_rule.SOURCE_RULE_ID
    assert binding.source_id == record.execution_id


def test_lifecycle_loads_chaos_daemons_battle_shock_hook_from_runtime_manifest() -> None:
    config = _chaos_daemons_lifecycle_config()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    state = _record_lifecycle_battle_state(lifecycle=lifecycle, config=config)
    unit_id = "army-alpha:manifestation-daemon"
    _remove_first_models(state, unit_instance_id=unit_id, count=3)
    wounded_model_id = _placed_model_ids(state, unit_id)[0]
    _replace_model_wounds(state, model_instance_id=wounded_model_id, wounds_remaining=1)
    _record_battle_shock_auto_pass(state, unit_instance_id=unit_id)
    bundle = _runtime_content_bundle(lifecycle)
    summary = bundle.to_summary_payload()

    assert army_rule.HOOK_ID in summary["battle_shock_hook_ids"]
    assert army_rule.SOURCE_RULE_ID in summary["selected_execution_record_ids"]
    assert any(
        path.endswith(".chaos_daemons.manifest") for path in summary["selected_module_paths"]
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
    assert manifestation_payload["source_rule_id"] == army_rule.SOURCE_RULE_ID
    assert _model_by_id(state, wounded_model_id).wounds_remaining == 2


def test_shadow_of_chaos_uses_phase_start_control_snapshot_for_all_tests() -> None:
    state = _battle_state(
        player_a_units=(
            _default_unit_selection("intercessor-unit-1"),
            _default_unit_selection("intercessor-unit-2"),
        )
    )
    _mark_player_as_chaos_daemons(state, player_id="player-a")
    unit_ids = ("army-alpha:intercessor-unit-1", "army-alpha:intercessor-unit-2")
    for unit_id in unit_ids:
        _remove_first_models(state, unit_instance_id=unit_id, count=3)
        _replace_unit_leadership(state, unit_instance_id=unit_id, leadership=99)
    _place_unit_near_center(state, unit_instance_id=unit_ids[0], offset=(0.0, 0.0))
    _place_unit_near_center(state, unit_instance_id=unit_ids[1], offset=(-1.5, -13.5))
    decisions = DecisionController()
    handler = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
        battle_shock_hooks=_chaos_daemons_battle_shock_hooks(),
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
    state = _battle_state()
    _mark_player_as_chaos_daemons(
        state,
        player_id="player-a",
        unit_name="Bloodthirster",
    )
    state.active_player_id = "player-b"
    state.command_step_state = None
    target_unit_id = "army-beta:intercessor-unit-3"
    _remove_first_models(state, unit_instance_id=target_unit_id, count=3)
    _replace_unit_leadership(state, unit_instance_id=target_unit_id, leadership=13)
    _place_units_near_center(
        state,
        source_unit_id="army-alpha:intercessor-unit-1",
        target_unit_id=target_unit_id,
    )
    starting_wounds = sum(
        model.wounds_remaining for model in _unit_by_id(state, target_unit_id).own_models
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
        model.wounds_remaining for model in _unit_by_id(state, target_unit_id).own_models
    )
    assert final_wounds < starting_wounds


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
    _complete_setup_through_gate(state=state, config=config)
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


def _chaos_daemons_lifecycle_config() -> GameConfig:
    catalog = _chaos_daemons_lifecycle_catalog()
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
                unit_selections=(
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
            defender_player_id="player-b",
        ),
    )


def _chaos_daemons_lifecycle_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    daemon_datasheet = _chaos_daemons_datasheet(base_datasheet)
    return replace(
        base_catalog,
        datasheets=(*base_catalog.datasheets, daemon_datasheet),
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
                unit_datasheet_ids=(CHAOS_DAEMONS_TEST_DATASHEET_ID,),
                force_disposition_ids=("phase17g-force",),
                source_ids=(
                    "gw-11e-faction-detachments-2026-27:detachment:chaos-daemons:warptide",
                ),
            ),
        ),
    )


def _chaos_daemons_datasheet(base_datasheet: DatasheetDefinition) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=CHAOS_DAEMONS_TEST_DATASHEET_ID,
        name="Manifestation Daemon",
        keywords=DatasheetKeywordSet(
            keywords=("Infantry", "Khorne"),
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


def _record_battle_shock_auto_pass(state: GameState, *, unit_instance_id: str) -> None:
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=f"phase17g-auto-pass:{unit_instance_id}",
            source_rule_id="phase17g:test:auto-pass",
            owner_player_id="player-a",
            target_unit_instance_ids=(unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhase.COMMAND,
            expiration=EffectExpiration.end_phase(
                battle_round=state.battle_round,
                phase=BattlePhase.COMMAND,
                player_id="player-a",
            ),
            effect_payload={"effect_kind": "battle_shock_auto_pass"},
        )
    )


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
    marker = _center_marker_definition(state)
    source = state.battlefield_state.unit_placement_by_id(source_unit_id)
    target = state.battlefield_state.unit_placement_by_id(target_unit_id)
    battlefield_state = state.battlefield_state.with_unit_placement(
        _with_model_offsets(source, marker, offsets=((0.0, 0.0),))
    )
    battlefield_state = battlefield_state.with_unit_placement(
        _with_model_offsets(target, marker, offsets=((1.0, 0.0),))
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
    marker = _center_marker_definition(state)
    unit = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        _with_model_offsets(unit, marker, offsets=(offset,))
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
