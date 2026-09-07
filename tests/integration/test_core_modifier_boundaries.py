from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, cast

import pytest
from tests.generic_modifier_helpers import generic_effect
from tests.historical_leadership_helpers import (
    completed_historical_leadership_session,
    completed_leadership_history,
)
from tests.phase13b_shooting_declaration_helpers import (
    _attached_enemy_declarations,
    _attached_enemy_unit_specs,
    _attached_formation_for_player,
    _attack_pool_for_test,
    _first_weapon_profile,
    _replace_unit_toughness,
    _ruleset,
    _shooting_lifecycle,
    _state,
)
from tests.phase15a_charge_declaration_helpers import charge_lifecycle, compact_test_unit_poses

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceExpression, DiceRollResult, DiceRollState
from warhammer40k_core.core.modified_dice import ModifiedRollResult, ModifiedRollResultPayload
from warhammer40k_core.core.modifiers import ModifierOperation, ModifierTerm, RollModifier
from warhammer40k_core.core.weapon_profiles import DamageProfile, RangeProfile
from warhammer40k_core.engine.advance_roll import AdvanceRollRequest, AdvanceRollResult
from warhammer40k_core.engine.attack_sequence_geometry_targets import (
    _damage_value,
    _target_unit_toughness,
)
from warhammer40k_core.engine.attack_sequence_hit_wound import _roll_hit, _roll_wound
from warhammer40k_core.engine.attack_sequence_model import (
    HitRoll,
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
)
from warhammer40k_core.engine.battle_shock_generic_leadership_authority import (
    _expired_at_test as historical_effect_expired,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.battle_shock_historical_authority import (
    HistoricalBattleShockAuthorityContext,
)
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.charge_declaration import ChargeRollResult, ChargeRollResultPayload
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.game_state import GameState, GameStatePayload
from warhammer40k_core.engine.generic_rule_attack_hooks import (
    generic_rule_unit_characteristic_modifiers,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.lone_operative import lone_operative_target_allowed
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies
from warhammer40k_core.engine.runtime_modifiers import (
    MovementBudgetModifierContext,
    ObjectiveControlModifierBinding,
    ObjectiveControlModifierContext,
    RuntimeModifierRegistry,
    UnitCharacteristicModifierBinding,
    UnitCharacteristicModifierContext,
)
from warhammer40k_core.engine.saves import SaveKind, SaveOption, resolve_saving_throw
from warhammer40k_core.engine.shooting_targets import (
    ShootingTargetViolationCode,
    shooting_target_candidate_for_model,
)
from warhammer40k_core.engine.stratagems_generic_rule_ir_runtime import (
    GENERIC_RULE_IR_CHARGE_ROLL_MODIFIER_EFFECT_KIND,
)
from warhammer40k_core.engine.unit_abilities import LoneOperativeAbilityProfile
from warhammer40k_core.geometry.pose import Pose


@pytest.fixture(scope="module")
def leadership_history() -> HistoricalBattleShockAuthorityContext:
    return completed_leadership_history(completed_historical_leadership_session())


@pytest.mark.parametrize(
    ("expiration", "expected"),
    [
        (EffectExpiration.end_of_battle(), False),
        (EffectExpiration.end_battle_round(battle_round=1), True),
        (EffectExpiration.end_battle_round(battle_round=3), False),
        (EffectExpiration.start_battle_round(battle_round=2), True),
        (EffectExpiration.end_battle_round(battle_round=2), False),
        (EffectExpiration.start_turn(battle_round=2, player_id="player-a"), True),
        (EffectExpiration.end_turn(battle_round=2, player_id="player-a"), True),
        (EffectExpiration.start_turn(battle_round=2, player_id="player-b"), True),
        (EffectExpiration.end_turn(battle_round=2, player_id="player-b"), False),
        (
            EffectExpiration.start_phase(
                battle_round=2, player_id="player-b", phase=BattlePhase.MOVEMENT
            ),
            True,
        ),
        (
            EffectExpiration.end_phase(
                battle_round=2, player_id="player-b", phase=BattlePhase.MOVEMENT
            ),
            False,
        ),
        (
            EffectExpiration.end_phase(
                battle_round=2, player_id="player-b", phase=BattlePhase.COMMAND
            ),
            True,
        ),
        (
            EffectExpiration.start_phase(
                battle_round=2, player_id="player-b", phase=BattlePhase.FIGHT
            ),
            False,
        ),
    ],
)
def test_historical_effect_expiration_uses_original_turn_and_phase(
    leadership_history: HistoricalBattleShockAuthorityContext,
    expiration: EffectExpiration,
    expected: bool,
) -> None:
    history = replace(
        leadership_history,
        request=replace(leadership_history.request, battle_round=2),
        active_player_id="player-b",
        phase=BattlePhase.MOVEMENT,
    )
    assert historical_effect_expired(expiration, history) is expected


@pytest.mark.parametrize("registered", [False, True])
@pytest.mark.parametrize("duplicate", [False, True])
@pytest.mark.parametrize("expires", [False, True])
def test_completed_battle_shock_restores_generic_leadership_history(
    registered: bool, duplicate: bool, expires: bool
) -> None:
    session = completed_historical_leadership_session(
        registered=registered, duplicate=duplicate, expires=expires
    )
    lifecycle = session.lifecycle
    resolved = [
        event.payload
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "battle_shock_test_resolved"
    ]
    assert len(resolved) == 1
    assert isinstance(resolved[0], dict)
    result = resolved[0]["battle_shock_result"]
    assert isinstance(result, dict)
    request_payload = result["request"]
    assert isinstance(request_payload, dict)
    assert request_payload["leadership_target"] == (6 if registered else 7)
    assert lifecycle.state is not None
    effects = [
        effect
        for effect in lifecycle.state.persisting_effects
        if effect.source_rule_id == "fixture:historical-leadership"
    ]
    assert len(effects) == (0 if expires else (2 if duplicate else 1))
    persisted = session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(persisted).to_persistence_payload() == persisted
    )
    snapshot = lifecycle.to_payload()
    assert GameLifecycle.from_payload(snapshot).to_payload() == snapshot
    assert (
        ReplayRunner.from_payload(
            session.replay_artifact(artifact_id="historical-leadership-replay")
        )
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize(
    "fault",
    [
        "delta",
        "target",
        "source",
        "expiration",
        "missing_creation",
        "creation_clock",
        "activation",
        "recorded_expiration",
    ],
)
def test_expired_generic_leadership_requires_original_source_evidence(fault: str) -> None:
    session = completed_historical_leadership_session(registered=True, duplicate=True, expires=True)
    original = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(original).to_payload() == original
    payload = cast(dict[str, Any], json.loads(json.dumps(original)))
    events = payload["decisions"]["event_log"]
    creations = [
        event
        for event in events
        if event["event_type"] == "rule_execution_effect_applied"
        and event["payload"].get("source_id") == "fixture:historical-leadership"
    ]
    assert len(creations) == 2
    for event in creations:
        effect = event["payload"]
        if fault == "delta":
            next(row for row in effect["effect"]["parameters"] if row["key"] == "delta")[
                "value"
            ] = 2
        elif fault == "target":
            effect["target_unit_instance_ids"] = ["army-beta:intercessor-unit-3"]
        elif fault == "source":
            effect["source_id"] = "fixture:unloaded-leadership"
        elif fault == "expiration":
            next(row for row in effect["duration"]["parameters"] if row["key"] == "endpoint")[
                "value"
            ] = "turn"
        elif fault == "creation_clock":
            effect["context"]["phase"] = "movement"
        elif fault == "activation":
            effect["context"]["trigger_payload"]["result_id"] = "invented-activation"
        elif fault == "missing_creation":
            events.remove(event)
    if fault == "recorded_expiration":
        changed = 0
        for event in events:
            result = event["payload"].get("rule_execution")
            if not isinstance(result, dict):
                continue
            for effect in cast(list[dict[str, Any]], result["created_persisting_effects"]):
                if effect["source_rule_id"] == "fixture:historical-leadership":
                    effect["expiration"]["phase"] = "movement"
                    changed += 1
        assert changed == 2
    for index, event in enumerate(events, start=1):
        event["event_id"] = f"event-{index:06d}"
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, payload))


