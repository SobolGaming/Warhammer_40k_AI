from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import cast

import pytest
from tests.phase11c_command_phase_helpers import (
    battle_state,
    phase11c_config,
    unit_selection,
    with_model_offsets,
)
from tests.setup_completion_helpers import (
    record_existing_primary_turn_start_evidence_events_for_fixture,
)

from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilitySourceKind,
    AbilityTimingDescriptor,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.mission_decisions import (
    apply_mission_decision,
    request_mission_action_opportunity,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.phases.shooting_model import ShootingPhaseState
from warhammer40k_core.engine.primary_mission_objective_control_source_authority import (
    _creation_family as creation_family,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.primary_mission_objective_control_source_authority import (
    _json_object as json_object,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.primary_mission_objective_control_source_authority import (
    _payload_bool as payload_bool,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.primary_mission_objective_control_source_authority import (
    _payload_non_negative_int as payload_non_negative_int,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.primary_mission_objective_control_source_authority import (
    _payload_optional_string as payload_optional_string,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.primary_mission_objective_control_source_authority import (
    _payload_positive_int as payload_positive_int,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.primary_mission_objective_control_source_authority import (
    _payload_string as payload_string,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.primary_mission_objective_control_source_authority import (
    _payload_string_tuple as payload_string_tuple,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.primary_mission_objective_control_source_authority import (
    _rule_clause_for_payload as rule_clause_for_payload,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.primary_mission_objective_control_source_authority import (
    _validate_detachment_effect_authority as validate_detachment_effect_authority,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.primary_mission_objective_control_source_authority import (
    _validate_enhancement_effect_authority as validate_enhancement_effect_authority,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.primary_mission_objective_control_source_authority import (
    _validated_execution_effect_payload as validated_execution_effect_payload,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    RuleExecutionStatus,
    execute_rule_ir,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.runtime_rule_ir_authority import (
    RuntimeRuleIRAuthorityIndex,
    RuntimeRuleIRSourceKey,
    runtime_rule_ir_authority_index_from_bundle,
)
from warhammer40k_core.engine.runtime_rule_ir_authority import (
    _ability_catalog_indexes as ability_catalog_indexes,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.runtime_rule_ir_authority import (
    _register_rule_ir as register_rule_ir,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.runtime_rule_ir_authority import (
    _stratagem_catalog_indexes as stratagem_catalog_indexes,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.runtime_rule_ir_authority import (
    _validated_global_source_keys as validated_global_source_keys,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.runtime_rule_ir_authority import (
    _validated_player_ids_mapping as validated_player_ids_mapping,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.runtime_rule_ir_authority import (
    _validated_provider_mapping as validated_provider_mapping,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.runtime_rule_ir_authority import (
    _validated_rule_ir_mapping as validated_rule_ir_mapping,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.scoring import SecondaryMissionCardState
from warhammer40k_core.engine.stratagems_model import StratagemCatalogIndex
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleDuration,
    RuleDurationKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleParameter,
    RuleTargetKind,
    RuleTargetSpec,
)

type AuthorityRuntime = tuple[GameState, RuleIR, RuntimeContentBundle, GameConfig]
type DirectOCAuthority = tuple[
    GameState,
    PersistingEffect,
    RuleIR,
    RuntimeRuleIRAuthorityIndex,
]


@pytest.fixture(scope="module")
def authority_runtime() -> AuthorityRuntime:
    state = battle_state()
    _enter_shooting_phase(state)
    rule_ir = _objective_control_rule_ir()
    config = phase11c_config()
    bundle = RuntimeContentBundle.from_contributions(
        activation=RuntimeContentActivation.from_armies(
            armies=tuple(state.army_definitions),
            catalog=config.army_catalog,
        ),
        armies=tuple(state.army_definitions),
        catalog=config.army_catalog,
        contributions=(),
        base_ability_records=(_ability_record(rule_ir),),
    )
    return state, rule_ir, bundle, config


@pytest.fixture(scope="module")
def direct_oc_authority(authority_runtime: AuthorityRuntime) -> DirectOCAuthority:
    base_state, rule_ir, bundle, _config = authority_runtime
    state = deepcopy(base_state)
    decisions = DecisionController()
    _apply_generic_oc_rule_ir(state=state, decisions=decisions, rule_ir=rule_ir)
    return (
        state,
        state.persisting_effects[0],
        rule_ir,
        runtime_rule_ir_authority_index_from_bundle(bundle),
    )


def test_full_restore_rejects_forged_generic_oc_source_and_execution_event(
    authority_runtime: AuthorityRuntime,
) -> None:
    base_state, legitimate_rule_ir, bundle, config = authority_runtime
    state = deepcopy(base_state)
    decisions = _decision_controller_for_checkpoint(state)
    forged_rule_ir = replace(
        legitimate_rule_ir,
        rule_id="test:forged-objective-control:rule",
        source_id="test:forged-objective-control",
    )
    _apply_generic_oc_rule_ir(
        state=state,
        decisions=decisions,
        rule_ir=forged_rule_ir,
    )
    _record_checkpoint(state=state, decisions=decisions)

    with pytest.raises(GameLifecycleError, match=r"authoritative|authority"):
        GameLifecycle.from_payload(
            _lifecycle_payload(
                state=state,
                decisions=decisions,
                config=config,
                bundle=bundle,
            ),
            runtime_content_bundle=bundle,
        )


def test_full_restore_accepts_source_backed_generic_oc_effect(
    authority_runtime: AuthorityRuntime,
) -> None:
    base_state, rule_ir, bundle, config = authority_runtime
    state = deepcopy(base_state)
    decisions = _decision_controller_for_checkpoint(state)
    _apply_generic_oc_rule_ir(state=state, decisions=decisions, rule_ir=rule_ir)
    _record_checkpoint(state=state, decisions=decisions)

    restored = GameLifecycle.from_payload(
        _lifecycle_payload(
            state=state,
            decisions=decisions,
            config=config,
            bundle=bundle,
        ),
        runtime_content_bundle=bundle,
    )

    assert not restored.decision_controller.queue.pending_requests
    assert restored.state is not None
    assert restored.state.persisting_effects == state.persisting_effects


def test_full_restore_rejects_forged_source_backed_generic_oc_effect_id(
    authority_runtime: AuthorityRuntime,
) -> None:
    base_state, rule_ir, bundle, config = authority_runtime
    state = deepcopy(base_state)
    decisions = _decision_controller_for_checkpoint(state)
    _apply_generic_oc_rule_ir(state=state, decisions=decisions, rule_ir=rule_ir)
    effect = state.persisting_effects[0]
    state.persisting_effects = [replace(effect, effect_id="rule-effect:forged-source-backed-oc")]
    _record_checkpoint(state=state, decisions=decisions)

    with pytest.raises(GameLifecycleError, match=r"identity|effect_id|authority"):
        GameLifecycle.from_payload(
            _lifecycle_payload(
                state=state,
                decisions=decisions,
                config=config,
                bundle=bundle,
            ),
            runtime_content_bundle=bundle,
        )


def test_full_restore_rejects_forged_source_backed_generic_oc_expiration(
    authority_runtime: AuthorityRuntime,
) -> None:
    base_state, rule_ir, bundle, config = authority_runtime
    state = deepcopy(base_state)
    decisions = _decision_controller_for_checkpoint(state)
    _apply_generic_oc_rule_ir(state=state, decisions=decisions, rule_ir=rule_ir)
    effect = state.persisting_effects[0]
    state.persisting_effects = [
        replace(
            effect,
            expiration=EffectExpiration.end_turn(
                battle_round=effect.started_battle_round + 1,
                player_id=effect.owner_player_id,
            ),
        )
    ]
    _record_checkpoint(state=state, decisions=decisions)

    with pytest.raises(GameLifecycleError, match=r"expiration|duration|identity|authority"):
        GameLifecycle.from_payload(
            _lifecycle_payload(
                state=state,
                decisions=decisions,
                config=config,
                bundle=bundle,
            ),
            runtime_content_bundle=bundle,
        )


def test_full_restore_rejects_cross_player_borrowed_generic_oc_source() -> None:
    player_a_units = (
        unit_selection(
            unit_selection_id="boyz-unit-1",
            datasheet_id="core-boyz-like-infantry",
            model_profile_id="core-boyz-like",
            model_count=10,
        ),
    )
    config = phase11c_config(player_a_units=player_a_units)
    state = battle_state(player_a_units=player_a_units)
    _enter_shooting_phase(state)
    rule_ir = _objective_control_rule_ir()
    bundle = RuntimeContentBundle.from_contributions(
        activation=RuntimeContentActivation.from_armies(
            armies=tuple(state.army_definitions),
            catalog=config.army_catalog,
        ),
        armies=tuple(state.army_definitions),
        catalog=config.army_catalog,
        contributions=(),
        base_ability_records=(
            _ability_record(
                rule_ir,
                datasheet_id="core-boyz-like-infantry",
            ),
        ),
    )
    record_id = "test:source-backed-objective-control:record"
    assert record_id in {
        record.record_id for record in bundle.ability_indexes_by_player_id["player-a"].all_records()
    }
    assert record_id not in {
        record.record_id for record in bundle.ability_indexes_by_player_id["player-b"].all_records()
    }
    decisions = _decision_controller_for_checkpoint(state)
    _apply_generic_oc_rule_ir(
        state=state,
        decisions=decisions,
        rule_ir=rule_ir,
        owner_player_id="player-b",
    )
    _record_checkpoint(state=state, decisions=decisions)

    with pytest.raises(GameLifecycleError, match=r"authoritative for this player"):
        GameLifecycle.from_payload(
            _lifecycle_payload(
                state=state,
                decisions=decisions,
                config=config,
                bundle=bundle,
            ),
            runtime_content_bundle=bundle,
        )


def test_full_restore_rejects_shooting_ability_executed_in_command_phase() -> None:
    state = battle_state()
    assert state.current_battle_phase is BattlePhase.COMMAND
    rule_ir = _objective_control_rule_ir()
    config = phase11c_config()
    bundle = RuntimeContentBundle.from_contributions(
        activation=RuntimeContentActivation.from_armies(
            armies=tuple(state.army_definitions),
            catalog=config.army_catalog,
        ),
        armies=tuple(state.army_definitions),
        catalog=config.army_catalog,
        contributions=(),
        base_ability_records=(_ability_record(rule_ir),),
    )
    decisions = _decision_controller_for_checkpoint(state)
    _apply_generic_oc_rule_ir(state=state, decisions=decisions, rule_ir=rule_ir)
    _record_checkpoint(state=state, decisions=decisions)

    with pytest.raises(GameLifecycleError, match=r"exact provider timing authority"):
        GameLifecycle.from_payload(
            _lifecycle_payload(
                state=state,
                decisions=decisions,
                config=config,
                bundle=bundle,
            ),
            runtime_content_bundle=bundle,
        )


def test_full_restore_rejects_generic_oc_effect_using_opponent_source_unit(
    authority_runtime: AuthorityRuntime,
) -> None:
    base_state, rule_ir, bundle, config = authority_runtime
    state = deepcopy(base_state)
    decisions = _decision_controller_for_checkpoint(state)
    _apply_generic_oc_rule_ir(
        state=state,
        decisions=decisions,
        rule_ir=rule_ir,
        source_unit_player_id="player-b",
    )
    effect = state.persisting_effects[0]
    assert effect.owner_player_id == "player-a"
    _record_checkpoint(state=state, decisions=decisions)

    with pytest.raises(GameLifecycleError, match=r"source unit ownership drifted"):
        GameLifecycle.from_payload(
            _lifecycle_payload(
                state=state,
                decisions=decisions,
                config=config,
                bundle=bundle,
            ),
            runtime_content_bundle=bundle,
        )


def test_full_restore_rejects_datasheet_ability_borrowed_by_same_player_unit() -> None:
    player_a_units = (
        unit_selection(
            unit_selection_id="boyz-unit-1",
            datasheet_id="core-boyz-like-infantry",
            model_profile_id="core-boyz-like",
            model_count=10,
        ),
        unit_selection(
            unit_selection_id="intercessor-unit-1",
            datasheet_id="core-intercessor-like-infantry",
            model_profile_id="core-intercessor-like",
            model_count=5,
        ),
    )
    config = phase11c_config(player_a_units=player_a_units)
    state = battle_state(player_a_units=player_a_units)
    _enter_shooting_phase(state)
    rule_ir = _objective_control_rule_ir()
    bundle = RuntimeContentBundle.from_contributions(
        activation=RuntimeContentActivation.from_armies(
            armies=tuple(state.army_definitions),
            catalog=config.army_catalog,
        ),
        armies=tuple(state.army_definitions),
        catalog=config.army_catalog,
        contributions=(),
        base_ability_records=(_ability_record(rule_ir, datasheet_id="core-boyz-like-infantry"),),
    )
    source_unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-a"
        for unit in army.units
        if unit.datasheet_id == "core-intercessor-like-infantry"
    )
    decisions = _decision_controller_for_checkpoint(state)
    _apply_generic_oc_rule_ir(
        state=state,
        decisions=decisions,
        rule_ir=rule_ir,
        source_unit_instance_id=source_unit.unit_instance_id,
    )
    _record_checkpoint(state=state, decisions=decisions)

    with pytest.raises(GameLifecycleError, match=r"exact provider timing authority"):
        GameLifecycle.from_payload(
            _lifecycle_payload(
                state=state,
                decisions=decisions,
                config=config,
                bundle=bundle,
            ),
            runtime_content_bundle=bundle,
        )


def test_runtime_rule_ir_authority_rejects_noncanonical_index_shapes(
    direct_oc_authority: DirectOCAuthority,
) -> None:
    _state, _effect, rule_ir, authority_index = direct_oc_authority
    key = RuntimeRuleIRSourceKey(rule_ir.source_id, rule_ir.ir_hash())
    record = _ability_record(rule_ir)
    player_ids_by_key = {key: ("player-a",)}

    assert authority_index.all_keys()
    assert authority_index.all_rule_irs()
    with pytest.raises(GameLifecycleError, match="source_id"):
        RuntimeRuleIRSourceKey("", rule_ir.ir_hash())
    with pytest.raises(GameLifecycleError, match="SHA-256"):
        RuntimeRuleIRSourceKey(rule_ir.source_id, "A" * 64)
    with pytest.raises(GameLifecycleError, match="index must be a mapping"):
        validated_rule_ir_mapping([])
    with pytest.raises(GameLifecycleError, match="index entry is invalid"):
        validated_rule_ir_mapping({"wrong-key": rule_ir})
    drifted_key = RuntimeRuleIRSourceKey("test:drifted-source", rule_ir.ir_hash())
    with pytest.raises(GameLifecycleError, match="index key drifted"):
        validated_rule_ir_mapping({drifted_key: rule_ir})

    with pytest.raises(GameLifecycleError, match="player authority index must be a mapping"):
        validated_player_ids_mapping(
            [],
            rule_ir_keys=frozenset({key}),
        )
    with pytest.raises(GameLifecycleError, match="inventory drifted"):
        validated_player_ids_mapping(
            {},
            rule_ir_keys=frozenset({key}),
        )
    with pytest.raises(GameLifecycleError, match="player authority entry is invalid"):
        validated_player_ids_mapping(
            {key: ["player-a"]},
            rule_ir_keys=frozenset({key}),
        )
    for player_ids in (("player-z", "player-a"), ("player-a", "player-a")):
        with pytest.raises(GameLifecycleError, match="player authority entry drifted"):
            validated_player_ids_mapping(
                {key: player_ids},
                rule_ir_keys=frozenset({key}),
            )

    with pytest.raises(GameLifecycleError, match="provider authority must be a mapping"):
        validated_provider_mapping(
            [],
            record_type=AbilityCatalogRecord,
            player_ids_by_key=player_ids_by_key,
        )
    invalid_provider_mappings: tuple[object, ...] = (
        {"wrong-key": (record,)},
        {(key,): (record,)},
        {(key, "player-a"): [record]},
        {(key, "player-b"): (record,)},
        {(key, "player-a"): (object(),)},
        {
            (key, "player-a"): (
                replace(record, record_id="test:z-record"),
                replace(record, record_id="test:a-record"),
            )
        },
        {(key, "player-a"): (record, record)},
    )
    for invalid_mapping in invalid_provider_mappings:
        with pytest.raises(GameLifecycleError, match="provider"):
            validated_provider_mapping(
                invalid_mapping,
                record_type=AbilityCatalogRecord,
                player_ids_by_key=player_ids_by_key,
            )
    with pytest.raises(GameLifecycleError, match="global authority must be a frozenset"):
        validated_global_source_keys(cast(object, set()), rule_ir_keys=frozenset({key}))
    with pytest.raises(GameLifecycleError, match="global authority entry is invalid"):
        validated_global_source_keys(
            cast(object, frozenset({object()})),
            rule_ir_keys=frozenset({key}),
        )
    with pytest.raises(GameLifecycleError, match="global authority inventory drifted"):
        validated_global_source_keys(
            frozenset({RuntimeRuleIRSourceKey("test:other-source", rule_ir.ir_hash())}),
            rule_ir_keys=frozenset({key}),
        )
    empty_global = frozenset[RuntimeRuleIRSourceKey]()
    assert validated_global_source_keys(empty_global, rule_ir_keys=frozenset({key})) == empty_global
    assert validated_global_source_keys(
        frozenset({key}),
        rule_ir_keys=frozenset({key}),
    ) == frozenset({key})


def test_runtime_rule_ir_authority_rejects_invalid_runtime_sources(
    authority_runtime: AuthorityRuntime,
) -> None:
    _state, rule_ir, bundle, _config = authority_runtime
    ability_index = next(iter(bundle.ability_indexes_by_player_id.values()))
    stratagem_index = next(iter(bundle.stratagem_indexes_by_player_id.values()))
    assert type(ability_index) is AbilityCatalogIndex
    assert type(stratagem_index) is StratagemCatalogIndex

    invalid_index_values: tuple[object, ...] = ([], {"player-a": object()})
    for values in invalid_index_values:
        with pytest.raises(GameLifecycleError, match="ability_indexes_by_player_id"):
            ability_catalog_indexes(values)
        with pytest.raises(GameLifecycleError, match="stratagem_indexes_by_player_id"):
            stratagem_catalog_indexes(values)
    with pytest.raises(GameLifecycleError, match="player_id"):
        ability_catalog_indexes({"": ability_index})
    with pytest.raises(GameLifecycleError, match="player_id"):
        stratagem_catalog_indexes({"": stratagem_index})
    with pytest.raises(GameLifecycleError, match="RuntimeContentBundle"):
        runtime_rule_ir_authority_index_from_bundle(object())  # type: ignore[arg-type]
    with pytest.raises(GameLifecycleError, match="source is invalid"):
        register_rule_ir(
            {},
            {},
            object(),  # type: ignore[arg-type]
            player_id=None,
        )
    with pytest.raises(GameLifecycleError, match="identifier"):
        register_rule_ir(
            {},
            {},
            rule_ir,
            player_id="",
        )
    with pytest.raises(GameLifecycleError, match="explicit global registration"):
        register_rule_ir(
            {},
            {},
            rule_ir,
            player_id=None,
        )
    global_keys: set[RuntimeRuleIRSourceKey] = set()
    register_rule_ir(
        {},
        {},
        rule_ir,
        player_id=None,
        global_keys=global_keys,
    )
    assert RuntimeRuleIRSourceKey(rule_ir.source_id, rule_ir.ir_hash()) in global_keys


def test_oc_source_payload_parsers_reject_noncanonical_values() -> None:
    assert json_object('{"a":1}', context="test") == {"a": 1}
    with pytest.raises(GameLifecycleError, match="JSON is invalid"):
        json_object("{", context="test")
    for value in ('{"a": 1}', "[]"):
        with pytest.raises(GameLifecycleError, match="JSON is not canonical"):
            json_object(value, context="test")

    assert payload_string({"value": "ok"}, key="value") == "ok"
    assert payload_optional_string({"value": None}, key="value") is None
    assert payload_positive_int({"value": 1}, key="value") == 1
    assert payload_non_negative_int({"value": 0}, key="value") == 0
    assert payload_string_tuple(
        {"value": ["one", "two"]},
        key="value",
    ) == ("one", "two")
    assert payload_bool({"value": True}, key="value") is True
    with pytest.raises(GameLifecycleError, match="requires value"):
        payload_string({"value": ""}, key="value")
    with pytest.raises(GameLifecycleError, match="requires value"):
        payload_optional_string({"value": 1}, key="value")
    with pytest.raises(GameLifecycleError, match="requires value"):
        payload_positive_int({"value": 0}, key="value")
    with pytest.raises(GameLifecycleError, match="requires value"):
        payload_positive_int({"value": True}, key="value")
    with pytest.raises(GameLifecycleError, match="requires value"):
        payload_non_negative_int({"value": -1}, key="value")
    with pytest.raises(GameLifecycleError, match="requires value"):
        payload_string_tuple({"value": "one"}, key="value")
    with pytest.raises(GameLifecycleError, match="requires value"):
        payload_string_tuple({"value": [""]}, key="value")
    with pytest.raises(GameLifecycleError, match="requires value"):
        payload_bool({"value": 1}, key="value")


def test_oc_source_creation_family_requires_complete_provider_authority() -> None:
    assert creation_family({}) == "direct"
    with pytest.raises(GameLifecycleError, match="enhancement effect authority is incomplete"):
        creation_family({"enhancement_assignment": {}})
    with pytest.raises(GameLifecycleError, match="detachment effect authority is incomplete"):
        creation_family({"coverage_descriptor_id": "coverage"})
    assert (
        creation_family(
            {
                "coverage_descriptor_id": "coverage",
                "execution_id": "execution",
                "detachment_id": "detachment",
                "generic_detachment_effect_id": "effect",
            }
        )
        == "detachment"
    )
    assert (
        creation_family(
            {
                "coverage_descriptor_id": "coverage",
                "execution_id": "execution",
                "enhancement_assignment": {},
            }
        )
        == "enhancement"
    )


def test_oc_execution_payload_rejects_rule_ir_and_provider_drift(
    direct_oc_authority: DirectOCAuthority,
) -> None:
    _state, effect, rule_ir, authority_index = direct_oc_authority
    raw_payload = effect.effect_payload
    assert isinstance(raw_payload, dict)
    base_payload = deepcopy(raw_payload)

    with pytest.raises(GameLifecycleError, match="payload is invalid"):
        validated_execution_effect_payload(
            effect=replace(effect, effect_payload=[]),
            authority_index=authority_index,
        )
    with pytest.raises(GameLifecycleError, match="lacks loaded RuleIR authority"):
        validated_execution_effect_payload(
            effect=effect,
            authority_index=None,
        )

    payload_mutations: tuple[tuple[str, JsonValue, str], ...] = (
        ("effect_index", True, "slot is invalid"),
        ("effect_kind", "forged", "contradicts loaded RuleIR"),
        ("conditions", [], "invented RuleIR conditions"),
        ("unsupported", "forged", "unsupported source metadata"),
    )
    for key, value, message in payload_mutations:
        payload = deepcopy(base_payload)
        payload[key] = value
        with pytest.raises(GameLifecycleError, match=message):
            validated_execution_effect_payload(
                effect=replace(effect, effect_payload=payload),
                authority_index=authority_index,
            )

    with pytest.raises(GameLifecycleError, match="source rule drifted"):
        validated_execution_effect_payload(
            effect=replace(effect, source_rule_id="test:drifted-source"),
            authority_index=authority_index,
        )
    with pytest.raises(GameLifecycleError, match="clause is not loaded"):
        rule_clause_for_payload(
            rule_ir=rule_ir,
            payload={"clause_id": "test:missing-clause"},
        )

    provider_cases: tuple[tuple[dict[str, JsonValue], str], ...] = (
        (
            {
                "coverage_descriptor_id": "coverage",
                "execution_id": "execution",
                "detachment_id": "detachment",
                "generic_detachment_effect_id": "effect",
            },
            "detachment",
        ),
        (
            {
                "coverage_descriptor_id": "coverage",
                "execution_id": "execution",
                "enhancement_assignment": {},
            },
            "enhancement",
        ),
    )
    for provider_fields, expected_family in provider_cases:
        payload = deepcopy(base_payload)
        payload.update(provider_fields)
        _execution_payload, creation_family, _loaded_rule_ir, _clause = (
            validated_execution_effect_payload(
                effect=replace(effect, effect_payload=payload),
                authority_index=authority_index,
            )
        )
        assert creation_family == expected_family


def test_oc_provider_validators_fail_closed_before_registry_lookup(
    direct_oc_authority: DirectOCAuthority,
) -> None:
    state, effect, _rule_ir, _authority_index = direct_oc_authority
    raw_payload = effect.effect_payload
    assert isinstance(raw_payload, dict)
    base_payload = deepcopy(raw_payload)

    validate_detachment_effect_authority(
        state=state,
        effect=effect,
        event_records=(),
        checkpoint_index=0,
        faction_rule_execution_registry=None,
        runtime_content_activation=None,
    )
    partial_payload = {**base_payload, "coverage_descriptor_id": "coverage"}
    with pytest.raises(GameLifecycleError, match="detachment effect authority is incomplete"):
        validate_detachment_effect_authority(
            state=state,
            effect=replace(effect, effect_payload=partial_payload),
            event_records=(),
            checkpoint_index=0,
            faction_rule_execution_registry=None,
            runtime_content_activation=None,
        )
    detachment_payload = {
        **base_payload,
        "coverage_descriptor_id": "coverage",
        "execution_id": "execution",
        "detachment_id": "detachment",
        "generic_detachment_effect_id": "effect",
    }
    invalid_context_payload = {**detachment_payload, "context": None}
    with pytest.raises(GameLifecycleError, match="detachment effect context is invalid"):
        validate_detachment_effect_authority(
            state=state,
            effect=replace(effect, effect_payload=invalid_context_payload),
            event_records=(),
            checkpoint_index=0,
            faction_rule_execution_registry=None,
            runtime_content_activation=None,
        )
    with pytest.raises(GameLifecycleError, match="lacks provider authority"):
        validate_detachment_effect_authority(
            state=state,
            effect=replace(effect, effect_payload=detachment_payload),
            event_records=(),
            checkpoint_index=0,
            faction_rule_execution_registry=None,
            runtime_content_activation=None,
        )

    enhancement_payload = {
        **base_payload,
        "coverage_descriptor_id": "coverage",
        "execution_id": "execution",
        "enhancement_assignment": None,
    }
    with pytest.raises(GameLifecycleError, match="enhancement assignment authority is invalid"):
        validate_enhancement_effect_authority(
            effect=replace(effect, effect_payload=enhancement_payload),
            event_records=(),
            checkpoint_index=0,
            faction_rule_execution_registry=None,
            runtime_content_activation=None,
        )
    enhancement_payload["enhancement_assignment"] = {
        "assignment_id": "assignment",
        "player_id": effect.owner_player_id,
        "army_id": "army",
        "enhancement_id": "enhancement",
        "target_unit_selection_id": "selection",
        "bearer_unit_instance_id": effect.target_unit_instance_ids[0],
        "source_id": effect.source_rule_id,
    }
    with pytest.raises(GameLifecycleError, match="lacks provider authority"):
        validate_enhancement_effect_authority(
            effect=replace(effect, effect_payload=enhancement_payload),
            event_records=(),
            checkpoint_index=0,
            faction_rule_execution_registry=None,
            runtime_content_activation=None,
        )


def _objective_control_rule_ir() -> RuleIR:
    text = "Until the end of the turn, add 1 to this unit's Objective Control."
    span = TextSpan(text=text, start=0, end=len(text))
    return RuleIR(
        rule_id="test:source-backed-objective-control:rule",
        source_id="test:source-backed-objective-control",
        normalized_text=text,
        parser_version="test-phase17n-runtime-rule-ir-oc-authority",
        clauses=(
            RuleClause(
                clause_id="test:source-backed-objective-control:clause",
                source_span=span,
                target=RuleTargetSpec(
                    kind=RuleTargetKind.THIS_UNIT,
                    source_span=span,
                ),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.MODIFY_CHARACTERISTIC,
                        source_span=span,
                        parameters=(
                            RuleParameter(key="characteristic", value="objective_control"),
                            RuleParameter(key="delta", value=1),
                        ),
                    ),
                ),
                duration=RuleDuration(
                    kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
                    source_span=span,
                    parameters=(RuleParameter(key="endpoint", value="turn"),),
                ),
            ),
        ),
    )


def _ability_record(
    rule_ir: RuleIR,
    *,
    datasheet_id: str | None = None,
) -> AbilityCatalogRecord:
    return AbilityCatalogRecord(
        record_id="test:source-backed-objective-control:record",
        definition=AbilityDefinition(
            ability_id="test:source-backed-objective-control:ability",
            name="Source-backed Objective Control",
            source_id=rule_ir.source_id,
            when_descriptor="Test execution before a Mission Action checkpoint.",
            effect_descriptor="Add 1 to a selected unit's Objective Control.",
            restrictions_descriptor="Test-only source-backed RuleIR.",
            timing=AbilityTimingDescriptor(
                trigger_kind=TimingTriggerKind.START_PHASE,
                phase=BattlePhaseKind.SHOOTING,
            ),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=validate_json_value({"rule_ir": rule_ir.to_payload()}),
        ),
        source_kind=(
            AbilitySourceKind.CORE if datasheet_id is None else AbilitySourceKind.DATASHEET
        ),
        datasheet_id=datasheet_id,
    )


def _apply_generic_oc_rule_ir(
    *,
    state: GameState,
    decisions: DecisionController,
    rule_ir: RuleIR,
    owner_player_id: str | None = None,
    source_unit_player_id: str | None = None,
    source_unit_instance_id: str | None = None,
) -> None:
    active_player_id = state.active_player_id
    phase = state.current_battle_phase
    assert active_player_id is not None
    assert phase is not None
    player_id = active_player_id if owner_player_id is None else owner_player_id
    source_player_id = player_id if source_unit_player_id is None else source_unit_player_id
    source_unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == source_player_id
        for unit in army.units
        if source_unit_instance_id is None or unit.unit_instance_id == source_unit_instance_id
    )
    result = execute_rule_ir(
        rule_ir=rule_ir,
        context=RuleExecutionContext(
            game_id=state.game_id,
            player_id=player_id,
            battle_round=state.battle_round,
            phase=BattlePhaseKind(phase.value),
            active_player_id=active_player_id,
            source_unit_instance_id=source_unit.unit_instance_id,
            target_unit_instance_ids=(source_unit.unit_instance_id,),
            state=state,
            event_log=decisions.event_log,
        ),
    )
    assert result.status is RuleExecutionStatus.APPLIED, result.reason
    assert len(result.created_persisting_effects) == 1
    assert decisions.event_log.records[-1].event_type == "rule_execution_effect_applied"


def _decision_controller_for_checkpoint(state: GameState) -> DecisionController:
    decisions = DecisionController()
    record_existing_primary_turn_start_evidence_events_for_fixture(
        state,
        decisions=decisions,
    )
    return decisions


def _enter_shooting_phase(state: GameState) -> None:
    player_id = state.active_player_id
    assert player_id is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id=player_id,
    )


def _record_checkpoint(*, state: GameState, decisions: DecisionController) -> None:
    player_id = state.active_player_id
    assert player_id is not None
    setup = state.mission_setup
    battlefield = state.battlefield_state
    army = state.army_definition_for_player(player_id)
    assert setup is not None
    assert battlefield is not None
    assert army is not None
    state.secondary_mission_choices = sorted(
        (
            *(
                choice
                for choice in state.secondary_mission_choices
                if choice.player_id != player_id
            ),
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("bring-it-down", "assassination"),
            ),
        ),
        key=lambda choice: choice.player_id,
    )
    state.secondary_mission_card_states = [
        card for card in state.secondary_mission_card_states if card.player_id != player_id
    ]
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_fixed(
            player_id=player_id,
            secondary_mission_id="bring-it-down",
        )
    )
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id=player_id,
            secondary_mission_id="cleanse",
            battle_round=state.battle_round,
            source_result_id="phase17n-runtime-cleanse-hold",
        )
    )
    central = next(
        marker
        for marker in setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    action_unit = army.units[0]
    placement = battlefield.unit_placement_by_id(action_unit.unit_instance_id)
    coherent_offsets = tuple(
        (float(index % 5), float(index // 5)) for index in range(len(placement.model_placements))
    )
    state.battlefield_state = battlefield.with_unit_placement(
        with_model_offsets(
            placement,
            central,
            offsets=coherent_offsets,
        )
    )
    _enter_shooting_phase(state)
    status = request_mission_action_opportunity(
        state=state,
        player_id=player_id,
        decisions=decisions,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    request = status.decision_request if status is not None else None
    assert request is not None
    option = next(
        option
        for option in request.options
        if option.option_id.startswith("start:cleanse-objective:")
    )
    result = DecisionResult.for_request(
        result_id=f"{request.request_id}:cleanse-result",
        request=request,
        selected_option_id=option.option_id,
    )
    record = decisions.submit_result(result)
    apply_mission_decision(
        state=state,
        request=record.request,
        result=result,
        decisions=decisions,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )


def _lifecycle_payload(
    *,
    state: GameState,
    decisions: DecisionController,
    config: GameConfig,
    bundle: RuntimeContentBundle,
) -> GameLifecyclePayload:
    return GameLifecycle(
        decision_controller=decisions,
        state=state,
        _config=config,
        _runtime_content_bundle=bundle,
    ).to_payload()
