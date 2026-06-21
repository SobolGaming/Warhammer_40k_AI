from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, RulesetDescriptor
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilityExecutionContext,
    AbilityResolutionStatus,
    AbilitySourceKind,
    AbilityTimingDescriptor,
    default_ability_handler_registry,
)
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    muster_army,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldScenario,
    UnitPlacement,
)
from warhammer40k_core.engine.command_points import (
    CommandPointSourceKind,
    initial_command_point_ledgers,
)
from warhammer40k_core.engine.effects import (
    EffectError,
    EffectExpiration,
    generic_rule_persisting_effect,
)
from warhammer40k_core.engine.event_log import EventLog, JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    RuleExecutionRegistry,
    RuleExecutionStatus,
    default_rule_execution_registry,
    execute_rule_ir,
    rule_execution_status_from_token,
    rule_ir_from_execution_payload,
)
from warhammer40k_core.engine.scoring import initial_victory_point_ledgers
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.rule_compiler import CompiledRuleSource, compile_rule_source_text
from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRPayload, RuleParameter
from warhammer40k_core.rules.source_data import RuleSourceText


def test_phase17d_generic_modifier_rule_executes_as_source_linked_effect() -> None:
    compiled = _compiled("Add 1 to hit rolls for that unit.")
    context = _execution_context(
        target_unit_instance_ids=("army-alpha:intercessor-unit-1",),
    )

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=context,
        registry=default_rule_execution_registry(),
    )
    effect_payload = result.effect_payloads[0]
    effect = _json_object(effect_payload["effect"])

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.reason is None
    assert result.applied_clause_ids == (compiled.rule_ir.clauses[0].clause_id,)
    assert effect["kind"] == "modify_dice_roll"
    assert effect["parameters"] == [
        {"key": "delta", "value": 1},
        {"key": "roll_type", "value": "hit"},
    ]
    assert result.event_records[0].event_type == "rule_execution_effect_applied"
    assert result.to_payload()["source_id"] == compiled.rule_ir.source_id


def test_phase17d_target_scoped_effect_requires_target_binding() -> None:
    compiled = _compiled("Add 1 to hit rolls for that unit.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "missing_target:unit_instance_ids"
    assert result.effect_payloads == ()
    assert result.event_records == ()


def test_phase17d_this_unit_effect_uses_source_unit_binding() -> None:
    source_unit_id = "army-alpha:intercessor-unit-1"
    unrelated_target_unit_id = "army-beta:intercessor-unit-2"
    compiled = _compiled("This unit can be set up more than 9 inches away from enemy units.")

    missing_source = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(),
        registry=default_rule_execution_registry(),
    )
    explicit_target_without_source = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(target_unit_instance_ids=(unrelated_target_unit_id,)),
        registry=default_rule_execution_registry(),
    )
    applied = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            source_unit_instance_id=source_unit_id,
            target_unit_instance_ids=(unrelated_target_unit_id,),
        ),
        registry=default_rule_execution_registry(),
    )

    assert missing_source.status is RuleExecutionStatus.INVALID
    assert missing_source.reason == "missing_input:source_unit_instance_id"
    assert explicit_target_without_source.status is RuleExecutionStatus.INVALID
    assert explicit_target_without_source.reason == "missing_input:source_unit_instance_id"
    assert applied.status is RuleExecutionStatus.APPLIED
    assert applied.effect_payloads[0]["target_unit_instance_ids"] == [source_unit_id]


def test_phase17d_optional_wargear_bearer_unit_effects_execute_generically() -> None:
    source_unit_id = "army-alpha:bloodletters-1"
    icon = _compiled("Models in the bearer's unit have a Leadership characteristic of 6+.")
    instrument = _compiled("Add 1 to Charge rolls made for the bearer's unit.")

    icon_result = execute_rule_ir(
        rule_ir=icon.rule_ir,
        context=_execution_context(source_unit_instance_id=source_unit_id),
        registry=default_rule_execution_registry(),
    )
    instrument_result = execute_rule_ir(
        rule_ir=instrument.rule_ir,
        context=_execution_context(source_unit_instance_id=source_unit_id),
        registry=default_rule_execution_registry(),
    )

    assert icon_result.status is RuleExecutionStatus.APPLIED
    assert icon_result.effect_payloads[0]["target_unit_instance_ids"] == [source_unit_id]
    assert _json_object(icon_result.effect_payloads[0]["effect"])["parameters"] == [
        {"key": "characteristic", "value": "leadership"},
        {"key": "value", "value": "6+"},
    ]
    assert instrument_result.status is RuleExecutionStatus.APPLIED
    assert instrument_result.effect_payloads[0]["target_unit_instance_ids"] == [source_unit_id]
    assert _json_object(instrument_result.effect_payloads[0]["effect"])["parameters"] == [
        {"key": "delta", "value": 1},
        {"key": "roll_type", "value": "charge"},
    ]