@pytest.mark.parametrize("negative_first", [True, False])
@pytest.mark.parametrize("restored", [False, True])
@pytest.mark.parametrize("through_attack", [False, True])
@pytest.mark.parametrize("attached", [False, True])
def test_generic_characteristic_deltas_are_cumulative_after_effect_deduplication(
    negative_first: bool,
    restored: bool,
    through_attack: bool,
    attached: bool,
) -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_specs=_attached_enemy_unit_specs() if attached else None,
        enemy_attachment_declarations=_attached_enemy_declarations() if attached else (),
    )
    state = _state(lifecycle)
    target = _replace_unit_toughness(
        state=state, unit=units["bodyguard-unit" if attached else "enemy"], toughness=6
    )
    target_id = (
        _attached_formation_for_player(state=state, player_id="player-b").attached_unit_instance_id
        if attached
        else target.unit_instance_id
    )
    negative = generic_effect(
        effect_id="a-negative" if negative_first else "z-negative",
        owner_player_id="player-b",
        target_unit_instance_ids=(target_id,),
        target_kind="this_unit",
        effect_kind="modify_characteristic",
        parameters={"characteristic": "toughness", "delta": -8},
    )
    positive = generic_effect(
        effect_id="z-positive" if negative_first else "a-positive",
        owner_player_id="player-b",
        target_unit_instance_ids=(target_id,),
        target_kind="this_unit",
        effect_kind="modify_characteristic",
        parameters={"characteristic": "toughness", "delta": 4},
    )
    duplicate = replace(negative, effect_id=f"{negative.effect_id}:duplicate")
    for effect in (negative, positive, duplicate):
        state.record_persisting_effect(effect)
    if restored:
        state = GameState.from_payload(
            cast(GameStatePayload, json.loads(json.dumps(state.to_payload())))
        )
    applicable = generic_rule_unit_characteristic_modifiers(
        state=state,
        unit_instance_id=target_id,
        characteristic=Characteristic.TOUGHNESS,
    )
    assert dict(applicable) == {duplicate.effect_id: -8, positive.effect_id: 4}
    assert applicable[0][1] == (-8 if negative_first else 4)
    registry = RuntimeModifierRegistry()
    if through_attack:
        value = _target_unit_toughness(
            state=state,
            target_unit_instance_id=target_id,
            runtime_modifier_registry=registry,
        )
    else:
        value = registry.modified_unit_characteristic(
            UnitCharacteristicModifierContext(
                state=state,
                unit_instance_id=target_id,
                characteristic=Characteristic.TOUGHNESS,
                base_value=6,
                current_value=6,
            )
        )
    assert value == 2


