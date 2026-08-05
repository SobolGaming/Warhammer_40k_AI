# pyright: reportPrivateUsage=false
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, cast

import pytest
from tests.support.catalog_package_fixtures import horrors_package
from tests.support.catalog_runtime_fixtures import (
    battle_state_with_armies,
    player_ability_index,
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.dice import DiceExpression, DiceRollResult, DiceRollSpec
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine import lifecycle as lifecycle_module
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.attached_unit_reconciliation import (
    reconcile_after_attack_sequence,
)
from warhammer40k_core.engine.attack_sequence import AttackSequence
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
)
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRuntimeState,
    ModelPlacement,
    PlacedArmy,
    UnitPlacement,
)
from warhammer40k_core.engine.catalog_model_materialization_runtime import (
    CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT,
    CATALOG_MODELS_MATERIALIZED_EVENT,
    CATALOG_UNIT_DATASHEET_REPLACED_EVENT,
    SUBMIT_CATALOG_MODEL_MATERIALIZATION_PLACEMENT_DECISION_TYPE,
    CatalogModelMaterializationRuntime,
    apply_recorded_catalog_model_materialization_placement,
    invalid_catalog_model_materialization_placement_status,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.faction_content.bundle import (
    RuntimeContentBundle,
    RuntimeContentContribution,
)
from warhammer40k_core.engine.faction_content.events import (
    RuntimeContentEventContext,
    RuntimeContentEventHandlerBinding,
    RuntimeContentEventResult,
    RuntimeContentEventSubscription,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.movement_proposals import PlacementProposalPayload, ProposalKind
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.phases.shooting import ShootingPhaseHandler
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage


@dataclass(frozen=True, slots=True)
class _SplitScenario:
    package: CanonicalCatalogPackage
    state: GameState
    decisions: DecisionController
    runtime: CatalogModelMaterializationRuntime
    context: AttackSequenceCompletedContext
    source_army: ArmyDefinition
    enemy_army: ArmyDefinition
    bodyguard: UnitInstance
    leader: UnitInstance
    attack_sequence: AttackSequence
    destroyed_model_instance_id: str
    attached_unit_instance_id: str


@pytest.mark.parametrize(
    ("pink_datasheet_id", "blue_datasheet_id"),
    [("000002584", "000002583"), ("000004127", "000004128")],
)
def test_split_materializes_models_then_hands_off_attached_unit_datasheet(
    pink_datasheet_id: str,
    blue_datasheet_id: str,
) -> None:
    scenario = _split_scenario(
        pink_datasheet_id=pink_datasheet_id,
        blue_datasheet_id=blue_datasheet_id,
        destruction_kind="attack",
    )
    starting_strength = scenario.state.starting_strength_record_for_unit(
        scenario.attached_unit_instance_id
    )

    status = scenario.runtime.resolve_completed_attack_sequence(scenario.context)

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = scenario.decisions.queue.peek_next()
    assert request.decision_type == SUBMIT_CATALOG_MODEL_MATERIALIZATION_PLACEMENT_DECISION_TYPE
    assert request.actor_id == scenario.source_army.player_id
    assert type(request).from_payload(request.to_payload()).to_payload() == request.to_payload()
    request_payload = cast(dict[str, JsonValue], request.payload)
    assert len(cast(list[JsonValue], request_payload["models"])) == 2

    valid_payload = _placement_payload(
        request=request,
        army=scenario.source_army,
        unit=scenario.bodyguard,
    )
    stale_payload = dict(valid_payload)
    stale_payload["proposal_request_id"] = "stale-split-request"
    stale_result = _parameterized_result(
        request=request,
        payload=validate_json_value(stale_payload),
        result_id="result:split:stale",
    )
    stale_status = invalid_catalog_model_materialization_placement_status(
        state=scenario.state,
        request=request,
        result=stale_result,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=scenario.package.army_catalog,
    )
    assert stale_status is not None
    assert stale_status.status_kind is LifecycleStatusKind.INVALID
    assert scenario.decisions.queue.peek_next() == request

    result = _parameterized_result(
        request=request,
        payload=valid_payload,
        result_id=f"result:split:{pink_datasheet_id}",
    )
    assert (
        invalid_catalog_model_materialization_placement_status(
            state=scenario.state,
            request=request,
            result=result,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            army_catalog=scenario.package.army_catalog,
        )
        is None
    )
    scenario.decisions.submit_result(result)
    placements = apply_recorded_catalog_model_materialization_placement(
        state=scenario.state,
        decisions=scenario.decisions,
        request=request,
        result=result,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=scenario.package.army_catalog,
    )
    assert len(placements) == 2
    assert {placement.placement_kind for placement in placements} == {
        BattlefieldPlacementKind.SPLIT_UNIT
    }

    assert scenario.runtime.resolve_completed_attack_sequence(scenario.context) is None
    assert (
        reconcile_after_attack_sequence(
            scenario.state,
            scenario.decisions.event_log,
            scenario.attack_sequence,
        )
        == ()
    )
    updated_bodyguard = _unit_by_id(scenario.state, scenario.bodyguard.unit_instance_id)
    assert updated_bodyguard.datasheet_id == blue_datasheet_id
    assert len(updated_bodyguard.own_models) == 2
    assert scenario.destroyed_model_instance_id not in updated_bodyguard.own_model_ids()
    assert {model.model_profile_id for model in updated_bodyguard.own_models} == {
        f"{blue_datasheet_id}:blue-horrors"
    }
    assert all(model.base_size.diameter_mm == 25.0 for model in updated_bodyguard.own_models)
    assert all(
        "horror-materialization:blue-horror" in model.source_ids
        for model in updated_bodyguard.own_models
    )
    rules_unit = rules_unit_view_by_id(
        state=scenario.state,
        unit_instance_id=scenario.bodyguard.unit_instance_id,
    )
    assert rules_unit.is_attached_rules_unit
    assert len(rules_unit.alive_models()) == 3
    assert starting_strength.starting_model_count == 2
    assert (
        scenario.state.starting_strength_record_for_unit(scenario.attached_unit_instance_id)
        == starting_strength
    )
    assert scenario.state.battlefield_state is not None
    assert scenario.destroyed_model_instance_id not in (
        scenario.state.battlefield_state.removed_model_ids
    )
    event_types = tuple(record.event_type for record in scenario.decisions.event_log.records)
    assert CATALOG_MODELS_MATERIALIZED_EVENT in event_types
    assert CATALOG_UNIT_DATASHEET_REPLACED_EVENT in event_types
    assert "battlefield_models_placed" in event_types
    restored = GameState.from_payload(scenario.state.to_payload())
    assert _unit_by_id(restored, scenario.bodyguard.unit_instance_id).datasheet_id == (
        blue_datasheet_id
    )
    assert GameState.from_payload(restored.to_payload()).to_payload() == restored.to_payload()


def test_split_triggers_for_hazardous_but_not_non_attack_destruction() -> None:
    hazardous = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind="hazardous",
    )
    status = hazardous.runtime.resolve_completed_attack_sequence(hazardous.context)
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION

    non_attack = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind="non_attack",
    )
    assert non_attack.runtime.resolve_completed_attack_sequence(non_attack.context) is None
    assert non_attack.decisions.queue.pending_requests == ()
    assert all(
        record.event_type != CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT
        for record in non_attack.decisions.event_log.records
    )


