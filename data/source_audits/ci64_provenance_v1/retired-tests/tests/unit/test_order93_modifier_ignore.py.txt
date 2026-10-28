from __future__ import annotations

from dataclasses import replace

import pytest

from warhammer40k_core.core.attributes import (
    Characteristic,
    CharacteristicError,
    CharacteristicValue,
)
from warhammer40k_core.core.count_profiles import AttackProfile, DamageProfile
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.modifiers import ModifierOperation, ModifierTerm
from warhammer40k_core.engine.profile_modifiers import profile_with_delta


def test_fixed_profile_keeps_opposing_source_operations_and_original_value() -> None:
    original = CharacteristicValue.from_raw(Characteristic.STRENGTH, 4)
    improved = profile_with_delta(
        original, 2, source_id="source:bonus", modifier_id="bonus:S", bound_numeric=True
    )
    modified = profile_with_delta(
        improved, -2, source_id="source:penalty", modifier_id="penalty:S", bound_numeric=True
    )
    assert isinstance(modified, CharacteristicValue)
    assert modified.raw == 4
    assert modified.final == 4
    assert modified.applied_modifier_ids == ("bonus:S", "penalty:S")
    trace = modified.modifier_trace
    assert trace is not None
    assert tuple(item.source_id for item in trace.modifiers) == ("source:bonus", "source:penalty")
    assert trace.resolve(ignored_modifier_ids=("penalty:S",)).final == 6
    assert trace.resolve(ignored_modifier_ids=("bonus:S",)).final == 2
    assert trace.resolve(ignored_modifier_ids=("bonus:S", "penalty:S")).final == 4
    assert CharacteristicValue.from_payload(modified.to_payload()) == modified


def test_fixed_profile_bounds_only_after_selected_operations() -> None:
    original = CharacteristicValue.from_raw(Characteristic.STRENGTH, 2)
    penalized = profile_with_delta(
        original, -3, source_id="source:penalty", modifier_id="penalty:S", bound_numeric=True
    )
    modified = profile_with_delta(
        penalized, 2, source_id="source:bonus", modifier_id="bonus:S", bound_numeric=True
    )
    assert modified.final == 1
    assert isinstance(modified, CharacteristicValue)
    assert modified.modifier_trace is not None
    assert modified.modifier_trace.resolve(ignored_modifier_ids=("penalty:S",)).final == 4


def test_fixed_profile_trace_rejects_arithmetic_and_selection_drift() -> None:
    modified = profile_with_delta(
        CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
        2,
        source_id="source:bonus",
        modifier_id="bonus:S",
        bound_numeric=True,
    )
    assert isinstance(modified, CharacteristicValue)
    with pytest.raises(CharacteristicError, match="trace"):
        replace(modified, final=9)
    trace = modified.modifier_trace
    assert trace is not None
    with pytest.raises(CharacteristicError, match="unknown"):
        trace.resolve(ignored_modifier_ids=("invented",))
    with pytest.raises(CharacteristicError, match="duplicated"):
        trace.resolve(ignored_modifier_ids=("bonus:S", "bonus:S"))


@pytest.mark.parametrize("profile_type", [AttackProfile, DamageProfile])
@pytest.mark.parametrize("random", [False, True])
def test_count_profiles_keep_raw_dice_and_individual_modifiers(
    profile_type: type[AttackProfile] | type[DamageProfile], random: bool
) -> None:
    characteristic = (
        Characteristic.ATTACKS if profile_type is AttackProfile else Characteristic.DAMAGE
    )
    profile = (
        profile_type.dice(DiceExpression(quantity=1, sides=6, modifier=1))
        if random
        else profile_type.fixed(2)
    )
    penalty = ModifierTerm(ModifierOperation.ADD, -3).bind(
        modifier_id="penalty", source_id="source:penalty", characteristic=characteristic
    )
    bonus = ModifierTerm(ModifierOperation.ADD, 2).bind(
        modifier_id="bonus", source_id="source:bonus", characteristic=characteristic
    )
    modified = profile.with_modifier(penalty).with_modifier(bonus)
    assert modified.dice_expression == profile.dice_expression
    assert modified.resolve_value(2) == 1
    assert modified.resolve_value(2, ignored_modifier_ids=("penalty",)) == 4
    if isinstance(modified, AttackProfile):
        assert AttackProfile.from_payload(modified.to_payload()) == modified
    else:
        assert DamageProfile.from_payload(modified.to_payload()) == modified


