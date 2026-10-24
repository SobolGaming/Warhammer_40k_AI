from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import cast

from tests.phase11c_command_phase_helpers import (
    battle_state_with_center_objective_positions,
    default_unit_selection,
)
from tests.unit_keyword_helpers import with_unit_keywords
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import DatasheetDefinition, DatasheetKeywordSet
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.dice import DiceRollResult, DiceRollSpec
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
)
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    AttackSequenceStep,
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
    resolve_attack_sequence_until_blocked,
)
from warhammer40k_core.engine.battle_formation_hooks import (
    SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE,
    BattleFormationRequestContext,
    BattleFormationResultContext,
)
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario, UnitPlacement
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.death_guard import (
    army_rule,
)
from warhammer40k_core.engine.faction_rule_states import FactionRuleState
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    BattlePhase,
    LifecycleStatus,
    SetupStep,
)
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
)
from warhammer40k_core.engine.saves import (
    SaveKind,
    saving_throw_roll_spec,
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack

DEATH_GUARD_TEST_DATASHEET_ID = "phase17g-death-guard-plague-marine"


DEATH_GUARD_UNIT_ID = "army-alpha:intercessor-unit-1"


ENEMY_UNIT_ID = "army-beta:intercessor-unit-3"


def _scenario_from_state(state: GameState) -> BattlefieldScenario:
    if state.battlefield_state is None:
        raise AssertionError("Death Guard test state requires battlefield_state.")
    return BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )


def _full_unit_straight_line_witness(
    *,
    unit_placement: UnitPlacement,
    delta_x: float,
    delta_y: float,
) -> PathWitness:
    model_paths: list[tuple[str, Pose, Pose]] = []
    for placement in unit_placement.model_placements:
        model_paths.append(
            (
                placement.model_instance_id,
                placement.pose,
                Pose.at(
                    x=placement.pose.position.x + delta_x,
                    y=placement.pose.position.y + delta_y,
                    z=placement.pose.position.z,
                    facing_degrees=placement.pose.facing.degrees,
                ),
            )
        )
    return PathWitness.for_straight_line_endpoints(tuple(model_paths))


def _death_guard_runtime_modifier_registry() -> RuntimeModifierRegistry:
    contribution = army_rule.runtime_contribution()
    return RuntimeModifierRegistry.from_bindings(
        unit_characteristic_modifier_bindings=contribution.unit_characteristic_modifier_bindings,
        hit_roll_modifier_bindings=contribution.hit_roll_modifier_bindings,
        save_option_modifier_bindings=contribution.save_option_modifier_bindings,
        movement_budget_modifier_bindings=contribution.movement_budget_modifier_bindings,
        objective_control_modifier_bindings=contribution.objective_control_modifier_bindings,
    )


def _single_attack_hit_payload(
    *,
    state: GameState,
    attacker: UnitInstance,
    defender: UnitInstance,
    source_phase: BattlePhase,
    sequence_id: str,
    hit_roll: int,
) -> dict[str, object]:
    weapon_profile = replace(
        _first_weapon_profile_for_unit(attacker),
        profile_id=f"{sequence_id}:weapon",
    )
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    decisions = DecisionController()
    resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        attack_sequence=AttackSequence.start(
            sequence_id=sequence_id,
            attacker_player_id=attacker_player_id(attacker),
            attacking_unit_instance_id=attacker.unit_instance_id,
            source_phase=source_phase,
            attack_pools=(
                _attack_pool_for_test(
                    attacker=attacker,
                    defender=defender,
                    weapon_profile=weapon_profile,
                ),
            ),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            sequence_id,
            event_log=decisions.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:hit",
                    spec=attack_sequence_hit_roll_spec(
                        weapon_profile_id=weapon_profile.profile_id,
                        attack_context_id=attack_context_id,
                        attacker_player_id=attacker_player_id(attacker),
                    ),
                    value=hit_roll,
                ),
            ),
        ),
        runtime_modifier_registry=_death_guard_runtime_modifier_registry(),
    )
    hit_event = _attack_step_payload(
        _event_payloads(decisions, "attack_sequence_step"),
        AttackSequenceStep.HIT,
    )
    return cast(dict[str, object], hit_event["payload"])


