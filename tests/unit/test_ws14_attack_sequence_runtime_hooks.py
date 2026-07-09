from __future__ import annotations

from dataclasses import replace

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import AbilityKind, WeaponKeyword, WeaponProfile
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.effects import (
    GENERIC_RULE_EFFECT_KIND,
    EffectExpiration,
    EffectExpirationBoundary,
    PersistingEffect,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.generic_rule_attack_conditions import (
    generic_rule_target_proximity_keyword_gate_applies,
)
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
    WargearSelection,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.runtime_modifiers import (
    DamageRollModifierContext,
    HitRollMinimumUnmodifiedSuccessContext,
    HitRollModifierContext,
    RuntimeModifierRegistry,
    SaveOptionModifierContext,
    WeaponProfileModifierContext,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.saves import SaveKind, SaveOption
from warhammer40k_core.engine.source_backed_rerolls import (
    source_backed_reroll_permission_context_for_unit,
)
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.engine.weapon_abilities import FIRE_OVERWATCH_RULE_ID


def test_ws14_generic_attack_roll_hooks_bind_attacker_and_target_roles() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    attacker = _unit(catalog=catalog, army_id="army-a", unit_selection_id="attacker-unit")
    defender = _unit(catalog=catalog, army_id="army-b", unit_selection_id="defender-unit")
    state = _state(
        _army(catalog=catalog, player_id="player-a", army_id="army-a", unit=attacker),
        _army(catalog=catalog, player_id="player-b", army_id="army-b", unit=defender),
    )
    profile = _weapon_profile(catalog, attacker.own_models[0].wargear_ids[0])
    registry = RuntimeModifierRegistry.empty()

    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:attacker-hit-bonus",
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="modify_dice_roll",
            parameters={"roll_type": "hit", "delta": 1},
        )
    )
    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:defender-hit-penalty",
            owner_player_id="player-b",
            target_unit_instance_ids=(defender.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="modify_dice_roll",
            parameters={"roll_type": "hit", "delta": -1},
        )
    )

    assert (
        registry.hit_roll_modifier(
            HitRollModifierContext(
                state=state,
                attacking_unit_instance_id=attacker.unit_instance_id,
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                target_unit_instance_id=defender.unit_instance_id,
                weapon_profile=profile,
                source_phase=BattlePhase.SHOOTING,
            )
        )
        == 0
    )
    assert (
        registry.hit_roll_modifier(
            HitRollModifierContext(
                state=state,
                attacking_unit_instance_id=defender.unit_instance_id,
                attacker_model_instance_id=defender.own_models[0].model_instance_id,
                target_unit_instance_id=attacker.unit_instance_id,
                weapon_profile=profile,
                source_phase=BattlePhase.SHOOTING,
            )
        )
        == 0
    )


def test_ws14_generic_selected_target_wound_and_damage_hooks_use_explicit_attack_role() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    attacker = _unit(catalog=catalog, army_id="army-a", unit_selection_id="attacker-unit")
    defender = _unit(catalog=catalog, army_id="army-b", unit_selection_id="defender-unit")
    state = _state(
        _army(catalog=catalog, player_id="player-a", army_id="army-a", unit=attacker),
        _army(catalog=catalog, player_id="player-b", army_id="army-b", unit=defender),
    )
    profile = _weapon_profile(catalog, attacker.own_models[0].wargear_ids[0])
    registry = RuntimeModifierRegistry.empty()

    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:selected-target-wound",
            owner_player_id="player-a",
            target_unit_instance_ids=(defender.unit_instance_id,),
            target_kind="selected_target",
            effect_kind="modify_dice_roll",
            parameters={"roll_type": "wound", "delta": 1, "attack_role": "target"},
        )
    )
    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:selected-target-damage",
            owner_player_id="player-a",
            target_unit_instance_ids=(defender.unit_instance_id,),
            target_kind="selected_target",
            effect_kind="modify_dice_roll",
            parameters={"roll_type": "damage", "delta": 2, "attack_role": "target"},
        )
    )

    assert (
        registry.wound_roll_modifier(
            WoundRollModifierContext(
                state=state,
                source_phase=BattlePhase.SHOOTING,
                attacking_unit_instance_id=attacker.unit_instance_id,
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                target_unit_instance_id=defender.unit_instance_id,
                weapon_profile=profile,
                strength=4,
                toughness=4,
            )
        )
        == 1
    )
    assert (
        registry.damage_roll_modifier(
            DamageRollModifierContext(
                state=state,
                source_phase=BattlePhase.SHOOTING,
                attacking_unit_instance_id=attacker.unit_instance_id,
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                target_unit_instance_id=defender.unit_instance_id,
                weapon_profile=profile,
                current_value=3,
            )
        )
        == 2
    )