def test_phase17d_generic_reroll_permission_executes() -> None:
    compiled = _compiled("After a hit roll, re-roll hit rolls.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            trigger_payload={"roll_type": "hit"},
            target_unit_instance_ids=("army-alpha:intercessor-unit-1",),
        ),
        registry=default_rule_execution_registry(),
    )
    effect = _json_object(result.effect_payloads[0]["effect"])

    assert result.status is RuleExecutionStatus.APPLIED
    assert effect["kind"] == "reroll_permission"
    assert effect["parameters"] == [{"key": "roll_type", "value": "hit"}]


def test_phase17d_generic_vp_scoring_rule_mutates_victory_point_ledger() -> None:
    state = _battle_state()
    event_log = EventLog()
    compiled = _compiled("When this unit is destroyed, score 5VP.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, event_log=event_log),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert state.victory_point_total("player-a") == 5
    assert result.victory_point_transactions[0]["amount"] == 5
    assert result.victory_point_transactions[0]["source_id"] == compiled.rule_ir.source_id
    assert event_log.records[-1].event_type == "rule_execution_victory_points_awarded"


def test_phase17d_generic_cp_rule_mutates_command_point_ledger_and_reports_cap() -> None:
    state = _battle_state()
    event_log = EventLog()
    compiled = _compiled("Gain 1CP and score 3VP.")

    first = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, event_log=event_log),
        registry=default_rule_execution_registry(),
    )
    event_count_after_first = len(event_log.records)
    capped = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, event_log=event_log),
        registry=default_rule_execution_registry(),
    )

    assert first.status is RuleExecutionStatus.APPLIED
    assert state.command_point_total("player-a") == 1
    assert state.victory_point_total("player-a") == 3
    assert first.command_point_transactions[0]["status"] == "applied"
    assert first.command_point_transactions[0]["applied_amount"] == 1
    assert capped.status is RuleExecutionStatus.INVALID
    assert capped.reason == "command_point_gain_capped"
    assert state.command_point_total("player-a") == 1
    assert state.victory_point_total("player-a") == 3
    assert len(event_log.records) == event_count_after_first


def test_phase17d_later_invalid_effect_does_not_leave_prior_mutation() -> None:
    state = _battle_state()
    event_log = EventLog()
    compiled = _compiled("Gain 1CP and score 3VP.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, event_log=event_log, phase=None),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "missing_phase"
    assert state.command_point_total("player-a") == 0
    assert state.victory_point_total("player-a") == 0
    assert event_log.records == ()


def test_phase17d_generic_cp_spend_rule_uses_command_point_ledger() -> None:
    spend_rule_ir = _command_point_spend_rule_ir()
    insufficient_state = _battle_state()
    funded_state = _battle_state()
    funded_state.gain_command_points(
        player_id="player-a",
        amount=1,
        source_id="phase17d:seed-cp",
        source_kind=CommandPointSourceKind.OTHER,
        cap_exempt=True,
    )

    insufficient = execute_rule_ir(
        rule_ir=spend_rule_ir,
        context=_execution_context(state=insufficient_state),
        registry=default_rule_execution_registry(),
    )
    applied = execute_rule_ir(
        rule_ir=spend_rule_ir,
        context=_execution_context(state=funded_state),
        registry=default_rule_execution_registry(),
    )

    assert insufficient.status is RuleExecutionStatus.INVALID
    assert insufficient.reason == "insufficient_command_points"
    assert insufficient_state.command_point_total("player-a") == 0
    assert applied.status is RuleExecutionStatus.APPLIED
    assert funded_state.command_point_total("player-a") == 0
    assert applied.command_point_transactions[0]["status"] == "applied"
    assert applied.command_point_transactions[0]["applied_amount"] == 1


def test_phase17d_duration_effect_records_generic_persisting_effect() -> None:
    state = _battle_state_with_scenario()
    target_unit_id = "army-alpha:intercessor-unit-1"
    compiled = _compiled("That unit gains Stealth until the end of the phase.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=state,
            target_unit_instance_ids=(target_unit_id,),
        ),
        registry=default_rule_execution_registry(),
    )
    effect = result.created_persisting_effects[0]
    payload = effect.to_payload()
    effect_payload = _json_object(payload["effect_payload"])

    assert result.status is RuleExecutionStatus.APPLIED
    assert state.persisting_effects_for_unit(target_unit_id) == (effect,)
    assert payload["started_phase"] == "command"
    assert payload["expiration"]["expiration_kind"] == "end_phase"
    assert effect_payload["effect_kind"] == "generic_rule_execution"


