from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

import pytest
from tests.unit.test_phase11c_command_phase import (
    _battle_state,  # pyright: ignore[reportPrivateUsage]
    _battle_state_with_center_objective_positions,  # pyright: ignore[reportPrivateUsage]
    _default_unit_selection,  # pyright: ignore[reportPrivateUsage]
    _unit_by_id,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import DatasheetDefinition, DatasheetKeywordSet
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.advance_eligibility_hooks import (
    AdvanceEligibilityContext,
    AdvanceEligibilityGrant,
    AdvanceEligibilityHookBinding,
    AdvanceEligibilityHookRegistry,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.faction_content.runtime import build_runtime_content_bundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.emperors_children import (
    army_rule,
)
from warhammer40k_core.engine.fall_back_hooks import FallBackEligibilityContext
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.phases.charge import (
    ChargePhaseState,
    _charge_target_candidates,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.phases.movement import (
    AdvancedUnitState,
    AdvanceRollRequest,
    AdvanceRollResult,
    FellBackUnitState,
    MovementDiceRecord,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.phases.shooting import ShootingPhaseState
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.target_restriction_hooks import (
    ChargeTargetRestrictionContext,
    ChargeTargetRestrictionHookBinding,
    ChargeTargetRestrictionHookRegistry,
    ShootingTargetRestrictionContext,
    ShootingTargetRestrictionHookBinding,
    ShootingTargetRestrictionHookRegistry,
    TargetRestriction,
)
from warhammer40k_core.engine.turn_start_engagement import (
    record_turn_start_engagement_snapshot,
    turn_start_enemy_unit_ids_for_friendly_unit,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.rules.mission_pack_import import (
    chapter_approved_2026_27_mission_pack,
)

EMPERORS_CHILDREN_TEST_DATASHEET_ID = "phase17g-emperors-children-noise-marine"
EMPERORS_CHILDREN_UNIT_ID = "army-alpha:intercessor-unit-1"
ENEMY_UNIT_ID = "army-beta:intercessor-unit-3"


def test_runtime_bundle_loads_thrill_seekers_opt_in_surfaces() -> None:
    bundle = build_runtime_content_bundle(_emperors_children_config())
    summary_payload = bundle.to_summary_payload()

    assert army_rule.ADVANCE_ELIGIBILITY_HOOK_ID in summary_payload["advance_eligibility_hook_ids"]
    assert army_rule.FALL_BACK_ELIGIBILITY_HOOK_ID in summary_payload["fall_back_hook_ids"]
    assert (
        army_rule.SHOOTING_TARGET_RESTRICTION_HOOK_ID
        in summary_payload["shooting_target_restriction_hook_ids"]
    )
    assert (
        army_rule.CHARGE_TARGET_RESTRICTION_HOOK_ID
        in summary_payload["charge_target_restriction_hook_ids"]
    )


def test_thrill_seekers_grants_shoot_and_charge_after_advance_and_fall_back() -> None:
    state = _emperors_children_battle_state()

    advance_grant = army_rule.thrill_seekers_advance_eligibility(
        AdvanceEligibilityContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
            movement_request_id="phase17g-ec-advance-request",
            movement_result_id="phase17g-ec-advance-result",
        )
    )
    fall_back_grant = army_rule.thrill_seekers_fall_back_eligibility(
        FallBackEligibilityContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
            movement_request_id="phase17g-ec-fall-back-request",
            movement_result_id="phase17g-ec-fall-back-result",
        )
    )

    assert advance_grant is not None
    assert advance_grant.can_shoot is True
    assert advance_grant.can_declare_charge is True
    assert fall_back_grant is not None
    assert fall_back_grant.can_shoot is True
    assert fall_back_grant.can_declare_charge is True


def test_thrill_seekers_does_not_apply_to_non_emperors_children_army() -> None:
    state = _battle_state()

    grant = army_rule.thrill_seekers_advance_eligibility(
        AdvanceEligibilityContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
            movement_request_id="phase17g-ec-non-faction-advance-request",
            movement_result_id="phase17g-ec-non-faction-advance-result",
        )
    )

    assert grant is None


def test_thrill_seekers_blocks_target_engaged_with_unit_at_turn_start() -> None:
    state = _emperors_children_battle_state(
        player_a_offsets=((0.0, 0.0),),
        player_b_offsets=((0.0, 0.0),),
    )
    record_turn_start_engagement_snapshot(
        state=state,
        player_id="player-a",
    )
    state.record_advanced_unit_state(
        _advanced_unit_state(state=state, unit_instance_id=EMPERORS_CHILDREN_UNIT_ID)
    )
    _advance_state_to_phase(state, BattlePhase.SHOOTING)

    restriction = army_rule.thrill_seekers_shooting_target_restriction(
        ShootingTargetRestrictionContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            attacking_unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
            target_unit_instance_id=ENEMY_UNIT_ID,
        )
    )

    assert restriction is not None
    assert restriction.violation_code == "thrill_seekers_turn_start_engagement"


def test_thrill_seekers_blocks_target_attacked_by_another_unit_this_phase() -> None:
    state = _emperors_children_battle_state()
    acting_attacker = _unit_by_id(state, EMPERORS_CHILDREN_UNIT_ID)
    other_attacker = _copy_unit_for_test(
        acting_attacker,
        unit_instance_id="army-alpha:noise-marine-unit-2",
    )
    _append_unit_to_player_army(state, player_id="player-a", unit=other_attacker)
    defender = _unit_by_id(state, ENEMY_UNIT_ID)
    state.record_advanced_unit_state(
        _advanced_unit_state(state=state, unit_instance_id=EMPERORS_CHILDREN_UNIT_ID)
    )
    _advance_state_to_phase(state, BattlePhase.SHOOTING)
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        attack_pools=(
            _attack_pool_for_test(
                attacker=other_attacker,
                defender=defender,
                weapon_profile=_first_weapon_profile_for_unit(other_attacker),
            ),
        ),
    )

    restriction = army_rule.thrill_seekers_shooting_target_restriction(
        ShootingTargetRestrictionContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            attacking_unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
            target_unit_instance_id=ENEMY_UNIT_ID,
        )
    )

    assert restriction is not None
    assert restriction.violation_code == "thrill_seekers_target_already_selected"