def _single_attack_save_payload(
    *,
    state: GameState,
    attacker: UnitInstance,
    defender: UnitInstance,
    defender_model_id: str,
    sequence_id: str,
    save_roll: int,
) -> dict[str, object]:
    weapon_profile = replace(
        _first_weapon_profile_for_unit(attacker),
        profile_id=f"{sequence_id}:weapon",
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
    )
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    decisions = DecisionController()
    resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        attack_sequence=AttackSequence.start(
            sequence_id=sequence_id,
            attacker_player_id=attacker_player_id(attacker),
            attacking_unit_instance_id=attacker.unit_instance_id,
            attack_pools=(
                _attack_pool_for_test(
                    attacker=attacker,
                    defender=defender,
                    weapon_profile=weapon_profile,
                    target_model_ids=(defender_model_id,),
                ),
            ),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            sequence_id,
            event_log=decisions.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:hit",
                    spec=attack_sequence_hit_roll_spec(
                        weapon_profile_id=weapon_profile.profile_id,
                        attack_context_id=attack_context_id,
                        attacker_player_id=attacker_player_id(attacker),
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:wound",
                    spec=attack_sequence_wound_roll_spec(
                        weapon_profile_id=weapon_profile.profile_id,
                        attack_context_id=attack_context_id,
                        attacker_player_id=attacker_player_id(attacker),
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:save",
                    spec=saving_throw_roll_spec(
                        save_kind=SaveKind.ARMOUR,
                        player_id=defender_player_id(defender),
                        allocated_model_id=defender_model_id,
                        attack_context_id=attack_context_id,
                    ),
                    value=save_roll,
                ),
            ),
        ),
        runtime_modifier_registry=_death_guard_runtime_modifier_registry(),
    )
    save_event = _attack_step_payload(
        _event_payloads(decisions, "attack_sequence_step"),
        AttackSequenceStep.SAVE,
    )
    return cast(dict[str, object], save_event["payload"])


def _attack_pool_for_test(
    *,
    attacker: UnitInstance,
    defender: UnitInstance,
    weapon_profile: WeaponProfile,
    target_model_ids: tuple[str, ...] | None = None,
) -> RangedAttackPool:
    defender_model_ids = (
        tuple(model.model_instance_id for model in defender.own_models)
        if target_model_ids is None
        else target_model_ids
    )
    return RangedAttackPool(
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        weapon_instance_id=f"weapon-instance:test:{weapon_profile.profile_id}",
        wargear_id=attacker.wargear_selections[0].wargear_ids[0],
        weapon_profile_id=weapon_profile.profile_id,
        weapon_profile=weapon_profile,
        target_unit_instance_id=defender.unit_instance_id,
        shooting_type=ShootingType.NORMAL,
        attacks=1,
        target_visible_model_ids=defender_model_ids,
        target_in_range_model_ids=defender_model_ids,
    )


def _first_weapon_profile_for_unit(unit: UnitInstance) -> WeaponProfile:
    wargear_id = unit.wargear_selections[0].wargear_ids[0]
    for wargear in _death_guard_catalog().wargear:
        if wargear.wargear_id == wargear_id:
            return wargear.weapon_profiles[0]
    raise AssertionError(f"Missing test wargear {wargear_id}.")


def _fixed_roll_result(
    *,
    roll_id: str,
    spec: DiceRollSpec,
    value: int,
) -> DiceRollResult:
    return DiceRollResult.from_values(
        roll_id=roll_id,
        spec=spec,
        values=(value,),
        source="fixed",
    )


def _event_payloads(
    decisions: DecisionController,
    event_type: str,
) -> tuple[dict[str, object], ...]:
    return tuple(
        cast(dict[str, object], event.payload)
        for event in decisions.event_log.records
        if event.event_type == event_type
    )


def _attack_step_payload(
    events: tuple[dict[str, object], ...],
    step: AttackSequenceStep,
) -> dict[str, object]:
    for event in events:
        if event["step"] == step.value:
            return event
    raise AssertionError(f"Missing attack sequence step {step.value}.")


def attacker_player_id(unit: UnitInstance) -> str:
    if unit.unit_instance_id.startswith("army-alpha:"):
        return "player-a"
    if unit.unit_instance_id.startswith("army-beta:"):
        return "player-b"
    raise AssertionError(f"Unknown attacker unit owner for {unit.unit_instance_id}.")


def defender_player_id(unit: UnitInstance) -> str:
    return attacker_player_id(unit)


def _death_guard_battle_state(plague: army_rule.NurglesGiftPlague) -> GameState:
    state = battle_state_with_center_objective_positions(
        player_a_offsets=((0.0, 0.0),),
        player_b_offsets=((2.0, -3.0), (2.0, -1.5), (2.0, 0.0), (2.0, 1.5), (2.0, 3.0)),
    )
    _mark_player_as_death_guard(state, player_id="player-a")
    _record_plague_selection(state, player_id="player-a", plague=plague)
    return state


def _mark_player_as_death_guard(state: GameState, *, player_id: str) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != player_id:
            updated_armies.append(army)
            continue
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            updated_units.append(with_unit_keywords(unit, faction_keywords=("Death Guard",)))
        updated_armies.append(
            replace(
                army,
                detachment_selection=replace(
                    army.detachment_selection,
                    faction_id=army_rule.DEATH_GUARD_FACTION_ID,
                ),
                units=tuple(updated_units),
            )
        )
    state.army_definitions = updated_armies


