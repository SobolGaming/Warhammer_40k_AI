from __future__ import annotations

from dataclasses import replace

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    DamagedEffectDefinition,
    DamagedEffectKind,
    DamagedWeaponScope,
)
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import WeaponKeyword, WeaponProfile
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.damaged_effects import (
    CatalogDamagedAbilitySelectionLimit,
    CatalogDamagedEffectRuntime,
    CatalogDamagedShootingWeaponSelectionLimit,
    catalog_damaged_ability_selection_limit_for_model,
    catalog_damaged_effect_hit_roll_modifier_bindings,
    catalog_damaged_effect_objective_control_modifier_bindings,
    catalog_damaged_effect_weapon_profile_modifier_bindings,
    catalog_damaged_shooting_weapon_selection_limit_for_profile,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierContext,
    ObjectiveControlModifierContext,
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
    WargearSelection,
)


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
    ignored_hit_effect = _damaged_effect(
        effect_id="core-character-leader:damaged:ignored-hit-roll",
        effect_kind=DamagedEffectKind.HIT_ROLL_MODIFIER,
        modifier=-1,
    )
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
        effects=(ignored_hit_effect, melee_bonus, all_weapons_halved),
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


def test_damaged_effects_modify_named_weapon_attacks_only_for_matching_profiles() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    unit_without_effects = _unit_with_damaged_effects(
        catalog=catalog,
        datasheet_id="core-character-leader",
        wounds_remaining=4,
        effects=(),
    )
    model = unit_without_effects.own_models[0]
    profile = _weapon_profile(catalog, model.wargear_ids[0])
    named_bonus = _damaged_effect(
        effect_id="core-character-leader:damaged:named-match",
        effect_kind=DamagedEffectKind.WEAPON_ATTACKS_MODIFIER,
        modifier=2,
        weapon_scope=DamagedWeaponScope.NAMED,
        weapon_names=(profile.name,),
    )
    unmatched_named_bonus = _damaged_effect(
        effect_id="core-character-leader:damaged:named-miss",
        effect_kind=DamagedEffectKind.WEAPON_ATTACKS_MODIFIER,
        modifier=3,
        weapon_scope=DamagedWeaponScope.NAMED,
        weapon_names=("other-weapon",),
    )
    unit = replace(
        unit_without_effects,
        damaged_effects=(named_bonus, unmatched_named_bonus),
    )
    army = _army(catalog=catalog, unit=unit)
    registry = RuntimeModifierRegistry.from_bindings(
        weapon_profile_modifier_bindings=catalog_damaged_effect_weapon_profile_modifier_bindings(
            armies=(army,),
        ),
    )

    modified_profile = registry.modified_weapon_profile(
        WeaponProfileModifierContext(
            state=_state(army),
            source_phase=BattlePhase.FIGHT,
            attacking_unit_instance_id=unit.unit_instance_id,
            attacker_model_instance_id=model.model_instance_id,
            target_unit_instance_id=unit.unit_instance_id,
            weapon_profile=profile,
        )
    )

    assert profile.attack_profile.fixed_attacks == 5
    assert modified_profile.attack_profile.fixed_attacks == 7