def test_phase17d_phase_duration_requires_phase_before_mutation() -> None:
    state = _battle_state_with_scenario()
    event_log = EventLog()
    target_unit_id = "army-alpha:intercessor-unit-1"
    compiled = _compiled("That unit gains Stealth until the end of the phase.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=state,
            event_log=event_log,
            target_unit_instance_ids=(target_unit_id,),
            phase=None,
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "missing_phase"
    assert state.persisting_effects_for_unit(target_unit_id) == ()
    assert event_log.records == ()


def test_phase17d_duration_effect_requires_state_before_applying() -> None:
    target_unit_id = "army-alpha:intercessor-unit-1"
    compiled = _compiled("That unit gains Stealth until the end of the phase.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            target_unit_instance_ids=(target_unit_id,),
            phase=BattlePhaseKind.COMMAND,
            state=None,
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "missing_input:game_state"
    assert result.effect_payloads == ()
    assert result.created_persisting_effects == ()


def test_phase17d_preflight_rejects_missing_state_before_vp_mutation() -> None:
    compiled = _compiled("When this unit is destroyed, score 5VP.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "missing_input:game_state"
    assert result.event_records == ()


def test_phase17d_handler_invalid_result_propagates_without_merge_exception() -> None:
    state = _battle_state()
    compiled = _compiled("When this unit is destroyed, score 5VP.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, phase=None),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "missing_phase"
    assert state.victory_point_total("player-a") == 0


def test_phase17d_generic_stratagem_target_binding_executes() -> None:
    compiled = _compiled("Select one enemy unit.")
    target_unit_id = "army-beta:intercessor-unit-2"

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            target_unit_instance_ids=(target_unit_id,),
            trigger_payload={"stratagem_id": "phase17d:test-stratagem"},
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.target_bindings == (
        {
            "rule_id": compiled.rule_ir.rule_id,
            "source_id": compiled.rule_ir.source_id,
            "clause_id": compiled.rule_ir.clauses[0].clause_id,
            "target_kind": "enemy_unit",
            "target_unit_instance_ids": [target_unit_id],
            "target_player_id": None,
        },
    )
    assert result.event_records[0].event_type == "rule_execution_target_bound"


def test_phase17d_preflight_rejects_missing_target_binding() -> None:
    compiled = _compiled("Select one enemy unit.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "missing_target:unit_instance_ids"
    assert result.target_bindings == ()


def test_phase17d_friendly_aura_evaluation_ignores_enemy_units_in_range() -> None:
    state = _battle_state_with_extra_friendly_unit()
    source_unit_id = "army-alpha:intercessor-unit-1"
    friendly_unit_id = "army-alpha:intercessor-unit-3"
    enemy_unit_id = "army-beta:intercessor-unit-2"
    compiled = _compiled(
        "Aura: while a friendly unit is within 6 inches, subtract 1 from wound rolls."
    )

    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=friendly_unit_id,
        pose=Pose.at(8.0, 6.0),
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=enemy_unit_id,
        pose=Pose.at(8.0, 6.0),
    )
    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, source_unit_instance_id=source_unit_id),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.aura_evaluations[0]["affected_unit_instance_ids"] == [friendly_unit_id]
    assert result.effect_payloads[0]["target_unit_instance_ids"] == [friendly_unit_id]


def test_phase17d_enemy_aura_evaluation_ignores_friendly_units_in_range() -> None:
    state = _battle_state_with_extra_friendly_unit()
    source_unit_id = "army-alpha:intercessor-unit-1"
    friendly_unit_id = "army-alpha:intercessor-unit-3"
    enemy_unit_id = "army-beta:intercessor-unit-2"
    compiled = _compiled(
        "Aura: while an enemy unit is within 6 inches, subtract 1 from wound rolls."
    )

    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=friendly_unit_id,
        pose=Pose.at(8.0, 6.0),
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=enemy_unit_id,
        pose=Pose.at(8.0, 6.0),
    )
    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, source_unit_instance_id=source_unit_id),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.aura_evaluations[0]["affected_unit_instance_ids"] == [enemy_unit_id]
    assert result.effect_payloads[0]["target_unit_instance_ids"] == [enemy_unit_id]


def test_phase17d_any_aura_evaluation_affects_all_allegiances_in_range() -> None:
    state = _battle_state_with_extra_friendly_unit()
    source_unit_id = "army-alpha:intercessor-unit-1"
    friendly_unit_id = "army-alpha:intercessor-unit-3"
    enemy_unit_id = "army-beta:intercessor-unit-2"
    compiled = _compiled("Aura: while a unit is within 6 inches, subtract 1 from wound rolls.")

    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=friendly_unit_id,
        pose=Pose.at(8.0, 6.0),
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=enemy_unit_id,
        pose=Pose.at(8.0, 6.0),
    )
    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, source_unit_instance_id=source_unit_id),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.aura_evaluations[0]["affected_unit_instance_ids"] == [
        friendly_unit_id,
        enemy_unit_id,
    ]