def test_ws14_generic_save_and_weapon_profile_hooks_execute_from_persisted_payloads() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    attacker = _unit(catalog=catalog, army_id="army-a", unit_selection_id="attacker-unit")
    defender = _unit(catalog=catalog, army_id="army-b", unit_selection_id="defender-unit")
    state = _state(
        _army(catalog=catalog, player_id="player-a", army_id="army-a", unit=attacker),
        _army(catalog=catalog, player_id="player-b", army_id="army-b", unit=defender),
    )
    model = attacker.own_models[0]
    profile = _weapon_profile(catalog, model.wargear_ids[0])
    registry = RuntimeModifierRegistry.empty()

    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:attacker-lethal-hits",
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="grant_weapon_ability",
            parameters={
                "weapon_ability": WeaponKeyword.LETHAL_HITS.value,
                "weapon_scope": "all",
            },
        )
    )
    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:attacker-strength",
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="modify_characteristic",
            parameters={"characteristic": "strength", "delta": 1},
        )
    )
    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:target-save-bonus",
            owner_player_id="player-b",
            target_unit_instance_ids=(defender.unit_instance_id,),
            target_kind="selected_target",
            effect_kind="modify_dice_roll",
            parameters={"roll_type": "save", "delta": 1, "attack_role": "target"},
        )
    )

    modified_profile = registry.modified_weapon_profile(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id=attacker.unit_instance_id,
            attacker_model_instance_id=model.model_instance_id,
            target_unit_instance_id=defender.unit_instance_id,
            weapon_profile=profile,
        )
    )
    modified_saves = registry.modified_save_options(
        SaveOptionModifierContext(
            state=state,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id=attacker.unit_instance_id,
            attacker_model_instance_id=model.model_instance_id,
            target_unit_instance_id=defender.unit_instance_id,
            weapon_profile=profile,
            save_options=(
                SaveOption(
                    save_kind=SaveKind.ARMOUR,
                    target_number=4,
                    characteristic_target_number=4,
                    armor_penetration=0,
                ),
            ),
        )
    )

    assert WeaponKeyword.LETHAL_HITS in modified_profile.keywords
    assert any(
        ability.ability_kind is AbilityKind.LETHAL_HITS for ability in modified_profile.abilities
    )
    assert modified_profile.strength.final == profile.strength.final + 1
    assert modified_saves[0].target_number == 3
    assert modified_saves[0].characteristic_target_number == 3


def test_ws14_generic_reroll_permission_uses_source_backed_attack_path() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    attacker = _unit(catalog=catalog, army_id="army-a", unit_selection_id="attacker-unit")
    defender = _unit(catalog=catalog, army_id="army-b", unit_selection_id="defender-unit")
    state = _state(
        _army(catalog=catalog, player_id="player-a", army_id="army-a", unit=attacker),
        _army(catalog=catalog, player_id="player-b", army_id="army-b", unit=defender),
    )
    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:attacker-hit-reroll",
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="reroll_permission",
            parameters={
                "roll_type": "hit",
                "attack_role": "attacker",
                "reroll_unmodified_value": 1,
            },
        )
    )

    context = source_backed_reroll_permission_context_for_unit(
        state=state,
        player_id="player-a",
        unit_instance_id=attacker.unit_instance_id,
        model_instance_id=attacker.own_models[0].model_instance_id,
        roll_type="attack_sequence.hit",
        timing_window="attack_sequence.hit",
        attack_kind="ranged",
        target_unit_instance_id=defender.unit_instance_id,
    )

    assert context is not None
    assert context.permission.eligible_roll_type == "attack_sequence.hit"
    assert context.permission.timing_window == "attack_sequence.hit"
    assert context.source_payload["effect_kind"] == GENERIC_RULE_EFFECT_KIND
    assert context.source_payload["conditional_hit_reroll"] == {
        "reroll_unmodified_values": [1],
    }