def test_damaged_effects_expose_ctan_power_selection_limit_by_wound_range() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    selection_limit_effect = _damaged_effect(
        effect_id="core-vehicle-monster:damaged:ctan-selection",
        effect_kind=DamagedEffectKind.SHOOTING_WEAPON_SELECTION_LIMIT,
        max_selections=1,
        baseline_max_selections=2,
        selection_group="C'tan Powers weapons",
    )
    fresh_unit = _unit_with_damaged_effects(
        catalog=catalog,
        datasheet_id="core-vehicle-monster",
        wounds_remaining=6,
        effects=(selection_limit_effect,),
    )
    damaged_unit = _unit_with_damaged_effects(
        catalog=catalog,
        datasheet_id="core-vehicle-monster",
        wounds_remaining=5,
        effects=(selection_limit_effect,),
    )
    fresh_model = fresh_unit.own_models[0]
    damaged_model = damaged_unit.own_models[0]
    profile = replace(
        _weapon_profile(catalog, fresh_model.wargear_ids[0]),
        keywords=(WeaponKeyword.CTAN_POWER,),
    )

    fresh_limit = catalog_damaged_shooting_weapon_selection_limit_for_profile(
        unit=fresh_unit,
        model=fresh_model,
        profile=profile,
    )
    damaged_limit = catalog_damaged_shooting_weapon_selection_limit_for_profile(
        unit=damaged_unit,
        model=damaged_model,
        profile=profile,
    )

    assert fresh_limit is not None
    assert fresh_limit.max_selections == 2
    assert fresh_limit.baseline_max_selections == 2
    assert not fresh_limit.damaged_profile_active
    assert damaged_limit is not None
    assert damaged_limit.max_selections == 1
    assert damaged_limit.baseline_max_selections == 2
    assert damaged_limit.damaged_profile_active


def test_ctan_power_selection_limit_ignores_unaffected_profiles_and_models() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    selection_limit_effect = _damaged_effect(
        effect_id="core-vehicle-monster:damaged:ctan-selection",
        effect_kind=DamagedEffectKind.SHOOTING_WEAPON_SELECTION_LIMIT,
        max_selections=1,
        baseline_max_selections=2,
        selection_group="C'tan Powers weapons",
    )
    unit = _unit_with_damaged_effects(
        catalog=catalog,
        datasheet_id="core-vehicle-monster",
        wounds_remaining=5,
        effects=(selection_limit_effect,),
    )
    model = unit.own_models[0]
    base_profile = _weapon_profile(catalog, model.wargear_ids[0])
    ctan_profile = replace(base_profile, keywords=(WeaponKeyword.CTAN_POWER,))

    assert (
        catalog_damaged_shooting_weapon_selection_limit_for_profile(
            unit=unit,
            model=model,
            profile=base_profile,
        )
        is None
    )
    assert (
        catalog_damaged_shooting_weapon_selection_limit_for_profile(
            unit=replace(unit, damaged_effects=()),
            model=model,
            profile=ctan_profile,
        )
        is None
    )

    dead_model = replace(model, wounds_remaining=0)
    assert (
        catalog_damaged_shooting_weapon_selection_limit_for_profile(
            unit=replace(unit, own_models=(dead_model,)),
            model=dead_model,
            profile=ctan_profile,
        )
        is None
    )

    unmatched_effect = _damaged_effect(
        effect_id="core-vehicle-monster:damaged:ctan-unmatched",
        effect_kind=DamagedEffectKind.SHOOTING_WEAPON_SELECTION_LIMIT,
        model_profile_id="other-model-profile",
        max_selections=1,
        baseline_max_selections=2,
        selection_group="C'tan Powers weapons",
    )
    assert (
        catalog_damaged_shooting_weapon_selection_limit_for_profile(
            unit=replace(unit, damaged_effects=(unmatched_effect,)),
            model=model,
            profile=ctan_profile,
        )
        is None
    )