def test_phase17d_unsupported_rule_ir_produces_typed_unsupported_status() -> None:
    compiled = _compiled("Roll a scatter die and consult the legacy table.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.UNSUPPORTED
    assert result.reason == "unsupported_rule_ir"
    assert result.applied_clause_ids == ()
    assert result.event_records == ()


def test_phase17d_missing_registry_binding_produces_typed_unsupported_status() -> None:
    compiled = _compiled("Add 1 to hit rolls for that unit.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(),
        registry=RuleExecutionRegistry.empty(),
    )

    assert result.status is RuleExecutionStatus.UNSUPPORTED
    assert result.reason == "missing_effect_handler:modify_dice_roll"
    assert result.event_records == ()


def test_phase17d_no_effect_clause_executes_as_deterministic_noop() -> None:
    compiled = _compiled("At the start of your Command phase.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(),
        registry=default_rule_execution_registry(),
    )
    replay_payload = _json_object(result.replay_payload)

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.applied_clause_ids == (compiled.rule_ir.clauses[0].clause_id,)
    assert result.effect_payloads == ()
    assert result.event_records == ()
    assert replay_payload["executed_clause_count"] == 1
    assert replay_payload["event_count"] == 0


def test_phase17d_rule_ir_payload_round_trips_through_execution_result() -> None:
    compiled = _compiled("Add 1 to hit rolls for that unit.")
    rule_ir_payload = cast(RuleIRPayload, json.loads(compiled.rule_ir.to_json_bytes()))

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            target_unit_instance_ids=("army-alpha:intercessor-unit-1",),
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.to_payload()["rule_ir_hash"] == rule_ir_payload["ir_hash"]
    assert "<" not in json.dumps(result.to_payload(), sort_keys=True)
    assert "object at 0x" not in json.dumps(result.to_payload(), sort_keys=True)


def test_phase17d_execution_payload_and_registry_metadata_are_json_safe() -> None:
    compiled = _compiled("Add 1 to hit rolls for that unit.")
    execution_payload = validate_json_value({"rule_ir": compiled.rule_ir.to_payload()})

    rule_ir = rule_ir_from_execution_payload(execution_payload)
    registry_payload = default_rule_execution_registry().to_payload()

    assert rule_ir.ir_hash() == compiled.rule_ir.ir_hash()
    assert rule_execution_status_from_token("applied") is RuleExecutionStatus.APPLIED
    assert "phase17d:generic-command-points" in {
        binding["binding_id"] for binding in registry_payload
    }
    assert "<" not in json.dumps(registry_payload, sort_keys=True)
    with pytest.raises(GameLifecycleError, match="must be a JSON object"):
        rule_ir_from_execution_payload([])
    with pytest.raises(GameLifecycleError, match="requires rule_ir"):
        rule_ir_from_execution_payload({"missing": None})
    with pytest.raises(GameLifecycleError, match="must be a string"):
        rule_execution_status_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported RuleExecutionStatus"):
        rule_execution_status_from_token("not-a-status")


def test_phase17d_generic_persisting_effect_rejects_invalid_payload_shape() -> None:
    with pytest.raises(EffectError, match="JSON object"):
        generic_rule_persisting_effect(
            effect_id="phase17d:effect",
            source_rule_id="phase17d:source",
            owner_player_id="player-a",
            target_unit_instance_ids=("army-alpha:intercessor-unit-1",),
            started_battle_round=1,
            started_phase=BattlePhaseKind.COMMAND,
            expiration=EffectExpiration.end_phase(
                battle_round=1,
                phase=BattlePhaseKind.COMMAND,
                player_id="player-a",
            ),
            effect_payload="not-object",
        )
    with pytest.raises(EffectError, match="payload kind"):
        generic_rule_persisting_effect(
            effect_id="phase17d:effect",
            source_rule_id="phase17d:source",
            owner_player_id="player-a",
            target_unit_instance_ids=("army-alpha:intercessor-unit-1",),
            started_battle_round=1,
            started_phase=BattlePhaseKind.COMMAND,
            expiration=EffectExpiration.end_phase(
                battle_round=1,
                phase=BattlePhaseKind.COMMAND,
                player_id="player-a",
            ),
            effect_payload={"effect_kind": "wrong"},
        )


def test_phase17d_ability_bridge_executes_compiled_rule_ir_payload() -> None:
    compiled = _compiled("Add 1 to hit rolls for that unit.")
    record = AbilityCatalogRecord(
        record_id="phase17d:ability-record",
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id="phase17d:datasheet",
        definition=AbilityDefinition(
            ability_id="phase17d:ability",
            name="phase17d generic ability",
            source_id="phase17d:ability-source",
            when_descriptor="phase17d:when",
            effect_descriptor="phase17d:effect",
            restrictions_descriptor="phase17d:restrictions",
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.ANY_PHASE),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=validate_json_value({"rule_ir": compiled.rule_ir.to_payload()}),
        ),
    )

    result = default_ability_handler_registry().execute(
        record=record,
        context=AbilityExecutionContext(
            game_id="phase17d-game",
            player_id="player-a",
            battle_round=1,
            phase=BattlePhaseKind.COMMAND,
            active_player_id="player-a",
            trigger_kind=TimingTriggerKind.ANY_PHASE,
            target_unit_instance_id="army-alpha:intercessor-unit-1",
            source_keywords=(),
        ),
    )
    replay_payload = _json_object(result.replay_payload)
    rule_execution = _json_object(replay_payload["rule_execution"])

    assert result.status is AbilityResolutionStatus.APPLIED
    assert rule_execution["status"] == "applied"
    assert rule_execution["rule_ir_hash"] == compiled.rule_ir.ir_hash()