def test_general_hit_modifier_choice_uses_session_and_replays() -> None:
    from tests.order93_modifier_helpers import modifier_session, reach_modifier_request

    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session = modifier_session()
    request = reach_modifier_request(session)
    assert request.decision_type == "select_modifier_ignores"
    assert isinstance(request.payload, dict)
    assert isinstance(request.payload["subject"], dict)
    assert request.payload["subject"]["kind"] in {"hit_roll", "ballistic_skill_characteristic"}
    before = GameLifecycle.from_payload(session.lifecycle.to_payload())
    assert before.to_payload() == session.lifecycle.to_payload()
    status = session.submit_option(
        request_id=request.request_id,
        result_id=f"{request.request_id}:ignore",
        option_id="ignore-remaining",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    restored = GameLifecycle.from_payload(session.lifecycle.to_payload())
    assert restored.to_payload() == session.lifecycle.to_payload()


@pytest.mark.parametrize("phase", ["shooting", "fight"])
def test_general_modifier_linear_subsets_cap_only_after_choice_and_hide_evidence(
    phase: str,
) -> None:
    from typing import cast

    from tests.order93_modifier_helpers import modifier_session, reach_modifier_request
    from tests.psychic_modifier_helpers import pending_request

    from warhammer40k_core.engine.event_log import JsonValue, canonical_json
    from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
    from warhammer40k_core.engine.replay import ReplayRunner

    session = modifier_session(BattlePhase(phase))
    request = reach_modifier_request(session)
    choices = 0
    for _ in range(25):
        if request.decision_type == "select_modifier_ignores":
            payload = cast(dict[str, JsonValue], request.payload)
            subject = cast(dict[str, JsonValue], payload["subject"])
            assert len(request.options) <= 4
            inventory = cast(list[dict[str, JsonValue]], payload["modifiers"])
            decided = cast(list[str], payload["decided_modifier_ids"])
            operation = cast(dict[str, JsonValue], inventory[len(decided)]["operation"])
            # Ignore positive Hit modifiers, keep all skill modifiers.
            ignore = subject["kind"] == "hit_roll" and cast(int, operation["operand"]) > 0
            prefix = "ignore:" if ignore else "keep:"
            option = next(
                (option for option in request.options if option.option_id.startswith(prefix)), None
            )
            if option is None:
                option = next(
                    option
                    for option in request.options
                    if option.option_id == ("ignore-remaining" if ignore else "keep-remaining")
                )
            opponent = "player-b" if request.actor_id == "player-a" else "player-a"
            assert "source_context" not in canonical_json(session.view(viewer_player_id=opponent))
            choices += 1
        else:
            option = next(
                (
                    option
                    for option in request.options
                    if "decline" in option.option_id or "keep" in option.option_id
                ),
                request.options[0],
            )
        status = session.submit_option(
            request_id=request.request_id,
            result_id=f"{request.request_id}:chosen",
            option_id=option.option_id,
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
        hits = [
            event.payload
            for event in session.lifecycle.decision_controller.event_log.records
            if event.event_type == "attack_sequence_step"
            and isinstance(event.payload, dict)
            and event.payload.get("step") == "hit"
        ]
        if hits:
            hit = cast(dict[str, JsonValue], hits[0]["payload"])
            assert hit["modifier"] == -2
            assert hit["capped_modifier"] == -1
            break
        request = pending_request(session)
    else:
        raise AssertionError("No hit after modifier choices.")
    assert choices == 4
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id=f"modifier-{phase}"))
        .run()
        .reproduced_exactly
    )


def test_charge_subsets_over_ten_modifiers_restore_and_replay_without_option_explosion() -> None:
    from typing import cast

    from tests.order93_movement_helpers import (
        finish_modifier_choices,
        movement_modifier_session,
        start_modifier_action,
    )

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.event_log import JsonValue
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.replay import ReplayRunner

    session = movement_modifier_session(BattlePhase.CHARGE, extra_charge_modifiers=11)
    request = start_modifier_action(session)
    assert isinstance(request.payload, dict)
    assert len(cast(list[JsonValue], request.payload["modifiers"])) == 13
    assert len(request.options) == 4
    session = LocalGameSession.from_persistence_payload(session.to_persistence_payload())
    ignored = tuple(f"test:modifier-ignore:charge-extra-{index:02d}" for index in range(0, 11, 2))
    finish_modifier_choices(session, ignored)
    record = session.lifecycle.decision_controller.records[-1]
    assert record.request.decision_type == "select_modifier_ignores"
    assert isinstance(record.result.payload, dict)
    assert record.result.payload["ignored_modifier_ids"] == list(ignored)
    assert (
        GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
        == session.lifecycle.to_payload()
    )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="many-modifiers"))
        .run()
        .reproduced_exactly
    )