def test_ctan_power_selection_limit_rejects_ambiguous_or_incomplete_effects() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    first_effect = _damaged_effect(
        effect_id="core-vehicle-monster:damaged:ctan-selection-a",
        effect_kind=DamagedEffectKind.SHOOTING_WEAPON_SELECTION_LIMIT,
        max_selections=1,
        baseline_max_selections=2,
        selection_group="C'tan Powers weapons",
    )
    second_effect = _damaged_effect(
        effect_id="core-vehicle-monster:damaged:ctan-selection-b",
        effect_kind=DamagedEffectKind.SHOOTING_WEAPON_SELECTION_LIMIT,
        max_selections=1,
        baseline_max_selections=2,
        selection_group="C'tan Powers weapons",
    )
    unit = _unit_with_damaged_effects(
        catalog=catalog,
        datasheet_id="core-vehicle-monster",
        wounds_remaining=5,
        effects=(first_effect, second_effect),
    )
    model = unit.own_models[0]
    profile = replace(
        _weapon_profile(catalog, model.wargear_ids[0]),
        keywords=(WeaponKeyword.CTAN_POWER,),
    )

    with pytest.raises(GameLifecycleError, match="ambiguous"):
        catalog_damaged_shooting_weapon_selection_limit_for_profile(
            unit=unit,
            model=model,
            profile=profile,
        )

    with pytest.raises(GameLifecycleError, match="requires a unit"):
        catalog_damaged_shooting_weapon_selection_limit_for_profile(
            unit="damaged-unit",  # type: ignore[arg-type]
            model=model,
            profile=profile,
        )
    with pytest.raises(GameLifecycleError, match="requires a model"):
        catalog_damaged_shooting_weapon_selection_limit_for_profile(
            unit=unit,
            model="damaged-model",  # type: ignore[arg-type]
            profile=profile,
        )
    with pytest.raises(GameLifecycleError, match="requires a profile"):
        catalog_damaged_shooting_weapon_selection_limit_for_profile(
            unit=unit,
            model=model,
            profile="ctan-profile",  # type: ignore[arg-type]
        )


def test_damaged_effects_expose_ability_selection_limit_by_wound_range() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    selection_limit_effect = _damaged_effect(
        effect_id="core-vehicle-monster:damaged:ability-selection",
        effect_kind=DamagedEffectKind.ABILITY_SELECTION_LIMIT,
        max_selections=1,
        baseline_max_selections=2,
        selection_group="Relics of the Matriarchs ability",
    )
    fresh_unit = _unit_with_damaged_effects(
        catalog=catalog,
        datasheet_id="core-vehicle-monster",
        wounds_remaining=6,
        effects=(selection_limit_effect,),
    )
    damaged_unit = _unit_with_damaged_effects(
        catalog=catalog,
        datasheet_id="core-vehicle-monster",
        wounds_remaining=5,
        effects=(selection_limit_effect,),
    )

    fresh_limit = catalog_damaged_ability_selection_limit_for_model(
        unit=fresh_unit,
        model=fresh_unit.own_models[0],
        selection_group="Relics of the Matriarchs ability",
    )
    damaged_limit = catalog_damaged_ability_selection_limit_for_model(
        unit=damaged_unit,
        model=damaged_unit.own_models[0],
        selection_group="Relics of the Matriarchs ability",
    )

    assert fresh_limit is not None
    assert fresh_limit.max_selections == 2
    assert fresh_limit.baseline_max_selections == 2
    assert not fresh_limit.damaged_profile_active
    assert damaged_limit is not None
    assert damaged_limit.max_selections == 1
    assert damaged_limit.baseline_max_selections == 2
    assert damaged_limit.damaged_profile_active


def test_ability_selection_limit_ignores_unmatched_groups_models_and_dead_models() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    selection_limit_effect = _damaged_effect(
        effect_id="core-vehicle-monster:damaged:ability-selection",
        effect_kind=DamagedEffectKind.ABILITY_SELECTION_LIMIT,
        max_selections=1,
        baseline_max_selections=2,
        selection_group="Relics of the Matriarchs ability",
    )
    unit = _unit_with_damaged_effects(
        catalog=catalog,
        datasheet_id="core-vehicle-monster",
        wounds_remaining=5,
        effects=(selection_limit_effect,),
    )
    model = unit.own_models[0]

    assert (
        catalog_damaged_ability_selection_limit_for_model(
            unit=unit,
            model=model,
            selection_group="Other ability",
        )
        is None
    )
    assert (
        catalog_damaged_ability_selection_limit_for_model(
            unit=replace(unit, damaged_effects=()),
            model=model,
            selection_group="Relics of the Matriarchs ability",
        )
        is None
    )

    dead_model = replace(model, wounds_remaining=0)
    assert (
        catalog_damaged_ability_selection_limit_for_model(
            unit=replace(unit, own_models=(dead_model,)),
            model=dead_model,
            selection_group="Relics of the Matriarchs ability",
        )
        is None
    )

    unmatched_effect = _damaged_effect(
        effect_id="core-vehicle-monster:damaged:ability-unmatched",
        effect_kind=DamagedEffectKind.ABILITY_SELECTION_LIMIT,
        model_profile_id="other-model-profile",
        max_selections=1,
        baseline_max_selections=2,
        selection_group="Relics of the Matriarchs ability",
    )
    assert (
        catalog_damaged_ability_selection_limit_for_model(
            unit=replace(unit, damaged_effects=(unmatched_effect,)),
            model=model,
            selection_group="Relics of the Matriarchs ability",
        )
        is None
    )


