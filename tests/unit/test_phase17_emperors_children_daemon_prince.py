from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from functools import cache
from typing import Any, cast

from tests.phase15c_fight_order_helpers import fight_lifecycle
from tools import generate_emperors_children_daemon_prince_rule_ir as generator
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.datasheet import CatalogAbilitySupport
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import RangeProfileKind, WeaponProfile
from warhammer40k_core.engine.ability_catalog import (
    build_player_ability_index,
    catalog_ability_records_from_catalog,
)
from warhammer40k_core.engine.ability_coverage import (
    AbilityCoverageSupportStage,
    ability_coverage_rows_from_catalog,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.catalog_datasheet_rule_runtime import CatalogDatasheetRuleRuntime
from warhammer40k_core.engine.catalog_datasheet_rule_support import (
    CATALOG_IR_CHARGED_MELEE_WEAPON_CHARACTERISTIC_AURA_CONSUMER_ID,
    CATALOG_IR_CONDITIONAL_LONE_OPERATIVE_CONSUMER_ID,
    CATALOG_IR_FIGHT_ON_DEATH_SOURCE_CONSUMER_ID,
    registered_consumer_ids,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_ir_consumers_for_rule,
)
from warhammer40k_core.engine.damage_allocation import (
    DECLINE_DESTRUCTION_REACTION_OPTION_ID,
    SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
    DamageKind,
    DestructionReactionKind,
    DestructionReactionSource,
    apply_damage_to_model,
)
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.fight_on_death import model_is_present_on_battlefield
from warhammer40k_core.engine.fight_order import CHARGE_FIGHTS_FIRST_EFFECT_KIND
from warhammer40k_core.engine.fight_resolution import (
    SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
    MeleeDeclarationProposalRequest,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.target_restriction_hooks import ShootingTargetRestrictionContext
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.pose import Pose
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
from warhammer40k_core.rules.source_patch import source_row_hash
from warhammer40k_core.rules.wahapedia_schema import (
    WahapediaJsonArtifact,
    WahapediaJsonArtifactPayload,
)

DAEMON_PRINCE_ID = "000004086"
TORMENTORS_ID = "000004079"
EXPECTED_PACKAGE_HASH = "86cf74bc36db389c92c05dba0752832eed98272a0a0fa2d16923c1e2b5f16d84"


def test_generated_artifact_is_exact_predecessor_source_bound_and_deterministic() -> None:
    payload = generator.generated_artifact_payload()

    assert payload == generator.generated_artifact_payload()
    assert payload["artifact_schema"] == generator.ARTIFACT_SCHEMA
    assert payload["source_package_id"] == generator.SOURCE_PACKAGE_ID
    assert payload["source_artifact_hash"] == generator.EXPECTED_SOURCE_ARTIFACT_HASH
    assert payload["official_document_pages"] == []
    assert payload["datasheets"] == [generator.EXPECTED_REVIEW_ROW]
    assert payload["package_hash"] == EXPECTED_PACKAGE_HASH

    records = cast(dict[str, dict[str, Any]], payload["records"])
    assert set(records) == set(generator.ABILITY_NAMES)
    for source_row_id, expected_name in generator.ABILITY_NAMES.items():
        record = records[source_row_id]
        assert record["datasheet_id"] == DAEMON_PRINCE_ID
        assert record["datasheet_name"] == generator.DATASHEET_NAME
        assert record["ability_name"] == expected_name
        assert (
            record["normalized_text_sha256"]
            == generator.EXPECTED_PREDECESSOR_TEXT_SHA256[source_row_id]
        )
        rule_ir = RuleIR.from_payload(cast(RuleIRPayload, record["rule_ir"]))
        assert rule_ir.is_supported
        assert rule_ir.source_id == f"{generator.SOURCE_PACKAGE_ID}:datasheet:{source_row_id}"


def test_exact_source_row_hashes_match_the_pinned_normalized_rows() -> None:
    source_payload = json.loads(generator.SOURCE_PATH.read_text(encoding="utf-8"))
    source_artifact = WahapediaJsonArtifact.from_payload(
        cast(WahapediaJsonArtifactPayload, source_payload)
    )
    assert source_artifact.artifact_hash() == generator.EXPECTED_SOURCE_ARTIFACT_HASH

    rows = {
        row.source_row_id: row
        for row in source_artifact.rows
        if row.source_row_id in generator.ABILITY_NAMES
    }
    assert set(rows) == set(generator.ABILITY_NAMES)
    for source_row_id, row in rows.items():
        fields = row.runtime_fields_payload()
        description = fields["description"]
        assert type(description) is str
        assert fields["datasheet_id"] == DAEMON_PRINCE_ID
        assert fields["name"] == generator.ABILITY_NAMES[source_row_id]
        assert source_row_hash(row) == generator.EXPECTED_SOURCE_ROW_HASHES[source_row_id]
        assert (
            hashlib.sha256(description.encode()).hexdigest()
            == generator.EXPECTED_PREDECESSOR_TEXT_SHA256[source_row_id]
        )


def test_lord_of_excess_and_ecstatic_death_use_existing_generic_contracts() -> None:
    lord = _generated_rule(generator.LORD_OF_EXCESS_ROW_ID)
    lord_clause = lord.clauses[0]
    assert lord_clause.template_id == "phase17c:conditional-ability-grant"
    assert lord_clause.trigger is None
    assert lord_clause.target is not None
    assert lord_clause.target.kind is RuleTargetKind.THIS_MODEL
    assert lord_clause.duration is not None
    assert lord_clause.duration.kind is RuleDurationKind.WHILE_CONDITION_TRUE
    assert len(lord_clause.conditions) == 1
    assert lord_clause.conditions[0].kind is RuleConditionKind.DISTANCE_PREDICATE
    assert parameter_payload(lord_clause.conditions[0].parameters) == {
        "allegiance": "friendly",
        "distance_inches": 3,
        "object_kind": "unit",
        "predicate": "within",
        "required_keyword_sequence": ("SLAANESH", "INFANTRY"),
    }
    assert len(lord_clause.effects) == 1
    assert lord_clause.effects[0].kind is RuleEffectKind.GRANT_ABILITY
    assert parameter_payload(lord_clause.effects[0].parameters) == {
        "ability": "lone_operative",
        "target_scope": "this_model",
    }
    assert catalog_rule_ir_consumers_for_rule(lord) == (
        CATALOG_IR_CONDITIONAL_LONE_OPERATIVE_CONSUMER_ID,
    )

    ecstatic = _generated_rule(generator.ECSTATIC_DEATH_ROW_ID)
    ecstatic_clause = ecstatic.clauses[0]
    assert ecstatic_clause.template_id == "phase17c:conditional-model-fight-on-death"
    assert ecstatic_clause.trigger is not None
    assert ecstatic_clause.trigger.kind is RuleTriggerKind.MODEL_DESTROYED
    assert parameter_payload(ecstatic_clause.trigger.parameters) == {
        "destroyed_target": "this_model",
        "timing_window": "after_attacking_unit_finished_attacks",
    }
    assert {condition.kind for condition in ecstatic_clause.conditions} == {
        RuleConditionKind.TARGET_CONSTRAINT
    }
    assert {
        tuple(sorted(parameter_payload(condition.parameters).items()))
        for condition in ecstatic_clause.conditions
    } == {
        (
            ("attack_kind", "melee"),
            ("gate_subject", "destroyed_model"),
            ("relationship", "destroyed_by_attack"),
        ),
        (
            ("gate_subject", "destroyed_model"),
            ("relationship", "has_not_fought_this_phase"),
        ),
    }
    assert parameter_payload(ecstatic_clause.effects[0].parameters) == {
        "ability": "fight_on_death",
        "optional": True,
        "trigger_roll_threshold": 2,
        "trigger_roll_type": "emperors_children_ecstatic_death",
    }
    assert catalog_rule_ir_consumers_for_rule(ecstatic) == (
        CATALOG_IR_FIGHT_ON_DEATH_SOURCE_CONSUMER_ID,
    )


def test_excessive_vigour_is_a_compound_continuous_charged_melee_ap_aura() -> None:
    rule_ir = _generated_rule(generator.EXCESSIVE_VIGOUR_ROW_ID)
    clause = rule_ir.clauses[0]

    assert clause.template_id == "phase17p:charged-melee-weapon-characteristic-aura"
    assert clause.trigger is None
    assert clause.duration is not None
    assert clause.duration.kind is RuleDurationKind.WHILE_CONDITION_TRUE
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.AURA_UNITS
    assert parameter_payload(clause.target.parameters) == {
        "allegiance": "friendly",
        "include_source_unit": True,
    }
    assert tuple(condition.kind for condition in clause.conditions) == (
        RuleConditionKind.AURA,
        RuleConditionKind.DISTANCE_PREDICATE,
        RuleConditionKind.KEYWORD_GATE,
    )
    assert parameter_payload(clause.conditions[1].parameters) == {
        "distance_inches": 6,
        "object_kind": "unit",
        "object_reference": "this_model",
        "predicate": "within",
    }
    assert parameter_payload(clause.conditions[2].parameters) == {"required_keyword": "SLAANESH"}
    assert len(clause.effects) == 1
    assert clause.effects[0].kind is RuleEffectKind.MODIFY_CHARACTERISTIC
    assert parameter_payload(clause.effects[0].parameters) == {
        "characteristic": "armor_penetration",
        "delta": -1,
        "requires_charge_move_this_turn": True,
        "target_scope": "aura_units",
        "weapon_scope": "melee",
    }


def test_excessive_vigour_has_a_generic_runtime_consumer() -> None:
    consumers = catalog_rule_ir_consumers_for_rule(
        _generated_rule(generator.EXCESSIVE_VIGOUR_ROW_ID)
    )
    assert consumers == (CATALOG_IR_CHARGED_MELEE_WEAPON_CHARACTERISTIC_AURA_CONSUMER_ID,)
    assert CATALOG_IR_CHARGED_MELEE_WEAPON_CHARACTERISTIC_AURA_CONSUMER_ID in set(
        registered_consumer_ids()
    )


def test_catalog_promotes_all_three_rules_and_preserves_geometry_and_wargear() -> None:
    package = _package()
    datasheet = package.army_catalog.datasheet_by_id(DAEMON_PRINCE_ID)

    assert datasheet.name == generator.DATASHEET_NAME
    assert datasheet.model_profiles[0].model_profile_id == (
        f"{DAEMON_PRINCE_ID}:daemon-prince-of-slaanesh"
    )
    assert datasheet.model_profiles[0].base_size.diameter_mm == 60.0
    geometry = next(
        geometry
        for geometry in package.model_geometries
        if geometry.model_profile_id == datasheet.model_profiles[0].model_profile_id
    )
    assert geometry.height.height_inches == 4.75

    profiles = {
        profile.profile_id: profile
        for wargear in package.army_catalog.wargear
        for profile in wargear.weapon_profiles
        if wargear.wargear_id.startswith(f"{DAEMON_PRINCE_ID}:")
    }
    assert set(profiles) == {
        f"{DAEMON_PRINCE_ID}:infernal-cannon:standard",
        f"{DAEMON_PRINCE_ID}:hellforged-weapons:strike",
        f"{DAEMON_PRINCE_ID}:hellforged-weapons:sweep",
    }
    assert profiles[f"{DAEMON_PRINCE_ID}:infernal-cannon:standard"].range_profile.kind is (
        RangeProfileKind.DISTANCE
    )
    assert profiles[f"{DAEMON_PRINCE_ID}:hellforged-weapons:strike"].range_profile.kind is (
        RangeProfileKind.MELEE
    )

    expected_source_by_name = {
        generator.ABILITY_NAMES[source_row_id]: (
            f"{generator.SOURCE_PACKAGE_ID}:datasheet:{source_row_id}"
        )
        for source_row_id in generator.ABILITY_NAMES
    }
    abilities = {ability.name: ability for ability in datasheet.abilities}
    for ability_name, source_id in expected_source_by_name.items():
        ability = abilities[ability_name]
        assert ability.support is CatalogAbilitySupport.GENERIC_RULE_IR
        assert ability.rule_ir_payload is not None
        assert (
            RuleIR.from_payload(cast(RuleIRPayload, ability.rule_ir_payload)).source_id == source_id
        )

    coverage = {
        row.ability_name: row
        for row in ability_coverage_rows_from_catalog(
            package.army_catalog,
            datasheet_ids=(DAEMON_PRINCE_ID,),
        )
    }
    for ability_name in expected_source_by_name:
        assert coverage[ability_name].support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        assert coverage[ability_name].runtime_consumer_ids


def test_lord_of_excess_uses_live_friendly_slaanesh_infantry_proximity() -> None:
    fixture = _runtime_fixture()
    bindings = fixture.runtime.shooting_target_restriction_bindings()
    assert len(bindings) == 1
    context = ShootingTargetRestrictionContext(
        state=fixture.state,
        player_id="player-b",
        battle_round=fixture.state.battle_round,
        attacking_unit_instance_id=fixture.enemy_prince.unit_instance_id,
        attacker_model_instance_id=fixture.enemy_prince.own_models[0].model_instance_id,
        target_unit_instance_id=fixture.prince.unit_instance_id,
    )

    restriction = bindings[0].handler(context)
    assert restriction is not None
    assert restriction.violation_code == "conditional_lone_operative_range"

    _move_unit(fixture.state, fixture.escort.unit_instance_id, x=70.0, y=20.0)
    assert bindings[0].handler(context) is None

    _move_unit(fixture.state, fixture.escort.unit_instance_id, x=23.0, y=20.0)
    _move_unit(fixture.state, fixture.enemy_prince.unit_instance_id, x=30.0, y=20.0)
    assert bindings[0].handler(context) is None


def test_excessive_vigour_modifies_only_charged_friendly_slaanesh_melee_profiles() -> None:
    fixture = _runtime_fixture()
    source_id = _generated_rule(generator.EXCESSIVE_VIGOUR_ROW_ID).source_id
    binding = next(
        binding
        for binding in fixture.runtime.weapon_profile_modifier_bindings()
        if binding.source_id == source_id
    )
    melee = _weapon_profile(fixture.package, TORMENTORS_ID, "Close combat weapon")
    attacker = next(
        model
        for model in fixture.escort.own_models
        if f"{TORMENTORS_ID}:close-combat-weapon" in model.wargear_ids
    )
    context = WeaponProfileModifierContext(
        state=fixture.state,
        source_phase=BattlePhase.FIGHT,
        attacking_unit_instance_id=fixture.escort.unit_instance_id,
        attacker_model_instance_id=attacker.model_instance_id,
        target_unit_instance_id=fixture.enemy_prince.unit_instance_id,
        weapon_profile=melee,
    )

    assert binding.handler(context) == melee
    _record_charge_move(fixture.state, fixture.escort)
    modified = binding.handler(context)
    assert modified.armor_penetration.final == melee.armor_penetration.final - 1

    boltgun = _weapon_profile(fixture.package, TORMENTORS_ID, "Boltgun")
    assert binding.handler(replace(context, weapon_profile=boltgun)) == boltgun

    _move_unit(fixture.state, fixture.prince.unit_instance_id, x=70.0, y=20.0)
    assert binding.handler(context) == melee


def test_excessive_vigour_includes_the_charged_source_unit() -> None:
    fixture = _runtime_fixture()
    source_id = _generated_rule(generator.EXCESSIVE_VIGOUR_ROW_ID).source_id
    binding = next(
        binding
        for binding in fixture.runtime.weapon_profile_modifier_bindings()
        if binding.source_id == source_id
    )
    _record_charge_move(fixture.state, fixture.prince)
    melee = _weapon_profile(fixture.package, DAEMON_PRINCE_ID, "Hellforged weapons - strike")
    context = WeaponProfileModifierContext(
        state=fixture.state,
        source_phase=BattlePhase.FIGHT,
        attacking_unit_instance_id=fixture.prince.unit_instance_id,
        attacker_model_instance_id=fixture.prince.own_models[0].model_instance_id,
        target_unit_instance_id=fixture.enemy_prince.unit_instance_id,
        weapon_profile=melee,
    )

    modified = binding.handler(context)
    assert modified.armor_penetration.final == melee.armor_penetration.final - 1


def test_two_excessive_vigour_sources_do_not_stack_the_same_aura_rule() -> None:
    fixture = _runtime_fixture(include_second_aura_source=True)
    assert fixture.second_prince is not None
    source_id = _generated_rule(generator.EXCESSIVE_VIGOUR_ROW_ID).source_id
    friendly_source_prefixes = (
        f"catalog-ir:datasheet:{fixture.prince.unit_instance_id}:",
        f"catalog-ir:datasheet:{fixture.second_prince.unit_instance_id}:",
    )
    bindings = tuple(
        binding
        for binding in fixture.runtime.weapon_profile_modifier_bindings()
        if binding.source_id == source_id
        and binding.modifier_id.startswith(friendly_source_prefixes)
    )
    assert len(bindings) == 2
    assert len({binding.modifier_id for binding in bindings}) == 2

    _record_charge_move(fixture.state, fixture.escort)
    melee = _weapon_profile(fixture.package, TORMENTORS_ID, "Close combat weapon")
    attacker = next(
        model
        for model in fixture.escort.own_models
        if f"{TORMENTORS_ID}:close-combat-weapon" in model.wargear_ids
    )
    context = WeaponProfileModifierContext(
        state=fixture.state,
        source_phase=BattlePhase.FIGHT,
        attacking_unit_instance_id=fixture.escort.unit_instance_id,
        attacker_model_instance_id=attacker.model_instance_id,
        target_unit_instance_id=fixture.enemy_prince.unit_instance_id,
        weapon_profile=melee,
    )
    assert all(
        binding.handler(context).armor_penetration.final == melee.armor_penetration.final - 1
        for binding in bindings
    )

    modified = RuntimeModifierRegistry.from_bindings(
        weapon_profile_modifier_bindings=bindings,
    ).modified_weapon_profile(context)

    assert modified.armor_penetration.final == melee.armor_penetration.final - 1
    assert modified.source_ids.count(source_id) == 1


def test_ecstatic_death_registers_idempotent_serializable_two_plus_model_source() -> None:
    fixture = _runtime_fixture()

    first = fixture.runtime.record_static_destruction_reaction_sources(state=fixture.state)
    second = fixture.runtime.record_static_destruction_reaction_sources(state=fixture.state)
    assert first == second

    model_id = fixture.prince.own_models[0].model_instance_id
    sources = fixture.state.destruction_reaction_sources_for_model(model_instance_id=model_id)
    matching = tuple(
        source
        for source in sources
        if source.source_rule_id == _generated_rule(generator.ECSTATIC_DEATH_ROW_ID).source_id
    )
    assert len(matching) == 1
    source = matching[0]
    assert source.reaction_kind is DestructionReactionKind.FIGHT_ON_DEATH
    assert source.optional is True
    assert DestructionReactionSource.from_payload(source.to_payload()) == source
    payload = cast(dict[str, Any], source.payload)
    assert payload["consumer_id"] == CATALOG_IR_FIGHT_ON_DEATH_SOURCE_CONSUMER_ID
    assert payload["rule_ir_hash"] == _generated_rule(generator.ECSTATIC_DEATH_ROW_ID).ir_hash()
    assert payload["trigger_roll_threshold"] == 2
    assert payload["trigger_roll_type"] == "emperors_children_ecstatic_death"
    assert payload["requires_destroyed_by_melee_attack"] is True
    assert payload["requires_not_fought_this_phase"] is True
    assert payload["unit_instance_id"] == fixture.prince.unit_instance_id
    assert payload["model_instance_id"] == model_id

    restored = GameState.from_payload(
        json.loads(json.dumps(fixture.state.to_payload(), sort_keys=True))
    )
    assert restored.destruction_reaction_sources_by_model_id == (
        fixture.state.destruction_reaction_sources_by_model_id
    )


def test_ecstatic_death_melee_destruction_fights_then_removes_through_adapter_replay() -> None:
    session, attacker, target = _ecstatic_death_fight_session()
    state = session.lifecycle.state
    assert state is not None
    target_model_id = target.own_models[0].model_instance_id

    status = session.advance_until_decision_or_terminal()
    status = _advance_ecstatic_death_session(
        session=session,
        status=status,
        stop_at_decision_type="select_fight_activation",
        result_id_prefix="ecstatic-death:before-attacker",
    )
    activation_request = status.decision_request
    assert activation_request is not None
    attacker_option_id = next(
        option.option_id
        for option in activation_request.options
        if attacker.unit_instance_id in option.option_id
    )
    status = session.submit_option(
        request_id=activation_request.request_id,
        option_id=attacker_option_id,
        result_id="ecstatic-death:attacker-activation",
    )
    status = _advance_ecstatic_death_session(
        session=session,
        status=status,
        stop_at_decision_type=SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
        result_id_prefix="ecstatic-death:attacker",
        melee_profile_suffix=":strike",
    )

    reaction_request = status.decision_request
    assert reaction_request is not None
    assert reaction_request.actor_id == "player-b"
    reaction_payload = cast(dict[str, JsonValue], reaction_request.payload)
    destruction_context = cast(dict[str, JsonValue], reaction_payload["destruction_context"])
    provenance = cast(dict[str, JsonValue], destruction_context["destruction_provenance"])
    assert provenance["attack_kind"] == "melee"
    assert destruction_context["model_instance_id"] == target_model_id
    assert not model_is_present_on_battlefield(
        state=state,
        model_instance_id=target_model_id,
    )

    trigger_event = next(
        event
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "destruction_reaction_trigger_rolled"
        and cast(dict[str, JsonValue], event.payload)["model_instance_id"] == target_model_id
    )
    trigger_payload = cast(dict[str, JsonValue], trigger_event.payload)
    trigger_roll = cast(dict[str, JsonValue], trigger_payload["trigger_roll"])
    original_result = cast(dict[str, JsonValue], trigger_roll["original_result"])
    roll_spec = cast(dict[str, JsonValue], original_result["spec"])
    assert roll_spec["roll_type"] == "emperors_children_ecstatic_death"
    assert trigger_payload["trigger_roll_threshold"] == 2
    assert trigger_payload["triggered"] is True
    assert cast(int, trigger_roll["current_total"]) >= 2

    lifecycle_payload = json.loads(json.dumps(session.lifecycle.to_payload(), sort_keys=True))
    assert GameLifecycle.from_payload(lifecycle_payload).to_payload() == lifecycle_payload

    reaction_option_id = next(
        option.option_id
        for option in reaction_request.options
        if option.option_id != DECLINE_DESTRUCTION_REACTION_OPTION_ID
    )
    status = session.submit_option(
        request_id=reaction_request.request_id,
        option_id=reaction_option_id,
        result_id="ecstatic-death:accept",
    )
    assert model_is_present_on_battlefield(
        state=state,
        model_instance_id=target_model_id,
    )
    assert any(
        event.event_type == "fight_on_death_model_awaiting_attack"
        for event in session.lifecycle.decision_controller.event_log.records
    )

    _advance_ecstatic_death_until_model_removed(
        session=session,
        status=status,
        model_instance_id=target_model_id,
        result_id_prefix="ecstatic-death:target",
    )

    assert not model_is_present_on_battlefield(
        state=state,
        model_instance_id=target_model_id,
    )
    cleanup_payload = next(
        cast(dict[str, JsonValue], event.payload)
        for event in reversed(session.lifecycle.decision_controller.event_log.records)
        if event.event_type == "fight_on_death_models_removed"
    )
    assert cleanup_payload["model_instance_ids"] == [target_model_id]
    assert cleanup_payload["reason"] == "unit_attacked"
    activation_payload = next(
        cast(dict[str, JsonValue], event.payload)
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "fight_on_death_activation_started"
    )
    activation_selection = cast(
        dict[str, JsonValue],
        activation_payload["activation_selection"],
    )
    assert activation_selection["player_id"] == "player-b"
    assert activation_selection["unit_instance_id"] == target.unit_instance_id
    assert activation_selection["result_id"] == "ecstatic-death:accept"

    replay_payload = json.loads(
        json.dumps(
            session.replay_artifact(artifact_id="replay:ecstatic-death:daemon-prince"),
            sort_keys=True,
        )
    )
    replay = ReplayRunner.from_payload(replay_payload).run()
    assert replay.status is ReplayRunStatus.REPRODUCED


def _ecstatic_death_fight_session() -> tuple[LocalGameSession, UnitInstance, UnitInstance]:
    catalog = replace(
        _package().army_catalog,
        detachments=(
            DetachmentDefinition(
                detachment_id="daemon-prince-rule-ir-test",
                name="Daemon Prince RuleIR Test",
                faction_id="EC",
                detachment_point_cost=1,
                unit_datasheet_ids=(DAEMON_PRINCE_ID,),
                force_disposition_ids=("purge-the-foe",),
                source_ids=("test:emperors-children:daemon-prince-rule-ir-detachment",),
            ),
        ),
    )
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("attacker",),
        enemy_unit_ids=("target",),
        origins={
            "attacker": Pose.at(x=10.0, y=20.0),
            "target": Pose.at(x=11.0, y=20.0),
        },
        game_id="ecstatic-proto-2",
        datasheet_id=DAEMON_PRINCE_ID,
        model_profile_id=f"{DAEMON_PRINCE_ID}:daemon-prince-of-slaanesh",
        model_count=1,
        catalog=catalog,
        alpha_faction_id="EC",
        alpha_detachment_ids=("daemon-prince-rule-ir-test",),
        enemy_faction_id="EC",
        enemy_detachment_ids=("daemon-prince-rule-ir-test",),
    )
    state = lifecycle.state
    assert state is not None
    attacker = units["attacker"]
    target = units["target"]
    target_model = target.own_models[0]
    setup_damage = apply_damage_to_model(
        state=state,
        target_unit_instance_id=target.unit_instance_id,
        model_instance_id=target_model.model_instance_id,
        damage=target_model.wounds_remaining - 1,
        damage_kind=DamageKind.NORMAL,
    )
    assert setup_damage.final_wounds_remaining == 1
    assert not setup_damage.destroyed
    return LocalGameSession(lifecycle=lifecycle), attacker, target


def _advance_ecstatic_death_session(
    *,
    session: LocalGameSession,
    status: LifecycleStatus,
    stop_at_decision_type: str,
    result_id_prefix: str,
    melee_profile_suffix: str = ":sweep",
) -> LifecycleStatus:
    current = status
    for result_index in range(1, 129):
        if current.status_kind is LifecycleStatusKind.ADVANCED:
            current = session.advance_until_decision_or_terminal()
        request = current.decision_request
        assert request is not None, (
            current.status_kind,
            current.message,
            current.payload,
        )
        if request.decision_type == stop_at_decision_type:
            return current
        if request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE:
            current = _submit_ecstatic_death_no_move(
                session=session,
                status=current,
                result_id=f"{result_id_prefix}:movement-{result_index:03d}",
            )
            continue
        if request.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE:
            current = _submit_ecstatic_death_melee(
                session=session,
                status=current,
                profile_suffix=melee_profile_suffix,
                result_id=f"{result_id_prefix}:melee-{result_index:03d}",
            )
            continue
        if request.decision_type == "select_fight_activation":
            raise AssertionError(f"Reached Fight activation before {stop_at_decision_type}.")
        assert request.options
        selected_option_id = next(
            (option.option_id for option in request.options if "decline" in option.option_id),
            request.options[0].option_id,
        )
        current = session.submit_option(
            request_id=request.request_id,
            option_id=selected_option_id,
            result_id=f"{result_id_prefix}:finite-{result_index:03d}",
        )
    raise AssertionError(f"Lifecycle did not reach {stop_at_decision_type}.")


def _advance_ecstatic_death_until_model_removed(
    *,
    session: LocalGameSession,
    status: LifecycleStatus,
    model_instance_id: str,
    result_id_prefix: str,
) -> LifecycleStatus:
    current = status
    for result_index in range(1, 129):
        state = session.lifecycle.state
        assert state is not None
        if not model_is_present_on_battlefield(
            state=state,
            model_instance_id=model_instance_id,
        ):
            return current
        if current.status_kind is LifecycleStatusKind.ADVANCED:
            current = session.advance_until_decision_or_terminal()
        request = current.decision_request
        assert request is not None, (
            current.status_kind,
            current.message,
            current.payload,
        )
        if request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE:
            current = _submit_ecstatic_death_no_move(
                session=session,
                status=current,
                result_id=f"{result_id_prefix}:movement-{result_index:03d}",
            )
            continue
        if request.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE:
            current = _submit_ecstatic_death_melee(
                session=session,
                status=current,
                profile_suffix=":sweep",
                result_id=f"{result_id_prefix}:melee-{result_index:03d}",
            )
            continue
        assert request.options
        selected_option_id = next(
            (option.option_id for option in request.options if "decline" in option.option_id),
            request.options[0].option_id,
        )
        current = session.submit_option(
            request_id=request.request_id,
            option_id=selected_option_id,
            result_id=f"{result_id_prefix}:finite-{result_index:03d}",
        )
    raise AssertionError("Fight On Death model was not removed after its attack.")


def _submit_ecstatic_death_no_move(
    *,
    session: LocalGameSession,
    status: LifecycleStatus,
    result_id: str,
) -> LifecycleStatus:
    request = status.decision_request
    assert request is not None
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    context = cast(dict[str, JsonValue], proposal.context)
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=result_id,
        payload={
            "proposal_request_id": proposal.request_id,
            "proposal_kind": proposal.proposal_kind.value,
            "unit_instance_id": proposal.unit_instance_id,
            "movement_phase_action": proposal.movement_phase_action,
            "movement_mode": context["movement_mode"],
        },
    )


