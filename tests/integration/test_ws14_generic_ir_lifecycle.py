from __future__ import annotations

import json
from dataclasses import replace

import pytest
from tests.setup_completion_helpers import enter_battle_for_fixture

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import DatasheetKeywordSet
from warhammer40k_core.core.detachment import (
    DetachmentDefinition,
    EnhancementDefinition,
    StratagemDefinition,
)
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, RulesetDescriptor
from warhammer40k_core.engine.army_mustering import (
    ArmyMusterRequest,
    EnhancementAssignment,
    muster_army,
)
from warhammer40k_core.engine.command_points import CommandPointGainStatus, CommandPointSourceKind
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_rule_execution import (
    FactionRuleExecutionContext,
    FactionRuleExecutionResult,
    FactionRuleExecutionStatus,
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
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.runtime_modifiers import HitRollModifierContext
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_DECISION_TYPE,
    StratagemEligibilityContext,
    request_stratagem_use_from_index,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionStatus,
)

_MORE_DAKKA_GENERIC_EXECUTION_IDS = (
    "phase17f:phase17e:enhancement:orks:more-dakka:000009991003",
    "phase17f:phase17e:enhancement:orks:more-dakka:000009991004",
    "phase17f:phase17e:enhancement:orks:more-dakka:000009991005",
)


@pytest.mark.integration
def test_ws14_more_dakka_generic_ir_rows_execute_from_lifecycle_runtime_bundle() -> None:
    config = _more_dakka_lifecycle_config()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.advance_until_decision_or_terminal()

    bundle = _runtime_content_bundle(lifecycle)

    assert "orks" in bundle.activation.selected_faction_ids
    assert "more-dakka" in bundle.activation.selected_detachment_ids
    assert set(_MORE_DAKKA_GENERIC_EXECUTION_IDS).issubset(
        bundle.activation.selected_execution_record_ids
    )

    context = FactionRuleExecutionContext(
        game_id=config.game_id,
        player_id="player-a",
        battle_round=1,
        phase=BattlePhaseKind.SHOOTING,
        active_player_id="player-a",
        source_unit_instance_id="army-alpha:boyz-1",
        trigger_payload={"event": "ws14-more-dakka-generic-ir-demo"},
    )
    results = tuple(
        bundle.faction_rule_execution_registry.execute(
            execution_id=execution_id,
            context=context,
        )
        for execution_id in _MORE_DAKKA_GENERIC_EXECUTION_IDS
    )

    assert tuple(result.status for result in results) == (
        FactionRuleExecutionStatus.APPLIED,
        FactionRuleExecutionStatus.APPLIED,
        FactionRuleExecutionStatus.APPLIED,
    )
    for result in results:
        record = bundle.faction_rule_execution_registry.record_by_execution_id(result.execution_id)
        assert record.execution_status is Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
        assert record.rule_ir_hash is not None
        assert FactionRuleExecutionResult.from_payload(result.to_payload()) == result
        replay_payload = _json_object(result.replay_payload)
        rule_result_payload = _json_object(replay_payload["generic_rule_execution_result"])
        assert rule_result_payload["status"] == "applied"

    payload = lifecycle.to_payload()
    rebuilt = GameLifecycle.from_payload(payload)

    assert _runtime_content_bundle(rebuilt).to_summary_payload() == bundle.to_summary_payload()
    assert "object at 0x" not in json.dumps(payload, sort_keys=True)