def test_adapter_submission_dispatches_model_placed_runtime_events() -> None:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind="attack",
    )
    status = scenario.runtime.resolve_completed_attack_sequence(scenario.context)
    assert status is not None
    request = scenario.decisions.queue.peek_next()
    payload = _placement_payload(
        request=request,
        army=scenario.source_army,
        unit=scenario.bodyguard,
    )
    config = _game_config(scenario)
    lifecycle = GameLifecycle(
        state=scenario.state,
        decision_controller=scenario.decisions,
    )
    lifecycle._config = config
    lifecycle._shooting_phase_handler = ShootingPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    )
    seen_model_ids: list[str] = []
    subscription = RuntimeContentEventSubscription(
        subscription_id="test:model-placed:subscription",
        source_rule_id="test:model-placed:rule",
        trigger_kind=TimingTriggerKind.MODEL_PLACED_ON_BATTLEFIELD,
        handler_id="test:model-placed:handler",
        filters={"player_id": scenario.source_army.player_id},
    )

    def record_placement(context: RuntimeContentEventContext) -> RuntimeContentEventResult:
        event_payload = cast(dict[str, JsonValue], context.event.event_payload)
        seen_model_ids.append(cast(str, event_payload["model_instance_id"]))
        lifecycle._runtime_content_activation_input_hash = (
            lifecycle_module._runtime_content_activation_input_hash(
                config=config,
                armies=tuple(context.state.army_definitions),
            )
        )
        return RuntimeContentEventResult.applied(
            subscription,
            replay_payload={"model_instance_id": event_payload["model_instance_id"]},
        )

    activation = RuntimeContentActivation.from_armies(
        armies=(scenario.source_army, scenario.enemy_army),
        catalog=config.army_catalog,
    )
    bundle = RuntimeContentBundle.from_contributions(
        activation=activation,
        armies=(scenario.source_army, scenario.enemy_army),
        catalog=config.army_catalog,
        contributions=(
            RuntimeContentContribution(
                contribution_id="test:horror:model-placed",
                event_subscriptions=(subscription,),
                event_handler_bindings=(
                    RuntimeContentEventHandlerBinding(
                        handler_id="test:model-placed:handler",
                        handler=record_placement,
                    ),
                ),
            ),
        ),
    )
    lifecycle._runtime_content_bundle = bundle
    lifecycle._runtime_content_activation_input_hash = (
        lifecycle_module._runtime_content_activation_input_hash(
            config=config,
            armies=(scenario.source_army, scenario.enemy_army),
        )
    )
    lifecycle._battle_round_flow = BattleRoundFlow(
        phase_handlers=lifecycle._phase_handlers(),
        runtime_modifier_registry=bundle.runtime_modifier_registry,
        runtime_event_index=bundle.event_index,
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    )
    session = LocalGameSession(lifecycle=lifecycle)

    submission_status = session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=payload,
        result_id="result:split:adapter",
    )

    assert submission_status.status_kind is not LifecycleStatusKind.INVALID
    assert tuple(sorted(seen_model_ids)) == tuple(
        sorted(cast(list[str], cast(dict[str, JsonValue], request.payload)["model_instance_ids"]))
    )
    resolved_events = tuple(
        record
        for record in lifecycle.decision_controller.event_log.records
        if record.event_type == "runtime_content_event_resolved"
    )
    assert len(resolved_events) == 2
    assert all(
        cast(dict[str, JsonValue], record.payload)["trigger_kind"]
        == TimingTriggerKind.MODEL_PLACED_ON_BATTLEFIELD.value
        for record in resolved_events
    )