def _submit_ecstatic_death_melee(
    *,
    session: LocalGameSession,
    status: LifecycleStatus,
    profile_suffix: str,
    result_id: str,
) -> LifecycleStatus:
    request = status.decision_request
    assert request is not None
    proposal = MeleeDeclarationProposalRequest.from_decision_request(request)
    profile = next(
        cast(dict[str, JsonValue], weapon)
        for weapon in proposal.available_weapons
        if cast(str, cast(dict[str, JsonValue], weapon)["weapon_profile_id"]).endswith(
            profile_suffix
        )
    )
    target_ids = cast(list[str], profile["engaged_target_unit_instance_ids"])
    assert len(target_ids) == 1
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=result_id,
        payload={
            "proposal_request_id": proposal.request_id,
            "proposal_kind": proposal.proposal_kind,
            "player_id": proposal.actor_id,
            "battle_round": proposal.battle_round,
            "unit_instance_id": proposal.unit_instance_id,
            "source_decision_request_id": proposal.source_decision_request_id,
            "source_decision_result_id": proposal.source_decision_result_id,
            "declarations": [
                {
                    "attacker_model_instance_id": profile["model_instance_id"],
                    "wargear_id": profile["wargear_id"],
                    "weapon_profile_id": profile["weapon_profile_id"],
                    "target_allocations": [
                        {"target_unit_instance_id": target_ids[0]},
                    ],
                }
            ],
        },
    )


