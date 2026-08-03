from __future__ import annotations

import json
from dataclasses import replace
from functools import lru_cache
from typing import Any, cast

import pytest
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)
from tools.generate_emperors_children_lucius_rule_ir import (
    OUTPUT_PATH as LUCIUS_RULE_IR_OUTPUT_PATH,
)
from tools.generate_emperors_children_lucius_rule_ir import (
    generated_artifact_payload as generated_lucius_rule_ir_artifact_payload,
)

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import AbilityKind, WeaponKeyword, WeaponProfile
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.ability_catalog import (
    build_player_ability_index,
    catalog_ability_records_from_catalog,
)
from warhammer40k_core.engine.ability_coverage import (
    AbilityCoverageSupportStage,
    ability_coverage_rows_from_catalog,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.catalog_datasheet_rule_runtime import (
    CatalogDatasheetRuleRuntime,
)
from warhammer40k_core.engine.catalog_datasheet_rule_support import (
    CATALOG_IR_CONDITIONAL_NOT_LEADING_FIGHTS_FIRST_CONSUMER_ID,
    CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID,
    CATALOG_IR_WOUND_ROLL_REROLL_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_ir_consumers_for_rule,
)
from warhammer40k_core.engine.core_descriptor_consumption import (
    CORE_LONE_OPERATIVE_SHOOTING_TARGET_CONSUMER_ID,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.effects import EffectExpirationBoundary, EffectExpirationKind
from warhammer40k_core.engine.faction_content.events import (
    RuntimeContentEvent,
    RuntimeContentEventHandlerRegistry,
    RuntimeContentEventIndex,
    RuntimeContentEventResult,
)
from warhammer40k_core.engine.fights_first import FightsFirstRegistry
from warhammer40k_core.engine.game_state import GameState, GameStatePayload
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.runtime_modifiers import (
    AttackRerollPermissionContext,
    RuntimeModifierRegistry,
)
from warhammer40k_core.engine.shooting_targets import (
    ShootingTargetViolationCode,
    shooting_target_candidates_for_unit,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.rule_ir import RuleIR
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    emperors_children_lucius_2026_07 as lucius_source_package,
)

_LUCIUS_ID = "000004083"
_FLAWLESS_BLADES_ID = "000004089"
_NIGHT_SPINNER_ID = "000000611"
_AUTARCH_ID = "000000577"
_WAR_WALKER_ID = "000000612"
_BELAKOR_ID = "000001148"


def test_lucius_generated_rule_ir_and_catalog_are_complete_and_source_bound() -> None:
    committed = cast(
        dict[str, Any],
        json.loads(LUCIUS_RULE_IR_OUTPUT_PATH.read_text(encoding="utf-8")),
    )

    assert committed == generated_lucius_rule_ir_artifact_payload()
    assert lucius_source_package.supported_datasheet_source_row_ids() == (
        f"{_LUCIUS_ID}:5",
        f"{_LUCIUS_ID}:6",
    )
    assert committed["package_hash"] == lucius_source_package.PACKAGE_HASH
    assert committed["official_document_pages"] == []
    assert committed["review_row_id"] == f"source:{_LUCIUS_ID}"
    assert committed["review_treatment"] == "unchanged_predecessor"

    committed["package_hash"] = "0" * 64
    with pytest.raises(lucius_source_package.LuciusRuleIrArtifactError, match="hash is stale"):
        lucius_source_package.validate_generated_artifact_bytes(json.dumps(committed).encode())

    package = _catalog_package()
    datasheet = package.army_catalog.datasheet_by_id(_LUCIUS_ID)
    characteristics = {
        value.characteristic: value.final for value in datasheet.model_profiles[0].characteristics
    }
    assert (
        characteristics[Characteristic.MOVEMENT],
        characteristics[Characteristic.TOUGHNESS],
        characteristics[Characteristic.SAVE],
        characteristics[Characteristic.WOUNDS],
        characteristics[Characteristic.LEADERSHIP],
        characteristics[Characteristic.OBJECTIVE_CONTROL],
        characteristics[Characteristic.INVULNERABLE_SAVE],
    ) == (8, 5, 2, 6, 6, 1, 4)
    assert datasheet.model_profiles[0].base_size.diameter_mm == 50.0
    assert tuple(
        (eligibility.role.value, target.bodyguard_datasheet_id)
        for eligibility in datasheet.attachment_eligibilities
        for target in eligibility.targets
    ) == (("leader", _FLAWLESS_BLADES_ID),)
    geometry = next(
        record
        for record in package.model_geometries
        if record.model_profile_id == datasheet.model_profiles[0].model_profile_id
    )
    assert geometry.height.height_inches == 2.25
    assert {ability.name for ability in datasheet.abilities} == {
        "A Challenge Worthy of Skill",
        "Duellist's Hubris",
        "Feel No Pain",
        "Leader",
        "Lone Operative",
        "Thrill Seekers",
    }
    lone_operative_coverage = next(
        row
        for row in ability_coverage_rows_from_catalog(
            package.army_catalog,
            datasheet_ids=(_LUCIUS_ID,),
        )
        if row.ability_name == "Lone Operative"
    )
    assert lone_operative_coverage.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
    assert lone_operative_coverage.runtime_consumer_ids == (
        CORE_LONE_OPERATIVE_SHOOTING_TARGET_CONSUMER_ID,
    )

    blade = _weapon_profile(_LUCIUS_ID, "Blade of the Laer")
    lash = _weapon_profile(_LUCIUS_ID, "Lash of Torment")
    assert (
        blade.attack_profile.fixed_attacks,
        blade.skill.final,
        blade.strength.final,
        blade.armor_penetration.final,
        blade.damage_profile.fixed_damage,
    ) == (6, 2, 8, -3, 3)
    assert blade.keywords == (WeaponKeyword.PRECISION,)
    assert (
        lash.attack_profile.fixed_attacks,
        lash.skill.final,
        lash.strength.final,
        lash.armor_penetration.final,
        lash.damage_profile.fixed_damage,
    ) == (10, 2, 4, -1, 1)
    assert lash.keywords == (WeaponKeyword.SUSTAINED_HITS,)
    assert len(lash.abilities) == 1
    assert lash.abilities[0].ability_kind is AbilityKind.SUSTAINED_HITS
    assert lash.abilities[0].parameters[0].value == 1

    assert set(catalog_rule_ir_consumers_for_rule(_lucius_rule_ir(f"{_LUCIUS_ID}:5"))) == {
        CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_WOUND_ROLL_REROLL_CONSUMER_ID,
    }
    assert catalog_rule_ir_consumers_for_rule(_lucius_rule_ir(f"{_LUCIUS_ID}:6")) == (
        CATALOG_IR_CONDITIONAL_NOT_LEADING_FIGHTS_FIRST_CONSUMER_ID,
    )


@pytest.mark.parametrize("roll_type", ["attack_sequence.hit", "attack_sequence.wound"])
def test_lucius_challenge_rerolls_apply_to_each_qualifying_target_keyword(
    roll_type: str,
) -> None:
    armies, state, indexes, lucius, targets, _ = _lucius_runtime_fixture(attached=False)
    registry = RuntimeModifierRegistry.from_bindings(
        attack_reroll_permission_bindings=CatalogDatasheetRuleRuntime(
            indexes, armies
        ).attack_reroll_permission_bindings()
    )

    for target_kind in ("character", "monster", "walker"):
        target = targets[target_kind]
        context = registry.attack_reroll_permission_context(
            AttackRerollPermissionContext(
                state=state,
                player_id="player-a",
                attacking_unit_instance_id=lucius.unit_instance_id,
                attacker_model_instance_id=lucius.own_models[0].model_instance_id,
                target_unit_instance_id=target.unit_instance_id,
                source_phase=BattlePhase.FIGHT,
                roll_type=roll_type,
                timing_window=roll_type,
            )
        )
        assert context is not None
        assert context.permission.eligible_roll_type == roll_type
        assert cast(dict[str, Any], context.source_payload)["required_target_keywords"] == [
            "CHARACTER",
            "MONSTER",
            "WALKER",
        ]

    non_qualifying = targets["other"]
    assert (
        registry.attack_reroll_permission_context(
            AttackRerollPermissionContext(
                state=state,
                player_id="player-a",
                attacking_unit_instance_id=lucius.unit_instance_id,
                attacker_model_instance_id=lucius.own_models[0].model_instance_id,
                target_unit_instance_id=non_qualifying.unit_instance_id,
                source_phase=BattlePhase.FIGHT,
                roll_type=roll_type,
                timing_window=roll_type,
            )
        )
        is None
    )


def test_lucius_rules_are_model_scoped_and_hubris_snapshots_not_leading() -> None:
    armies, state, indexes, lucius, targets, bodyguard = _lucius_runtime_fixture(attached=True)
    assert bodyguard is not None
    formation = armies[0].attached_units[0]
    runtime = CatalogDatasheetRuleRuntime(indexes, armies)
    runtime.record_static_sources(state=state)
    registry = RuntimeModifierRegistry.from_bindings(
        attack_reroll_permission_bindings=runtime.attack_reroll_permission_bindings()
    )
    target = targets["character"]
    shooter = targets["other"]
    _move_unit(state, shooter.unit_instance_id, x=5.0, y=5.0)
    _move_unit(state, lucius.unit_instance_id, x=30.0, y=5.0)
    _move_unit(state, bodyguard.unit_instance_id, x=30.0, y=8.0)
    battlefield = state.battlefield_state
    assert battlefield is not None

    assert (
        registry.attack_reroll_permission_context(
            AttackRerollPermissionContext(
                state=state,
                player_id="player-a",
                attacking_unit_instance_id=formation.attached_unit_instance_id,
                attacker_model_instance_id=lucius.own_models[0].model_instance_id,
                target_unit_instance_id=target.unit_instance_id,
                source_phase=BattlePhase.FIGHT,
                roll_type="attack_sequence.hit",
                timing_window="attack_sequence.hit",
            )
        )
        is not None
    )
    assert (
        registry.attack_reroll_permission_context(
            AttackRerollPermissionContext(
                state=state,
                player_id="player-a",
                attacking_unit_instance_id=formation.attached_unit_instance_id,
                attacker_model_instance_id=bodyguard.own_models[0].model_instance_id,
                target_unit_instance_id=target.unit_instance_id,
                source_phase=BattlePhase.FIGHT,
                roll_type="attack_sequence.hit",
                timing_window="attack_sequence.hit",
            )
        )
        is None
    )

    attached_target = shooting_target_candidates_for_unit(
        scenario=BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=battlefield,
        ),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        attacker_unit=shooter,
        weapon_profile=_weapon_profile(_NIGHT_SPINNER_ID, "Doomweaver"),
        target_unit_ids=(formation.attached_unit_instance_id,),
    )[0]
    assert attached_target.is_legal
    attached_result = _dispatch_lucius_fight_phase_start(runtime=runtime, state=state)
    assert cast(dict[str, Any], attached_result.replay_payload) == {
        "granted": False,
        "reason": "source_is_unavailable_or_leading",
        "source_unit_instance_id": lucius.unit_instance_id,
    }

    for model in bodyguard.own_models:
        _set_model_wounds(state, model_instance_id=model.model_instance_id, wounds=0)
    lone_target = shooting_target_candidates_for_unit(
        scenario=BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=battlefield,
        ),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        attacker_unit=shooter,
        weapon_profile=_weapon_profile(_NIGHT_SPINNER_ID, "Doomweaver"),
        target_unit_ids=(formation.attached_unit_instance_id,),
    )[0]
    assert lone_target.violation_code is ShootingTargetViolationCode.LONE_OPERATIVE
    assert not FightsFirstRegistry.from_state(state).has_unit(formation.attached_unit_instance_id)

    standalone_armies, standalone_state, standalone_indexes, standalone_lucius, _, _ = (
        _lucius_runtime_fixture(attached=False)
    )
    standalone_runtime = CatalogDatasheetRuleRuntime(standalone_indexes, standalone_armies)
    standalone_runtime.record_static_sources(state=standalone_state)
    standalone_result = _dispatch_lucius_fight_phase_start(
        runtime=standalone_runtime,
        state=standalone_state,
    )
    assert (
        RuntimeContentEventResult.from_payload(
            json.loads(json.dumps(standalone_result.to_payload()))
        )
        == standalone_result
    )
    replay_payload = cast(dict[str, Any], standalone_result.replay_payload)
    assert replay_payload["granted"] is True
    effect = next(
        effect
        for effect in standalone_state.persisting_effects
        if effect.source_rule_id == _lucius_rule_ir(f"{_LUCIUS_ID}:6").source_id
    )
    assert replay_payload["persisting_effect"] == effect.to_payload()
    assert effect.expiration.expiration_kind is EffectExpirationKind.END_PHASE
    assert effect.expiration.phase is BattlePhaseKind.FIGHT

    restored_state = GameState.from_payload(
        cast(GameStatePayload, json.loads(json.dumps(standalone_state.to_payload())))
    )
    fights_first = FightsFirstRegistry.from_state(restored_state)
    assert fights_first.has_unit(standalone_lucius.unit_instance_id)
    assert (
        FightsFirstRegistry.from_payload(json.loads(json.dumps(fights_first.to_payload())))
        == fights_first
    )
    restored_state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.phase_end(
            battle_round=restored_state.battle_round,
            phase=BattlePhaseKind.FIGHT,
            player_id="player-a",
        )
    )
    assert not FightsFirstRegistry.from_state(restored_state).has_unit(
        standalone_lucius.unit_instance_id
    )