def test_horror_catalog_keeps_materialized_profiles_out_of_mustering() -> None:
    package = horrors_package()
    for pink_datasheet_id, blue_datasheet_id in (
        ("000002584", "000002583"),
        ("000004127", "000004128"),
    ):
        pink = package.army_catalog.datasheet_by_id(pink_datasheet_id)
        assert tuple(profile.model_profile_id for profile in pink.composition) == (
            f"{pink_datasheet_id}:pink-horrors",
        )
        materialized = pink.model_profile_by_id(f"{pink_datasheet_id}:blue-horror-brimstone-horror")
        assert materialized.base_size.diameter_mm == 25.0
        pink_unit = _single_model_unit(
            package=package,
            army_id="army-catalog",
            unit_selection_id=f"pink-{pink_datasheet_id}",
            datasheet_id=pink_datasheet_id,
            model_profile_id=f"{pink_datasheet_id}:pink-horrors",
        )
        blue_unit = _single_model_unit(
            package=package,
            army_id="army-catalog",
            unit_selection_id=f"blue-{blue_datasheet_id}",
            datasheet_id=blue_datasheet_id,
            model_profile_id=f"{blue_datasheet_id}:blue-horrors",
        )
        assert pink_unit.own_models[0].wargear_ids == (
            f"{pink_datasheet_id}:coruscating-pink-flames",
            f"{pink_datasheet_id}:pink-claws",
        )
        assert blue_unit.own_models[0].wargear_ids == (
            f"{blue_datasheet_id}:coruscating-blue-flames",
            f"{blue_datasheet_id}:blue-claws",
        )