def _record_plague_selection(
    state: GameState,
    *,
    player_id: str,
    plague: army_rule.NurglesGiftPlague,
) -> None:
    state.record_faction_rule_state(
        FactionRuleState(
            state_id=f"{army_rule.HOOK_ID}:{player_id}:plague-selection",
            player_id=player_id,
            faction_id=army_rule.DEATH_GUARD_FACTION_ID,
            source_rule_id=army_rule.SOURCE_RULE_ID,
            state_kind=army_rule.NURGLES_GIFT_STATE_KIND,
            setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
            request_id="phase17g-death-guard-test-request",
            result_id=f"phase17g-death-guard-test-result:{plague.value}",
            payload={
                "plague_id": plague.value,
                "hook_id": army_rule.HOOK_ID,
            },
        )
    )


def _test_battle_formation_request(
    *,
    context: BattleFormationRequestContext,
    hook_id: str,
) -> DecisionRequest:
    return DecisionRequest(
        request_id=context.state.next_decision_request_id(),
        decision_type=SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE,
        actor_id="player-a",
        payload={
            "hook_id": hook_id,
            "setup_step": SetupStep.DECLARE_BATTLE_FORMATIONS.value,
        },
        options=(
            DecisionOption(
                option_id=f"{hook_id}:option",
                label=hook_id,
                payload={"hook_id": hook_id},
            ),
        ),
    )


def _bad_battle_formation_request_handler(
    context: BattleFormationRequestContext,
) -> DecisionRequest | None:
    assert type(context) is BattleFormationRequestContext
    return cast(DecisionRequest, object())


def _bad_battle_formation_result_handler(context: BattleFormationResultContext) -> bool:
    assert type(context) is BattleFormationResultContext
    return cast(bool, "yes")


def _advance_through_secondary_choices(lifecycle: GameLifecycle) -> LifecycleStatus:
    status = lifecycle.advance_until_decision_or_terminal()
    for result_id in (
        "phase17g-death-guard-secondary-player-a",
        "phase17g-death-guard-secondary-player-b",
    ):
        request = status.decision_request
        assert request is not None
        status = lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id=result_id,
                request=request,
                selected_option_id="fixed:assassination:bring_it_down",
            )
        )
    return status


def _death_guard_config() -> GameConfig:
    catalog = _death_guard_catalog()
    return GameConfig(
        game_id="phase17g-death-guard-lifecycle-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
            descriptor_version="core-v2-phase17g-death-guard-test",
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
                    faction_id=army_rule.DEATH_GUARD_FACTION_ID,
                    detachment_ids=("plague-company",),
                ),
                force_disposition_id="take-and-hold",
                unit_selections=(
                    UnitMusterSelection(
                        unit_selection_id="plague-marine",
                        datasheet_id=DEATH_GUARD_TEST_DATASHEET_ID,
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
                force_disposition_id="purge-the-foe",
                unit_selections=(default_unit_selection("enemy-unit"),),
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


def _death_guard_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    death_guard_datasheet = _death_guard_datasheet(base_datasheet)
    return replace(
        base_catalog,
        datasheets=(*base_catalog.datasheets, death_guard_datasheet),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id=army_rule.DEATH_GUARD_FACTION_ID,
                name="Death Guard",
                faction_keywords=("Death Guard",),
                source_ids=("gw-11e-faction-detachments-2026-27:faction:death-guard",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                canonical_detachment_id="plague-company",
                detachment_id="plague-company",
                name="Plague Company",
                faction_id=army_rule.DEATH_GUARD_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(DEATH_GUARD_TEST_DATASHEET_ID,),
                force_disposition_ids=("phase17g-force", "take-and-hold"),
                source_ids=(
                    "gw-11e-faction-detachments-2026-27:detachment:death-guard:plague-company",
                ),
            ),
        ),
    )


def _death_guard_datasheet(base_datasheet: DatasheetDefinition) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=DEATH_GUARD_TEST_DATASHEET_ID,
        name="Plague Marine",
        keywords=DatasheetKeywordSet(
            keywords=("Infantry", "Battleline"),
            faction_keywords=("Death Guard",),
        ),
        attachment_eligibilities=(),
        source_ids=("phase17g:test:death-guard:plague-marine",),
    )


def _runtime_content_bundle(lifecycle: GameLifecycle) -> RuntimeContentBundle:
    require_runtime_content_bundle = cast(
        Callable[[], RuntimeContentBundle],
        object.__getattribute__(lifecycle, "_require_runtime_content_bundle"),
    )
    return require_runtime_content_bundle()


__all__ = [
    "_advance_through_secondary_choices",
    "_attack_pool_for_test",
    "_attack_step_payload",
    "_bad_battle_formation_request_handler",
    "_bad_battle_formation_result_handler",
    "_death_guard_battle_state",
    "_death_guard_catalog",
    "_death_guard_config",
    "_death_guard_datasheet",
    "_death_guard_runtime_modifier_registry",
    "_event_payloads",
    "_first_weapon_profile_for_unit",
    "_fixed_roll_result",
    "_full_unit_straight_line_witness",
    "_mark_player_as_death_guard",
    "_record_plague_selection",
    "_runtime_content_bundle",
    "_scenario_from_state",
    "_single_attack_hit_payload",
    "_single_attack_save_payload",
    "_test_battle_formation_request",
    "attacker_player_id",
    "defender_player_id",
]