def test_phase17d_leading_model_condition_survives_destroyed_bodyguard_split() -> None:
    leader_state = _bodyguard_destroyed_split_state()
    support_state = _bodyguard_destroyed_split_state()
    bodyguard_state = _bodyguard_destroyed_split_state()
    bodyguard_id = "army-alpha:bodyguard-unit"
    leader_id = "army-alpha:leader-unit"
    support_id = "army-alpha:support-unit"
    compiled = _compiled(_skullmaster_fury_text())

    leader_result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=leader_state,
            source_model_instance_id=f"{leader_id}:core-character-leader:001",
            target_unit_instance_ids=(leader_id,),
            phase=BattlePhaseKind.CHARGE,
        ),
        registry=default_rule_execution_registry(),
    )
    support_result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=support_state,
            source_unit_instance_id=support_id,
            target_unit_instance_ids=(support_id,),
            phase=BattlePhaseKind.CHARGE,
        ),
        registry=default_rule_execution_registry(),
    )
    bodyguard_result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=bodyguard_state,
            source_unit_instance_id=bodyguard_id,
            target_unit_instance_ids=(leader_id,),
            phase=BattlePhaseKind.CHARGE,
        ),
        registry=default_rule_execution_registry(),
    )

    assert not leader_state.army_definitions[0].attached_units
    assert leader_state.unit_started_battle_as_attached_leader_or_support(leader_id)
    assert leader_state.unit_started_battle_as_attached_leader_or_support(support_id)
    assert (
        GameState.from_payload(leader_state.to_payload()).to_payload() == leader_state.to_payload()
    )
    assert leader_result.status is RuleExecutionStatus.APPLIED
    assert support_result.status is RuleExecutionStatus.APPLIED
    assert bodyguard_result.status is RuleExecutionStatus.INVALID
    assert bodyguard_result.reason == "condition_not_met:this_model_leading_unit"