def _split_scenario(
    *,
    pink_datasheet_id: str,
    blue_datasheet_id: str,
    destruction_kind: str,
) -> _SplitScenario:
    package = horrors_package()
    bodyguard = _single_model_unit(
        package=package,
        army_id="army-horrors",
        unit_selection_id="pink-bodyguard",
        datasheet_id=pink_datasheet_id,
        model_profile_id=f"{pink_datasheet_id}:pink-horrors",
    )
    destroyed_model = replace(bodyguard.own_models[0], wounds_remaining=0)
    bodyguard = replace(bodyguard, own_models=(destroyed_model,))
    leader = _single_model_unit(
        package=package,
        army_id="army-horrors",
        unit_selection_id="blue-leader",
        datasheet_id=blue_datasheet_id,
        model_profile_id=f"{blue_datasheet_id}:blue-horrors",
    )
    attacker = _single_model_unit(
        package=package,
        army_id="army-enemy",
        unit_selection_id="blue-attacker",
        datasheet_id=blue_datasheet_id,
        model_profile_id=f"{blue_datasheet_id}:blue-horrors",
    )
    attached_unit_id = "attached-unit:army-horrors:pink-and-leader"
    formation = AttachedUnitFormation(
        attached_unit_instance_id=attached_unit_id,
        bodyguard_unit_instance_id=bodyguard.unit_instance_id,
        leader_unit_instance_ids=(leader.unit_instance_id,),
        component_unit_instance_ids=tuple(
            sorted((bodyguard.unit_instance_id, leader.unit_instance_id))
        ),
        source_id="test:horrors:attached",
        attachment_source_ids=("test:horrors:attached:eligibility",),
    )
    source_army = _army(
        package=package,
        army_id="army-horrors",
        player_id="player-horrors",
        units=(bodyguard, leader),
        attached_units=(formation,),
    )
    enemy_army = _army(
        package=package,
        army_id="army-enemy",
        player_id="player-enemy",
        units=(attacker,),
    )
    battlefield = BattlefieldRuntimeState(
        battlefield_id="horror-split-battlefield",
        battlefield_width_inches=60.0,
        battlefield_depth_inches=44.0,
        placed_armies=(
            PlacedArmy(
                army_id=source_army.army_id,
                player_id=source_army.player_id,
                unit_placements=(_unit_placement(source_army, leader, Pose.at(10.0, 11.6)),),
            ),
            PlacedArmy(
                army_id=enemy_army.army_id,
                player_id=enemy_army.player_id,
                unit_placements=(_unit_placement(enemy_army, attacker, Pose.at(30.0, 10.0)),),
            ),
        ),
        removed_model_ids=(destroyed_model.model_instance_id,),
    )
    attack_sequence = _attack_sequence(
        package=package,
        attacker=(bodyguard if destruction_kind == "hazardous" else attacker),
        attacker_player_id=(
            source_army.player_id if destruction_kind == "hazardous" else enemy_army.player_id
        ),
        target=(attacker if destruction_kind == "hazardous" else leader),
        target_unit_instance_id=(
            attacker.unit_instance_id if destruction_kind == "hazardous" else attached_unit_id
        ),
    )
    state = battle_state_with_armies(
        armies=(source_army, enemy_army),
        battlefield=battlefield,
        active_player_id=attack_sequence.attacker_player_id,
        phase=BattlePhase.SHOOTING,
    )
    decisions = DecisionController()
    if destruction_kind == "hazardous":
        decisions.event_log.append(
            "hazardous_mortal_wounds_applied",
            {
                "sequence_id": attack_sequence.sequence_id,
                "mortal_wound_application": {
                    "applications": [
                        {
                            "model_instance_id": destroyed_model.model_instance_id,
                            "destroyed": True,
                        }
                    ]
                },
            },
        )
    else:
        decisions.event_log.append(
            "model_destroyed",
            {
                "sequence_id": (
                    attack_sequence.sequence_id if destruction_kind == "attack" else None
                ),
                "target_unit_instance_id": bodyguard.unit_instance_id,
                "model_instance_id": destroyed_model.model_instance_id,
            },
        )
    completed_event = decisions.event_log.append(
        "attack_sequence_completed",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attacker_player_id": attack_sequence.attacker_player_id,
            "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
        },
    )
    dice_manager = DiceRollManager(
        state.game_id,
        event_log=decisions.event_log,
        injected_results=(
            DiceRollResult.from_values(
                roll_id=f"roll:split:{pink_datasheet_id}:{destruction_kind}",
                spec=DiceRollSpec(
                    expression=DiceExpression(quantity=1, sides=6),
                    reason=f"Model materialization for {destroyed_model.model_instance_id}",
                    roll_type="catalog.model_materialization.trigger",
                    actor_id=source_army.player_id,
                ),
                values=(6,),
                source="fixed",
            ),
        ),
    )
    runtime = CatalogModelMaterializationRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: player_ability_index(package=package, army=source_army),
            enemy_army.player_id: player_ability_index(package=package, army=enemy_army),
        },
        armies=(source_army, enemy_army),
        army_catalog=package.army_catalog,
    )
    context = AttackSequenceCompletedContext(
        state=state,
        decisions=decisions,
        dice_manager=dice_manager,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        source_phase=BattlePhase.SHOOTING,
        attack_sequence=attack_sequence,
        attack_sequence_completed_event_id=completed_event.event_id,
    )
    return _SplitScenario(
        package=package,
        state=state,
        decisions=decisions,
        runtime=runtime,
        context=context,
        source_army=source_army,
        enemy_army=enemy_army,
        bodyguard=bodyguard,
        leader=leader,
        attack_sequence=attack_sequence,
        destroyed_model_instance_id=destroyed_model.model_instance_id,
        attached_unit_instance_id=attached_unit_id,
    )


