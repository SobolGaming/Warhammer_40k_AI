from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from functools import cache
from typing import cast

import pytest
from tests.support.catalog_runtime_fixtures import (
    battle_state_with_armies,
    player_ability_index,
)
from tools.canonical_json_hash import canonical_json_sha256
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)
from tools.generate_aeldari_solitaire_rule_ir import (
    BLITZ_ROW_ID,
    BLUR_OF_MOVEMENT_ROW_ID,
    EXPECTED_ABILITIES_SOURCE_ARTIFACT_HASH,
    EXPECTED_DISPARATE_PATHS_ROW_HASH,
    EXPECTED_REVIEW_ROW,
    EXPECTED_SOURCE_ARTIFACT_HASH,
    EXPECTED_SOURCE_ROW_HASHES,
    FLIP_BELT_ROW_ID,
    OFFICIAL_PDF_PATH,
    REVIEW_MANIFEST_PATH,
    RULE_IR_SOURCE_ROW_IDS,
    generated_artifact_payload,
)

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.datasheet import (
    MUSTERING_WARLORD_FORBIDDEN,
    MUSTERING_WARLORD_RULE_KEY,
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
)
from warhammer40k_core.core.model_geometry_catalog import GeometryReviewStatus
from warhammer40k_core.core.weapon_profiles import (
    RangeProfileKind,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.ability_coverage import (
    WARLORD_RESTRICTION_MUSTERING_CONSUMER_ID,
    AbilityCoverageSupportStage,
    ability_coverage_row_for_descriptor,
)
from warhammer40k_core.engine.advance_eligibility_hooks import (
    AdvanceEligibilityContext,
    AdvanceEligibilityHookRegistry,
)
from warhammer40k_core.engine.advance_hooks import (
    AdvanceMoveContext,
    AdvanceMoveGrant,
    AdvanceMoveHookRegistry,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.catalog_datasheet_rule_descriptors import (
    random_movement_attack_boost_descriptor_for_clause,
)
from warhammer40k_core.engine.catalog_datasheet_rule_runtime import CatalogDatasheetRuleRuntime
from warhammer40k_core.engine.catalog_datasheet_rule_support import (
    CATALOG_IR_MOVEMENT_ACTION_GRANT_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_movement_transit import (
    clause_is_supported_movement_transit_permission,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID,
    CATALOG_IR_MOVEMENT_TRANSIT_PERMISSION_CONSUMER_ID,
    CATALOG_IR_ONCE_PER_BATTLE_ABILITY_CONSUMER_ID,
    CatalogAdvanceEligibilityRuntime,
    catalog_movement_transit_permissions_for_model,
    catalog_rule_ir_consumers_for_rule,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.effects import (
    EffectExpiration,
    PersistingEffect,
)
from warhammer40k_core.engine.event_log import EventLog, JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.movement_budget_modifiers import MovementBudgetModifierContext
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.phases.movement_action_decisions import (
    _record_movement_action_grant_effects,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.rule_frequency import (
    RULE_FREQUENCY_LIMIT_CONSUMED_EVENT,
    OptionalAbilityFrequencyUsage,
    OptionalAbilityFrequencyUsagePayload,
    optional_ability_frequency_usage_unavailable_reason,
)
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.rule_ir import (
    RuleConditionKind,
    RuleDurationKind,
    RuleEffectKind,
    RuleIR,
    RuleIRPayload,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import faction_pack_rule_ir
from warhammer40k_core.rules.wahapedia_bridge_defaults import (
    AELDARI_SOLITAIRE_HEIGHT_OVERRIDES,
)

SOLITAIRE_DATASHEET_ID = "000002538"
SOLITAIRE_SOURCE_PACKAGE_ID = "gw-11e-aeldari-solitaire-datasheet-2026-08"
WRAITHBLADES_DATASHEET_ID = "000000598"


@cache
def _package() -> CanonicalCatalogPackage:
    return _ability_support_catalog_package()


def _source_package() -> faction_pack_rule_ir.SourcePackageRuleIrArtifact:
    return faction_pack_rule_ir.source_package_artifact(SOLITAIRE_SOURCE_PACKAGE_ID)


def test_generated_rule_ir_artifact_is_exact_source_bound_and_fail_fast() -> None:
    source_package = _source_package()
    committed = source_package.payload()

    assert committed == generated_artifact_payload()
    assert committed["source_artifact_hash"] == EXPECTED_SOURCE_ARTIFACT_HASH
    assert committed["official_document_filename"] == OFFICIAL_PDF_PATH.name
    assert (
        committed["official_document_sha256"]
        == hashlib.sha256(OFFICIAL_PDF_PATH.read_bytes()).hexdigest()
    )
    assert committed["official_document_pages"] == []
    assert committed["review_manifest_filename"] == REVIEW_MANIFEST_PATH.name
    assert committed["review_manifest_sha256"] == canonical_json_sha256(REVIEW_MANIFEST_PATH)
    assert committed["review_row_id"] == EXPECTED_REVIEW_ROW["review_row_id"]
    assert committed["review_treatment"] == EXPECTED_REVIEW_ROW["treatment"]
    assert source_package.supported_datasheet_source_row_ids() == RULE_IR_SOURCE_ROW_IDS
    assert committed["package_hash"] == source_package.package_hash
    assert EXPECTED_SOURCE_ROW_HASHES == {
        "000002538:5": "9fb6a60d9569ef218781538a7230e4d9b6288a7c81fe7af4ac09f4fe601c1067",
        "000002538:6": "9ea4336d9d3f3172e95406c7b6296913e0acaef48dc8a26846fe743531c8211b",
        "000002538:7": "78f23f7ed60e51ab6b9045011b91ceebac67a4a4d5898872556af3b1e88cdd87",
        "000002538:8": "c674d63ce799698d3666314f44274310aee1ad5056420b36391c5cfb2cd87bbb",
        "000002538:9": "7c9b047b1c82c1f3f5ac84333db059aa669a666a724d300703f4f8fd3e0fc273",
    }
    assert EXPECTED_ABILITIES_SOURCE_ARTIFACT_HASH == (
        "5d2718402066eecc33195e14f98d44900e374e8450ef246c2b766dd08e833990"
    )
    assert EXPECTED_DISPARATE_PATHS_ROW_HASH == (
        "4d4c33de2795689a0fcdc0b56570b95f22664ada3b67a492da111d102a610635"
    )

    committed["package_hash"] = "0" * 64
    with pytest.raises(faction_pack_rule_ir.FactionPackRuleIrRegistryError, match="hash is stale"):
        source_package.validate_generated_artifact_bytes(json.dumps(committed).encode())


def test_blitz_rule_ir_is_one_compound_pre_move_runtime_grant() -> None:
    rule = _rule_ir(BLITZ_ROW_ID)
    assert catalog_rule_ir_consumers_for_rule(rule) == (
        CATALOG_IR_MOVEMENT_ACTION_GRANT_CONSUMER_ID,
        CATALOG_IR_ONCE_PER_BATTLE_ABILITY_CONSUMER_ID,
    )

    (clause,) = rule.clauses
    assert clause.trigger is not None
    assert clause.trigger.kind is RuleTriggerKind.UNIT_SELECTED
    assert parameter_payload(clause.trigger.parameters) == {
        "action": "normal_move",
        "owner": "active_player",
        "optional": True,
        "phase": "movement",
        "subject": "this_model",
        "timing_window": "before_normal_move",
    }
    assert len(clause.conditions) == 1
    assert clause.conditions[0].kind is RuleConditionKind.FREQUENCY_LIMIT
    assert parameter_payload(clause.conditions[0].parameters) == {
        "activation_kind": "optional_ability_use",
        "max_uses": 1,
        "scope": "battle",
        "usage_subject": "this_model",
    }
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.THIS_MODEL
    assert clause.duration is not None
    assert clause.duration.kind is RuleDurationKind.UNTIL_TIMING_ENDPOINT
    assert parameter_payload(clause.duration.parameters) == {"endpoint": "turn"}

    movement, attacks = clause.effects
    assert movement.kind is RuleEffectKind.MODIFY_MOVE_DISTANCE
    assert parameter_payload(movement.parameters) == {
        "characteristic": Characteristic.MOVEMENT.value,
        "operation": "add",
        "roll_expression": "2D6",
        "target_scope": "this_model",
    }
    assert attacks.kind is RuleEffectKind.MODIFY_CHARACTERISTIC
    assert parameter_payload(attacks.parameters) == {
        "characteristic": Characteristic.ATTACKS.value,
        "delta": 3,
        "target_scope": "this_model",
        "weapon_names": ("Solitaire weapons",),
    }
    descriptor = random_movement_attack_boost_descriptor_for_clause(clause)
    assert descriptor is not None
    assert descriptor.movement_action == "normal_move"
    assert descriptor.movement_bonus_expression.canonical() == "2D6"
    assert descriptor.attacks_delta == 3
    assert descriptor.weapon_names == ("Solitaire weapons",)


def test_blur_and_flip_belt_are_model_scoped_generic_runtime_rules() -> None:
    blur = _rule_ir(BLUR_OF_MOVEMENT_ROW_ID)
    flip_belt = _rule_ir(FLIP_BELT_ROW_ID)

    assert catalog_rule_ir_consumers_for_rule(blur) == (
        CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID,
    )
    (blur_clause,) = blur.clauses
    assert blur_clause.target is not None
    assert blur_clause.target.kind is RuleTargetKind.THIS_MODEL
    assert blur_clause.duration is not None
    assert blur_clause.duration.kind is RuleDurationKind.PERMANENT
    assert blur_clause.effects[0].kind is RuleEffectKind.GRANT_ABILITY
    assert parameter_payload(blur_clause.effects[0].parameters) == {
        "ability": "can_advance_and_charge",
        "target_scope": "this_model",
    }

    assert catalog_rule_ir_consumers_for_rule(flip_belt) == (
        CATALOG_IR_MOVEMENT_TRANSIT_PERMISSION_CONSUMER_ID,
    )
    (flip_clause,) = flip_belt.clauses
    assert clause_is_supported_movement_transit_permission(flip_clause)
    assert flip_clause.trigger is not None
    assert flip_clause.trigger.kind is RuleTriggerKind.TIMING_WINDOW
    assert parameter_payload(flip_clause.trigger.parameters) == {
        "edge": "during",
        "movement_modes": ("normal", "advance", "fall_back", "charge"),
        "phase": "movement",
        "subject": "this_model",
        "timing_window": "model_makes_move",
    }
    assert flip_clause.target is not None
    assert flip_clause.target.kind is RuleTargetKind.THIS_MODEL
    assert flip_clause.effects[0].kind is RuleEffectKind.MOVEMENT_TRANSIT_PERMISSION
    assert parameter_payload(flip_clause.effects[0].parameters) == {
        "movement_modes": ("normal", "advance", "fall_back", "charge"),
        "permission": "ignore_vertical_distance",
    }


def test_blitz_registry_grant_and_resolved_effect_use_source_backed_consumers() -> None:
    package, armies, state, indexes, solitaire, enemy = _runtime_fixture()
    runtime = CatalogDatasheetRuleRuntime(indexes, armies)
    registry = AdvanceMoveHookRegistry.from_bindings(runtime.advance_move_hook_bindings())
    events = EventLog()
    context = AdvanceMoveContext(
        state=state,
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=solitaire.unit_instance_id,
        movement_phase_action="normal_move",
        movement_request_id="solitaire-blitz-movement-request",
        movement_result_id="solitaire-blitz-movement-result",
        event_log=events,
    )

    grants = registry.grants_for(context)
    assert len(grants) == 1
    grant = grants[0]
    assert grant.label == "Blitz"
    assert grant.movement_bonus_dice_expression is not None
    assert grant.movement_bonus_dice_expression.canonical() == "2D6"
    assert grant.movement_bonus_inches == 0
    assert grant.unit_effect_expiration == "end_turn"
    assert grant.rule_frequency_usage is not None
    usage = grant.rule_frequency_usage
    assert OptionalAbilityFrequencyUsage.from_payload(usage.to_payload()) == usage
    assert AdvanceMoveGrant.from_payload(grant.to_payload()) == grant
    model = solitaire.own_models[0]
    assert (
        usage.activation_kind,
        usage.scope,
        usage.max_uses,
        usage.usage_subject,
        usage.source_unit_instance_id,
        usage.source_model_instance_id,
    ) == (
        "optional_ability_use",
        "battle",
        1,
        "this_model",
        solitaire.unit_instance_id,
        model.model_instance_id,
    )

    payload = cast(dict[str, JsonValue], grant.unit_effect_payload)
    assert payload["attacks_delta"] == 3
    assert payload["weapon_names"] == ["Solitaire weapons"]
    decisions = DecisionController(event_log=events)
    (resolved_effect,) = _record_movement_action_grant_effects(
        state=state,
        decisions=decisions,
        player_id="player-a",
        unit_instance_id=solitaire.unit_instance_id,
        source_request_id="solitaire-blitz-grant-request",
        source_result_id="solitaire-blitz-grant-result",
        grant=grant,
    )
    resolved_payload = cast(dict[str, JsonValue], resolved_effect.effect_payload)
    assert PersistingEffect.from_payload(resolved_effect.to_payload()) == resolved_effect
    assert resolved_effect.source_rule_id == grant.source_id
    assert resolved_effect.owner_player_id == "player-a"
    assert resolved_effect.target_unit_instance_ids == (solitaire.unit_instance_id,)
    assert resolved_effect.started_phase is BattlePhase.MOVEMENT
    assert resolved_effect.expiration == EffectExpiration.end_turn(
        battle_round=state.battle_round,
        player_id="player-a",
    )
    assert set(resolved_payload) == {
        "effect_kind",
        "catalog_record_id",
        "source_rule_id",
        "source_unit_instance_id",
        "source_model_instance_id",
        "rules_unit_instance_id",
        "clause_id",
        "attacks_delta",
        "weapon_names",
        "movement_bonus_inches",
        "movement_bonus_roll",
    }
    movement_bonus = resolved_payload["movement_bonus_inches"]
    assert type(movement_bonus) is int
    assert 2 <= movement_bonus <= 12
    movement_roll = cast(dict[str, JsonValue], resolved_payload["movement_bonus_roll"])
    assert movement_roll["characteristic"] == Characteristic.MOVEMENT.value
    assert movement_roll["timing"] == "unit_when_selected_to_move"
    assert movement_roll["value"] == movement_bonus
    roll_state = cast(dict[str, JsonValue], movement_roll["roll_state"])
    original_result = cast(dict[str, JsonValue], roll_state["original_result"])
    roll_spec = cast(dict[str, JsonValue], original_result["spec"])
    assert roll_spec["expression"] == {"quantity": 2, "sides": 6, "modifier": 0}
    modifier_registry = RuntimeModifierRegistry.from_bindings(
        movement_budget_modifier_bindings=runtime.movement_budget_modifier_bindings(),
        weapon_profile_modifier_bindings=runtime.weapon_profile_modifier_bindings(),
    )
    assert (
        modifier_registry.modified_movement_inches(
            MovementBudgetModifierContext(
                state=state,
                unit_instance_id=solitaire.unit_instance_id,
                model_instance_id=model.model_instance_id,
                base_movement_inches=12.0,
                current_movement_inches=12.0,
            )
        )
        == 12.0 + movement_bonus
    )

    solitaire_weapons = _first_weapon_profile_for_model(package, solitaire)
    modified_solitaire_weapons = modifier_registry.modified_weapon_profile(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.FIGHT,
            attacking_unit_instance_id=solitaire.unit_instance_id,
            attacker_model_instance_id=model.model_instance_id,
            target_unit_instance_id=enemy.unit_instance_id,
            weapon_profile=solitaire_weapons,
        )
    )
    assert solitaire_weapons.name == "Solitaire weapons"
    assert solitaire_weapons.attack_profile.fixed_attacks == 9
    assert modified_solitaire_weapons.attack_profile.fixed_attacks == 12

    other_weapons = _first_weapon_profile_for_model(package, enemy)
    assert other_weapons.name != "Solitaire weapons"
    assert (
        modifier_registry.modified_weapon_profile(
            WeaponProfileModifierContext(
                state=state,
                source_phase=BattlePhase.FIGHT,
                attacking_unit_instance_id=solitaire.unit_instance_id,
                attacker_model_instance_id=model.model_instance_id,
                target_unit_instance_id=enemy.unit_instance_id,
                weapon_profile=other_weapons,
            )
        )
        == other_weapons
    )

    (frequency_event,) = tuple(
        record for record in events.records if record.event_type == "rule_frequency_limit_consumed"
    )
    assert frequency_event.event_type == "rule_frequency_limit_consumed"
    assert cast(dict[str, JsonValue], frequency_event.payload)["usage_key"] == usage.usage_key
    assert registry.grants_for(context) == ()


def test_blitz_frequency_usage_rejects_canonical_metadata_drift() -> None:
    _, armies, state, indexes, solitaire, _ = _runtime_fixture()
    runtime = CatalogDatasheetRuleRuntime(indexes, armies)
    registry = AdvanceMoveHookRegistry.from_bindings(runtime.advance_move_hook_bindings())
    (grant,) = registry.grants_for(
        AdvanceMoveContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=solitaire.unit_instance_id,
            movement_phase_action="normal_move",
            movement_request_id="solitaire-frequency-movement-request",
            movement_result_id="solitaire-frequency-movement-result",
            event_log=EventLog(),
        )
    )
    usage = grant.rule_frequency_usage
    assert usage is not None
    canonical = usage.to_payload()
    assert OptionalAbilityFrequencyUsage.from_payload(canonical) == usage

    drifted_values: tuple[tuple[str, JsonValue], ...] = (
        ("usage_key", "rule-frequency:" + "0" * 64),
        ("rule_id", "drifted-rule"),
        ("source_id", "drifted-source"),
        ("rule_ir_hash", "1" * 64),
        ("clause_id", "drifted-clause"),
        ("player_id", "player-b"),
        ("source_unit_instance_id", "drifted-unit"),
        ("source_model_instance_id", "drifted-model"),
        ("usage_subject", "bearer"),
    )
    for field_name, value in drifted_values:
        drifted = dict(canonical)
        drifted[field_name] = value
        with pytest.raises(GameLifecycleError, match="frequency usage_key"):
            OptionalAbilityFrequencyUsage.from_payload(
                cast(OptionalAbilityFrequencyUsagePayload, drifted)
            )

    event_payload = cast(dict[str, JsonValue], dict(canonical))
    event_payload.update(
        {
            "battle_round": state.battle_round,
            "phase": BattlePhase.MOVEMENT.value,
            "active_player_id": "player-a",
            "timing_window_id": "before_normal_move",
        }
    )
    restored_events = EventLog()
    restored_events.append(
        RULE_FREQUENCY_LIMIT_CONSUMED_EVENT,
        {**event_payload, "player_id": "player-b"},
    )
    with pytest.raises(GameLifecycleError, match="frequency usage_key"):
        optional_ability_frequency_usage_unavailable_reason(
            usage=usage,
            event_log=restored_events,
        )

    missing_metadata = dict(event_payload)
    del missing_metadata["battle_round"]
    malformed_events = EventLog()
    malformed_events.append(RULE_FREQUENCY_LIMIT_CONSUMED_EVENT, missing_metadata)
    with pytest.raises(GameLifecycleError, match="exact typed metadata"):
        optional_ability_frequency_usage_unavailable_reason(
            usage=usage,
            event_log=malformed_events,
        )

    invalid_round = EventLog()
    invalid_round.append(
        RULE_FREQUENCY_LIMIT_CONSUMED_EVENT,
        {**event_payload, "battle_round": 0},
    )
    with pytest.raises(GameLifecycleError, match="battle_round must be at least 1"):
        optional_ability_frequency_usage_unavailable_reason(
            usage=usage,
            event_log=invalid_round,
        )


def test_blitz_restored_effect_drift_is_rejected_by_movement_and_weapon_consumers() -> None:
    package, armies, state, indexes, solitaire, enemy = _runtime_fixture()
    runtime = CatalogDatasheetRuleRuntime(indexes, armies)
    grant_registry = AdvanceMoveHookRegistry.from_bindings(runtime.advance_move_hook_bindings())
    events = EventLog()
    (grant,) = grant_registry.grants_for(
        AdvanceMoveContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=solitaire.unit_instance_id,
            movement_phase_action="normal_move",
            movement_request_id="solitaire-restored-movement-request",
            movement_result_id="solitaire-restored-movement-result",
            event_log=events,
        )
    )
    (resolved_effect,) = _record_movement_action_grant_effects(
        state=state,
        decisions=DecisionController(event_log=events),
        player_id="player-a",
        unit_instance_id=solitaire.unit_instance_id,
        source_request_id="solitaire-restored-grant-request",
        source_result_id="solitaire-restored-grant-result",
        grant=grant,
    )
    restored_effect = PersistingEffect.from_payload(resolved_effect.to_payload())
    state.persisting_effects = [restored_effect]
    model = solitaire.own_models[0]
    modifier_registry = RuntimeModifierRegistry.from_bindings(
        movement_budget_modifier_bindings=runtime.movement_budget_modifier_bindings(),
        weapon_profile_modifier_bindings=runtime.weapon_profile_modifier_bindings(),
    )
    movement_context = MovementBudgetModifierContext(
        state=state,
        unit_instance_id=solitaire.unit_instance_id,
        model_instance_id=model.model_instance_id,
        base_movement_inches=12.0,
        current_movement_inches=12.0,
    )
    weapon_context = WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.FIGHT,
        attacking_unit_instance_id=solitaire.unit_instance_id,
        attacker_model_instance_id=model.model_instance_id,
        target_unit_instance_id=enemy.unit_instance_id,
        weapon_profile=_first_weapon_profile_for_model(package, solitaire),
    )
    movement_bonus = cast(dict[str, JsonValue], restored_effect.effect_payload)[
        "movement_bonus_inches"
    ]
    assert type(movement_bonus) is int
    assert modifier_registry.modified_movement_inches(movement_context) == 12.0 + movement_bonus
    assert (
        modifier_registry.modified_weapon_profile(weapon_context).attack_profile.fixed_attacks == 12
    )

    payload = cast(dict[str, JsonValue], restored_effect.effect_payload)
    payload_drifts: list[dict[str, JsonValue]] = []
    for field_name, value in (
        ("effect_kind", "drifted-effect-kind"),
        ("catalog_record_id", "drifted-catalog-record"),
        ("source_rule_id", "drifted-source-rule"),
        ("source_unit_instance_id", "drifted-source-unit"),
        ("source_model_instance_id", "drifted-source-model"),
        ("rules_unit_instance_id", enemy.unit_instance_id),
        ("clause_id", "drifted-clause"),
        ("attacks_delta", 4),
        ("weapon_names", ["Drifted weapons"]),
        ("movement_bonus_inches", 2 if movement_bonus != 2 else 3),
    ):
        drifted = deepcopy(payload)
        drifted[field_name] = cast(JsonValue, value)
        payload_drifts.append(drifted)
    missing_field = deepcopy(payload)
    del missing_field["clause_id"]
    payload_drifts.append(missing_field)
    extra_field = deepcopy(payload)
    extra_field["untrusted_extra"] = True
    payload_drifts.append(extra_field)
    for roll_field, value in (
        ("timing", "per_use"),
        ("scope_id", "drifted-roll-scope"),
        ("value", 2 if movement_bonus != 2 else 3),
    ):
        drifted = deepcopy(payload)
        roll = cast(dict[str, JsonValue], drifted["movement_bonus_roll"])
        roll[roll_field] = cast(JsonValue, value)
        payload_drifts.append(drifted)
    drifted_expression = deepcopy(payload)
    drifted_roll = cast(dict[str, JsonValue], drifted_expression["movement_bonus_roll"])
    drifted_state = cast(dict[str, JsonValue], drifted_roll["roll_state"])
    drifted_result = cast(dict[str, JsonValue], drifted_state["original_result"])
    drifted_spec = cast(dict[str, JsonValue], drifted_result["spec"])
    drifted_spec["expression"] = {"quantity": 2, "sides": 8, "modifier": 0}
    payload_drifts.append(drifted_expression)

    outer_drifts = (
        replace(restored_effect, owner_player_id="player-b"),
        replace(restored_effect, source_rule_id="drifted-source-rule"),
        replace(
            restored_effect,
            target_unit_instance_ids=(solitaire.unit_instance_id, enemy.unit_instance_id),
        ),
        replace(
            restored_effect,
            started_battle_round=state.battle_round + 1,
            expiration=EffectExpiration.end_turn(
                battle_round=state.battle_round + 1,
                player_id="player-a",
            ),
        ),
        replace(restored_effect, started_phase=BattlePhase.FIGHT),
        replace(
            restored_effect,
            expiration=EffectExpiration.end_turn(
                battle_round=state.battle_round,
                player_id="player-b",
            ),
        ),
    )
    drifted_effects = (
        *outer_drifts,
        *(
            replace(restored_effect, effect_payload=drifted_payload)
            for drifted_payload in payload_drifts
        ),
    )
    for drifted_effect in drifted_effects:
        state.persisting_effects = [drifted_effect]
        with pytest.raises(GameLifecycleError, match="Random movement attack boost"):
            modifier_registry.modified_movement_inches(movement_context)
        with pytest.raises(GameLifecycleError, match="Random movement attack boost"):
            modifier_registry.modified_weapon_profile(weapon_context)


def test_blur_of_movement_runtime_grants_charge_eligibility_after_advancing() -> None:
    package, armies, state, indexes, solitaire, _ = _runtime_fixture()
    runtime = CatalogAdvanceEligibilityRuntime(indexes, armies)
    registry = AdvanceEligibilityHookRegistry.from_bindings(runtime.bindings())
    grants = registry.grants_for(
        AdvanceEligibilityContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=solitaire.unit_instance_id,
            movement_request_id="solitaire-advance-request",
            movement_result_id="solitaire-advance-result",
        )
    )

    assert len(grants) == 1
    grant = grants[0]
    assert grant.hook_id == CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID
    assert grant.can_shoot is False
    assert grant.can_declare_charge is True
    blur = next(
        ability
        for ability in package.army_catalog.datasheet_by_id(SOLITAIRE_DATASHEET_ID).abilities
        if ability.name == "Blur of Movement"
    )
    replay_payload = cast(dict[str, JsonValue], grant.replay_payload)
    assert replay_payload["ability"] == "can_advance_and_charge"
    assert replay_payload["ability_ids"] == [blur.ability_id]
    assert replay_payload["source_rule_ids"] == [blur.source_id]


def test_flip_belt_runtime_permission_is_scoped_to_its_bearer_model() -> None:
    _, _, _, indexes, solitaire, _ = _runtime_fixture()
    model = solitaire.own_models[0]

    for movement_mode in ("normal", "advance", "fall_back", "charge"):
        permissions = catalog_movement_transit_permissions_for_model(
            ability_index=indexes["player-a"],
            unit=solitaire,
            model_instance_id=model.model_instance_id,
            current_model_instance_ids=(model.model_instance_id,),
            movement_mode=movement_mode,
        )
        assert len(permissions) == 1
        permission = permissions[0]
        assert permission.ability_id == f"{SOLITAIRE_DATASHEET_ID}:flip-belt"
        assert permission.permission == "ignore_vertical_distance"
        assert permission.movement_modes == ("advance", "charge", "fall_back", "normal")

    without_flip_belt = replace(
        solitaire,
        own_models=(
            replace(
                model,
                wargear_ids=tuple(
                    wargear_id
                    for wargear_id in model.wargear_ids
                    if wargear_id != f"{SOLITAIRE_DATASHEET_ID}:flip-belt"
                ),
            ),
        ),
    )
    assert (
        catalog_movement_transit_permissions_for_model(
            ability_index=indexes["player-a"],
            unit=without_flip_belt,
            model_instance_id=model.model_instance_id,
            current_model_instance_ids=(model.model_instance_id,),
            movement_mode="normal",
        )
        == ()
    )


def test_solitaire_catalog_is_complete_engine_consumed_and_fieldable() -> None:
    package = _package()
    catalog = package.army_catalog
    datasheet = catalog.datasheet_by_id(SOLITAIRE_DATASHEET_ID)
    model = datasheet.model_profiles[0]
    values = {value.characteristic: value.final for value in model.characteristics}

    assert datasheet.name == "Solitaire"
    assert (
        values[Characteristic.MOVEMENT],
        values[Characteristic.TOUGHNESS],
        values[Characteristic.SAVE],
        values[Characteristic.WOUNDS],
        values[Characteristic.LEADERSHIP],
        values[Characteristic.OBJECTIVE_CONTROL],
        values[Characteristic.INVULNERABLE_SAVE],
    ) == (12, 3, 6, 4, 6, 1, 4)
    assert model.base_size.diameter_mm == 25.0
    assert datasheet.keywords.keywords == (
        "AELDARI",
        "CHARACTER",
        "EPIC HERO",
        "INFANTRY",
        "SOLITAIRE",
    )
    assert datasheet.keywords.faction_keywords == ("HARLEQUINS",)
    assert (datasheet.composition[0].min_models, datasheet.composition[0].max_models) == (1, 1)

    wargear = {
        item.wargear_id: item
        for item in catalog.wargear
        if item.wargear_id.startswith(f"{SOLITAIRE_DATASHEET_ID}:")
    }
    assert set(wargear) == {
        f"{SOLITAIRE_DATASHEET_ID}:flip-belt",
        f"{SOLITAIRE_DATASHEET_ID}:solitaire-weapons",
    }
    weapon = wargear[f"{SOLITAIRE_DATASHEET_ID}:solitaire-weapons"].weapon_profiles[0]
    assert weapon.name == "Solitaire weapons"
    assert weapon.range_profile.kind is RangeProfileKind.MELEE
    assert weapon.attack_profile.fixed_attacks == 9
    assert (weapon.skill.final, weapon.strength.final, weapon.armor_penetration.final) == (2, 6, -2)
    assert weapon.damage_profile.fixed_damage == 2
    assert weapon.keywords == (WeaponKeyword.PRECISION,)

    abilities = {ability.name: ability for ability in datasheet.abilities}
    assert set(abilities) == {
        "Battle Focus",
        "Blitz",
        "Blur of Movement",
        "Disparate Paths",
        "Fights First",
        "Flip Belt",
        "Lone Operative",
        "PATH OF DAMNATION",
        "Stealth",
    }
    for name in ("Blitz", "Blur of Movement", "Flip Belt"):
        assert abilities[name].support is CatalogAbilitySupport.GENERIC_RULE_IR
        coverage = ability_coverage_row_for_descriptor(
            catalog_id=catalog.catalog_id,
            datasheet_id=datasheet.datasheet_id,
            datasheet_name=datasheet.name,
            ability=abilities[name],
        )
        assert coverage.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED

    flip_belt = abilities["Flip Belt"]
    assert flip_belt.source_kind is CatalogAbilitySourceKind.WARGEAR
    assert flip_belt.source_wargear_id == f"{SOLITAIRE_DATASHEET_ID}:flip-belt"

    path = abilities["PATH OF DAMNATION"]
    assert path.support is CatalogAbilitySupport.DESCRIPTOR_ONLY
    assert path.source_kind is CatalogAbilitySourceKind.DATASHEET
    assert path.rule_ir_payload == {
        MUSTERING_WARLORD_RULE_KEY: MUSTERING_WARLORD_FORBIDDEN,
    }
    path_coverage = ability_coverage_row_for_descriptor(
        catalog_id=catalog.catalog_id,
        datasheet_id=datasheet.datasheet_id,
        datasheet_name=datasheet.name,
        ability=path,
    )
    assert path_coverage.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
    assert path_coverage.runtime_consumer_ids == (WARLORD_RESTRICTION_MUSTERING_CONSUMER_ID,)

    disparate_paths = abilities["Disparate Paths"]
    assert disparate_paths.ability_id == "000009896"
    assert disparate_paths.source_kind is CatalogAbilitySourceKind.FACTION
    assert disparate_paths.effect_description.startswith(
        "When mustering your army, you can include Harlequins units in your army"
    )
    assert disparate_paths.source_id.endswith(":Datasheets_abilities:000002538:5")

    geometry = next(
        row for row in package.model_geometries if row.model_profile_id == model.model_profile_id
    )
    assert len(AELDARI_SOLITAIRE_HEIGHT_OVERRIDES) == 1
    height_override = AELDARI_SOLITAIRE_HEIGHT_OVERRIDES[0]
    assert (
        height_override.datasheet_id,
        height_override.model_name,
        height_override.height,
        height_override.height_source_id,
    ) == (
        SOLITAIRE_DATASHEET_ID,
        "Solitaire - EPIC HERO",
        2.25,
        "geometry-review:aeldari:solitaire:height",
    )
    assert geometry.height.height_inches == 2.25
    assert any(
        evidence.reviewer_status is GeometryReviewStatus.ACCEPTED for evidence in geometry.evidence
    )

    factory = UnitFactory(catalog=catalog, model_geometries=package.model_geometries)
    unit = factory.instantiate_unit(
        army_id="army-aeldari",
        datasheet=datasheet,
        selection=UnitMusterSelection(
            unit_selection_id="anvanth-solitaire",
            datasheet_id=SOLITAIRE_DATASHEET_ID,
            model_profile_selections=(ModelProfileSelection(model.model_profile_id, 1),),
        ),
    )
    assert unit.own_models[0].wargear_ids == (
        f"{SOLITAIRE_DATASHEET_ID}:solitaire-weapons",
        f"{SOLITAIRE_DATASHEET_ID}:flip-belt",
    )


def _rule_ir(source_row_id: str) -> RuleIR:
    payload = _source_package().datasheet_rule_ir_payload_by_source_row_id(source_row_id)
    return RuleIR.from_payload(cast(RuleIRPayload, payload))


def _runtime_fixture() -> tuple[
    CanonicalCatalogPackage,
    tuple[ArmyDefinition, ...],
    GameState,
    dict[str, AbilityCatalogIndex],
    UnitInstance,
    UnitInstance,
]:
    package = _package()
    catalog = package.army_catalog
    factory = UnitFactory(catalog=catalog, model_geometries=package.model_geometries)
    solitaire = _instantiate_default_unit(
        factory,
        army_id="army-a",
        selection_id="solitaire",
        datasheet_id=SOLITAIRE_DATASHEET_ID,
    )
    enemy = _instantiate_default_unit(
        factory,
        army_id="army-b",
        selection_id="wraithblades",
        datasheet_id=WRAITHBLADES_DATASHEET_ID,
    )
    armies = (
        _army(catalog, army_id="army-a", player_id="player-a", units=(solitaire,)),
        _army(catalog, army_id="army-b", player_id="player-b", units=(enemy,)),
    )
    state = battle_state_with_armies(
        armies=armies,
        battlefield=create_deterministic_battlefield_scenario(
            battlefield_id="aeldari-solitaire-runtime-battlefield",
            armies=armies,
        ).battlefield_state,
        active_player_id="player-a",
        phase=BattlePhase.MOVEMENT,
    )
    indexes = {army.player_id: player_ability_index(package=package, army=army) for army in armies}
    return package, armies, state, indexes, solitaire, enemy


def _army(
    catalog: ArmyCatalog,
    *,
    army_id: str,
    player_id: str,
    units: tuple[UnitInstance, ...],
) -> ArmyDefinition:
    return ArmyDefinition(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="AE",
            detachment_ids=("corsair-coterie",),
        ),
        force_disposition_id=("take-and-hold" if player_id == "player-a" else "purge-the-foe"),
        units=units,
    )


def _instantiate_default_unit(
    factory: UnitFactory,
    *,
    army_id: str,
    selection_id: str,
    datasheet_id: str,
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
                ModelProfileSelection(
                    model_profile.model_profile_id,
                    datasheet.composition[0].min_models,
                ),
            ),
        ),
    )


def _first_weapon_profile_for_model(
    package: CanonicalCatalogPackage,
    unit: UnitInstance,
) -> WeaponProfile:
    equipped_ids = set(unit.own_models[0].wargear_ids)
    profiles = tuple(
        profile
        for wargear in package.army_catalog.wargear
        if wargear.wargear_id in equipped_ids
        for profile in wargear.weapon_profiles
    )
    if not profiles:
        raise AssertionError("Solitaire runtime fixture model must have an equipped weapon.")
    return profiles[0]