@pytest.mark.integration
def test_ws14_more_dakka_stratagem_activation_binds_target_through_lifecycle_bundle() -> None:
    lifecycle = _more_dakka_battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.COMMAND)
    _grant_cp(state, player_id="player-a", amount=2)
    bundle = _runtime_content_bundle(lifecycle)
    player_index = bundle.stratagem_indexes_by_player_id["player-a"]
    context = StratagemEligibilityContext.from_state(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.START_PHASE,
    )

    status = request_stratagem_use_from_index(
        state=state,
        decisions=lifecycle.decision_controller,
        index=player_index,
        context=context,
    )

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = lifecycle.pending_decision_request()
    assert request is not None
    assert request.decision_type == STRATAGEM_DECISION_TYPE
    selected_option = next(
        option
        for option in request.options
        if _option_stratagem_id(option.payload) == "000009992003"
    )

    result = DecisionResult.for_request(
        result_id="ws14-more-dakka-get-stuck-in-result",
        request=request,
        selected_option_id=selected_option.option_id,
    )
    lifecycle.submit_decision(result)

    assert state.command_point_total("player-a") == 1
    use_record = state.stratagem_use_records[-1]
    assert use_record.stratagem_id == "000009992003"
    assert use_record.command_point_cost == 2
    spent = _last_event_payload(lifecycle, "command_points_spent")
    assert spent["player_id"] == "player-a"
    assert spent["requested_amount"] == 2
    assert spent["applied_amount"] == 2
    assert spent["source_id"] == use_record.use_id
    assert spent["source_kind"] == "stratagem_spend"
    spent_transaction = _json_object(spent["transaction"])
    assert spent_transaction["amount"] == -2
    assert spent_transaction["transaction_id"] == use_record.command_point_transaction_id
    assert use_record.targeted_unit_instance_ids == ("army-alpha:boyz-1",)
    target_bound = _last_event_payload(lifecycle, "rule_execution_target_bound")
    assert target_bound["target_kind"] == "friendly_unit"
    assert target_bound["target_unit_instance_ids"] == ["army-alpha:boyz-1"]
    assert GameLifecycle.from_payload(lifecycle.to_payload()).to_payload() == lifecycle.to_payload()
    assert "object at 0x" not in json.dumps(lifecycle.to_payload(), sort_keys=True)


@pytest.mark.integration
def test_ws14_more_dakka_generic_enhancement_ir_binds_to_assigned_bearer() -> None:
    lifecycle = _more_dakka_battle_lifecycle()
    state = _state(lifecycle)
    bundle = _runtime_content_bundle(lifecycle)

    assignment_payloads = [
        assignment.to_payload()
        for assignment in bundle.activation.selected_enhancement_assignments
        if assignment.player_id == "player-a"
    ]
    assert assignment_payloads == [
        {
            "assignment_id": "army-alpha:000009991004:boyz-1",
            "player_id": "player-a",
            "army_id": "army-alpha",
            "enhancement_id": "000009991004",
            "target_unit_selection_id": "boyz-1",
            "bearer_unit_instance_id": "army-alpha:boyz-1",
            "source_id": "ws14-more-dakka:assignment:boyz-1:000009991004",
        }
    ]

    bearer_effects = tuple(state.persisting_effects_for_unit("army-alpha:boyz-1"))
    generic_hit_effects = tuple(
        effect
        for effect in bearer_effects
        if _json_object(effect.effect_payload)["execution_id"]
        == "phase17f:phase17e:enhancement:orks:more-dakka:000009991004"
    )
    assert len(generic_hit_effects) == 1
    effect_payload = _json_object(generic_hit_effects[0].effect_payload)
    assert effect_payload["effect_kind"] == "generic_rule_execution"
    assert effect_payload["target_unit_instance_ids"] == ["army-alpha:boyz-1"]
    effect = _json_object(effect_payload["effect"])
    assert effect["kind"] == "modify_dice_roll"
    assignment = _json_object(effect_payload["enhancement_assignment"])
    assert assignment["bearer_unit_instance_id"] == "army-alpha:boyz-1"

    weapon_profile = next(
        wargear
        for wargear in _more_dakka_catalog().wargear
        if wargear.wargear_id == "core-mob-shoota"
    ).weapon_profiles[0]
    model_instance_id = state.army_definitions[0].units[0].own_models[0].model_instance_id
    assert (
        bundle.runtime_modifier_registry.hit_roll_modifier(
            HitRollModifierContext(
                state=state,
                attacking_unit_instance_id="army-alpha:boyz-1",
                attacker_model_instance_id=model_instance_id,
                target_unit_instance_id="army-beta:boyz-2",
                weapon_profile=weapon_profile,
                source_phase=BattlePhase.SHOOTING,
            )
        )
        == 1
    )
    assert GameLifecycle.from_payload(lifecycle.to_payload()).to_payload() == lifecycle.to_payload()
    assert "object at 0x" not in json.dumps(lifecycle.to_payload(), sort_keys=True)