def test_ws14_generic_attack_hooks_observe_persisting_effect_expiry() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    attacker = _unit(catalog=catalog, army_id="army-a", unit_selection_id="attacker-unit")
    defender = _unit(catalog=catalog, army_id="army-b", unit_selection_id="defender-unit")
    state = _state(
        _army(catalog=catalog, player_id="player-a", army_id="army-a", unit=attacker),
        _army(catalog=catalog, player_id="player-b", army_id="army-b", unit=defender),
    )
    profile = _weapon_profile(catalog, attacker.own_models[0].wargear_ids[0])
    registry = RuntimeModifierRegistry.empty()
    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:expiring-hit-bonus",
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="modify_dice_roll",
            parameters={"roll_type": "hit", "delta": 1, "attack_role": "attacker"},
        )
    )
    context = HitRollModifierContext(
        state=state,
        attacking_unit_instance_id=attacker.unit_instance_id,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        target_unit_instance_id=defender.unit_instance_id,
        weapon_profile=profile,
        source_phase=BattlePhase.SHOOTING,
    )

    assert registry.hit_roll_modifier(context) == 1

    state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.phase_end(
            battle_round=1,
            phase=BattlePhase.SHOOTING,
            player_id="player-a",
        )
    )

    assert registry.hit_roll_modifier(context) == 0


def test_ws14_generic_minimum_unmodified_hit_success_status_is_targeting_rule_gated() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    attacker = _unit(catalog=catalog, army_id="army-a", unit_selection_id="attacker-unit")
    defender = _unit(catalog=catalog, army_id="army-b", unit_selection_id="defender-unit")
    state = _state(
        _army(catalog=catalog, player_id="player-a", army_id="army-a", unit=attacker),
        _army(catalog=catalog, player_id="player-b", army_id="army-b", unit=defender),
    )
    profile = _weapon_profile(catalog, attacker.own_models[0].wargear_ids[0])
    registry = RuntimeModifierRegistry.empty()
    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:fire-overwatch-hit-threshold",
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="set_contextual_status",
            parameters={
                "status": "minimum_unmodified_hit_success",
                "roll_type": "hit",
                "attack_role": "attacker",
                "required_targeting_rule_id": FIRE_OVERWATCH_RULE_ID,
                "minimum_unmodified_success": 5,
            },
        )
    )
    context = HitRollMinimumUnmodifiedSuccessContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=attacker.unit_instance_id,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        target_unit_instance_id=defender.unit_instance_id,
        weapon_profile=profile,
        targeting_rule_ids=(FIRE_OVERWATCH_RULE_ID,),
        current_minimum_unmodified_success=6,
    )

    assert registry.minimum_unmodified_hit_success(context) == 5
    assert registry.minimum_unmodified_hit_success(replace(context, targeting_rule_ids=())) == 6
    assert (
        registry.minimum_unmodified_hit_success(
            replace(context, current_minimum_unmodified_success=4)
        )
        == 4
    )


def test_ws14_target_proximity_keyword_gate_is_ignored_when_not_configured() -> None:
    assert (
        generic_rule_target_proximity_keyword_gate_applies(
            state=object(),
            parameters={},
            attacking_unit_instance_id="attacker",
            target_unit_instance_id=None,
        )
        is True
    )


def test_ws14_target_proximity_keyword_gate_requires_target_unit() -> None:
    assert (
        generic_rule_target_proximity_keyword_gate_applies(
            state=object(),
            parameters={
                "target_proximity_distance_inches": 9,
                "target_proximity_required_keyword_sequence": ["THOUSAND_SONS", "PSYKER"],
                "target_proximity_unit_allegiance": "friendly",
            },
            attacking_unit_instance_id="attacker",
            target_unit_instance_id=None,
        )
        is False
    )


