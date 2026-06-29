from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    DamagedEffectDefinition,
    DamagedEffectKind,
    DamagedWeaponScope,
)
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.damaged_effects import (
    catalog_damaged_effect_hit_roll_modifier_bindings,
    catalog_damaged_effect_objective_control_modifier_bindings,
    catalog_damaged_effect_weapon_profile_modifier_bindings,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
    WargearSelection,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierContext,
    ObjectiveControlModifierContext,
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance


def test_damaged_effects_modify_hit_roll_and_objective_control_inside_wound_range() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    hit_effect = _damaged_effect(
        effect_id="core-vehicle-monster:damaged:001",
        effect_kind=DamagedEffectKind.HIT_ROLL_MODIFIER,
        modifier=-1,
    )
    objective_control_effect = _damaged_effect(
        effect_id="core-vehicle-monster:damaged:002",
        effect_kind=DamagedEffectKind.OBJECTIVE_CONTROL_MODIFIER,
        modifier=-4,
    )
    unit = _unit_with_damaged_effects(
        catalog=catalog,
        datasheet_id="core-vehicle-monster",
        wounds_remaining=5,
        effects=(hit_effect, objective_control_effect),
    )
    army = _army(catalog=catalog, unit=unit)
    state = _state(army)
    model = unit.own_models[0]
    registry = RuntimeModifierRegistry.from_bindings(
        hit_roll_modifier_bindings=catalog_damaged_effect_hit_roll_modifier_bindings(
            armies=(army,),
        ),
        objective_control_modifier_bindings=(
            catalog_damaged_effect_objective_control_modifier_bindings(armies=(army,))
        ),
    )

    assert (
        registry.hit_roll_modifier(
            HitRollModifierContext(
                state=state,
                attacking_unit_instance_id=unit.unit_instance_id,
                attacker_model_instance_id=model.model_instance_id,
                target_unit_instance_id=unit.unit_instance_id,
                weapon_profile=_weapon_profile(catalog, model.wargear_ids[0]),
                source_phase=BattlePhase.SHOOTING,
            )
        )
        == -1
    )
    assert (
        registry.modified_objective_control(
            ObjectiveControlModifierContext(
                state=state,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                base_objective_control=5,
                current_objective_control=5,
            )
        )
        == 1
    )

    fresh_unit = replace(
        unit,
        own_models=(replace(model, wounds_remaining=6),),
    )
    fresh_army = _army(catalog=catalog, unit=fresh_unit)
    fresh_state = _state(fresh_army)
    assert (
        registry.hit_roll_modifier(
            HitRollModifierContext(
                state=fresh_state,
                attacking_unit_instance_id=fresh_unit.unit_instance_id,
                attacker_model_instance_id=fresh_unit.own_models[0].model_instance_id,
                target_unit_instance_id=fresh_unit.unit_instance_id,
                weapon_profile=_weapon_profile(catalog, model.wargear_ids[0]),
                source_phase=BattlePhase.SHOOTING,
            )
        )
        == 0
    )
    assert (
        registry.modified_objective_control(
            ObjectiveControlModifierContext(
                state=fresh_state,
                unit_instance_id=fresh_unit.unit_instance_id,
                model_instance_id=fresh_unit.own_models[0].model_instance_id,
                base_objective_control=5,
                current_objective_control=5,
            )
        )
        == 5
    )


def test_damaged_effects_modify_fixed_weapon_attacks_by_scope() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    melee_bonus = _damaged_effect(
        effect_id="core-character-leader:damaged:001",
        effect_kind=DamagedEffectKind.WEAPON_ATTACKS_MODIFIER,
        modifier=2,
        weapon_scope=DamagedWeaponScope.MELEE,
    )
    all_weapons_halved = _damaged_effect(
        effect_id="core-character-leader:damaged:002",
        effect_kind=DamagedEffectKind.WEAPON_ATTACKS_HALVE,
        weapon_scope=DamagedWeaponScope.ALL,
    )
    unit = _unit_with_damaged_effects(
        catalog=catalog,
        datasheet_id="core-character-leader",
        wounds_remaining=4,
        effects=(melee_bonus, all_weapons_halved),
    )
    army = _army(catalog=catalog, unit=unit)
    state = _state(army)
    model = unit.own_models[0]
    profile = _weapon_profile(catalog, model.wargear_ids[0])
    registry = RuntimeModifierRegistry.from_bindings(
        weapon_profile_modifier_bindings=catalog_damaged_effect_weapon_profile_modifier_bindings(
            armies=(army,),
        ),
    )

    modified_profile = registry.modified_weapon_profile(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.FIGHT,
            attacking_unit_instance_id=unit.unit_instance_id,
            attacker_model_instance_id=model.model_instance_id,
            target_unit_instance_id=unit.unit_instance_id,
            weapon_profile=profile,
        )
    )

    assert profile.attack_profile.fixed_attacks == 5
    assert modified_profile.attack_profile.fixed_attacks == 4


def _damaged_effect(
    *,
    effect_id: str,
    effect_kind: DamagedEffectKind,
    modifier: int | None = None,
    weapon_scope: DamagedWeaponScope | None = None,
) -> DamagedEffectDefinition:
    return DamagedEffectDefinition(
        damaged_effect_id=effect_id,
        model_profile_id=None,
        wounds_min=1,
        wounds_max=5,
        effect_kind=effect_kind,
        modifier=modifier,
        weapon_scope=weapon_scope,
        weapon_names=(),
        source_id=f"source:{effect_id}",
    )


def _unit_with_damaged_effects(
    *,
    catalog: ArmyCatalog,
    datasheet_id: str,
    wounds_remaining: int,
    effects: tuple[DamagedEffectDefinition, ...],
) -> UnitInstance:
    datasheet = catalog.datasheet_by_id(datasheet_id)
    profile = datasheet.model_profiles[0]
    option = datasheet.wargear_options[0]
    unit = UnitFactory(catalog=catalog).instantiate_unit(
        army_id="army-a",
        selection=UnitMusterSelection(
            unit_selection_id="damaged-unit",
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id=profile.model_profile_id,
                    model_count=1,
                ),
            ),
            wargear_selections=(
                WargearSelection(
                    option_id=option.option_id,
                    model_profile_id=profile.model_profile_id,
                    wargear_ids=option.default_wargear_ids,
                ),
            ),
        ),
        datasheet=datasheet,
    )
    model = unit.own_models[0]
    return replace(
        unit,
        own_models=(replace(model, wounds_remaining=wounds_remaining),),
        damaged_effects=effects,
    )


def _army(*, catalog: ArmyCatalog, unit: UnitInstance) -> ArmyDefinition:
    detachment = catalog.detachments[0]
    return ArmyDefinition(
        army_id="army-a",
        player_id="player-a",
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=detachment.faction_id,
            detachment_ids=(detachment.detachment_id,),
        ),
        units=(unit,),
    )


def _state(army: ArmyDefinition) -> GameState:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    state = GameState(
        game_id="damaged-effects-game",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=tuple(descriptor.battle_phase_sequence.phases),
        setup_step_index=None,
        battle_phase_index=0,
        battle_round=1,
        active_player_id=army.player_id,
        player_ids=(army.player_id, "player-b"),
        turn_order=(army.player_id, "player-b"),
        tactical_secondary_draw_count=2,
    )
    state.record_army_definition(army)
    return state


def _weapon_profile(catalog: ArmyCatalog, wargear_id: str) -> WeaponProfile:
    for wargear in catalog.wargear:
        if wargear.wargear_id == wargear_id:
            return wargear.weapon_profiles[0]
    raise AssertionError(f"Unknown wargear id: {wargear_id}")
