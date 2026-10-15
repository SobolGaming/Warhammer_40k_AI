# pyright: reportPrivateUsage=false
from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from typing import Any, cast

import pytest

from tests.horror_destruction_helpers import resolve_horror_completion
from tests.parameterized_projection_helpers import assert_parameterized_projection
from tests.support.catalog_package_fixtures import horrors_package
from tests.support.catalog_runtime_fixtures import battle_state_with_armies, player_ability_index
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceExpression, DiceRollResult, DiceRollSpec
from warhammer40k_core.core.ruleset_descriptor import (
    FightEligibilityKind,
    FightPhaseStepKind,
    RulesetDescriptor,
    battle_phase_kind_from_token,
)
from warhammer40k_core.core.weapon_profiles import DamageProfile, WeaponKeyword
from warhammer40k_core.engine import lifecycle as lifecycle_module
from warhammer40k_core.engine import rule_model_destruction
from warhammer40k_core.engine.ability_catalog import catalog_ability_records_from_catalog
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.attached_unit_reconciliation import reconcile_after_attack_sequence
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    apply_feel_no_pain_decision,
    attack_sequence_wound_roll_spec,
    deadly_demise_trigger_roll_spec,
    resolve_attack_sequence_until_blocked,
)
from warhammer40k_core.engine.attack_sequence_completion_hooks import AttackSequenceCompletedContext
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRuntimeState,
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
    ModelPlacement,
    PlacedArmy,
    UnitPlacement,
)
from warhammer40k_core.engine.catalog_materialization_integrity import (
    _required_string_list,
    authenticated_catalog_materialized_model_payloads_by_unit_id,
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
from warhammer40k_core.engine.catalog_selected_target_mortal_wounds import (
    resolve_selected_target_mortal_wound_effect,
)
from warhammer40k_core.engine.damage_allocation import (
    DECLINE_DESTRUCTION_REACTION_OPTION_ID,
    DestructionReactionKind,
    DestructionReactionSource,
    FeelNoPainSource,
    feel_no_pain_roll_spec,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.destruction_provenance import (
    DestructionSourceKind,
    ModelDestructionAttribution,
)
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
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
from warhammer40k_core.engine.fight_order import (
    FightActivationSelection,
    FightPhaseState,
    FightsFirstRegistry,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT,
)
from warhammer40k_core.engine.mortal_wound_model_allocation import (
    is_mortal_wound_model_request,
    resolve_mortal_wound_decision,
)
from warhammer40k_core.engine.movement_proposals import PlacementProposalPayload, ProposalKind
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.phases.fight import FightPhaseHandler
from warhammer40k_core.engine.phases.movement import MovementPhaseHandler
from warhammer40k_core.engine.phases.shooting import (
    OutOfPhaseShootingState,
    ShootingPhaseHandler,
    ShootingPhaseState,
)
from warhammer40k_core.engine.reaction_queue import ReactionQueue, ReactionQueueFrame
from warhammer40k_core.engine.rule_model_destruction import RULE_MODEL_DESTRUCTION_FINALIZED_EVENT
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.saves import (
    mandatory_save_option,
    save_options_for_model,
    saving_throw_roll_spec,
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.timing_windows import (
    ReactionWindow,
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitFactory, UnitInstance
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
    destroyed_model_instance_ids: tuple[str, ...]
    attached_unit_instance_id: str


def _record_split_interrupt_activation(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    target_unit_instance_id: str,
) -> FightActivationSelection:
    """Bind the synthetic post-executor fixture to its accepted selection first."""
    from tests.completed_attack_fixture_helpers import record_fight_selection_for_executor_fixture

    policy = state.runtime_ruleset_descriptor().fight_policy
    active_player_id = state.active_player_id
    assert active_player_id is not None
    fight_state = FightPhaseState.start(
        battle_round=state.battle_round,
        active_player_id=active_player_id,
        policy=policy,
        engaged_at_fight_step_start_unit_ids=(
            attack_sequence.attacking_unit_instance_id,
            target_unit_instance_id,
        ),
        fights_first_registry=FightsFirstRegistry(),
    ).with_current_step(
        current_step=FightPhaseStepKind.FIGHT,
        policy=policy,
    )
    activation = FightActivationSelection(
        player_id=attack_sequence.attacker_player_id,
        battle_round=state.battle_round,
        unit_instance_id=attack_sequence.attacking_unit_instance_id,
        ordering_band=fight_state.current_ordering_band,
        fight_type=policy.fight_types[0],
        eligibility_reasons=(FightEligibilityKind.ENGAGED_AT_FIGHT_STEP_START,),
        request_id="request:fight-interrupt:horror-split",
        result_id="result:fight-interrupt:horror-split",
        interrupt_id="interrupt:fight:horror-split",
    )
    fight_state = (
        fight_state.with_activation(activation)
        .with_active_activation(activation)
        .with_attack_sequence_update(
            attack_sequence=attack_sequence,
            allocated_model_ids_this_phase=(),
        )
    )
    state.replace_fight_phase_state(fight_state)
    record_fight_selection_for_executor_fixture(decisions=decisions, selection=activation)
    return activation


def _split_scenario(
    *,
    pink_datasheet_id: str,
    blue_datasheet_id: str,
    destruction_kind: str,
    source_phase: BattlePhase = BattlePhase.SHOOTING,
    parent_battle_phase: BattlePhase | None = None,
    attached: bool = True,
    pink_model_count: int = 1,
    roll_values: tuple[int, ...] = (6,),
    destroyed_horror_kinds: tuple[str, ...] = (),
    retained_horror_kinds: tuple[str, ...] = (),
    event_sequence_matches: bool = False,
    non_attack_source_step: str = "ability_resolution",
    models_start_destroyed: bool = True,
    emit_destruction_events: bool = True,
    game_id: str | None = None,
    random_materialized_wounds: bool = False,
    fight_interrupt_activation: bool = False,
) -> _SplitScenario:
    package = horrors_package()
    if random_materialized_wounds:
        from warhammer40k_core.core.random_profile_values import RandomProfileValue

        source_sheet = package.army_catalog.datasheet_by_id(pink_datasheet_id)
        source_sheet = replace(
            source_sheet,
            model_profiles=tuple(
                replace(
                    profile,
                    characteristics=tuple(
                        RandomProfileValue(
                            Characteristic.WOUNDS, DiceExpression(1, 6, 2), profile.source_ids[0]
                        )
                        if value.characteristic is Characteristic.WOUNDS
                        else value
                        for value in profile.characteristics
                    ),
                )
                if profile.model_profile_id.endswith(":blue-horror-brimstone-horror")
                else profile
                for profile in source_sheet.model_profiles
            ),
        )
        package = replace(
            package,
            army_catalog=replace(
                package.army_catalog,
                datasheets=tuple(
                    source_sheet if sheet.datasheet_id == pink_datasheet_id else sheet
                    for sheet in package.army_catalog.datasheets
                ),
            ),
        )
    bodyguard = _model_count_unit(
        package=package,
        army_id="army-horrors",
        unit_selection_id="pink-bodyguard",
        datasheet_id=pink_datasheet_id,
        model_profile_id=f"{pink_datasheet_id}:pink-horrors",
        model_count=pink_model_count,
    )
    models_to_destroy = (
        tuple(
            _retained_horror_model(
                package=package,
                pink_datasheet_id=pink_datasheet_id,
                bodyguard=bodyguard,
                horror_kind=horror_kind,
                index=index,
            )
            for index, horror_kind in enumerate(destroyed_horror_kinds, start=1)
        )
        if destroyed_horror_kinds
        else bodyguard.own_models
    )
    destroyed_models = tuple(model for model in models_to_destroy)
    retained_models = tuple(
        _retained_horror_model(
            package=package,
            pink_datasheet_id=pink_datasheet_id,
            bodyguard=bodyguard,
            horror_kind=horror_kind,
            index=index,
        )
        for index, horror_kind in enumerate(
            retained_horror_kinds,
            start=len(destroyed_horror_kinds) + 1,
        )
    )
    bodyguard = replace(bodyguard, own_models=(*destroyed_models, *retained_models))
    leader = _single_model_unit(
        package=package,
        army_id="army-horrors",
        unit_selection_id="blue-leader",
        datasheet_id=blue_datasheet_id,
        model_profile_id=f"{blue_datasheet_id}:blue-horrors",
    )
    leader = replace(
        leader,
        own_models=tuple(
            replace(
                model,
                keyword_assignment=replace(
                    model.keyword_assignment,
                    keywords=tuple(sorted({*model.keywords, "CHARACTER"})),
                    source_ids=(
                        *model.keyword_assignment.source_ids,
                        "test:horrors:leader-keyword",
                    ),
                ),
            )
            for model in leader.own_models
        ),
    )
    attacker = _single_model_unit(
        package=package,
        army_id="army-enemy",
        unit_selection_id="blue-attacker",
        datasheet_id=blue_datasheet_id,
        model_profile_id=f"{blue_datasheet_id}:blue-horrors",
    )
    attached_unit_id = "attached-unit:army-horrors:pink-and-leader"
    formation = (
        AttachedUnitFormation(
            attached_unit_instance_id=attached_unit_id,
            bodyguard_unit_instance_id=bodyguard.unit_instance_id,
            leader_unit_instance_ids=(leader.unit_instance_id,),
            component_unit_instance_ids=tuple(
                sorted((bodyguard.unit_instance_id, leader.unit_instance_id))
            ),
            source_id="test:horrors:attached",
            attachment_source_ids=("test:horrors:attached:eligibility",),
        )
        if attached
        else None
    )
    source_army = _army(
        package=package,
        army_id="army-horrors",
        player_id="player-horrors",
        force_disposition_id="take-and-hold",
        units=(bodyguard, leader),
        attached_units=(() if formation is None else (formation,)),
    )
    enemy_army = _army(
        package=package,
        army_id="army-enemy",
        player_id="player-enemy",
        force_disposition_id="purge-the-foe",
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
                unit_placements=tuple(
                    placement
                    for placement in (
                        _alive_unit_placement_or_none(
                            source_army,
                            bodyguard,
                            origin=Pose.at(10.0, 10.0),
                        ),
                        _unit_placement(source_army, leader, Pose.at(10.0, 11.6)),
                    )
                    if placement is not None
                ),
            ),
            PlacedArmy(
                army_id=enemy_army.army_id,
                player_id=enemy_army.player_id,
                unit_placements=(_unit_placement(enemy_army, attacker, Pose.at(30.0, 10.0)),),
            ),
        ),
        removed_model_ids=tuple(
            model.model_instance_id for model in destroyed_models if not model.is_alive
        ),
    )
    attack_sequence = _attack_sequence(
        package=package,
        attacker=(bodyguard if destruction_kind == "hazardous" else attacker),
        attacker_player_id=(
            source_army.player_id if destruction_kind == "hazardous" else enemy_army.player_id
        ),
        target=(attacker if destruction_kind == "hazardous" else bodyguard),
        target_unit_instance_id=(
            attacker.unit_instance_id
            if destruction_kind == "hazardous"
            else (attached_unit_id if attached else bodyguard.unit_instance_id)
        ),
        source_phase=source_phase,
    )
    if destruction_kind == "hazardous" and emit_destruction_events:
        base_pool = attack_sequence.attack_pools[0]
        profile = replace(
            base_pool.weapon_profile,
            keywords=tuple(
                sorted(
                    {*base_pool.weapon_profile.keywords, WeaponKeyword.HAZARDOUS},
                    key=lambda keyword: keyword.value,
                )
            ),
        )
        attack_sequence = replace(
            attack_sequence,
            attacking_unit_instance_id=(
                attached_unit_id if attached else bodyguard.unit_instance_id
            ),
            attack_pools=(replace(base_pool, weapon_profile=profile),),
        )
    resolved_parent_battle_phase = (
        source_phase if parent_battle_phase is None else parent_battle_phase
    )
    state = battle_state_with_armies(
        armies=(source_army, enemy_army),
        battlefield=battlefield,
        active_player_id=attack_sequence.attacker_player_id,
        phase=resolved_parent_battle_phase,
    )
    if game_id is not None:
        state.game_id = game_id
    if (
        source_phase is BattlePhase.SHOOTING
        and resolved_parent_battle_phase is not BattlePhase.SHOOTING
    ):
        attack_sequence = replace(
            attack_sequence, sequence_id=f"out-of-phase-{attack_sequence.sequence_id}"
        )
    decisions = DecisionController()
    if source_phase is BattlePhase.SHOOTING:
        from tests.completed_attack_fixture_helpers import (
            record_shooting_declaration_for_executor_fixture,
        )

        record_shooting_declaration_for_executor_fixture(
            state=state,
            decisions=decisions,
            sequence=attack_sequence,
            result_id=attack_sequence.sequence_id.split("attack-sequence:", 1)[1],
        )
    else:
        from tests.completed_attack_fixture_helpers import (
            record_melee_declaration_for_executor_fixture,
        )

        result_id = "horror-split-melee"
        attack_sequence = replace(
            attack_sequence,
            sequence_id=(
                f"melee-sequence:{state.game_id}:round-{state.battle_round:02d}:"
                f"{attack_sequence.attacking_unit_instance_id}:{result_id}"
            ),
        )
        activation = (
            _record_split_interrupt_activation(
                state=state,
                decisions=decisions,
                attack_sequence=attack_sequence,
                target_unit_instance_id=(
                    attached_unit_id if attached else bodyguard.unit_instance_id
                ),
            )
            if fight_interrupt_activation
            else None
        )
        record_melee_declaration_for_executor_fixture(
            state=state,
            decisions=decisions,
            sequence=attack_sequence,
            result_id=result_id,
            activation=activation,
        )
    if emit_destruction_events and destruction_kind != "hazardous":
        assert models_start_destroyed
        from tests.horror_destruction_helpers import (
            destroy_horror_models_for_completion_fixture,
            finish_prior_horror_destruction_triggers,
        )

        destroy_horror_models_for_completion_fixture(
            state=state,
            decisions=decisions,
            sequence=attack_sequence,
            target_unit_id=(attached_unit_id if attached else bodyguard.unit_instance_id),
            model_ids=tuple(model.model_instance_id for model in destroyed_models),
            source_kind=DestructionSourceKind(destruction_kind),
            source_step=("damage" if destruction_kind == "attack" else non_attack_source_step),
            event_sequence_matches=event_sequence_matches,
        )
        finish_prior_horror_destruction_triggers(state=state, decisions=decisions)
        source_army = next(
            army for army in state.army_definitions if army.player_id == source_army.player_id
        )
        bodyguard = next(
            unit
            for unit in source_army.units
            if unit.unit_instance_id == bodyguard.unit_instance_id
        )
    from tests.completed_attack_fixture_helpers import record_attack_completion_for_executor_fixture

    completed_event = record_attack_completion_for_executor_fixture(
        state=state,
        decisions=decisions,
        sequence=attack_sequence,
    )
    hazard_rolls = (
        (
            DiceRollResult.from_values(
                roll_id="roll:horror-fixture:hazardous",
                spec=DiceRollSpec(
                    expression=DiceExpression(quantity=1, sides=6),
                    reason=(
                        f"Hazardous tests for {attack_sequence.attacking_unit_instance_id} "
                        f"after {source_phase.value}"
                    ),
                    roll_type="hazardous_test",
                    actor_id=attack_sequence.attacking_unit_instance_id,
                ),
                values=(1,),
                source="fixed",
            ),
        )
        if destruction_kind == "hazardous" and emit_destruction_events
        else ()
    )
    dice_manager = DiceRollManager(
        state.game_id,
        event_log=decisions.event_log,
        injected_results=hazard_rolls
        + tuple(
            DiceRollResult.from_values(
                roll_id=f"roll:split:{pink_datasheet_id}:{destruction_kind}:{index}",
                spec=DiceRollSpec(
                    expression=DiceExpression(quantity=1, sides=6),
                    reason=f"Model materialization for {model.model_instance_id}",
                    roll_type="catalog.model_materialization.trigger",
                    actor_id=source_army.player_id,
                ),
                values=(roll_value,),
                source="fixed",
            )
            for index, (model, roll_value) in enumerate(
                zip(destroyed_models, roll_values, strict=True), start=1
            )
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
        source_phase=source_phase,
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
        destroyed_model_instance_id=destroyed_models[0].model_instance_id,
        destroyed_model_instance_ids=tuple(model.model_instance_id for model in destroyed_models),
        attached_unit_instance_id=(attached_unit_id if attached else bodyguard.unit_instance_id),
    )


def _single_model_unit(
    *,
    package: CanonicalCatalogPackage,
    army_id: str,
    unit_selection_id: str,
    datasheet_id: str,
    model_profile_id: str,
) -> UnitInstance:
    return _model_count_unit(
        package=package,
        army_id=army_id,
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_id=model_profile_id,
        model_count=1,
    )


def _model_count_unit(
    *,
    package: CanonicalCatalogPackage,
    army_id: str,
    unit_selection_id: str,
    datasheet_id: str,
    model_profile_id: str,
    model_count: int,
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
    return replace(unit, own_models=unit.own_models[:model_count])


def _retained_horror_model(
    *,
    package: CanonicalCatalogPackage,
    pink_datasheet_id: str,
    bodyguard: UnitInstance,
    horror_kind: str,
    index: int,
) -> ModelInstance:
    if horror_kind == "blue":
        name = "Blue Horror"
        wargear_ids = (
            f"{pink_datasheet_id}:coruscating-blue-flames",
            f"{pink_datasheet_id}:blue-claws",
        )
        descriptor_id = "horror-materialization:blue-horror"
    elif horror_kind == "brimstone":
        name = "Brimstone Horror"
        wargear_ids = (
            f"{pink_datasheet_id}:coruscating-yellow-flames",
            f"{pink_datasheet_id}:yellow-claws",
        )
        descriptor_id = "horror-materialization:brimstone-horror"
    else:
        raise AssertionError("Unsupported retained Horror kind.")
    return UnitFactory(package.army_catalog).instantiate_materialized_model(
        datasheet_id=pink_datasheet_id,
        model_profile_id=f"{pink_datasheet_id}:blue-horror-brimstone-horror",
        model_instance_id=f"{bodyguard.unit_instance_id}:retained:{horror_kind}:{index}",
        model_name=name,
        wargear_ids=wargear_ids,
        source_id="test:horrors:prior-split",
        materialization_descriptor_id=descriptor_id,
    )


def _army(
    *,
    package: CanonicalCatalogPackage,
    army_id: str,
    player_id: str,
    force_disposition_id: str,
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
            detachment_ids=("daemonic-incursion",),
        ),
        force_disposition_id=force_disposition_id,
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


def _alive_unit_placement_or_none(
    army: ArmyDefinition,
    unit: UnitInstance,
    *,
    origin: Pose,
) -> UnitPlacement | None:
    alive_models = tuple(model for model in unit.own_models if model.is_alive)
    if not alive_models:
        return None
    return UnitPlacement(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=Pose.at(origin.position.x + index * 1.2, origin.position.y),
            )
            for index, model in enumerate(alive_models)
        ),
    )


def _attack_sequence(
    *,
    package: CanonicalCatalogPackage,
    attacker: UnitInstance,
    attacker_player_id: str,
    target: UnitInstance,
    target_unit_instance_id: str,
    source_phase: BattlePhase = BattlePhase.SHOOTING,
) -> AttackSequence:
    wargear_id = attacker.own_models[0].wargear_ids[0]
    wargear = next(item for item in package.army_catalog.wargear if item.wargear_id == wargear_id)
    profile = wargear.weapon_profiles[0]
    pool = RangedAttackPool(
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        weapon_instance_id=f"weapon-instance:test:{attacker.own_models[0].model_instance_id}",
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
        source_phase=source_phase,
        used_pool_indices=(0,),
        pool_index=1,
    )


def _placement_payload(
    *,
    request: Any,
    army: ArmyDefinition,
    unit: UnitInstance,
    y_offset: float = 0.0,
) -> dict[str, JsonValue]:
    request_payload = cast(dict[str, JsonValue], request.payload)
    model_ids = cast(list[str], request_payload["model_instance_ids"])
    poses = (
        Pose.at(10.0, 10.0 + y_offset),
        Pose.at(11.2, 10.0 + y_offset),
    )
    assert 0 < len(model_ids) <= len(poses)
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
            poses[: len(model_ids)],
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


def _authenticated_materialization_evidence(
    *,
    destruction_kind: str,
    destroyed_horror_kinds: tuple[str, ...] = (),
) -> tuple[_SplitScenario, tuple[EventRecord, ...], tuple[DecisionRecord, ...]]:
    scenario = _split_scenario(
        pink_datasheet_id="000002584",
        blue_datasheet_id="000002583",
        destruction_kind=destruction_kind,
        destroyed_horror_kinds=destroyed_horror_kinds,
    )
    status = resolve_horror_completion(scenario.runtime, scenario.context)
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = scenario.decisions.queue.peek_next()
    result = _parameterized_result(
        request=request,
        payload=_placement_payload(
            request=request,
            army=scenario.source_army,
            unit=scenario.bodyguard,
        ),
        result_id=f"result:authenticated-materialization:{destruction_kind}",
    )
    scenario.decisions.submit_result(result)
    placements = apply_recorded_catalog_model_materialization_placement(
        state=scenario.state,
        decisions=scenario.decisions,
        request=request,
        result=result,
        ability_indexes_by_player_id=scenario.runtime.ability_indexes_by_player_id,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=scenario.package.army_catalog,
    )
    assert placements
    event_records = scenario.decisions.event_log.records
    decision_records = scenario.decisions.records
    authenticated = authenticated_catalog_materialized_model_payloads_by_unit_id(
        game_id=scenario.state.game_id,
        catalog=scenario.package.army_catalog,
        expected_armies=(scenario.source_army, scenario.enemy_army),
        event_records=event_records,
        decision_records=decision_records,
    )
    assert set(authenticated) == {scenario.bodyguard.unit_instance_id}
    return scenario, event_records, decision_records


def _unique_event_index(events: list[EventRecord], event_type: str) -> int:
    matches = tuple(index for index, event in enumerate(events) if event.event_type == event_type)
    assert len(matches) == 1
    return matches[0]


def _corrupt_authenticated_materialization_evidence(
    *,
    scenario: _SplitScenario,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    tamper_kind: str,
) -> tuple[tuple[EventRecord, ...], tuple[DecisionRecord, ...]]:
    events = list(event_records)
    records = list(decision_records)
    materialized_index = _unique_event_index(events, CATALOG_MODELS_MATERIALIZED_EVENT)
    roll_index = _unique_event_index(events, CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT)
    completion_index = _unique_event_index(events, "attack_sequence_completed")
    materialized = cast(dict[str, JsonValue], events[materialized_index].payload)
    (record_index,) = tuple(
        index
        for index, record in enumerate(records)
        if record.result.result_id == materialized["result_id"]
    )
    selected = records[record_index]
    (requested_index,) = tuple(
        index
        for index, event in enumerate(events)
        if event.event_type == "decision_requested"
        and cast(dict[str, JsonValue], event.payload)["request_id"] == selected.request.request_id
    )
    (recorded_index,) = tuple(
        index
        for index, event in enumerate(events)
        if event.event_type == "decision_recorded"
        and cast(dict[str, JsonValue], event.payload)["record_id"] == selected.record_id
    )

    if tamper_kind == "materialized_game_id":
        payload = copy.deepcopy(cast(dict[str, JsonValue], events[materialized_index].payload))
        payload["game_id"] = "game:unrelated"
        events[materialized_index] = replace(events[materialized_index], payload=payload)
    elif tamper_kind == "missing_request_id":
        payload = copy.deepcopy(cast(dict[str, JsonValue], events[materialized_index].payload))
        payload["request_id"] = None
        events[materialized_index] = replace(events[materialized_index], payload=payload)
    elif tamper_kind == "missing_decision_record":
        payload = copy.deepcopy(cast(dict[str, JsonValue], events[materialized_index].payload))
        payload["result_id"] = "result:unrelated"
        events[materialized_index] = replace(events[materialized_index], payload=payload)
    elif tamper_kind == "malformed_request_payload":
        record = records[record_index]
        records[record_index] = replace(record, request=replace(record.request, payload=None))
    elif tamper_kind in {"inactive_source", "request_payload", "roll_identity"}:
        record = records[record_index]
        request_payload = copy.deepcopy(cast(dict[str, JsonValue], record.request.payload))
        if tamper_kind == "inactive_source":
            request_payload["catalog_record_id"] = "catalog-record:unrelated"
        elif tamper_kind == "request_payload":
            request_payload["submission_kind"] = "submission:unrelated"
        else:
            request_payload["roll_event_id"] = events[completion_index].event_id
        records[record_index] = replace(
            record, request=replace(record.request, payload=request_payload)
        )
    elif tamper_kind == "decision_identity":
        record = records[record_index]
        request = replace(record.request, decision_type="decision:unrelated")
        result = replace(record.result, decision_type=request.decision_type)
        records[record_index] = replace(record, request=request, result=result)
    elif tamper_kind == "malformed_result_payload":
        record = records[record_index]
        records[record_index] = replace(record, result=replace(record.result, payload=None))
    elif tamper_kind in {"accepted_placement", "accepted_model_set"}:
        record = records[record_index]
        result_payload = copy.deepcopy(cast(dict[str, JsonValue], record.result.payload))
        if tamper_kind == "accepted_placement":
            result_payload["placement_kind"] = BattlefieldPlacementKind.DEPLOYMENT.value
        else:
            placement = cast(dict[str, JsonValue], result_payload["attempted_placement"])
            model_placements = cast(list[JsonValue], placement["model_placements"])
            model_placement = cast(dict[str, JsonValue], model_placements[0])
            model_placement["model_instance_id"] = (
                f"{scenario.bodyguard.unit_instance_id}:unrelated-model"
            )
        records[record_index] = replace(
            record, result=replace(record.result, payload=result_payload)
        )
    elif tamper_kind in {
        "roll_context",
        "destroyed_model_source",
        "malformed_roll_payload",
        "roll_specification",
        "unsuccessful_roll",
        "invalid_battle_round",
    }:
        roll_payload = copy.deepcopy(cast(dict[str, JsonValue], events[roll_index].payload))
        if tamper_kind == "roll_context":
            roll_payload["result_count"] = 3
        elif tamper_kind == "destroyed_model_source":
            roll_payload["destroyed_model_instance_id"] = scenario.leader.own_models[
                0
            ].model_instance_id
        elif tamper_kind == "malformed_roll_payload":
            roll_payload["roll"] = None
        elif tamper_kind == "roll_specification":
            raw_roll = cast(dict[str, JsonValue], roll_payload["roll"])
            original_result = cast(dict[str, JsonValue], raw_roll["original_result"])
            spec = cast(dict[str, JsonValue], original_result["spec"])
            spec["reason"] = "Unrelated roll"
        elif tamper_kind == "unsuccessful_roll":
            raw_roll = cast(dict[str, JsonValue], roll_payload["roll"])
            original_result = cast(dict[str, JsonValue], raw_roll["original_result"])
            original_result["values"] = [1]
            original_result["total"] = 1
            raw_roll["current_values"] = [1]
            raw_roll["current_total"] = 1
        else:
            roll_payload["battle_round"] = "1"
        events[roll_index] = replace(events[roll_index], payload=roll_payload)
    elif tamper_kind == "completion_sequence":
        payload = copy.deepcopy(cast(dict[str, JsonValue], events[completion_index].payload))
        payload["sequence_id"] = "attack-sequence:unrelated"
        events[completion_index] = replace(events[completion_index], payload=payload)
    elif tamper_kind == "roll_before_completion":
        events[completion_index], events[roll_index] = events[roll_index], events[completion_index]
    elif tamper_kind == "destruction_evidence":
        destroyed_index = _unique_event_index(events, "model_destroyed")
        events.pop(destroyed_index)
    elif tamper_kind == "evidence_order":
        events[requested_index], events[recorded_index] = (
            events[recorded_index],
            events[requested_index],
        )
    elif tamper_kind == "missing_terminal":
        events.pop(materialized_index + 1)
    elif tamper_kind == "terminal_payload":
        terminal_index = materialized_index + 1
        payload = copy.deepcopy(cast(dict[str, JsonValue], events[terminal_index].payload))
        payload["source_rule_id"] = "source-rule:unrelated"
        events[terminal_index] = replace(events[terminal_index], payload=payload)
    elif tamper_kind in {"request_provenance", "record_provenance"}:
        provenance_index = (
            requested_index if tamper_kind == "request_provenance" else recorded_index
        )
        payload = copy.deepcopy(cast(dict[str, JsonValue], events[provenance_index].payload))
        payload["tampered"] = True
        events[provenance_index] = replace(events[provenance_index], payload=payload)
    elif tamper_kind == "malformed_materialized_event":
        events[materialized_index] = replace(events[materialized_index], payload=None)
    elif tamper_kind == "malformed_completion_event":
        events[completion_index] = replace(events[completion_index], payload=None)
    elif tamper_kind == "completion_payload":
        payload = copy.deepcopy(cast(dict[str, JsonValue], events[materialized_index].payload))
        payload["action_phase"] = BattlePhase.MOVEMENT.value
        events[materialized_index] = replace(events[materialized_index], payload=payload)
    else:
        raise AssertionError(f"Unsupported authenticated evidence tamper: {tamper_kind}")
    return tuple(events), tuple(records)


def _tamper_materialization_lifecycle_payload(
    lifecycle_payload: Any,
    *,
    tamper_kind: str,
) -> None:
    decisions_payload = cast(dict[str, Any], lifecycle_payload["decisions"])
    queue_payload = cast(dict[str, Any], decisions_payload["queue"])
    request_payload = cast(
        dict[str, Any],
        cast(list[dict[str, Any]], queue_payload["pending_requests"])[0]["payload"],
    )
    if tamper_kind == "source_rule":
        request_payload["source_rule_id"] = "tampered:source-rule"
        return
    if tamper_kind == "clause":
        request_payload["clause_id"] = "tampered:clause"
        return
    if tamper_kind == "descriptor":
        request_payload["materialization_descriptor_id"] = "tampered:descriptor"
        return
    if tamper_kind == "model_profile":
        cast(list[dict[str, Any]], request_payload["models"])[0]["model_profile_id"] = (
            "tampered:model-profile"
        )
        return
    if tamper_kind == "wargear":
        model = cast(list[dict[str, Any]], request_payload["models"])[0]
        cast(list[str], model["wargear_ids"])[0] = "tampered:wargear"
        return
    if tamper_kind == "model_ids":
        model_ids = cast(list[str], request_payload["model_instance_ids"])
        model_ids[0] = f"{model_ids[0]}:tampered"
        return
    event_payloads = cast(list[dict[str, Any]], decisions_payload["event_log"])
    roll_payload = next(
        cast(dict[str, Any], event["payload"])
        for event in event_payloads
        if event["event_type"] == CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT
    )
    if tamper_kind == "roll":
        cast(dict[str, Any], roll_payload["roll"])["current_total"] = 1
        return
    if tamper_kind == "result_count":
        roll_payload["result_count"] = 3
        return
    raise AssertionError(f"Unsupported tamper kind: {tamper_kind}")


def _unit_by_id(state: GameState, unit_instance_id: str) -> UnitInstance:
    matches = tuple(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == unit_instance_id
    )
    assert len(matches) == 1
    return matches[0]


def _record_successful_materialization_rolls(scenario: _SplitScenario) -> None:
    source = next(
        source
        for source in scenario.runtime.sources(armies=tuple(scenario.state.army_definitions))
        if source.source_unit_instance_id == scenario.bodyguard.unit_instance_id
        and source.materialization is not None
        and scenario.bodyguard.own_models[0].model_profile_id
        in source.materialization.destroyed_model_profile_ids
    )
    descriptor = source.materialization
    assert descriptor is not None
    parent_battle_phase = scenario.state.current_battle_phase
    assert parent_battle_phase is not None
    manager = DiceRollManager(
        scenario.state.game_id,
        event_log=scenario.decisions.event_log,
    )
    for model_instance_id in scenario.destroyed_model_instance_ids:
        roll = manager.roll_fixed(
            DiceRollSpec(
                expression=DiceExpression(quantity=1, sides=6),
                reason=f"Model materialization for {model_instance_id}",
                roll_type="catalog.model_materialization.trigger",
                actor_id=source.player_id,
            ),
            [6],
        )
        scenario.decisions.event_log.append(
            CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT,
            validate_json_value(
                {
                    "game_id": scenario.state.game_id,
                    "battle_round": scenario.state.battle_round,
                    "phase": parent_battle_phase.value,
                    "action_phase": scenario.attack_sequence.source_phase.value,
                    "parent_battle_phase": parent_battle_phase.value,
                    "attack_sequence_id": scenario.attack_sequence.sequence_id,
                    "attack_sequence_completed_event_id": (
                        scenario.context.attack_sequence_completed_event_id
                    ),
                    "catalog_record_id": source.record.record_id,
                    "clause_id": source.clause.clause_id,
                    "source_rule_id": source.source_rule_id,
                    "source_unit_instance_id": source.source_unit_instance_id,
                    "destroyed_model_instance_id": model_instance_id,
                    "success_threshold": descriptor.success_threshold,
                    "roll": roll.to_payload(),
                    "successful": True,
                    "result_count": descriptor.result_count,
                }
            ),
        )


def _configure_phase_lifecycle(
    *,
    lifecycle: GameLifecycle,
    scenario: _SplitScenario,
) -> None:
    state = lifecycle.state
    assert state is not None
    config = _game_config(scenario)
    from warhammer40k_core.engine.faction_content.runtime import (
        build_runtime_content_bundle_for_armies,
    )

    bundle = build_runtime_content_bundle_for_armies(
        config=config, armies=tuple(state.army_definitions)
    )
    lifecycle._config = config
    lifecycle._runtime_content_bundle = bundle
    lifecycle._runtime_content_activation_input_hash = (
        lifecycle_module._runtime_content_activation_input_hash(
            config=config,
            armies=tuple(state.army_definitions),
        )
    )
    lifecycle._movement_phase_handler = MovementPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    )
    lifecycle._shooting_phase_handler = ShootingPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
        attack_sequence_completed_hooks=bundle.attack_sequence_completed_hook_registry,
        ability_indexes_by_player_id=bundle.ability_indexes_by_player_id,
        runtime_modifier_registry=bundle.runtime_modifier_registry,
    )
    lifecycle._fight_phase_handler = FightPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
        attack_sequence_completed_hooks=bundle.attack_sequence_completed_hook_registry,
        runtime_modifier_registry=bundle.runtime_modifier_registry,
    )
    lifecycle._battle_round_flow = BattleRoundFlow(
        phase_handlers=lifecycle._phase_handlers(),
        runtime_modifier_registry=bundle.runtime_modifier_registry,
        runtime_event_index=bundle.event_index,
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    )