def test_thrill_seekers_allows_target_already_attacked_by_same_unit_this_phase() -> None:
    state = _emperors_children_battle_state()
    attacker = _unit_by_id(state, EMPERORS_CHILDREN_UNIT_ID)
    defender = _unit_by_id(state, ENEMY_UNIT_ID)
    state.record_advanced_unit_state(
        _advanced_unit_state(state=state, unit_instance_id=EMPERORS_CHILDREN_UNIT_ID)
    )
    _advance_state_to_phase(state, BattlePhase.SHOOTING)
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=_first_weapon_profile_for_unit(attacker),
            ),
        ),
    )

    restriction = army_rule.thrill_seekers_shooting_target_restriction(
        ShootingTargetRestrictionContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            attacking_unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
            target_unit_instance_id=ENEMY_UNIT_ID,
        )
    )

    assert restriction is None


def test_thrill_seekers_charge_target_restriction_reaches_charge_candidate_filter() -> None:
    state = _emperors_children_battle_state(
        player_a_offsets=((0.0, 0.0),),
        player_b_offsets=((6.0, 0.0),),
    )
    state.record_fell_back_unit_state(
        FellBackUnitState(
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
            can_shoot=True,
            can_declare_charge=True,
        )
    )
    _advance_state_to_phase(state, BattlePhase.CHARGE)
    state.charge_phase_state = ChargePhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        declared_target_unit_instance_ids_by_unit={
            "army-alpha:previous-charger": (ENEMY_UNIT_ID,),
        },
    )

    candidates = _charge_target_candidates(
        state=state,
        unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        charge_target_restriction_hooks=(
            build_runtime_content_bundle(
                _emperors_children_config()
            ).charge_target_restriction_hook_registry
        ),
    )

    assert len(candidates) == 1
    assert candidates[0].target_unit_instance_id == ENEMY_UNIT_ID
    assert candidates[0].is_legal is False
    assert candidates[0].violation_code == "thrill_seekers_target_already_selected"