def _lucius_runtime_fixture(
    *,
    attached: bool,
) -> tuple[
    tuple[ArmyDefinition, ...],
    GameState,
    dict[str, AbilityCatalogIndex],
    UnitInstance,
    dict[str, UnitInstance],
    UnitInstance | None,
]:
    package = _catalog_package()
    catalog = package.army_catalog
    factory = UnitFactory(catalog=catalog, model_geometries=package.model_geometries)
    lucius = _instantiate_unit(
        factory=factory,
        army_id="army-a",
        datasheet_id=_LUCIUS_ID,
        selection_id="lucius",
    )
    bodyguard = (
        _instantiate_unit(
            factory=factory,
            army_id="army-a",
            datasheet_id=_FLAWLESS_BLADES_ID,
            selection_id="flawless-blades",
            model_count=3,
        )
        if attached
        else None
    )
    target_datasheet_ids = {
        "character": _AUTARCH_ID,
        "monster": _BELAKOR_ID,
        "walker": _WAR_WALKER_ID,
        "other": _NIGHT_SPINNER_ID,
    }
    targets = {
        target_kind: _instantiate_unit(
            factory=factory,
            army_id="army-b",
            datasheet_id=datasheet_id,
            selection_id=f"lucius-target-{target_kind}",
        )
        for target_kind, datasheet_id in target_datasheet_ids.items()
    }
    formations = (
        (
            AttachedUnitFormation(
                attached_unit_instance_id="attached-unit:army-a:lucius-flawless-blades",
                bodyguard_unit_instance_id=bodyguard.unit_instance_id,
                leader_unit_instance_ids=(lucius.unit_instance_id,),
                component_unit_instance_ids=tuple(
                    sorted((bodyguard.unit_instance_id, lucius.unit_instance_id))
                ),
                source_id="test:lucius-flawless-blades-formation",
                attachment_source_ids=("test:lucius-flawless-blades-eligibility",),
            ),
        )
        if bodyguard is not None
        else ()
    )
    armies = (
        _army(
            catalog=catalog,
            army_id="army-a",
            player_id="player-a",
            faction_id="emperors-children",
            units=(lucius,) if bodyguard is None else (lucius, bodyguard),
            attached_units=formations,
        ),
        _army(
            catalog=catalog,
            army_id="army-b",
            player_id="player-b",
            faction_id="lucius-target-fixtures",
            units=tuple(targets.values()),
        ),
    )
    state = _battle_state(armies=armies, game_id=f"lucius-{'attached' if attached else 'solo'}")
    records = catalog_ability_records_from_catalog(catalog)
    indexes = {
        army.player_id: build_player_ability_index(records, army=army, catalog=catalog)
        for army in armies
    }
    return armies, state, indexes, lucius, targets, bodyguard