@pytest.mark.parametrize("profile_type", [AttackProfile, DamageProfile])
def test_count_profile_loader_rejects_noncanonical_modifier_metadata(
    profile_type: type[AttackProfile] | type[DamageProfile],
) -> None:
    from typing import Any, cast

    from warhammer40k_core.core.weapon_profile_errors import WeaponProfileError

    payload = dict(profile_type.fixed(2).to_payload())
    with pytest.raises(WeaponProfileError, match="fields"):
        profile_type.from_payload(cast(Any, {**payload, "ignored_modifier_ids": []}))
    with pytest.raises(WeaponProfileError, match="fields"):
        profile_type.from_payload(cast(Any, {**payload, "invented": 1}))
    with pytest.raises(WeaponProfileError, match="source operations"):
        profile_type.from_payload(
            cast(
                Any,
                {**payload, "source_fixed_value": 2, "modifiers": [], "ignored_modifier_ids": []},
            )
        )


def test_random_movement_selection_keeps_raw_roll_and_operation_inventory() -> None:
    from tests.order93_movement_helpers import (
        UNIT_ID,
        finish_modifier_choices,
        movement_modifier_session,
        start_modifier_action,
    )

    from warhammer40k_core.core.random_profile_values import RandomProfileValue
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.movement_budget_modifiers import (
        MovementBudgetModifierContext,
        model_movement_characteristic,
    )
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.replay import ReplayRunner
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

    session = movement_modifier_session(BattlePhase.MOVEMENT, random_movement=True)
    start_modifier_action(session)
    finish_modifier_choices(session, ("test:modifier-ignore:movement-penalty",))
    state = session.lifecycle.state
    assert state is not None
    model = next(
        model
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == UNIT_ID
        for model in unit.own_models
    )
    value = model_movement_characteristic(model)
    assert isinstance(value, RandomProfileValue)
    assert (
        RuntimeModifierRegistry.empty().modified_movement_inches(
            MovementBudgetModifierContext(state, UNIT_ID, model.model_instance_id, value)
        )
        == value.raw
    )
    assert (
        GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
        == session.lifecycle.to_payload()
    )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="random-movement-modifiers"))
        .run()
        .reproduced_exactly
    )