def test_thrill_seekers_charge_restriction_requires_advance_or_fall_back() -> None:
    state = _emperors_children_battle_state()
    _advance_state_to_phase(state, BattlePhase.CHARGE)
    state.charge_phase_state = ChargePhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        declared_target_unit_instance_ids_by_unit={
            "army-alpha:previous-charger": (ENEMY_UNIT_ID,),
        },
    )

    restriction = army_rule.thrill_seekers_charge_target_restriction(
        ChargeTargetRestrictionContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            charging_unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
            target_unit_instance_id=ENEMY_UNIT_ID,
        )
    )

    assert restriction is None


def test_advance_eligibility_registry_fails_fast_on_invalid_bindings() -> None:
    state = _emperors_children_battle_state()
    context = AdvanceEligibilityContext(
        state=state,
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
        movement_request_id="phase17g-ec-registry-request",
        movement_result_id="phase17g-ec-registry-result",
    )

    def _stubbed_invalid_advance_handler(_context: AdvanceEligibilityContext) -> object:
        return object()

    invalid_binding = AdvanceEligibilityHookBinding(
        hook_id="phase17g:advance:invalid",
        source_id="phase17g:advance:source",
        handler=cast(Any, _stubbed_invalid_advance_handler),
    )
    with pytest.raises(GameLifecycleError, match="return grants or None"):
        AdvanceEligibilityHookRegistry.from_bindings((invalid_binding,)).grants_for(context)

    def _stubbed_drift_advance_handler(
        _context: AdvanceEligibilityContext,
    ) -> AdvanceEligibilityGrant:
        return AdvanceEligibilityGrant(
            hook_id="phase17g:advance:other",
            source_id="phase17g:advance:source",
            can_shoot=True,
            can_declare_charge=False,
        )

    drift_binding = AdvanceEligibilityHookBinding(
        hook_id="phase17g:advance:drift",
        source_id="phase17g:advance:source",
        handler=_stubbed_drift_advance_handler,
    )
    with pytest.raises(GameLifecycleError, match="hook_id drift"):
        AdvanceEligibilityHookRegistry.from_bindings((drift_binding,)).grants_for(context)

    with pytest.raises(GameLifecycleError, match="handler must be callable"):
        AdvanceEligibilityHookBinding(
            hook_id="phase17g:advance:not-callable",
            source_id="phase17g:advance:source",
            handler=cast(Any, None),
        )
    with pytest.raises(GameLifecycleError, match="bindings must be a tuple"):
        AdvanceEligibilityHookRegistry(bindings=cast(Any, []))
    with pytest.raises(GameLifecycleError, match="hook IDs must be unique"):
        AdvanceEligibilityHookRegistry.from_bindings((drift_binding, drift_binding))
    with pytest.raises(GameLifecycleError, match="must grant at least one permission"):
        AdvanceEligibilityGrant(
            hook_id="phase17g:advance:no-permission",
            source_id="phase17g:advance:source",
            can_shoot=False,
            can_declare_charge=False,
        )