@pytest.mark.parametrize("negative_first", [True, False])
@pytest.mark.parametrize("restored", [False, True])
@pytest.mark.parametrize("movement", [False, True])
def test_generic_oc_and_movement_collect_before_bounds_and_keep_distance_separate(
    negative_first: bool,
    restored: bool,
    movement: bool,
) -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    unit = units["enemy"]
    characteristic = Characteristic.MOVEMENT if movement else Characteristic.OBJECTIVE_CONTROL
    model = unit.own_models[0]
    base = next(value for value in model.characteristics if value.characteristic is characteristic)
    for name, delta in (("negative", -(base.raw + 2)), ("positive", 4)):
        prefix = "a" if (name == "negative") == negative_first else "z"
        state.record_persisting_effect(
            generic_effect(
                effect_id=f"{prefix}-{name}",
                owner_player_id="player-b",
                target_unit_instance_ids=(unit.unit_instance_id,),
                target_kind="this_unit",
                effect_kind="modify_characteristic",
                parameters={"characteristic": characteristic.value, "delta": delta},
            )
        )
    if movement:
        for effect_id, distance_delta in (("a-distance", -4), ("z-distance", 2.5)):
            state.record_persisting_effect(
                generic_effect(
                    effect_id=effect_id,
                    owner_player_id="player-b",
                    target_unit_instance_ids=(unit.unit_instance_id,),
                    target_kind="this_unit",
                    effect_kind="modify_move_distance",
                    parameters={"delta": distance_delta},
                )
            )
    if restored:
        state = GameState.from_payload(
            cast(GameStatePayload, json.loads(json.dumps(state.to_payload())))
        )
    registry = RuntimeModifierRegistry()
    if movement:
        value, applications = registry.movement_budget_modifier_trace(
            MovementBudgetModifierContext(
                state=state,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                movement=base,
            )
        )
        assert value == 0.5
        assert len(applications) == 4
        assert {application.modifier_id for application in applications} == {
            "a-negative" if negative_first else "z-negative",
            "z-positive" if negative_first else "a-positive",
            "a-distance",
            "z-distance",
        }
        assert all(application.source_id is not None for application in applications)
        assert applications[-1].after_inches == 0.5
    else:
        assert (
            registry.modified_objective_control(
                ObjectiveControlModifierContext(
                    state=state,
                    unit_instance_id=unit.unit_instance_id,
                    model_instance_id=model.model_instance_id,
                    base_objective_control=base.raw,
                    current_objective_control=base.raw,
                )
            )
            == 2
        )