def test_resolved_save_events_redact_source_inventory_but_preserve_public_resolution() -> None:
    import json

    from tests.order93_save_damage_helpers import reach_save_damage_request, save_damage_session

    from warhammer40k_core.adapters.access_control import AuthenticatedPrincipal, PrincipalRole
    from warhammer40k_core.adapters.event_stream import EventStreamCursor
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session = save_damage_session()
    request = reach_save_damage_request(session, kind="damage_characteristic")
    status = session.submit_option(
        request_id=request.request_id,
        result_id="save-public-resolution",
        option_id="keep-remaining",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    private = session.events_since_for_context(
        EventStreamCursor(),
        viewer=AuthenticatedPrincipal(
            principal_id="order93-admin", role=PrincipalRole.ADMINISTRATOR
        ).bind_to_session(player_ids=("player-a", "player-b")),
    )
    private_json = json.dumps(private, sort_keys=True)
    assert '"characteristic_trace"' in private_json
    assert '"armor_penetration_trace"' in private_json
    for player in ("player-a", "player-b"):
        public = session.events_since(EventStreamCursor(), viewer_player_id=player)
        public_json = json.dumps(public, sort_keys=True)
        assert '"attack_sequence_step"' in public_json
        assert '"save_roll"' in public_json
        assert '"target_number"' in public_json
        for field in (
            "characteristic_trace",
            "armor_penetration_trace",
            "inherent_roll_modifiers",
            "ignored_roll_modifier_ids",
        ):
            assert f'"{field}"' not in public_json
        assert '"attack_save_modifiers_prepared"' not in public_json


@pytest.mark.parametrize("with_runtime_operation", [False, True])
def test_objective_control_runtime_keeps_profile_source_before_final_bound(
    with_runtime_operation: bool,
) -> None:
    from tests.phase11c_command_phase_helpers import battle_state

    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.runtime_characteristic_modifiers import (
        resolve_runtime_objective_control,
    )
    from warhammer40k_core.engine.runtime_modifiers import (
        ObjectiveControlModifierBinding,
        ObjectiveControlModifierContext,
    )

    state = battle_state(decisions=DecisionController())
    unit = state.army_definitions[0].units[0]
    value = profile_with_delta(
        CharacteristicValue.from_raw(Characteristic.OBJECTIVE_CONTROL, 2),
        -3,
        source_id="source:oc-penalty",
        modifier_id="oc:penalty",
        bound_numeric=True,
    )
    assert isinstance(value, CharacteristicValue)
    context = ObjectiveControlModifierContext(
        state=state,
        unit_instance_id=unit.unit_instance_id,
        model_instance_id=unit.own_models[0].model_instance_id,
        base_objective_control=2,
        current_objective_control=value.final,
    )

    def bonus(_context: ObjectiveControlModifierContext) -> tuple[ModifierTerm, ...]:
        return (ModifierTerm(ModifierOperation.ADD, 2),)

    result = resolve_runtime_objective_control(
        context=context,
        value=value,
        bindings=(ObjectiveControlModifierBinding("oc:bonus", "source:oc-bonus", bonus),)
        if with_runtime_operation
        else (),
    )
    assert result.modifier_trace is not None
    assert result.modifier_trace.source_value == 2
    if with_runtime_operation:
        assert result.final == 1
        assert tuple(item.modifier_id for item in result.modifier_trace.modifiers) == (
            "oc:penalty",
            "oc:bonus",
        )
        assert result.modifier_trace.resolve(ignored_modifier_ids=("oc:penalty",)).final == 4
    else:
        assert result is value
    assert CharacteristicValue.from_payload(result.to_payload()) == result


@pytest.mark.parametrize("profile_type", [AttackProfile, DamageProfile])
def test_count_profile_rejects_unknown_nested_operation_fields(
    profile_type: type[AttackProfile] | type[DamageProfile],
) -> None:
    from typing import Any, cast

    operation = ModifierTerm(ModifierOperation.ADD, 1).bind(
        modifier_id="count:bonus",
        source_id="source:count-bonus",
        characteristic=(
            Characteristic.ATTACKS if profile_type is AttackProfile else Characteristic.DAMAGE
        ),
    )
    payload = profile_type.fixed(2).with_modifier(operation).to_payload()
    assert "modifiers" in payload
    cast(dict[str, object], payload["modifiers"][0]["scope"])["invented"] = True
    with pytest.raises(CharacteristicError, match="scope fields"):
        profile_type.from_payload(cast(Any, payload))


def test_absent_modifier_evidence_preserves_rng_but_actual_operations_remain_bound() -> None:
    from warhammer40k_core.engine.decision import (
        _rng_payload_history_token,  # pyright: ignore[reportPrivateUsage]
    )
    from warhammer40k_core.engine.event_log import JsonValue

    original: JsonValue = {"contributors": [{"model_instance_id": "model-a", "raw": 2}]}
    absent: JsonValue = {
        "contributors": [{"model_instance_id": "model-a", "raw": 2, "modifier_trace": None}]
    }
    assert _rng_payload_history_token(absent) == _rng_payload_history_token(original)
    traced = profile_with_delta(
        CharacteristicValue.from_raw(Characteristic.OBJECTIVE_CONTROL, 2),
        1,
        source_id="source:oc-bonus",
        bound_numeric=True,
    )
    assert isinstance(traced, CharacteristicValue)
    trace = traced.modifier_trace
    assert trace is not None
    from warhammer40k_core.engine.event_log import validate_json_value

    actual = validate_json_value(
        {
            "contributors": [
                {"model_instance_id": "model-a", "raw": 2, "modifier_trace": trace.to_payload()}
            ]
        }
    )
    assert _rng_payload_history_token(actual) != _rng_payload_history_token(original)
    ignored = validate_json_value(
        {
            "contributors": [
                {
                    "model_instance_id": "model-a",
                    "raw": 2,
                    "modifier_trace": replace(
                        trace, ignored_modifier_ids=(trace.modifiers[0].modifier_id,)
                    ).to_payload(),
                }
            ]
        }
    )
    assert _rng_payload_history_token(ignored) != _rng_payload_history_token(actual)


@pytest.mark.parametrize(
    "operation", [ModifierOperation.SET, ModifierOperation.SET_DASH, ModifierOperation.SET_STAR]
)
def test_movement_source_replacement_stays_terminal_until_its_operation_is_ignored(
    operation: ModifierOperation,
) -> None:
    from tests.generic_modifier_helpers import generic_effect
    from tests.phase13b_shooting_declaration_helpers import _shooting_lifecycle

    from warhammer40k_core.core.profile_modifier_trace import CharacteristicModifierTrace
    from warhammer40k_core.engine.movement_budget_modifiers import (
        MovementBudgetModifierContext,
        generic_rule_movement_modifier_trace,
    )

    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = lifecycle.state
    assert state is not None
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
    replacement = ModifierTerm(operation, 0).bind(
        modifier_id="movement-lock",
        source_id="source:movement-lock",
        characteristic=Characteristic.MOVEMENT,
    )
    context = MovementBudgetModifierContext(
        state=state,
        unit_instance_id=unit.unit_instance_id,
        model_instance_id=unit.own_models[0].model_instance_id,
        movement=CharacteristicModifierTrace(Characteristic.MOVEMENT, 6, (replacement,)).value(),
    )
    assert generic_rule_movement_modifier_trace(context)[0] == 0
    assert (
        generic_rule_movement_modifier_trace(
            context, ignored_modifier_ids=frozenset((replacement.modifier_id,))
        )[0]
        == 10
    )


def test_save_audit_preserves_rng_but_operations_and_choices_remain_bound() -> None:
    from warhammer40k_core.core.modifiers import RollModifier
    from warhammer40k_core.engine.decision import (
        _rng_payload_history_token,  # pyright: ignore[reportPrivateUsage]
    )
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.save_modifier_operations import (
        save_option_ignoring_modifiers,
        save_option_with_characteristic_terms,
        save_option_with_roll_modifier,
    )
    from warhammer40k_core.engine.saves import SaveKind, SaveOption

    option = SaveOption(SaveKind.ARMOUR, 5, 3, -2)
    payload = validate_json_value(option.to_payload())
    assert isinstance(payload, dict)
    gameplay = {
        key: value
        for key, value in payload.items()
        if key
        not in (
            "characteristic_trace",
            "armor_penetration_trace",
            "roll_modifiers",
            "inherent_roll_modifiers",
            "ignored_roll_modifier_ids",
        )
    }
    original = _rng_payload_history_token(gameplay)
    assert _rng_payload_history_token(payload) == original
    variants = (
        save_option_with_characteristic_terms(
            option,
            characteristic=Characteristic.SAVE,
            terms=(ModifierTerm(ModifierOperation.ADD, -1),),
            source_id="source:save-bonus",
            modifier_id="save-bonus",
        ),
        save_option_with_characteristic_terms(
            option,
            characteristic=Characteristic.ARMOR_PENETRATION,
            terms=(ModifierTerm(ModifierOperation.ADD, -1),),
            source_id="source:ap-bonus",
            modifier_id="ap-bonus",
        ),
        save_option_with_roll_modifier(
            option, RollModifier("save-roll-bonus", 1, source_id="source:save-roll-bonus")
        ),
        save_option_ignoring_modifiers(option, (option.inherent_roll_modifiers[0].modifier_id,)),
    )
    evidence_keys = (
        "characteristic_trace",
        "armor_penetration_trace",
        "roll_modifiers",
        "ignored_roll_modifier_ids",
    )
    for variant, evidence_key in zip(variants, evidence_keys, strict=True):
        evidence = validate_json_value(variant.to_payload())
        assert isinstance(evidence, dict)
        # Compare identical gameplay fields so evidence itself must bind the stream.
        without_evidence = {key: value for key, value in evidence.items() if key != evidence_key}
        assert _rng_payload_history_token(evidence) != _rng_payload_history_token(without_evidence)


def test_random_profile_redundant_raw_is_rng_neutral_but_symbolic_source_is_bound() -> None:
    from warhammer40k_core.core.random_profile_values import RandomProfileValue
    from warhammer40k_core.engine.decision import (
        _rng_payload_history_token,  # pyright: ignore[reportPrivateUsage]
    )
    from warhammer40k_core.engine.event_log import validate_json_value

    random = RandomProfileValue(Characteristic.MOVEMENT, DiceExpression(1, 6), "source:random")
    numeric = random.evaluate(raw=4, evaluation_id="roll:one", target_id="model:one")
    payload = validate_json_value(numeric.to_payload())
    assert isinstance(payload, dict)
    assert payload["evaluation_raw"] == 4
    without_redundant_raw = {
        key: value for key, value in payload.items() if key != "evaluation_raw"
    }
    assert _rng_payload_history_token(payload) == _rng_payload_history_token(without_redundant_raw)
    replaced = replace(
        random,
        modifiers=(
            ModifierTerm(ModifierOperation.SET_DASH, 0).bind(
                modifier_id="lock",
                source_id="source:lock",
                characteristic=Characteristic.MOVEMENT,
            ),
        ),
    )
    first = replaced.evaluate(raw=4, evaluation_id="roll:one", target_id="model:one")
    second = replaced.evaluate(raw=5, evaluation_id="roll:one", target_id="model:one")
    assert first.resolved_value() == second.resolved_value()
    assert _rng_payload_history_token(validate_json_value(first.to_payload())) != (
        _rng_payload_history_token(validate_json_value(second.to_payload()))
    )