def test_target_restriction_registries_fail_fast_on_invalid_bindings() -> None:
    state = _emperors_children_battle_state()
    shooting_context = ShootingTargetRestrictionContext(
        state=state,
        player_id="player-a",
        battle_round=state.battle_round,
        attacking_unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
        target_unit_instance_id=ENEMY_UNIT_ID,
    )
    charge_context = ChargeTargetRestrictionContext(
        state=state,
        player_id="player-a",
        battle_round=state.battle_round,
        charging_unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
        target_unit_instance_id=ENEMY_UNIT_ID,
    )

    def _stubbed_invalid_shooting_restriction_handler(
        _context: ShootingTargetRestrictionContext,
    ) -> object:
        return object()

    shooting_binding = ShootingTargetRestrictionHookBinding(
        hook_id="phase17g:shooting:invalid",
        source_id="phase17g:restriction:source",
        handler=cast(Any, _stubbed_invalid_shooting_restriction_handler),
    )
    with pytest.raises(GameLifecycleError, match="return restrictions or None"):
        ShootingTargetRestrictionHookRegistry.from_bindings((shooting_binding,)).restrictions_for(
            shooting_context
        )

    def _stubbed_drift_charge_restriction_handler(
        _context: ChargeTargetRestrictionContext,
    ) -> TargetRestriction:
        return TargetRestriction(
            hook_id="phase17g:charge:other",
            source_id="phase17g:restriction:source",
            violation_code="phase17g_restriction",
            message="Target is restricted by the test hook.",
        )

    charge_binding = ChargeTargetRestrictionHookBinding(
        hook_id="phase17g:charge:drift",
        source_id="phase17g:restriction:source",
        handler=_stubbed_drift_charge_restriction_handler,
    )
    with pytest.raises(GameLifecycleError, match="hook_id drift"):
        ChargeTargetRestrictionHookRegistry.from_bindings((charge_binding,)).restrictions_for(
            charge_context
        )

    with pytest.raises(GameLifecycleError, match="handler must be callable"):
        ShootingTargetRestrictionHookBinding(
            hook_id="phase17g:shooting:not-callable",
            source_id="phase17g:restriction:source",
            handler=cast(Any, None),
        )
    with pytest.raises(GameLifecycleError, match="bindings must be a tuple"):
        ChargeTargetRestrictionHookRegistry(bindings=cast(Any, []))
    with pytest.raises(GameLifecycleError, match="hook IDs must be unique"):
        ChargeTargetRestrictionHookRegistry.from_bindings((charge_binding, charge_binding))
    with pytest.raises(GameLifecycleError, match="message must not be empty"):
        TargetRestriction(
            hook_id="phase17g:restriction:empty-message",
            source_id="phase17g:restriction:source",
            violation_code="phase17g_restriction",
            message=" ",
        )


def test_turn_start_engagement_snapshot_is_idempotent_and_fails_fast() -> None:
    state = _emperors_children_battle_state(
        player_a_offsets=((0.0, 0.0),),
        player_b_offsets=((0.0, 0.0),),
    )

    first_snapshot = record_turn_start_engagement_snapshot(state=state, player_id="player-a")
    second_snapshot = record_turn_start_engagement_snapshot(state=state, player_id="player-a")

    assert first_snapshot is not None
    assert second_snapshot is first_snapshot
    assert turn_start_enemy_unit_ids_for_friendly_unit(
        state,
        player_id="player-a",
        battle_round=state.battle_round,
        friendly_unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
    ) == (ENEMY_UNIT_ID,)

    with pytest.raises(GameLifecycleError, match="requires a GameState"):
        record_turn_start_engagement_snapshot(state=cast(Any, object()), player_id="player-a")
    with pytest.raises(GameLifecycleError, match="lookup requires a GameState"):
        turn_start_enemy_unit_ids_for_friendly_unit(
            cast(Any, object()),
            player_id="player-a",
            battle_round=state.battle_round,
            friendly_unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
        )


def _emperors_children_battle_state(
    *,
    player_a_offsets: tuple[tuple[float, float], ...] = ((0.0, 0.0),),
    player_b_offsets: tuple[tuple[float, float], ...] = ((6.0, 0.0),),
) -> GameState:
    state = _battle_state_with_center_objective_positions(
        player_a_offsets=player_a_offsets,
        player_b_offsets=player_b_offsets,
    )
    _mark_player_as_emperors_children(state, player_id="player-a")
    return state


def _mark_player_as_emperors_children(state: GameState, *, player_id: str) -> None:
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
                    faction_id=army_rule.EMPERORS_CHILDREN_FACTION_ID,
                ),
                units=tuple(
                    replace(unit, faction_keywords=(army_rule.EMPERORS_CHILDREN_FACTION_KEYWORD,))
                    for unit in army.units
                ),
            )
        )
    state.army_definitions = updated_armies


def _copy_unit_for_test(unit: UnitInstance, *, unit_instance_id: str) -> UnitInstance:
    return replace(
        unit,
        unit_instance_id=unit_instance_id,
        own_models=tuple(
            replace(model, model_instance_id=f"{unit_instance_id}:model-{index + 1}")
            for index, model in enumerate(unit.own_models)
        ),
    )