def test_movement_preserves_terminal_replacement_through_runtime_distance_effects() -> None:
    from warhammer40k_core.core.attributes import CharacteristicValueKind

    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    unit = units["enemy"]
    state.record_persisting_effect(
        generic_effect(
            effect_id="distance-bonus",
            owner_player_id="player-b",
            target_unit_instance_ids=(unit.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="modify_move_distance",
            parameters={"delta": 4},
        )
    )
    for kind in (
        CharacteristicValueKind.REPLACEMENT_ZERO,
        CharacteristicValueKind.REPLACEMENT_DASH,
        CharacteristicValueKind.REPLACEMENT_STAR,
    ):
        assert (
            RuntimeModifierRegistry().modified_movement_inches(
                MovementBudgetModifierContext(
                    state=state,
                    unit_instance_id=unit.unit_instance_id,
                    model_instance_id=unit.own_models[0].model_instance_id,
                    movement=CharacteristicValue(Characteristic.MOVEMENT, 0, 0, 0, (), kind),
                )
            )
            == 0
        )


@pytest.mark.parametrize(
    "operation", [ModifierOperation.SET, ModifierOperation.SET_DASH, ModifierOperation.SET_STAR]
)
def test_registered_replacement_retains_terminal_semantics_at_numeric_consumer(
    operation: ModifierOperation,
) -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    unit = units["enemy"]

    def replacement(context: UnitCharacteristicModifierContext) -> tuple[ModifierTerm, ...]:
        assert context.unit_instance_id == unit.unit_instance_id
        return (ModifierTerm(operation, 0),)

    registry = RuntimeModifierRegistry.from_bindings(
        unit_characteristic_modifier_bindings=(
            UnitCharacteristicModifierBinding(
                "test:replacement", "test:replacement-source", replacement
            ),
        )
    )
    state.record_persisting_effect(
        generic_effect(
            effect_id="generic-bonus",
            owner_player_id="player-b",
            target_unit_instance_ids=(unit.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="modify_characteristic",
            parameters={"characteristic": "toughness", "delta": 4},
        )
    )
    context = UnitCharacteristicModifierContext(
        state,
        unit.unit_instance_id,
        Characteristic.TOUGHNESS,
        6,
        6,
    )
    if operation is ModifierOperation.SET:
        assert registry.modified_unit_characteristic(context) == 0
    else:
        with pytest.raises(GameLifecycleError, match="symbolic replacement"):
            registry.modified_unit_characteristic(context)


@pytest.mark.parametrize("replacement_value", [0, 1])
def test_registered_oc_replacement_preserves_typed_result_and_original_source_id(
    replacement_value: int,
) -> None:
    from warhammer40k_core.core.attributes import CharacteristicValueKind

    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    unit = units["enemy"]

    def replacement(context: ObjectiveControlModifierContext) -> tuple[ModifierTerm, ...]:
        assert context.current_objective_control == 2
        return (
            ModifierTerm(ModifierOperation.SET, replacement_value),
            ModifierTerm(ModifierOperation.ADD, 4),
        )

    registry = RuntimeModifierRegistry.from_bindings(
        objective_control_modifier_bindings=(
            ObjectiveControlModifierBinding("test:oc", "test:oc-source", replacement),
        )
    )
    context = ObjectiveControlModifierContext(
        state, unit.unit_instance_id, unit.own_models[0].model_instance_id, 2, 2
    )
    source = CharacteristicValue.from_raw(Characteristic.OBJECTIVE_CONTROL, 2)
    result = registry.resolve_objective_control(context, value=source)
    assert result.raw == 2
    assert result.base == replacement_value
    assert result.final == (0 if replacement_value == 0 else 5)
    assert result.value_kind is (
        CharacteristicValueKind.REPLACEMENT_ZERO
        if replacement_value == 0
        else CharacteristicValueKind.NUMERIC
    )
    assert result.applied_modifier_ids == ("test:oc",)
    assert CharacteristicValue.from_payload(json.loads(json.dumps(result.to_payload()))) == result
    with pytest.raises(GameLifecycleError, match="typed characteristic"):
        registry.resolve_objective_control(
            context, value=CharacteristicValue.from_raw(Characteristic.TOUGHNESS, 2)
        )
    with pytest.raises(GameLifecycleError, match="context drifted"):
        registry.resolve_objective_control(context, value=replace(source, final=1))


def test_movement_trace_allows_negative_arithmetic_without_negative_budget() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    unit = units["enemy"]
    state.record_persisting_effect(
        generic_effect(
            effect_id="movement-penalty",
            owner_player_id="player-b",
            target_unit_instance_ids=(unit.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="modify_characteristic",
            parameters={"characteristic": "movement", "delta": -10},
        )
    )
    value, applications = RuntimeModifierRegistry().movement_budget_modifier_trace(
        MovementBudgetModifierContext(
            state,
            unit.unit_instance_id,
            unit.own_models[0].model_instance_id,
            CharacteristicValue(Characteristic.MOVEMENT, 4, 4, 6),
        )
    )
    assert value == 1
    assert len(applications) == 1
    assert applications[0].before_inches == 6
    assert applications[0].after_inches == -4


def test_hit_wound_and_save_consumers_keep_natural_one_separate_from_negative_modifiers() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker, target = units["intercessor-1"], units["enemy"]
    pool = _attack_pool_for_test(
        attacker=attacker,
        defender=target,
        weapon_profile=_first_weapon_profile(lifecycle, attacker),
        attacks=1,
    )
    state.record_persisting_effect(
        generic_effect(
            effect_id="hit-penalty",
            owner_player_id="player-b",
            target_unit_instance_ids=(target.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="modify_dice_roll",
            parameters={"roll_type": "hit", "delta": -10},
        )
    )
    hit_spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=pool.weapon_profile_id,
        attack_context_id="limits-hit",
        attacker_player_id="player-a",
    )
    wound_spec = attack_sequence_wound_roll_spec(
        weapon_profile_id=pool.weapon_profile_id,
        attack_context_id="limits-wound",
        attacker_player_id="player-a",
    )
    hit_manager = DiceRollManager(
        "hit",
        injected_results=(
            DiceRollResult.from_values(
                roll_id="roll-000001", spec=hit_spec, values=(1,), source="rng"
            ),
        ),
    )
    wound_manager = DiceRollManager(
        "wound",
        injected_results=(
            DiceRollResult.from_values(
                roll_id="roll-000001", spec=wound_spec, values=(1,), source="rng"
            ),
        ),
    )
    hit = _roll_hit(
        state=state,
        manager=hit_manager,
        pool=pool,
        attacker_player_id="player-a",
        attack_context_id="limits-hit",
        source_phase=BattlePhase.SHOOTING,
    )
    wound = _roll_wound(
        manager=wound_manager,
        pool=pool,
        toughness=4,
        attacker_player_id="player-a",
        attack_context_id="limits-wound",
        critical_threshold=6,
        wound_modifier=-10,
    )
    for result in (hit, wound):
        assert result.unmodified_roll == 1
        assert result.capped_modifier == -1
        assert result.final_roll == 1
        assert not result.successful
    assert HitRoll.from_payload(hit.to_payload()) == hit
    assert json.loads(json.dumps(wound.to_payload()))["final_roll"] == 1
    assert hit.roll_state is not None
    save = resolve_saving_throw(
        option=SaveOption(
            save_kind=SaveKind.ARMOUR,
            target_number=6,
            characteristic_target_number=3,
            armor_penetration=-3,
        ),
        roll_state=hit.roll_state,
    )
    assert save.unmodified_roll == save.final_roll == 1
    assert not save.successful


def test_modifier_source_artifact_matches_reviewed_evidence_and_rejects_drift() -> None:
    from tools.build_core_modifiers_source import ARTIFACT_PATH, AUDIT_PATH, build_payloads

    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_modifiers_2026_09 as source,
    )

    payload, audit = build_payloads()
    assert json.loads(ARTIFACT_PATH.read_bytes()) == payload
    assert json.loads(AUDIT_PATH.read_bytes()) == audit
    package = source.source_package()
    assert len(source.source_rules()) == 3
    for rule in source.source_rules():
        assert rule.source_id in package.evidence_required_source_ids
        assert package.source_catalog.source_text_by_id(rule.source_id).raw_text == rule.source_text
        assert rule.load_support_status == "loaded"
        assert rule.semantic_execution_status == "executable_engine_runtime"
        assert rule.runtime_consumer_ids
    with pytest.raises(source.CoreModifiersSourceError, match="reviewed pin"):
        source.validate_source_artifact_bytes(ARTIFACT_PATH.read_bytes() + b"\n")


@pytest.mark.parametrize("delta", [-100, 2])
def test_random_damage_preserves_intrinsic_expression_and_modified_event(delta: int) -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker, target = units["intercessor-1"], units["enemy"]
    profile = _first_weapon_profile(lifecycle, attacker)
    state.record_persisting_effect(
        generic_effect(
            effect_id="damage-modifier",
            owner_player_id="player-a",
            target_unit_instance_ids=(target.unit_instance_id,),
            target_kind="selected_target",
            effect_kind="modify_dice_roll",
            parameters={"roll_type": "damage", "delta": delta, "attack_role": "target"},
        )
    )
    value, status = _damage_value(
        state=state,
        decisions=lifecycle.decision_controller,
        manager=DiceRollManager("order27-damage"),
        profile=DamageProfile.dice(DiceExpression(quantity=1, sides=6, modifier=1)),
        attack_context_id="attack:damage",
        attacker_player_id="player-a",
        affected_unit_instance_id=attacker.unit_instance_id,
        attacking_unit_instance_id=attacker.unit_instance_id,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        target_unit_instance_id=target.unit_instance_id,
        weapon_profile=profile,
        source_phase=BattlePhase.SHOOTING,
        stratagem_index=None,
    )
    assert status is None
    event = lifecycle.decision_controller.event_log.records[-1]
    assert event.event_type == "random_characteristic_rolled"
    assert isinstance(event.payload, dict)
    trace = ModifiedRollResult.from_payload(
        cast(ModifiedRollResultPayload, event.payload["modified_roll"])
    )
    assert trace.intrinsic_offset == 1
    assert event.payload["value"] == trace.unmodified.value + 1
    assert trace.unbounded_value == trace.unmodified.value + 1 + delta
    assert value == trace.final_value == max(1, trace.unbounded_value)


@pytest.mark.parametrize(("delta", "expected"), [(100, 12), (-100, 1)])
def test_charge_limits_reach_facade_events_restore_and_exact_replay(
    delta: int, expected: int
) -> None:
    lifecycle, units = charge_lifecycle(
        alpha_unit_ids=("charger",),
        enemy_model_poses=compact_test_unit_poses(origin=Pose.at(20, 20), model_count=5),
        game_id=f"order27-charge-{delta}",
    )
    state = lifecycle.state
    assert state is not None
    unit_id = units["charger"].unit_instance_id
    # A real, serialized generic effect exercises the production collection path.
    state.record_persisting_effect(
        PersistingEffect(
            effect_id="fixture:charge-modifier",
            source_rule_id="fixture:charge-source",
            owner_player_id="player-a",
            target_unit_instance_ids=(unit_id,),
            started_battle_round=1,
            started_phase=None,
            expiration=EffectExpiration.end_of_battle(),
            effect_payload={
                "effect_kind": GENERIC_RULE_IR_CHARGE_ROLL_MODIFIER_EFFECT_KIND,
                "source_rule_id": "fixture:charge-source",
                "stratagem_id": "fixture:charge-stratagem",
                "stratagem_use_id": "fixture:charge-use",
                "target_unit_instance_id": unit_id,
                "roll_type": "charge",
                "delta": delta,
                "generic_rule_execution_result": {"status": "applied"},
                "generic_rule_effect": {"roll_type": "charge", "delta": delta},
            },
        )
    )
    session = LocalGameSession(lifecycle=lifecycle)
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    session.submit_option(
        request_id=request.request_id, option_id=unit_id, result_id="select-charger"
    )
    event = next(
        e
        for e in lifecycle.decision_controller.event_log.records
        if e.event_type == "charge_roll_resolved"
    )
    assert isinstance(event.payload, dict)
    payload = cast(ChargeRollResultPayload, event.payload["roll_result"])
    roll = ChargeRollResult.from_payload(payload)
    trace = roll.request.resolve_roll(roll.roll_state)
    assert roll.request.spec.expression.modifier == 0
    assert trace.unmodified.value == sum(roll.roll_state.current_values)
    assert trace.unbounded_value == trace.unmodified.value + delta
    assert trace.modified_value == max(1, trace.unbounded_value)
    assert trace.final_value == roll.value == expected
    assert trace.applied_modifier_ids == ("fixture:charge-modifier",)
    assert event.payload["maximum_distance_inches"] == expected
    for viewer in ("player-a", "player-b"):
        projected = session.events_since(EventStreamCursor(), viewer_player_id=viewer)
        public = next(e for e in projected["events"] if e["event_type"] == "charge_roll_resolved")
        assert public["payload"] == event.to_payload()["payload"]
    checkpoint = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    assert restored.to_persistence_payload() == checkpoint
    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="order27-charge-replay")
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED
    drifted = cast(ChargeRollResultPayload, json.loads(json.dumps(payload)))
    drifted["modified_roll"]["final_value"] += 1
    with pytest.raises(ValueError, match="modif"):
        ChargeRollResult.from_payload(drifted)
    drifted = cast(ChargeRollResultPayload, json.loads(json.dumps(payload)))
    drifted["value"] += 1
    with pytest.raises(GameLifecycleError, match="bounded modified"):
        ChargeRollResult.from_payload(drifted)
    if expected == 1:
        with pytest.raises(GameLifecycleError, match="bounded modified"):
            replace(roll, value=True)


@pytest.mark.parametrize(("delta", "expected"), [(10, 16), (-10, 1)])
def test_advance_retains_raw_dice_and_has_no_six_result_cap(delta: int, expected: int) -> None:
    request = AdvanceRollRequest.for_unit(
        request_id="advance-request",
        game_id="order27-advance",
        battle_round=1,
        player_id="player-a",
        unit_instance_id="army:unit",
        roll_modifiers=(RollModifier("advance-effect", delta),),
    )
    state = DiceRollState.from_result(
        DiceRollResult.from_values(
            roll_id="advance-die",
            spec=request.spec,
            values=(6,),
            source="fixed",
        )
    )
    result = AdvanceRollResult.from_roll_state(request=request, roll_state=state)
    assert state.current_total == 6
    assert result.modified_roll.unbounded_value == 6 + delta
    assert result.value == expected
    assert AdvanceRollResult.from_payload(result.to_payload()) == result
    if expected == 1:
        with pytest.raises(GameLifecycleError, match="bounded modifier"):
            replace(result, value=True)


@pytest.mark.parametrize(
    ("base_range", "bonus", "target_x", "expected"),
    [
        (1.0, 0, 19.4, True),
        (1.0, 0, 21.0, False),
        (100.0, 0, 39.0, True),
        (100.0, 0, 43.0, False),
        (1.0, 20, 29.0, True),
        (1.0, 20, 35.0, False),
    ],
)
def test_hidden_detection_uses_the_shared_terminal_range(
    base_range: float,
    bonus: int,
    target_x: float,
    expected: bool,
) -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_pose=Pose.at(target_x, 35),
    )
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions), battlefield_state=state.battlefield_state
    )
    attacker, target = units["intercessor-1"], units["enemy"]
    ruleset = _ruleset()
    ruleset = replace(
        ruleset,
        descriptor_hash="",
        terrain_visibility_policy=replace(
            ruleset.terrain_visibility_policy,
            hidden_detection_range_inches=base_range,
        ),
    )
    profile = replace(
        _first_weapon_profile(lifecycle, attacker), range_profile=RangeProfile.distance(100)
    )
    candidate = shooting_target_candidate_for_model(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        attacker_unit=attacker,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        weapon_profile=profile,
        target_unit_id=target.unit_instance_id,
        hidden_target_model_ids=tuple(m.model_instance_id for m in target.own_models),
        target_detection_range_bonus_inches=bonus,
    )
    assert candidate.is_legal is expected
    if not expected:
        assert candidate.violation_code is ShootingTargetViolationCode.OUTSIDE_DETECTION_RANGE


@pytest.mark.parametrize(
    ("range_inches", "target_x", "expected"),
    [
        (1.0, 19.4, True),
        (1.0, 21.0, False),
        (100.0, 39.0, True),
        (100.0, 43.0, False),
    ],
)
def test_lone_operative_uses_the_same_terminal_range(
    range_inches: float,
    target_x: float,
    expected: bool,
) -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",), enemy_pose=Pose.at(target_x, 35)
    )
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions), battlefield_state=state.battlefield_state
    )
    attacker, target = units["intercessor-1"], units["enemy"]
    view = rules_unit_view_from_armies(
        armies=scenario.armies, unit_instance_id=target.unit_instance_id
    )
    assert (
        lone_operative_target_allowed(
            scenario=scenario,
            attacker_unit=attacker,
            attacker_model_instance_id=attacker.own_models[0].model_instance_id,
            target_rules_unit=view,
            profile=LoneOperativeAbilityProfile(
                source_id="fixture:lone-operative", range_inches=range_inches
            ),
        )
        is expected
    )
