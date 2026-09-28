"""R93-001: permission discovery retains the real attack and subject identities."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.catalog_modifier_ignore import (
    CatalogModifierIgnorePermission,
    ModifierIgnoreKind,
    modifier_ignore_permissions_for_subject,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError


def test_attack_permission_context_round_trip_and_closed_payload() -> None:
    from warhammer40k_core.engine.generic_rule_effect_targets import AttackRole
    from warhammer40k_core.engine.modifier_permission_context import ModifierPermissionAttackContext

    profile = ArmyCatalog.phase9a_canonical_content_pack().wargear[0].weapon_profiles[0]
    context = ModifierPermissionAttackContext(
        attacking_unit_instance_id="attacker",
        attacker_model_instance_id="attacker:model",
        target_unit_instance_id="target",
        subject_role="target",
        source_phase=BattlePhase.SHOOTING,
        weapon_profile=profile,
        attack_strength=4,
        target_toughness=None,
    )
    assert ModifierPermissionAttackContext.from_payload(context.to_payload()) == context
    mutations: tuple[dict[str, object], ...] = (
        {"unexpected": 1},
        {"subject_role": "owner"},
        {"attack_strength": True},
        {"target_toughness": 0},
        {"source_phase": "not-a-phase"},
        {"target_unit_instance_id": ""},
        {"subject_role": []},
        {"weapon_profile": {}},
        {"weapon_profile": {**profile.to_payload(), "unexpected": 1}},
    )
    for mutation in mutations:
        with pytest.raises(GameLifecycleError):
            ModifierPermissionAttackContext.from_payload({**context.to_payload(), **mutation})
    payload = context.to_payload()
    del payload["weapon_profile"]
    with pytest.raises(GameLifecycleError, match="fields"):
        ModifierPermissionAttackContext.from_payload(payload)
    with pytest.raises(GameLifecycleError, match="subject role"):
        replace(context, subject_role=cast(AttackRole, []))


@pytest.mark.parametrize("role", ["attacker", "target"])
@pytest.mark.parametrize("model_scope", [False, True])
def test_permission_query_keeps_attack_role_and_own_model_separate(
    role: str, model_scope: bool
) -> None:
    from tests.generic_modifier_helpers import generic_effect
    from tests.phase11c_command_phase_helpers import battle_state

    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.generic_rule_effect_targets import AttackRole
    from warhammer40k_core.engine.modifier_permission_context import ModifierPermissionAttackContext

    state = battle_state(decisions=DecisionController())
    attacker = state.army_definitions[0].units[0]
    target = state.army_definitions[1].units[0]
    subject = attacker if role == "attacker" else target
    model = subject.own_models[0]
    profile = ArmyCatalog.phase9a_canonical_content_pack().wargear[0].weapon_profiles[0]
    context = ModifierPermissionAttackContext(
        attacking_unit_instance_id=attacker.unit_instance_id,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        target_unit_instance_id=target.unit_instance_id,
        subject_role=cast(AttackRole, role),
        source_phase=BattlePhase.SHOOTING,
        weapon_profile=profile,
        attack_strength=6,
        target_toughness=4,
    )
    state.record_persisting_effect(
        generic_effect(
            effect_id=f"permission:{role}",
            owner_player_id=state.army_definitions[0 if role == "attacker" else 1].player_id,
            target_unit_instance_ids=(subject.unit_instance_id,),
            target_kind="this_model" if model_scope else "this_unit",
            source_model_instance_id=model.model_instance_id if model_scope else None,
            effect_kind="grant_ability",
            parameters={
                "ability": "modifier_ignore_permission",
                "selection": "any_or_all",
                "modifier_kinds": ["save_roll"],
                "attack_role": role,
                "source_phase": "shooting",
                "required_keyword": "INFANTRY",
                "required_keyword_sequence": ["INFANTRY"],
                "selected_target_unit_instance_id": target.unit_instance_id,
                "target_required_keyword": "INFANTRY",
                "target_allegiance": "enemy",
                "target_constraint": "attack_strength_greater_than_target_toughness",
            },
        )
    )

    def permissions(
        attack: ModifierPermissionAttackContext | None,
    ) -> tuple[CatalogModifierIgnorePermission, ...]:
        return modifier_ignore_permissions_for_subject(
            state=state,
            ability_index=AbilityCatalogIndex.from_records(()),
            unit_instance_id=subject.unit_instance_id,
            model_instance_id=model.model_instance_id,
            kind=ModifierIgnoreKind.SAVE_ROLL,
            attack_context=attack,
        )

    assert len(permissions(context)) == 1
    assert permissions(replace(context, attack_strength=3)) == ()
    assert permissions(replace(context, source_phase=BattlePhase.FIGHT)) == ()
    with pytest.raises(GameLifecycleError, match="rules-unit owner"):
        permissions(replace(context, subject_role="target" if role == "attacker" else "attacker"))
    with pytest.raises(GameLifecycleError, match="not in the rules unit"):
        permissions(
            replace(context, attacker_model_instance_id=target.own_models[0].model_instance_id)
        )
    with pytest.raises(GameLifecycleError, match=r"unsupported.*attack context"):
        permissions(None)
    with pytest.raises(GameLifecycleError, match=r"unsupported.*Strength.*Toughness"):
        permissions(replace(context, attack_strength=None))
    # A restricted Save grant cannot break an unrelated nonattack query.
    assert (
        modifier_ignore_permissions_for_subject(
            state=state,
            ability_index=AbilityCatalogIndex.from_records(()),
            unit_instance_id=subject.unit_instance_id,
            model_instance_id=model.model_instance_id,
            kind=ModifierIgnoreKind.OBJECTIVE_CONTROL_CHARACTERISTIC,
        )
        == ()
    )


@pytest.mark.parametrize(
    "parameters",
    [
        {"weapon_scope": "ranged"},
        {"source_phase": "not-a-phase"},
        {"source_phase": 1},
    ],
)
def test_permission_query_preserves_explicit_unsupported_descriptors(
    parameters: dict[str, JsonValue],
) -> None:
    from tests.generic_modifier_helpers import generic_effect
    from tests.phase11c_command_phase_helpers import battle_state

    from warhammer40k_core.engine.decision_controller import DecisionController

    state = battle_state(decisions=DecisionController())
    army = state.army_definitions[0]
    unit = army.units[0]
    state.record_persisting_effect(
        generic_effect(
            effect_id="permission:unsupported",
            owner_player_id=army.player_id,
            target_unit_instance_ids=(unit.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="grant_ability",
            parameters={
                "ability": "modifier_ignore_permission",
                "selection": "any_or_all",
                **parameters,
            },
        )
    )
    with pytest.raises(GameLifecycleError, match=r"unsupported|phase must be"):
        modifier_ignore_permissions_for_subject(
            state=state,
            ability_index=AbilityCatalogIndex.from_records(()),
            unit_instance_id=unit.unit_instance_id,
            model_instance_id=unit.own_models[0].model_instance_id,
            kind=ModifierIgnoreKind.SAVE_ROLL,
        )


@pytest.mark.parametrize("role", ["attacker", "target"])
def test_permission_query_preserves_negative_target_gates(role: str) -> None:
    from tests.generic_modifier_helpers import generic_effect
    from tests.phase11c_command_phase_helpers import battle_state

    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.generic_rule_effect_targets import AttackRole
    from warhammer40k_core.engine.modifier_permission_context import ModifierPermissionAttackContext

    state = battle_state(decisions=DecisionController())
    attacker = state.army_definitions[0].units[0]
    target = state.army_definitions[1].units[0]
    subject = attacker if role == "attacker" else target
    profile = next(
        profile
        for wargear in ArmyCatalog.phase9a_canonical_content_pack().wargear
        for profile in wargear.weapon_profiles
        if profile.profile_id == "core-bolt-rifle:standard"
    )
    context = ModifierPermissionAttackContext(
        attacking_unit_instance_id=attacker.unit_instance_id,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        target_unit_instance_id=target.unit_instance_id,
        subject_role=cast(AttackRole, role),
        source_phase=BattlePhase.SHOOTING,
        weapon_profile=profile,
        attack_strength=4,
        target_toughness=4,
    )
    for index, restriction in enumerate(
        (
            {"selected_target_unit_instance_id": attacker.unit_instance_id},
            {"target_required_keyword": "TITANIC"},
            {"target_allegiance": "friendly"},
            {"attack_role": "target" if role == "attacker" else "attacker"},
        )
    ):
        effect = generic_effect(
            effect_id=f"permission:negative:{index}",
            owner_player_id=state.army_definitions[0 if role == "attacker" else 1].player_id,
            target_unit_instance_ids=(subject.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="grant_ability",
            parameters={
                "ability": "modifier_ignore_permission",
                "selection": "any_or_all",
                "modifier_kinds": ["save_roll"],
                "attack_role": role,
                **cast(dict[str, JsonValue], restriction),
            },
        )
        state.record_persisting_effect(effect)
    assert (
        modifier_ignore_permissions_for_subject(
            state=state,
            ability_index=AbilityCatalogIndex.from_records(()),
            unit_instance_id=subject.unit_instance_id,
            model_instance_id=subject.own_models[0].model_instance_id,
            kind=ModifierIgnoreKind.SAVE_ROLL,
            attack_context=context,
        )
        == ()
    )


@pytest.mark.parametrize(
    "constraint",
    ["source_unit_below_starting_strength", "source_unit_below_half_strength"],
)
@pytest.mark.parametrize("damaged_role", ["attacker", "target"])
def test_defensive_source_strength_permission_requires_explicit_source_authority(
    constraint: str, damaged_role: str
) -> None:
    from tests.generic_modifier_helpers import generic_effect
    from tests.phase11c_command_phase_helpers import battle_state

    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.modifier_permission_context import (
        ModifierPermissionAttackContext,
        UnsupportedModifierPermissionContextError,
    )

    state = battle_state(decisions=DecisionController())
    damaged_army_index = 0 if damaged_role == "attacker" else 1
    army = state.army_definitions[damaged_army_index]
    unit = army.units[0]
    assert len(unit.own_models) > 2
    damaged_unit = replace(
        unit,
        own_models=(
            unit.own_models[0],
            *(replace(model, wounds_remaining=0) for model in unit.own_models[1:]),
        ),
    )
    armies = list(state.army_definitions)
    armies[damaged_army_index] = replace(army, units=(damaged_unit, *army.units[1:]))
    state.replace_army_definitions(armies)
    attacker = state.army_definitions[0].units[0]
    target = state.army_definitions[1].units[0]
    assert (sum(model.is_alive for model in attacker.own_models) == 1) is (
        damaged_role == "attacker"
    )
    assert (sum(model.is_alive for model in target.own_models) == 1) is (damaged_role == "target")
    state.record_persisting_effect(
        generic_effect(
            effect_id="permission:defensive-source-strength",
            owner_player_id=state.army_definitions[1].player_id,
            target_unit_instance_ids=(target.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="grant_ability",
            parameters={
                "ability": "modifier_ignore_permission",
                "selection": "any_or_all",
                "modifier_kinds": ["save_roll"],
                "attack_role": "target",
                "target_constraint": constraint,
            },
        )
    )
    context = ModifierPermissionAttackContext(
        attacking_unit_instance_id=attacker.unit_instance_id,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        target_unit_instance_id=target.unit_instance_id,
        subject_role="target",
        source_phase=BattlePhase.SHOOTING,
        weapon_profile=ArmyCatalog.phase9a_canonical_content_pack().wargear[0].weapon_profiles[0],
        attack_strength=4,
        target_toughness=4,
    )
    with pytest.raises(UnsupportedModifierPermissionContextError, match="source-unit ownership"):
        modifier_ignore_permissions_for_subject(
            state=state,
            ability_index=AbilityCatalogIndex.from_records(()),
            unit_instance_id=target.unit_instance_id,
            model_instance_id=target.own_models[0].model_instance_id,
            kind=ModifierIgnoreKind.SAVE_ROLL,
            attack_context=context,
        )