def test_ability_selection_limit_rejects_ambiguous_or_invalid_inputs() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    first_effect = _damaged_effect(
        effect_id="core-vehicle-monster:damaged:ability-selection-a",
        effect_kind=DamagedEffectKind.ABILITY_SELECTION_LIMIT,
        max_selections=1,
        baseline_max_selections=2,
        selection_group="Relics of the Matriarchs ability",
    )
    second_effect = _damaged_effect(
        effect_id="core-vehicle-monster:damaged:ability-selection-b",
        effect_kind=DamagedEffectKind.ABILITY_SELECTION_LIMIT,
        max_selections=1,
        baseline_max_selections=2,
        selection_group="Relics of the Matriarchs ability",
    )
    unit = _unit_with_damaged_effects(
        catalog=catalog,
        datasheet_id="core-vehicle-monster",
        wounds_remaining=5,
        effects=(first_effect, second_effect),
    )
    model = unit.own_models[0]

    with pytest.raises(GameLifecycleError, match="ambiguous"):
        catalog_damaged_ability_selection_limit_for_model(
            unit=unit,
            model=model,
            selection_group="Relics of the Matriarchs ability",
        )
    with pytest.raises(GameLifecycleError, match="requires a unit"):
        catalog_damaged_ability_selection_limit_for_model(
            unit="damaged-unit",  # type: ignore[arg-type]
            model=model,
            selection_group="Relics of the Matriarchs ability",
        )
    with pytest.raises(GameLifecycleError, match="requires a model"):
        catalog_damaged_ability_selection_limit_for_model(
            unit=unit,
            model="damaged-model",  # type: ignore[arg-type]
            selection_group="Relics of the Matriarchs ability",
        )


def test_damaged_effect_runtime_rejects_invalid_context_and_armies() -> None:
    runtime = CatalogDamagedEffectRuntime(armies=())

    with pytest.raises(GameLifecycleError, match="Hit roll modifier requires context"):
        runtime.hit_roll_modifier(object())  # type: ignore[arg-type]
    with pytest.raises(GameLifecycleError, match="Objective Control modifier requires context"):
        runtime.objective_control_modifier(object())  # type: ignore[arg-type]
    with pytest.raises(GameLifecycleError, match="weapon profile modifier requires context"):
        runtime.weapon_profile_modifier(object())  # type: ignore[arg-type]
    with pytest.raises(GameLifecycleError, match="armies must be a tuple"):
        CatalogDamagedEffectRuntime(armies=[])  # type: ignore[arg-type]
    with pytest.raises(GameLifecycleError, match="must contain ArmyDefinition"):
        CatalogDamagedEffectRuntime(armies=(object(),))  # type: ignore[arg-type]