@dataclass(frozen=True, slots=True)
class _RuntimeFixture:
    package: CanonicalCatalogPackage
    armies: tuple[ArmyDefinition, ...]
    state: GameState
    runtime: CatalogDatasheetRuleRuntime
    prince: UnitInstance
    escort: UnitInstance
    enemy_prince: UnitInstance
    second_prince: UnitInstance | None


@cache
def _package() -> CanonicalCatalogPackage:
    return _ability_support_catalog_package(datasheet_ids=(DAEMON_PRINCE_ID, TORMENTORS_ID))


def _runtime_fixture(*, include_second_aura_source: bool = False) -> _RuntimeFixture:
    package = _package()
    catalog = package.army_catalog
    factory = UnitFactory(catalog=catalog, model_geometries=package.model_geometries)
    prince = _instantiate(factory, army_id="army-a", datasheet_id=DAEMON_PRINCE_ID)
    escort = _instantiate(factory, army_id="army-a", datasheet_id=TORMENTORS_ID)
    enemy_prince = _instantiate(
        factory,
        army_id="army-b",
        datasheet_id=DAEMON_PRINCE_ID,
        selection_suffix="enemy",
    )
    second_prince = (
        _instantiate(
            factory,
            army_id="army-a",
            datasheet_id=DAEMON_PRINCE_ID,
            selection_suffix="second-aura-source",
        )
        if include_second_aura_source
        else None
    )
    player_a_units = (
        (prince, second_prince, escort) if second_prince is not None else (prince, escort)
    )
    armies = (
        _army(catalog, army_id="army-a", player_id="player-a", units=player_a_units),
        _army(catalog, army_id="army-b", player_id="player-b", units=(enemy_prince,)),
    )
    state = _state(armies)
    _move_unit(state, prince.unit_instance_id, x=20.0, y=20.0)
    _move_unit(state, escort.unit_instance_id, x=23.0, y=20.0)
    _move_unit(state, enemy_prince.unit_instance_id, x=45.0, y=20.0)
    if second_prince is not None:
        _move_unit(state, second_prince.unit_instance_id, x=26.0, y=20.0)
    records = catalog_ability_records_from_catalog(catalog)
    indexes = {
        army.player_id: build_player_ability_index(records, army=army, catalog=catalog)
        for army in armies
    }
    return _RuntimeFixture(
        package=package,
        armies=armies,
        state=state,
        runtime=CatalogDatasheetRuleRuntime(indexes, armies),
        prince=prince,
        escort=escort,
        enemy_prince=enemy_prince,
        second_prince=second_prince,
    )