def test_phase17d_leading_model_condition_fails_closed_without_state_or_source() -> None:
    compiled = _compiled(_skullmaster_fury_text())

    missing_state = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            source_unit_instance_id="army-alpha:leader-unit",
            target_unit_instance_ids=("army-alpha:leader-unit",),
            phase=BattlePhaseKind.CHARGE,
        ),
        registry=default_rule_execution_registry(),
    )
    missing_source = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=_battle_state_with_attached_leader_support(),
            target_unit_instance_ids=("army-alpha:leader-unit",),
            phase=BattlePhaseKind.CHARGE,
        ),
        registry=default_rule_execution_registry(),
    )

    assert missing_state.status is RuleExecutionStatus.INVALID
    assert missing_state.reason == "missing_input:game_state"
    assert missing_source.status is RuleExecutionStatus.INVALID
    assert missing_source.reason == "missing_input:source_unit_instance_id"


def test_phase17d_ability_bridge_passes_state_for_leading_model_condition() -> None:
    state = _bodyguard_destroyed_split_state()
    leader_id = "army-alpha:leader-unit"
    compiled = _compiled(_skullmaster_fury_text())
    record = AbilityCatalogRecord(
        record_id="phase17d:leading-ability-record",
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id="phase17d:skullmaster",
        definition=AbilityDefinition(
            ability_id="phase17d:leading-ability",
            name="phase17d leading ability",
            source_id="phase17d:leading-ability-source",
            when_descriptor="phase17d:when",
            effect_descriptor="phase17d:effect",
            restrictions_descriptor="phase17d:restrictions",
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.ANY_PHASE),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=validate_json_value({"rule_ir": compiled.rule_ir.to_payload()}),
        ),
    )

    result = default_ability_handler_registry().execute(
        record=record,
        context=AbilityExecutionContext(
            game_id="phase17d-game",
            player_id="player-a",
            battle_round=1,
            phase=BattlePhaseKind.CHARGE,
            active_player_id="player-a",
            trigger_kind=TimingTriggerKind.ANY_PHASE,
            source_unit_instance_id=leader_id,
            target_unit_instance_id=leader_id,
            source_keywords=(),
            state=state,
        ),
    )

    assert result.status is AbilityResolutionStatus.APPLIED


def _compiled(raw_text: str) -> CompiledRuleSource:
    return compile_rule_source_text(
        RuleSourceText.from_raw(source_id=f"phase17d:{raw_text.lower()}", raw_text=raw_text)
    )


def _skullmaster_fury_text() -> str:
    return (
        "While this model is leading a unit, each time that unit ends a Charge move, "
        "until the end of the turn, Juggernaut's bladed horns equipped by models in "
        "that unit have the [DEVASTATING WOUNDS] ability."
    )


def _command_point_spend_rule_ir() -> RuleIR:
    compiled = _compiled("Gain 1CP and score 3VP.")
    clause = compiled.rule_ir.clauses[0]
    command_point_effect = clause.effects[0]
    spend_effect = replace(command_point_effect, parameters=(RuleParameter("delta", -1),))
    spend_clause = replace(clause, effects=(spend_effect,))
    return replace(compiled.rule_ir, clauses=(spend_clause,))


def _execution_context(
    *,
    state: GameState | None = None,
    event_log: EventLog | None = None,
    source_unit_instance_id: str | None = None,
    source_model_instance_id: str | None = None,
    target_unit_instance_ids: tuple[str, ...] = (),
    trigger_payload: JsonValue = None,
    phase: BattlePhaseKind | None = BattlePhaseKind.COMMAND,
) -> RuleExecutionContext:
    return RuleExecutionContext(
        game_id="phase17d-game",
        player_id="player-a",
        battle_round=1,
        phase=phase,
        active_player_id="player-a",
        timing_window_id="phase17d:test-window",
        source_unit_instance_id=source_unit_instance_id,
        source_model_instance_id=source_model_instance_id,
        target_unit_instance_ids=target_unit_instance_ids,
        trigger_payload=trigger_payload,
        state=state,
        event_log=event_log,
    )


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _battle_state() -> GameState:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    return GameState(
        game_id="phase17d-game",
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
        command_point_ledgers=initial_command_point_ledgers(("player-a", "player-b")),
        victory_point_ledgers=initial_victory_point_ledgers(("player-a", "player-b")),
    )


