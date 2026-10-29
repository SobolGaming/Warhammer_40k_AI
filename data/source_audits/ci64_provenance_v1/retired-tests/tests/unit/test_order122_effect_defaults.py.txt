"""Selected Core default lifetimes reach the real modifier consumer."""

from __future__ import annotations

import json

# pyright: reportPrivateUsage=false
from dataclasses import replace

import pytest
from tests.core_clause_evidence_helpers import assert_persistence_viewers_replay, clause_session
from tests.order97_gap_probes_01_08 import default_trigger_duration_observation
from tests.order122_helpers import (
    SOURCE_ID,
    advance_to_default_grant,
    default_effect_session,
    submit_quiet_choice,
)
from tests.support.ability_presence_fixtures import compiled_ability_rule

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.effects import EffectExpiration, EffectExpirationBoundary
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    RuleExecutionStatus,
    execute_rule_ir,
)
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    UnitCharacteristicModifierContext,
    WeaponProfileModifierContext,
)
from warhammer40k_core.rules.rule_ir import RuleDuration, RuleDurationKind, parameters_from_pairs

ATTACK_TEXT = (
    "Add 1 to the Attacks characteristic of ranged weapons equipped by models in this unit."
)


@pytest.mark.parametrize("triggered", [True, False])
def test_implicit_duration_reaches_weapon_characteristic_consumer(triggered: bool) -> None:
    observation = default_trigger_duration_observation(triggered=triggered)
    assert observation["observed_attacks"] == observation["expected_attacks"]


@pytest.mark.parametrize(
    ("prefix", "active_player", "kind"),
    [
        ("", "player-a", "end_phase"),
        ("", "player-b", "end_phase"),
        ("In the Shooting phase, ", "player-a", "end_phase"),
        ("In the Shooting phase, ", "player-b", "end_phase"),
        ("In your turn, ", "player-a", "end_turn"),
        ("In your opponent's turn, ", "player-b", "end_turn"),
        ("At the start of the first battle round, ", "player-a", "end_battle_round"),
    ],
)
def test_default_lifetime_uses_period_and_actual_turn_owner(
    prefix: str, active_player: str, kind: str
) -> None:
    session = clause_session(phase=BattlePhase.SHOOTING)
    state = session.lifecycle.state
    assert state is not None
    state.active_player_id = active_player
    unit = state.army_definitions[0].units[0]
    rule = compiled_ability_rule(prefix + ATTACK_TEXT.lower())
    assert not rule.diagnostics
    assert rule.clauses[0].duration is None
    result = execute_rule_ir(
        rule_ir=rule,
        context=RuleExecutionContext(
            game_id=state.game_id,
            player_id="player-a",
            battle_round=1,
            phase=BattlePhase.SHOOTING,
            active_player_id=active_player,
            source_unit_instance_id=unit.unit_instance_id,
            state=state,
        ),
    )
    assert result.status is RuleExecutionStatus.APPLIED
    effect = result.created_persisting_effects[0]
    assert effect.owner_player_id == "player-a"
    assert effect.source_rule_id == rule.source_id
    assert effect.expiration.expiration_kind.value == kind
    assert effect.expiration.player_id == (None if kind == "end_battle_round" else active_player)
    assert isinstance(effect.effect_payload, dict)
    assert effect.effect_payload["duration"] is None
    profile = next(
        item
        for item in session.lifecycle.config.army_catalog.wargear
        if item.wargear_id == "core-bolt-rifle"
    ).weapon_profiles[0]
    query = WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=unit.unit_instance_id,
        attacker_model_instance_id=unit.own_models[0].model_instance_id,
        target_unit_instance_id=state.army_definitions[1].units[0].unit_instance_id,
        weapon_profile=profile,
    )
    assert profile.attack_profile.fixed_attacks is not None
    assert RuntimeModifierRegistry.empty().modified_weapon_profile(
        query
    ).attack_profile.fixed_attacks == (profile.attack_profile.fixed_attacks + 1)
    wrong_player = "player-b" if active_player == "player-a" else "player-a"
    state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.phase_end(
            battle_round=1, phase=BattlePhase.SHOOTING, player_id=wrong_player
        )
    )
    assert state.persisting_effects == [effect]
    if kind != "end_phase":
        state.expire_persisting_effects_at_boundary(
            EffectExpirationBoundary.phase_end(
                battle_round=1, phase=BattlePhase.SHOOTING, player_id=active_player
            )
        )
        assert state.persisting_effects == [effect]
    boundary = EffectExpirationBoundary(
        expiration_kind=effect.expiration.expiration_kind,
        battle_round=effect.expiration.battle_round,
        phase=effect.expiration.phase,
        player_id=effect.expiration.player_id,
    )
    state.expire_persisting_effects_at_boundary(boundary)
    assert state.persisting_effects == []
    assert RuntimeModifierRegistry.empty().modified_weapon_profile(query) == profile