def _single_model_unit(
    *,
    package: CanonicalCatalogPackage,
    army_id: str,
    unit_selection_id: str,
    datasheet_id: str,
    model_profile_id: str,
) -> UnitInstance:
    datasheet = package.army_catalog.datasheet_by_id(datasheet_id)
    unit = UnitFactory(
        package.army_catalog,
        package.model_geometries,
    ).instantiate_unit(
        army_id=army_id,
        selection=UnitMusterSelection(
            unit_selection_id=unit_selection_id,
            datasheet_id=datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(model_profile_id=model_profile_id, model_count=10),
            ),
        ),
        datasheet=datasheet,
    )
    return replace(unit, own_models=(unit.own_models[0],))


def _army(
    *,
    package: CanonicalCatalogPackage,
    army_id: str,
    player_id: str,
    units: tuple[UnitInstance, ...],
    attached_units: tuple[AttachedUnitFormation, ...] = (),
) -> ArmyDefinition:
    return ArmyDefinition(
        army_id=army_id,
        player_id=player_id,
        catalog_id=package.army_catalog.catalog_id,
        source_package_id=package.army_catalog.source_package_id,
        ruleset_id=package.army_catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=package.army_catalog.factions[0].faction_id,
            detachment_ids=("test:horrors:detachment",),
        ),
        force_disposition_id="test:horrors:force",
        units=units,
        attached_units=attached_units,
    )


def _unit_placement(army: ArmyDefinition, unit: UnitInstance, pose: Pose) -> UnitPlacement:
    return UnitPlacement(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=(
            ModelPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=unit.own_models[0].model_instance_id,
                pose=pose,
            ),
        ),
    )