def test_ctan_power_selection_limit_payload_is_fail_fast() -> None:
    with pytest.raises(GameLifecycleError, match="requires a weapon keyword"):
        CatalogDamagedShootingWeaponSelectionLimit(
            damaged_effect_id="damaged:ctan-selection",
            source_id="source:damaged:ctan-selection",
            model_instance_id="model:ctan",
            weapon_keyword="C'tan Power",  # type: ignore[arg-type]
            max_selections=1,
            baseline_max_selections=2,
            damaged_profile_active=True,
        )
    with pytest.raises(GameLifecycleError, match="max_selections must be an int"):
        CatalogDamagedShootingWeaponSelectionLimit(
            damaged_effect_id="damaged:ctan-selection",
            source_id="source:damaged:ctan-selection",
            model_instance_id="model:ctan",
            weapon_keyword=WeaponKeyword.CTAN_POWER,
            max_selections="1",  # type: ignore[arg-type]
            baseline_max_selections=2,
            damaged_profile_active=True,
        )
    with pytest.raises(GameLifecycleError, match="max_selections must be greater than zero"):
        CatalogDamagedShootingWeaponSelectionLimit(
            damaged_effect_id="damaged:ctan-selection",
            source_id="source:damaged:ctan-selection",
            model_instance_id="model:ctan",
            weapon_keyword=WeaponKeyword.CTAN_POWER,
            max_selections=0,
            baseline_max_selections=2,
            damaged_profile_active=True,
        )
    with pytest.raises(GameLifecycleError, match="baseline is below max"):
        CatalogDamagedShootingWeaponSelectionLimit(
            damaged_effect_id="damaged:ctan-selection",
            source_id="source:damaged:ctan-selection",
            model_instance_id="model:ctan",
            weapon_keyword=WeaponKeyword.CTAN_POWER,
            max_selections=2,
            baseline_max_selections=1,
            damaged_profile_active=True,
        )
    with pytest.raises(GameLifecycleError, match="active flag must be a bool"):
        CatalogDamagedShootingWeaponSelectionLimit(
            damaged_effect_id="damaged:ctan-selection",
            source_id="source:damaged:ctan-selection",
            model_instance_id="model:ctan",
            weapon_keyword=WeaponKeyword.CTAN_POWER,
            max_selections=1,
            baseline_max_selections=2,
            damaged_profile_active=1,  # type: ignore[arg-type]
        )


def test_ability_selection_limit_payload_is_fail_fast() -> None:
    with pytest.raises(GameLifecycleError, match="selection_group must be a string"):
        CatalogDamagedAbilitySelectionLimit(
            damaged_effect_id="damaged:ability-selection",
            source_id="source:damaged:ability-selection",
            model_instance_id="model:triumph",
            selection_group=1,  # type: ignore[arg-type]
            max_selections=1,
            baseline_max_selections=2,
            damaged_profile_active=True,
        )
    with pytest.raises(GameLifecycleError, match="baseline is below max"):
        CatalogDamagedAbilitySelectionLimit(
            damaged_effect_id="damaged:ability-selection",
            source_id="source:damaged:ability-selection",
            model_instance_id="model:triumph",
            selection_group="Relics of the Matriarchs ability",
            max_selections=2,
            baseline_max_selections=1,
            damaged_profile_active=True,
        )
    with pytest.raises(GameLifecycleError, match="active flag must be a bool"):
        CatalogDamagedAbilitySelectionLimit(
            damaged_effect_id="damaged:ability-selection",
            source_id="source:damaged:ability-selection",
            model_instance_id="model:triumph",
            selection_group="Relics of the Matriarchs ability",
            max_selections=1,
            baseline_max_selections=2,
            damaged_profile_active=1,  # type: ignore[arg-type]
        )


def _damaged_effect(
    *,
    effect_id: str,
    effect_kind: DamagedEffectKind,
    model_profile_id: str | None = None,
    modifier: int | None = None,
    weapon_scope: DamagedWeaponScope | None = None,
    weapon_names: tuple[str, ...] = (),
    max_selections: int | None = None,
    baseline_max_selections: int | None = None,
    selection_group: str | None = None,
) -> DamagedEffectDefinition:
    return DamagedEffectDefinition(
        damaged_effect_id=effect_id,
        model_profile_id=model_profile_id,
        wounds_min=1,
        wounds_max=5,
        effect_kind=effect_kind,
        modifier=modifier,
        weapon_scope=weapon_scope,
        weapon_names=weapon_names,
        max_selections=max_selections,
        baseline_max_selections=baseline_max_selections,
        selection_group=selection_group,
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
        force_disposition_id="purge-the-foe",
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