@pytest.mark.parametrize(
    ("duration_kind", "parameters", "expected"),
    [
        (RuleDurationKind.IMMEDIATE, (), None),
        (RuleDurationKind.WHILE_CONDITION_TRUE, (), None),
        (RuleDurationKind.PERMANENT, (), EffectExpiration.end_of_battle()),
        (
            RuleDurationKind.UNTIL_TIMING_ENDPOINT,
            (("endpoint", "turn"),),
            EffectExpiration.end_turn(battle_round=1, player_id="player-a"),
        ),
    ],
)
def test_explicit_duration_always_overrides_default(
    duration_kind: RuleDurationKind,
    parameters: tuple[tuple[str, str], ...],
    expected: EffectExpiration | None,
) -> None:
    session = clause_session(phase=BattlePhase.SHOOTING)
    state = session.lifecycle.state
    assert state is not None
    rule = compiled_ability_rule("In the Shooting phase, " + ATTACK_TEXT.lower())
    clause = rule.clauses[0]
    rule = replace(
        rule,
        clauses=(
            replace(
                clause,
                duration=RuleDuration(
                    kind=duration_kind,
                    source_span=clause.source_span,
                    parameters=parameters_from_pairs(parameters),
                ),
            ),
        ),
    )
    result = execute_rule_ir(
        rule_ir=rule,
        context=RuleExecutionContext(
            game_id=state.game_id,
            player_id="player-a",
            battle_round=1,
            phase=BattlePhase.SHOOTING,
            active_player_id="player-a",
            source_unit_instance_id=state.army_definitions[0].units[0].unit_instance_id,
            state=state,
        ),
    )
    assert result.status is RuleExecutionStatus.APPLIED
    assert tuple(effect.expiration for effect in result.created_persisting_effects) == (
        () if expected is None else (expected,)
    )


@pytest.mark.parametrize("missing", ["phase", "active_player", "state"])
def test_missing_default_calendar_prevents_preceding_command_point_mutation(missing: str) -> None:
    session = clause_session(phase=BattlePhase.SHOOTING)
    state = session.lifecycle.state
    assert state is not None
    rule = compiled_ability_rule("You gain 1CP. " + ATTACK_TEXT)
    assert not rule.diagnostics
    before = state.to_payload()
    result = execute_rule_ir(
        rule_ir=rule,
        context=RuleExecutionContext(
            game_id=state.game_id,
            player_id="player-a",
            battle_round=1,
            phase=None if missing == "phase" else BattlePhase.SHOOTING,
            active_player_id=None if missing == "active_player" else "player-a",
            source_unit_instance_id=state.army_definitions[0].units[0].unit_instance_id,
            state=None if missing == "state" else state,
        ),
    )
    assert result.status is RuleExecutionStatus.INVALID
    assert (
        result.reason
        == {
            "phase": "missing_phase",
            "active_player": "missing_active_player",
            "state": "missing_input:game_state",
        }[missing]
    )
    assert state.to_payload() == before


def test_nonpersistent_rule_evaluation_needs_no_implicit_calendar() -> None:
    rule = compiled_ability_rule(ATTACK_TEXT)
    result = execute_rule_ir(
        rule_ir=rule,
        context=RuleExecutionContext(
            game_id="order122:evaluation",
            player_id="player-a",
            battle_round=1,
            phase=None,
            active_player_id=None,
            source_unit_instance_id="unit",
            record_persisting_effects=False,
        ),
    )
    assert result.status is RuleExecutionStatus.APPLIED
    assert result.effect_payloads
    assert not result.created_persisting_effects