def _attack_sequence(
    *,
    package: CanonicalCatalogPackage,
    attacker: UnitInstance,
    attacker_player_id: str,
    target: UnitInstance,
    target_unit_instance_id: str,
) -> AttackSequence:
    wargear_id = attacker.own_models[0].wargear_ids[0]
    wargear = next(item for item in package.army_catalog.wargear if item.wargear_id == wargear_id)
    profile = wargear.weapon_profiles[0]
    pool = RangedAttackPool(
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        wargear_id=wargear.wargear_id,
        weapon_profile_id=profile.profile_id,
        weapon_profile=profile,
        target_unit_instance_id=target_unit_instance_id,
        shooting_type=ShootingType.NORMAL,
        attacks=1,
        target_visible_model_ids=target.own_model_ids(),
        target_in_range_model_ids=target.own_model_ids(),
    )
    return AttackSequence(
        sequence_id=f"attack-sequence:horror-split:{attacker.unit_instance_id}",
        attacker_player_id=attacker_player_id,
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(pool,),
        source_phase=BattlePhase.SHOOTING,
        used_pool_indices=(0,),
        pool_index=1,
    )


def _placement_payload(
    *,
    request: Any,
    army: ArmyDefinition,
    unit: UnitInstance,
) -> dict[str, JsonValue]:
    request_payload = cast(dict[str, JsonValue], request.payload)
    model_ids = cast(list[str], request_payload["model_instance_ids"])
    placements = tuple(
        ModelPlacement(
            army_id=army.army_id,
            player_id=army.player_id,
            unit_instance_id=unit.unit_instance_id,
            model_instance_id=model_id,
            pose=pose,
        )
        for model_id, pose in zip(
            model_ids,
            (Pose.at(10.0, 10.0), Pose.at(11.2, 10.0)),
            strict=True,
        )
    )
    return cast(
        dict[str, JsonValue],
        PlacementProposalPayload(
            proposal_request_id=request.request_id,
            proposal_kind=ProposalKind.MODEL_MATERIALIZATION,
            unit_instance_id=unit.unit_instance_id,
            placement_kind=BattlefieldPlacementKind.SPLIT_UNIT,
            attempted_placement=UnitPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=unit.unit_instance_id,
                model_placements=placements,
            ),
        ).to_payload(),
    )


def _parameterized_result(*, request: Any, payload: JsonValue, result_id: str) -> DecisionResult:
    return DecisionResult(
        result_id=result_id,
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=request.options[0].option_id,
        payload=payload,
    )


def _unit_by_id(state: GameState, unit_instance_id: str) -> UnitInstance:
    matches = tuple(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == unit_instance_id
    )
    assert len(matches) == 1
    return matches[0]


def _game_config(scenario: _SplitScenario) -> GameConfig:
    requests = tuple(
        ArmyMusterRequest(
            army_id=army.army_id,
            player_id=army.player_id,
            catalog_id=army.catalog_id,
            source_package_id=army.source_package_id,
            ruleset_id=army.ruleset_id,
            detachment_selection=army.detachment_selection,
            force_disposition_id=army.force_disposition_id,
            unit_selections=tuple(
                UnitMusterSelection(
                    unit_selection_id=unit.unit_instance_id.removeprefix(f"{army.army_id}:"),
                    datasheet_id=unit.datasheet_id,
                    model_profile_selections=(
                        ModelProfileSelection(
                            model_profile_id=unit.own_models[0].model_profile_id,
                            model_count=len(unit.own_models),
                        ),
                    ),
                )
                for unit in army.units
            ),
        )
        for army in (scenario.source_army, scenario.enemy_army)
    )
    return GameConfig(
        game_id=scenario.state.game_id,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=scenario.package.army_catalog,
        army_muster_requests=requests,
        player_ids=scenario.state.player_ids,
        turn_order=scenario.state.turn_order,
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        mission_setup=scenario.state.mission_setup,
        allow_legacy_non_strict_rosters=True,
    )