@pytest.mark.parametrize(
    ("parameters", "error"),
    [
        (
            {
                "target_proximity_distance_inches": "9",
                "target_proximity_required_keyword_sequence": ["THOUSAND_SONS", "PSYKER"],
                "target_proximity_unit_allegiance": "friendly",
            },
            "target_proximity_distance_inches must be numeric",
        ),
        (
            {
                "target_proximity_distance_inches": -1,
                "target_proximity_required_keyword_sequence": ["THOUSAND_SONS", "PSYKER"],
                "target_proximity_unit_allegiance": "friendly",
            },
            "target_proximity_distance_inches must not be negative",
        ),
        (
            {
                "target_proximity_distance_inches": 9,
                "target_proximity_required_keyword_sequence": ["THOUSAND_SONS", "PSYKER"],
                "target_proximity_unit_allegiance": 1,
            },
            "target_proximity_unit_allegiance must be a string",
        ),
        (
            {
                "target_proximity_distance_inches": 9,
                "target_proximity_required_keyword_sequence": ["THOUSAND_SONS", "PSYKER"],
                "target_proximity_unit_allegiance": "neutral",
            },
            "Unsupported generic RuleIR target proximity allegiance",
        ),
        (
            {
                "target_proximity_distance_inches": 9,
                "target_proximity_required_keyword_sequence": "THOUSAND_SONS",
                "target_proximity_unit_allegiance": "friendly",
            },
            "target_proximity_required_keyword_sequence must be a list",
        ),
        (
            {
                "target_proximity_distance_inches": 9,
                "target_proximity_required_keyword_sequence": ["THOUSAND_SONS", 1],
                "target_proximity_unit_allegiance": "friendly",
            },
            "target_proximity_required_keyword_sequence must contain strings",
        ),
        (
            {
                "target_proximity_distance_inches": 9,
                "target_proximity_required_keyword_sequence": [],
                "target_proximity_unit_allegiance": "friendly",
            },
            "target_proximity_required_keyword_sequence must not be empty",
        ),
    ],
)
def test_ws14_target_proximity_keyword_gate_rejects_malformed_descriptor_parameters(
    *,
    parameters: dict[str, JsonValue],
    error: str,
) -> None:
    with pytest.raises(GameLifecycleError, match=error):
        generic_rule_target_proximity_keyword_gate_applies(
            state=object(),
            parameters=parameters,
            attacking_unit_instance_id="attacker",
            target_unit_instance_id="target",
        )


def test_ws14_generic_this_model_half_strength_hit_modifier_gates_target() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    attacker = _unit(catalog=catalog, army_id="army-a", unit_selection_id="attacker-unit")
    defender = _unit(catalog=catalog, army_id="army-b", unit_selection_id="defender-unit")
    state = _state(
        _army(catalog=catalog, player_id="player-a", army_id="army-a", unit=attacker),
        _army(catalog=catalog, player_id="player-b", army_id="army-b", unit=defender),
    )
    profile = _weapon_profile(catalog, attacker.own_models[0].wargear_ids[0])
    registry = RuntimeModifierRegistry.empty()
    source_model_id = attacker.own_models[0].model_instance_id

    state.record_persisting_effect(
        _generic_effect(
            effect_id="ws14:this-model-half-strength-hit-bonus",
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            target_kind="this_model",
            effect_kind="modify_dice_roll",
            parameters={"roll_type": "hit", "delta": 1},
            conditions=(
                {
                    "kind": "target_constraint",
                    "parameters": [
                        {"key": "gate_subject", "value": "attack_target"},
                        {"key": "relationship", "value": "this_model_makes_attack"},
                        {"key": "target_allegiance", "value": "enemy"},
                        {
                            "key": "target_constraint",
                            "value": "target_not_below_half_strength",
                        },
                    ],
                },
            ),
            source_model_instance_id=source_model_id,
        )
    )
    context = HitRollModifierContext(
        state=state,
        attacking_unit_instance_id=attacker.unit_instance_id,
        attacker_model_instance_id=source_model_id,
        target_unit_instance_id=defender.unit_instance_id,
        weapon_profile=profile,
        source_phase=BattlePhase.SHOOTING,
    )

    assert registry.hit_roll_modifier(context) == 1
    assert (
        registry.hit_roll_modifier(
            replace(
                context,
                attacker_model_instance_id=defender.own_models[0].model_instance_id,
            )
        )
        == 0
    )
    assert (
        registry.hit_roll_modifier(
            replace(context, target_unit_instance_id=attacker.unit_instance_id)
        )
        == 0
    )

    below_half_wounds = _below_half_wounds(defender.own_models[0].starting_wounds)
    _replace_unit(state, _unit_with_model_wounds(defender, wounds_remaining=below_half_wounds))

    assert registry.hit_roll_modifier(context) == 0