def _more_dakka_lifecycle_config() -> GameConfig:
    catalog = _more_dakka_catalog()
    return GameConfig(
        game_id="ws14-more-dakka-generic-ir-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        army_muster_requests=(
            _more_dakka_muster_request(
                catalog=catalog,
                army_id="army-alpha",
                player_id="player-a",
                unit_selection_id="boyz-1",
            ),
            _more_dakka_muster_request(
                catalog=catalog,
                army_id="army-beta",
                player_id="player-b",
                unit_selection_id="boyz-2",
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down"),
        mission_setup=_mission_setup(),
    )


def _more_dakka_battle_lifecycle() -> GameLifecycle:
    config = _more_dakka_lifecycle_config()
    armies = tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="ws14-more-dakka-battlefield",
        armies=armies,
    )
    state.record_battlefield_state(scenario.battlefield_state)
    _record_fixed_secondary_choices_for_fixture(state, config=config)
    enter_battle_for_fixture(state)
    return GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": DecisionController().to_payload(),
            "reaction_queue": ReactionQueue().to_payload(),
        }
    )


def _more_dakka_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-boyz-like-infantry")
    boyz_datasheet = replace(
        base_datasheet,
        datasheet_id="ws14-orks-boyz",
        name="WS14 Orks Boyz",
        keywords=DatasheetKeywordSet(
            keywords=("Character", "Infantry"),
            faction_keywords=("Orks",),
        ),
        source_ids=("datasheet:ws14-orks-boyz",),
    )
    mob_shoota = next(
        wargear for wargear in base_catalog.wargear if wargear.wargear_id == "core-mob-shoota"
    )
    return ArmyCatalog(
        catalog_id="ws14-more-dakka-demo",
        ruleset_id=base_catalog.ruleset_id,
        source_package_id="data-package:core-v2:ws14-more-dakka-demo:0.1.0",
        datasheets=(boyz_datasheet,),
        wargear=(mob_shoota,),
        factions=(
            FactionDefinition(
                faction_id="orks",
                name="Orks",
                faction_keywords=("Orks",),
                source_ids=("faction:orks",),
            ),
        ),
        detachments=(
            DetachmentDefinition(
                detachment_id="more-dakka",
                name="More Dakka",
                faction_id="orks",
                detachment_point_cost=1,
                unit_datasheet_ids=("ws14-orks-boyz",),
                force_disposition_ids=("purge-the-foe",),
                rule_source_ids=("phase17e:orks:more-dakka:rule",),
                enhancement_ids=(
                    "000009991002",
                    "000009991003",
                    "000009991004",
                    "000009991005",
                ),
                stratagem_ids=(
                    "000009992002",
                    "000009992003",
                    "000009992004",
                    "000009992005",
                    "000009992006",
                    "000009992007",
                ),
                source_ids=("detachment:more-dakka",),
            ),
        ),
        enhancements=(
            EnhancementDefinition(
                enhancement_id="000009991002",
                name="Da Gobshot Thunderbuss",
                source_id="phase17e:enhancement:orks:more-dakka:000009991002",
                points=15,
            ),
            EnhancementDefinition(
                enhancement_id="000009991003",
                name="Dead Shiny Shootas",
                source_id="phase17e:enhancement:orks:more-dakka:000009991003",
                points=35,
            ),
            EnhancementDefinition(
                enhancement_id="000009991004",
                name="Targetin Squigs",
                source_id="phase17e:enhancement:orks:more-dakka:000009991004",
                points=15,
            ),
            EnhancementDefinition(
                enhancement_id="000009991005",
                name="Zog Off and Eat Dakka",
                source_id="phase17e:enhancement:orks:more-dakka:000009991005",
                points=10,
            ),
        ),
        stratagems=(
            _more_dakka_stratagem("000009992002", "Orks Is Still Orks", 1),
            _more_dakka_stratagem("000009992003", "Get Stuck In Ladz", 2),
            _more_dakka_stratagem("000009992004", "Huge Show Offs", 1),
            _more_dakka_stratagem("000009992005", "Long Uncontrolled Bursts", 1),
            _more_dakka_stratagem("000009992006", "Speshul Shells", 1),
            _more_dakka_stratagem("000009992007", "Call Dat Dakka", 1),
        ),
        source_ids=("catalog:ws14-more-dakka-demo",),
    )