def _dispatch_lucius_fight_phase_start(
    *,
    runtime: CatalogDatasheetRuleRuntime,
    state: GameState,
) -> RuntimeContentEventResult:
    source_rule_id = _lucius_rule_ir(f"{_LUCIUS_ID}:6").source_id
    subscriptions = tuple(
        subscription
        for subscription in runtime.event_subscriptions()
        if subscription.source_rule_id == source_rule_id
    )
    assert len(subscriptions) == 1
    handler_ids = {subscription.handler_id for subscription in subscriptions}
    handler_registry = RuntimeContentEventHandlerRegistry.from_bindings(
        tuple(
            binding
            for binding in runtime.event_handler_bindings()
            if binding.handler_id in handler_ids
        )
    )
    event_index = RuntimeContentEventIndex.from_subscriptions(
        subscriptions,
        handler_registry=handler_registry,
    )
    results = event_index.dispatch(
        RuntimeContentEvent(
            event_id=(
                f"runtime-event:{state.game_id}:round-{state.battle_round}:"
                "fight-phase-start:player-a"
            ),
            game_id=state.game_id,
            player_id="player-a",
            battle_round=state.battle_round,
            trigger_kind=TimingTriggerKind.START_PHASE,
            phase=BattlePhaseKind.FIGHT,
            active_player_id="player-a",
        ),
        state=state,
        decisions=DecisionController(),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=_catalog_package().army_catalog,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert len(results) == 1
    return results[0]


def _instantiate_unit(
    *,
    factory: UnitFactory,
    army_id: str,
    datasheet_id: str,
    selection_id: str,
    model_count: int = 1,
) -> UnitInstance:
    datasheet = factory.catalog.datasheet_by_id(datasheet_id)
    model_profile = datasheet.model_profiles[0]
    return factory.instantiate_unit(
        army_id=army_id,
        datasheet=datasheet,
        selection=UnitMusterSelection(
            unit_selection_id=selection_id,
            datasheet_id=datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(model_profile.model_profile_id, model_count),
            ),
        ),
    )