def _battle_state_with_scenario() -> GameState:
    scenario = _scenario()
    state = _battle_state()
    for army_definition in scenario.armies:
        state.record_army_definition(army_definition)
    state.battlefield_state = scenario.battlefield_state
    return state


def _battle_state_with_attached_leader_support() -> GameState:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    state = _battle_state()
    state.record_army_definition(
        muster_army(
            catalog=catalog,
            request=_attached_leader_support_muster_request(catalog),
        )
    )
    return state


def _bodyguard_destroyed_split_state() -> GameState:
    state = _battle_state_with_attached_leader_support()
    state.recover_starting_strength_after_attached_unit_split(
        player_id="player-a",
        attached_unit_instance_id="attached-unit:army-alpha:bodyguard-unit",
        surviving_unit_instance_ids=(
            "army-alpha:leader-unit",
            "army-alpha:support-unit",
        ),
    )
    return state


def _battle_state_with_extra_friendly_unit() -> GameState:
    scenario = _scenario_with_extra_friendly_unit()
    state = _battle_state()
    for army_definition in scenario.armies:
        state.record_army_definition(army_definition)
    state.battlefield_state = scenario.battlefield_state
    return state


def _scenario() -> BattlefieldScenario:
    return create_deterministic_battlefield_scenario(
        battlefield_id="phase17d-battlefield",
        armies=_mustered_armies(),
    )


def _scenario_with_extra_friendly_unit() -> BattlefieldScenario:
    return create_deterministic_battlefield_scenario(
        battlefield_id="phase17d-battlefield-extra-friendly",
        armies=_mustered_armies_with_extra_friendly_unit(),
    )


def _mustered_armies() -> tuple[ArmyDefinition, ...]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return (
        muster_army(
            catalog=catalog,
            request=_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_id="intercessor-unit-1",
            ),
        ),
        muster_army(
            catalog=catalog,
            request=_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="intercessor-unit-2",
            ),
        ),
    )


def _mustered_armies_with_extra_friendly_unit() -> tuple[ArmyDefinition, ...]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return (
        muster_army(
            catalog=catalog,
            request=_muster_request_with_unit_ids(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=(
                    "intercessor-unit-1",
                    "intercessor-unit-3",
                ),
            ),
        ),
        muster_army(
            catalog=catalog,
            request=_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="intercessor-unit-2",
            ),
        ),
    )


def _muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_id: str,
) -> ArmyMusterRequest:
    return _muster_request_with_unit_ids(
        catalog=catalog,
        player_id=player_id,
        army_id=army_id,
        unit_selection_ids=(unit_selection_id,),
    )


def _muster_request_with_unit_ids(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_ids: tuple[str, ...],
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        unit_selections=tuple(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            )
            for unit_selection_id in unit_selection_ids
        ),
    )


def _attached_leader_support_muster_request(catalog: ArmyCatalog) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id="army-alpha",
        player_id="player-a",
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id="bodyguard-unit",
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
            UnitMusterSelection(
                unit_selection_id="leader-unit",
                datasheet_id="core-character-leader",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-character-leader",
                        model_count=1,
                    ),
                ),
            ),
            UnitMusterSelection(
                unit_selection_id="support-unit",
                datasheet_id="core-character-support",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-character-support",
                        model_count=1,
                    ),
                ),
            ),
        ),
        attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
            AttachmentDeclaration(
                source_unit_selection_id="support-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
        ),
    )


def _with_unit_pose(
    battlefield_state: BattlefieldRuntimeState | None,
    *,
    unit_instance_id: str,
    pose: Pose,
) -> BattlefieldRuntimeState:
    if battlefield_state is None:
        raise AssertionError("test requires battlefield_state")
    unit_placement = battlefield_state.unit_placement_by_id(unit_instance_id)
    moved = UnitPlacement(
        army_id=unit_placement.army_id,
        player_id=unit_placement.player_id,
        unit_instance_id=unit_placement.unit_instance_id,
        model_placements=tuple(
            model_placement.with_pose(
                Pose.at(
                    pose.position.x + index * 1.5,
                    pose.position.y,
                    pose.position.z,
                    model_placement.pose.facing.degrees,
                )
            )
            for index, model_placement in enumerate(unit_placement.model_placements)
        ),
    )
    return battlefield_state.with_unit_placement(moved)