def test_typed_trigger_period_cannot_be_granted_in_a_different_phase() -> None:
    session = clause_session(phase=BattlePhase.FIGHT)
    state = session.lifecycle.state
    assert state is not None
    rule = compiled_ability_rule("In the Shooting phase, " + ATTACK_TEXT.lower())
    before = state.to_payload()
    result = execute_rule_ir(
        rule_ir=rule,
        context=RuleExecutionContext(
            game_id=state.game_id,
            player_id="player-a",
            battle_round=1,
            phase=BattlePhase.FIGHT,
            active_player_id="player-a",
            source_unit_instance_id=state.army_definitions[0].units[0].unit_instance_id,
            state=state,
        ),
    )
    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "implicit_trigger_phase_mismatch"
    assert state.to_payload() == before


@pytest.mark.parametrize("activate", [True, False])
def test_loaded_default_grant_full_cycles_restore_fork_viewers_and_replay(activate: bool) -> None:
    session = default_effect_session()
    request = advance_to_default_grant(session)
    assert_persistence_viewers_replay(session)
    forked = session.fork()
    restored = LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    assert restored.to_persistence_payload() == session.to_persistence_payload()
    state = restored.lifecycle.state
    assert state is not None
    assert state.current_battle_phase is BattlePhase.FIGHT
    options = [
        option
        for option in request.options
        if isinstance(option.payload, dict) and option.payload.get("activate") is activate
    ]
    assert len(options) == 1
    status = restored.submit_option(
        request_id=request.request_id,
        option_id=options[0].option_id,
        result_id="order122-grant",
    )
    assert status.decision_request is not None
    assert state.current_battle_phase is BattlePhase.FIGHT
    fork_state = forked.lifecycle.state
    assert fork_state is not None
    assert not any(effect.source_rule_id == SOURCE_ID for effect in fork_state.persisting_effects)
    effects = [effect for effect in state.persisting_effects if effect.source_rule_id == SOURCE_ID]
    assert len(effects) == (3 if activate else 0)
    leader = state.army_definitions[0].unit_by_id("army-alpha:leader")
    profile = next(
        item
        for item in restored.lifecycle.config.army_catalog.wargear
        if item.wargear_id == "core-leader-blade"
    ).weapon_profiles[0]
    context = WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.FIGHT,
        attacking_unit_instance_id="attached-unit:army-alpha:passengers",
        attacker_model_instance_id=leader.own_models[0].model_instance_id,
        target_unit_instance_id=state.army_definitions[1].units[0].unit_instance_id,
        weapon_profile=profile,
    )
    bundle = restored.lifecycle._require_runtime_content_bundle()
    modified = bundle.runtime_modifier_registry.modified_weapon_profile(context)
    assert profile.attack_profile.fixed_attacks is not None
    assert modified.attack_profile.fixed_attacks == profile.attack_profile.fixed_attacks + (
        3 if activate else 0
    )
    assert (WeaponKeyword.DEVASTATING_WOUNDS in modified.keywords) is activate
    model = leader.own_models[0]
    oc = model.characteristic(Characteristic.OBJECTIVE_CONTROL).final
    oc_context = UnitCharacteristicModifierContext(
        state=state,
        unit_instance_id="attached-unit:army-alpha:passengers",
        model_instance_id=model.model_instance_id,
        characteristic=Characteristic.OBJECTIVE_CONTROL,
        base_value=oc,
        current_value=oc,
    )
    assert bundle.runtime_modifier_registry.modified_unit_characteristic(oc_context) == oc + (
        2 if activate else 0
    )
    bodyguard = state.army_definitions[0].unit_by_id("army-alpha:passengers").own_models[0]
    other_oc = bodyguard.characteristic(Characteristic.OBJECTIVE_CONTROL).final
    assert (
        bundle.runtime_modifier_registry.modified_unit_characteristic(
            replace(
                oc_context,
                model_instance_id=bodyguard.model_instance_id,
                base_value=other_oc,
                current_value=other_oc,
            )
        )
        == other_oc
    )
    assert_persistence_viewers_replay(restored)
    for index in range(120):
        status = restored.advance_until_decision_or_terminal()
        if state.battle_round == 2:
            break
        assert status.decision_request is not None
        submit_quiet_choice(restored, status.decision_request, result_id=f"order122-after-{index}")
    else:
        raise AssertionError("Complete phase cycles did not advance.")
    assert not any(effect.source_rule_id == SOURCE_ID for effect in state.persisting_effects)
    assert_persistence_viewers_replay(restored)