def _append_unit_to_player_army(state: GameState, *, player_id: str, unit: UnitInstance) -> None:
    state.army_definitions = [
        replace(army, units=(*army.units, unit)) if army.player_id == player_id else army
        for army in state.army_definitions
    ]


def _advanced_unit_state(*, state: GameState, unit_instance_id: str) -> AdvancedUnitState:
    request = AdvanceRollRequest.for_unit(
        request_id=f"phase17g-ec-advance-{unit_instance_id}",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-a",
        unit_instance_id=unit_instance_id,
    )
    roll_state = DiceRollManager("phase17g-ec-advance-state").roll_fixed(
        request.spec,
        [3],
    )
    advance_roll = AdvanceRollResult.from_roll_state(request=request, roll_state=roll_state)
    return AdvancedUnitState(
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=unit_instance_id,
        movement_dice_record=MovementDiceRecord(
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=unit_instance_id,
            movement_phase_action=MovementPhaseActionKind.ADVANCE,
            advance_roll=advance_roll,
        ),
        can_shoot=True,
        can_declare_charge=True,
    )


def _advance_state_to_phase(state: GameState, phase: BattlePhase) -> None:
    while state.current_battle_phase is not phase:
        if state.current_battle_phase is None:
            raise AssertionError("battle state ended before expected phase")
        state.advance_to_next_battle_phase()


def _attack_pool_for_test(
    *,
    attacker: UnitInstance,
    defender: UnitInstance,
    weapon_profile: WeaponProfile,
) -> RangedAttackPool:
    defender_model_ids = tuple(model.model_instance_id for model in defender.own_models)
    return RangedAttackPool(
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
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
    for wargear in ArmyCatalog.phase9a_canonical_content_pack().wargear:
        if wargear.wargear_id == wargear_id:
            return wargear.weapon_profiles[0]
    raise AssertionError(f"Missing test wargear {wargear_id}.")


def _emperors_children_config() -> GameConfig:
    catalog = _emperors_children_catalog()
    return GameConfig(
        game_id="phase17g-emperors-children-lifecycle-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
            descriptor_version="core-v2-phase17g-emperors-children-test",
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
                    faction_id=army_rule.EMPERORS_CHILDREN_FACTION_ID,
                    detachment_ids=("frenzied-host",),
                ),
                unit_selections=(
                    UnitMusterSelection(
                        unit_selection_id="noise-marine",
                        datasheet_id=EMPERORS_CHILDREN_TEST_DATASHEET_ID,
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
                unit_selections=(_default_unit_selection("enemy-unit"),),
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


def _emperors_children_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    return replace(
        base_catalog,
        datasheets=(*base_catalog.datasheets, _emperors_children_datasheet(base_datasheet)),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id=army_rule.EMPERORS_CHILDREN_FACTION_ID,
                name="Emperor's Children",
                faction_keywords=(army_rule.EMPERORS_CHILDREN_FACTION_KEYWORD,),
                source_ids=("gw-11e-faction-detachments-2026-27:faction:emperors-children",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                detachment_id="frenzied-host",
                name="Frenzied Host",
                faction_id=army_rule.EMPERORS_CHILDREN_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(EMPERORS_CHILDREN_TEST_DATASHEET_ID,),
                force_disposition_ids=("phase17g-force",),
                source_ids=(
                    "gw-11e-faction-detachments-2026-27:detachment:emperors-children:frenzied-host",
                ),
            ),
        ),
    )


def _emperors_children_datasheet(base_datasheet: DatasheetDefinition) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=EMPERORS_CHILDREN_TEST_DATASHEET_ID,
        name="Noise Marine",
        keywords=DatasheetKeywordSet(
            keywords=("Infantry", "Battleline"),
            faction_keywords=(army_rule.EMPERORS_CHILDREN_FACTION_KEYWORD,),
        ),
        attachment_eligibilities=(),
        source_ids=("phase17g:test:emperors-children:noise-marine",),
    )