def _army(
    *,
    catalog: Any,
    army_id: str,
    player_id: str,
    faction_id: str,
    units: tuple[UnitInstance, ...],
    attached_units: tuple[AttachedUnitFormation, ...] = (),
) -> ArmyDefinition:
    return ArmyDefinition(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=faction_id,
            detachment_ids=(f"{faction_id}-lucius-test",),
        ),
        force_disposition_id="purge-the-foe",
        units=units,
        attached_units=attached_units,
    )


def _battle_state(*, armies: tuple[ArmyDefinition, ...], game_id: str) -> GameState:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    phases = tuple(descriptor.battle_phase_sequence.phases)
    state = GameState(
        game_id=game_id,
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=phases,
        setup_step_index=None,
        battle_phase_index=phases.index(BattlePhase.FIGHT),
        battle_round=1,
        active_player_id="player-a",
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
    )
    for army in armies:
        state.record_army_definition(army)
    state.battlefield_state = create_deterministic_battlefield_scenario(
        battlefield_id=f"{game_id}-battlefield",
        armies=armies,
    ).battlefield_state
    return state


def _set_model_wounds(
    state: GameState,
    *,
    model_instance_id: str,
    wounds: int,
) -> None:
    found = False
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        units: list[UnitInstance] = []
        for unit in army.units:
            models = tuple(
                replace(model, wounds_remaining=wounds)
                if model.model_instance_id == model_instance_id
                else model
                for model in unit.own_models
            )
            found = found or models != unit.own_models
            units.append(replace(unit, own_models=models))
        updated_armies.append(replace(army, units=tuple(units)))
    assert found
    state.replace_army_definitions(updated_armies)


def _move_unit(state: GameState, unit_instance_id: str, *, x: float, y: float) -> None:
    battlefield = state.battlefield_state
    assert battlefield is not None
    placement = battlefield.unit_placement_by_id(unit_instance_id)
    state.replace_battlefield_state(
        battlefield.with_unit_placement(
            replace(
                placement,
                model_placements=tuple(
                    replace(model, pose=Pose.at(x=x, y=y + index * 1.5))
                    for index, model in enumerate(placement.model_placements)
                ),
            )
        )
    )


def _weapon_profile(datasheet_id: str, profile_name: str) -> WeaponProfile:
    return next(
        profile
        for wargear in _catalog_package().army_catalog.wargear
        if wargear.wargear_id.startswith(f"{datasheet_id}:")
        for profile in wargear.weapon_profiles
        if profile.name == profile_name
    )


def _lucius_rule_ir(source_row_id: str) -> RuleIR:
    payload = lucius_source_package.datasheet_rule_ir_payload_by_source_row_id(source_row_id)
    assert payload is not None
    return RuleIR.from_payload(payload)


@lru_cache(maxsize=1)
def _catalog_package() -> CanonicalCatalogPackage:
    return _ability_support_catalog_package()