def _unit(*, catalog: ArmyCatalog, army_id: str, unit_selection_id: str) -> UnitInstance:
    datasheet = catalog.datasheet_by_id("core-character-leader")
    profile = datasheet.model_profiles[0]
    option = datasheet.wargear_options[0]
    return UnitFactory(catalog=catalog).instantiate_unit(
        army_id=army_id,
        selection=UnitMusterSelection(
            unit_selection_id=unit_selection_id,
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


def _army(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit: UnitInstance,
) -> ArmyDefinition:
    detachment = catalog.detachments[0]
    return ArmyDefinition(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=detachment.faction_id,
            detachment_ids=(detachment.detachment_id,),
        ),
        units=(unit,),
    )


def _state(*armies: ArmyDefinition) -> GameState:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    state = GameState(
        game_id="ws14-attack-hooks-game",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=tuple(descriptor.battle_phase_sequence.phases),
        setup_step_index=None,
        battle_phase_index=0,
        battle_round=1,
        active_player_id="player-a",
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
    )
    for army in armies:
        state.record_army_definition(army)
    return state


def _weapon_profile(catalog: ArmyCatalog, wargear_id: str) -> WeaponProfile:
    for wargear in catalog.wargear:
        if wargear.wargear_id == wargear_id:
            return wargear.weapon_profiles[0]
    raise AssertionError(f"Unknown wargear id: {wargear_id}")


def _generic_effect(
    *,
    effect_id: str,
    owner_player_id: str,
    target_unit_instance_ids: tuple[str, ...],
    target_kind: str,
    effect_kind: str,
    parameters: dict[str, JsonValue],
    conditions: tuple[dict[str, JsonValue], ...] = (),
    source_model_instance_id: str | None = None,
) -> PersistingEffect:
    parameter_payloads: list[dict[str, JsonValue]] = [
        {"key": key, "value": value} for key, value in sorted(parameters.items())
    ]
    return PersistingEffect(
        effect_id=effect_id,
        source_rule_id=f"source:{effect_id}",
        owner_player_id=owner_player_id,
        target_unit_instance_ids=target_unit_instance_ids,
        started_battle_round=1,
        started_phase=BattlePhase.SHOOTING,
        expiration=EffectExpiration.end_phase(
            battle_round=1,
            phase=BattlePhase.SHOOTING,
            player_id="player-a",
        ),
        effect_payload=validate_json_value(
            {
                "effect_kind": GENERIC_RULE_EFFECT_KIND,
                "rule_id": f"rule:{effect_id}",
                "source_id": f"source:{effect_id}",
                "rule_ir_hash": "0" * 64,
                "clause_id": f"clause:{effect_id}",
                "source_span": {"start": 0, "end": 1, "text": "x"},
                "target": {
                    "kind": target_kind,
                    "source_span": {"start": 0, "end": 1, "text": "x"},
                    "parameters": [],
                },
                "target_unit_instance_ids": list(target_unit_instance_ids),
                "duration": None,
                "conditions": list(conditions),
                "effect": {
                    "kind": effect_kind,
                    "source_span": {"start": 0, "end": 1, "text": "x"},
                    "parameters": parameter_payloads,
                },
                "context": {
                    "state": None,
                    "player_id": owner_player_id,
                    "phase": BattlePhase.SHOOTING.value,
                    "source_model_instance_id": source_model_instance_id,
                },
            }
        ),
    )


def _unit_with_model_wounds(unit: UnitInstance, *, wounds_remaining: int) -> UnitInstance:
    return replace(
        unit,
        own_models=(
            replace(unit.own_models[0], wounds_remaining=wounds_remaining),
            *unit.own_models[1:],
        ),
    )


def _below_half_wounds(starting_wounds: int) -> int:
    if starting_wounds <= 2:
        return 0
    return max(1, (starting_wounds - 1) // 2)


def _replace_unit(state: GameState, replacement: UnitInstance) -> None:
    updated_armies: list[ArmyDefinition] = []
    did_update = False
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            if unit.unit_instance_id == replacement.unit_instance_id:
                updated_units.append(replacement)
                did_update = True
            else:
                updated_units.append(unit)
        updated_armies.append(replace(army, units=tuple(updated_units)))
    if not did_update:
        raise AssertionError(f"Unknown unit id: {replacement.unit_instance_id}")
    state.army_definitions = updated_armies