def _more_dakka_stratagem(
    stratagem_id: str,
    name: str,
    command_point_cost: int,
) -> StratagemDefinition:
    return StratagemDefinition(
        stratagem_id=stratagem_id,
        name=name,
        source_id=f"phase17e:stratagem:orks:more-dakka:{stratagem_id}",
        command_point_cost=command_point_cost,
        timing_tags=("shooting",),
    )


def _more_dakka_muster_request(
    *,
    catalog: ArmyCatalog,
    army_id: str,
    player_id: str,
    unit_selection_id: str,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="orks",
            detachment_ids=("more-dakka",),
            enhancement_ids=("000009991003", "000009991004", "000009991005"),
        ),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="ws14-orks-boyz",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-boyz-like",
                        model_count=10,
                    ),
                ),
            ),
        ),
        enhancement_assignments=(
            EnhancementAssignment(
                enhancement_id="000009991004",
                target_unit_selection_id=unit_selection_id,
                source_id=(f"ws14-more-dakka:assignment:{unit_selection_id}:000009991004"),
            ),
        ),
        roster_legality_required=False,
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _runtime_content_bundle(lifecycle: GameLifecycle) -> RuntimeContentBundle:
    bundle = object.__getattribute__(lifecycle, "_runtime_content_bundle")
    if type(bundle) is not RuntimeContentBundle:
        raise AssertionError("Runtime content bundle was not rebuilt.")
    return bundle


def _state(lifecycle: GameLifecycle) -> GameState:
    state = lifecycle.state
    assert state is not None
    return state


def _set_current_battle_phase(state: GameState, phase: BattlePhase) -> None:
    state.battle_phase_index = state.battle_phase_sequence.index(phase)


def _grant_cp(state: GameState, *, player_id: str, amount: int) -> None:
    result = state.gain_command_points(
        player_id=player_id,
        amount=amount,
        source_id=f"ws14-more-dakka-grant:{player_id}:{amount}",
        source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
    )
    assert result.status is CommandPointGainStatus.APPLIED


def _record_fixed_secondary_choices_for_fixture(
    state: GameState,
    *,
    config: GameConfig,
) -> None:
    for player_id in config.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=config.fixed_secondary_mission_ids,
            )
        )


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Expected a JSON object.")
    return value


def _option_stratagem_id(payload: JsonValue) -> str | None:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Stratagem option payload must be an object.")
    catalog_record = payload.get("catalog_record")
    if not isinstance(catalog_record, dict):
        raise GameLifecycleError("Stratagem option payload is missing catalog_record.")
    definition = catalog_record.get("definition")
    if not isinstance(definition, dict):
        raise GameLifecycleError("Stratagem option payload is missing definition.")
    stratagem_id = definition.get("stratagem_id")
    if stratagem_id is None:
        return None
    if type(stratagem_id) is not str:
        raise GameLifecycleError("Stratagem option stratagem_id must be a string.")
    return stratagem_id


def _last_event_payload(lifecycle: GameLifecycle, event_type: str) -> dict[str, JsonValue]:
    for event in reversed(lifecycle.decision_controller.event_log.records):
        if event.event_type == event_type:
            return _json_object(event.payload)
    raise AssertionError(f"Missing event type: {event_type}")