def _instantiate(
    factory: UnitFactory,
    *,
    army_id: str,
    datasheet_id: str,
    selection_suffix: str = "source",
) -> UnitInstance:
    datasheet = factory.catalog.datasheet_by_id(datasheet_id)
    return factory.instantiate_unit(
        army_id=army_id,
        datasheet=datasheet,
        selection=UnitMusterSelection(
            unit_selection_id=f"{datasheet_id}-{selection_suffix}",
            datasheet_id=datasheet_id,
            model_profile_selections=tuple(
                ModelProfileSelection(entry.model_profile_id, entry.min_models)
                for entry in datasheet.composition
                if entry.min_models > 0
            ),
        ),
    )


def _army(
    catalog: Any,
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
            faction_id="emperors-children",
            detachment_ids=("daemon-prince-rule-ir-test",),
        ),
        force_disposition_id="purge-the-foe",
        units=units,
    )


def _state(armies: tuple[ArmyDefinition, ...]) -> GameState:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    phases = tuple(descriptor.battle_phase_sequence.phases)
    state = GameState(
        game_id="emperors-children-daemon-prince-rule-ir-test",
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
        battlefield_id="emperors-children-daemon-prince-rule-ir-battlefield",
        armies=armies,
    ).battlefield_state
    return state


def _move_unit(
    state: GameState,
    unit_instance_id: str,
    *,
    x: float,
    y: float,
) -> None:
    battlefield = state.battlefield_state
    assert battlefield is not None
    placement = battlefield.unit_placement_by_id(unit_instance_id)
    moved = replace(
        placement,
        model_placements=tuple(
            replace(
                model_placement,
                pose=Pose.at(x=x, y=y + (2.0 * index)),
            )
            for index, model_placement in enumerate(placement.model_placements)
        ),
    )
    state.replace_battlefield_state(battlefield.with_unit_placement(moved))


def _record_charge_move(state: GameState, unit: UnitInstance) -> None:
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=f"{unit.unit_instance_id}:charge-move",
            source_rule_id="core-rules:charge:fights-first",
            owner_player_id="player-a",
            target_unit_instance_ids=(unit.unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.CHARGE,
            expiration=EffectExpiration.end_turn(
                battle_round=state.battle_round,
                player_id="player-a",
            ),
            effect_payload={"effect_kind": CHARGE_FIGHTS_FIRST_EFFECT_KIND},
        )
    )


def _weapon_profile(
    package: CanonicalCatalogPackage,
    datasheet_id: str,
    name: str,
) -> WeaponProfile:
    matches = tuple(
        profile
        for wargear in package.army_catalog.wargear
        if wargear.wargear_id.startswith(f"{datasheet_id}:")
        for profile in wargear.weapon_profiles
        if profile.name == name
    )
    assert len(matches) == 1
    return matches[0]


def _generated_rule(source_row_id: str) -> RuleIR:
    records = cast(dict[str, dict[str, Any]], generator.generated_artifact_payload()["records"])
    return RuleIR.from_payload(cast(RuleIRPayload, records[source_row_id]["rule_ir"]))