def _restored_phase_lifecycle(
    *,
    lifecycle: GameLifecycle,
    scenario: _SplitScenario,
) -> GameLifecycle:
    payload = lifecycle.to_payload()
    payload["config"] = None
    restored = GameLifecycle.from_payload(payload)
    _configure_phase_lifecycle(lifecycle=restored, scenario=scenario)
    assert restored._config == _game_config(scenario)
    assert restored._runtime_content_bundle is not None
    return restored


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


def _runtime_content_bundle(scenario: _SplitScenario) -> RuntimeContentBundle:
    armies = (scenario.source_army, scenario.enemy_army)
    return RuntimeContentBundle.from_contributions(
        activation=RuntimeContentActivation.from_armies(
            armies=armies,
            catalog=scenario.package.army_catalog,
        ),
        armies=armies,
        catalog=scenario.package.army_catalog,
        contributions=(),
        base_ability_records=catalog_ability_records_from_catalog(scenario.package.army_catalog),
    )


__all__: list[str] = []
__all__ += ["Any", "ArmyDefinition", "ArmyMusterRequest", "AttachedUnitFormation"]
__all__ += ["AttackSequence", "AttackSequenceCompletedContext", "BattlePhase", "BattleRoundFlow"]
__all__ += ["BattlefieldPlacementKind", "BattlefieldRuntimeState", "BattlefieldTransitionBatch"]
__all__ += ["CATALOG_MODELS_MATERIALIZED_EVENT", "BattlefieldTransitionBatchPayload"]
__all__ += ["CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT", "CATALOG_UNIT_DATASHEET_REPLACED_EVENT"]
__all__ += ["CanonicalCatalogPackage", "CatalogModelMaterializationRuntime", "Characteristic"]
__all__ += ["DECLINE_DESTRUCTION_REACTION_OPTION_ID", "CharacteristicValue", "DamageProfile"]
__all__ += ["DecisionController", "DecisionRecord", "DecisionResult", "DestructionReactionKind"]
__all__ += ["DestructionReactionSource", "DestructionSourceKind", "DetachmentSelection"]
__all__ += ["DiceExpression", "DiceRollManager", "DiceRollResult", "DiceRollSpec"]
__all__ += ["EffectExpiration", "EventRecord", "FeelNoPainSource", "FightActivationSelection"]
__all__ += ["FightEligibilityKind", "FightPhaseHandler", "FightPhaseState", "FightPhaseStepKind"]
__all__ += ["FightsFirstRegistry", "GameConfig", "GameLifecycle", "GameLifecycleError"]
__all__ += ["GameState", "JsonValue", "LifecycleStatusKind", "LocalGameSession"]
__all__ += ["MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT", "ModelDestructionAttribution"]
__all__ += ["ModelInstance", "ModelPlacement", "ModelProfileSelection", "MovementPhaseHandler"]
__all__ += ["OutOfPhaseShootingState", "PersistingEffect", "PlacedArmy"]
__all__ += ["PlacementProposalPayload", "Pose", "ProposalKind"]
__all__ += ["RULE_MODEL_DESTRUCTION_FINALIZED_EVENT", "RangedAttackPool", "ReactionQueue"]
__all__ += ["ReactionQueueFrame", "ReactionWindow", "RulesetDescriptor"]
__all__ += ["RuntimeContentActivation", "RuntimeContentBundle", "RuntimeContentContribution"]
__all__ += ["RuntimeContentEventContext", "RuntimeContentEventHandlerBinding"]
__all__ += ["RuntimeContentEventResult", "RuntimeContentEventSubscription"]
__all__ += ["RuntimeModifierRegistry"]
__all__ += ["SUBMIT_CATALOG_MODEL_MATERIALIZATION_PLACEMENT_DECISION_TYPE"]
__all__ += ["ShootingPhaseHandler", "ShootingPhaseState", "ShootingType", "TimingTriggerKind"]
__all__ += ["TimingWindow", "TimingWindowDescriptor", "UnitFactory", "UnitInstance"]
__all__ += ["UnitMusterSelection", "UnitPlacement", "WeaponKeyword", "_SplitScenario"]
__all__ += ["_alive_unit_placement_or_none", "_army", "_attack_sequence"]
__all__ += ["_authenticated_materialization_evidence", "_configure_phase_lifecycle"]
__all__ += ["_corrupt_authenticated_materialization_evidence", "_game_config"]
__all__ += ["_model_count_unit", "_parameterized_result", "_placement_payload"]
__all__ += ["_record_split_interrupt_activation", "_record_successful_materialization_rolls"]
__all__ += ["_required_string_list", "_restored_phase_lifecycle", "_retained_horror_model"]
__all__ += ["_runtime_content_bundle", "_single_model_unit", "_split_scenario"]
__all__ += ["_tamper_materialization_lifecycle_payload", "_unique_event_index", "_unit_by_id"]
__all__ += ["_unit_placement", "apply_feel_no_pain_decision"]
__all__ += ["apply_recorded_catalog_model_materialization_placement"]
__all__ += ["assert_parameterized_projection", "attack_sequence_wound_roll_spec"]
__all__ += ["authenticated_catalog_materialized_model_payloads_by_unit_id"]
__all__ += ["battle_phase_kind_from_token", "battle_state_with_armies", "cast"]
__all__ += ["catalog_ability_records_from_catalog", "copy", "dataclass"]
__all__ += ["deadly_demise_trigger_roll_spec", "feel_no_pain_roll_spec", "horrors_package"]
__all__ += ["invalid_catalog_model_materialization_placement_status"]
__all__ += ["is_mortal_wound_model_request", "lifecycle_module", "mandatory_save_option"]
__all__ += ["player_ability_index", "pytest", "reconcile_after_attack_sequence", "replace"]
__all__ += ["resolve_attack_sequence_until_blocked", "resolve_horror_completion"]
__all__ += ["resolve_mortal_wound_decision", "resolve_selected_target_mortal_wound_effect"]
__all__ += ["rule_model_destruction", "rules_unit_view_by_id", "save_options_for_model"]
__all__ += ["saving_throw_roll_spec", "validate_json_value"]
