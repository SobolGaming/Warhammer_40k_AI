from typing import Any, cast

from tests.shared.category_migration.generic_rule_effect_identity import (
    BattlePhase,
    EventLog,
    GameLifecycleError,
    ObjectiveRuleScope,
    Pose,
    RuleClause,
    RuleExecutionContext,
    RuleExecutionStatus,
    RuleIR,
    RuleSourceText,
    _scene,
    compile_rule_source_text,
    execute_rule_ir,
    fight_lifecycle,
    generic_rule_persisting_effect_id,
    keyword_source,
    pytest,
    replace,
)


@pytest.mark.parametrize("change", ["owner", "activation", "binding"])
def test_separate_generic_activations_and_bindings_coexist(change: str) -> None:
    rule_ir, context = _scene()
    first = execute_rule_ir(rule_ir=rule_ir, context=context)
    if change == "owner":
        second_context = replace(
            context,
            player_id="player-b",
            source_unit_instance_id="army-beta:enemy",
            source_model_instance_id="army-beta:enemy:core-character-leader:001",
            target_unit_instance_ids=("army-beta:enemy",),
            target_player_id="player-b",
        )
    elif change == "activation":
        second_context = replace(
            context,
            timing_window_id="order42:second-activation",
            trigger_payload={"decision_result_id": "order42:second-result"},
        )
    else:
        second_context = replace(context, target_unit_instance_ids=("army-alpha:second",))
    second = execute_rule_ir(rule_ir=rule_ir, context=second_context)
    assert first.status is RuleExecutionStatus.APPLIED
    assert second.status is RuleExecutionStatus.APPLIED
    first_effect = first.created_persisting_effects[0]
    second_effect = second.created_persisting_effects[0]
    assert first_effect.effect_id != second_effect.effect_id
    assert first_effect.expiration == second_effect.expiration
    state = context.state
    assert state is not None
    assert state.persisting_effects == sorted(
        [first_effect, second_effect], key=lambda effect: effect.effect_id
    )
    before = state.to_payload()
    with pytest.raises(GameLifecycleError, match="already exists for effect_id"):
        execute_rule_ir(rule_ir=rule_ir, context=second_context)
    assert state.to_payload() == before


@pytest.mark.parametrize("shared_object", [False, True])
def test_identical_effect_slots_have_separate_persisted_identities(shared_object: bool) -> None:
    rule_ir, context = _scene()
    clause = rule_ir.clauses[0]
    effect = clause.effects[0]
    repeated = effect if shared_object else replace(effect)
    rule_ir = replace(rule_ir, clauses=(replace(clause, effects=(effect, repeated)),))
    result = execute_rule_ir(rule_ir=rule_ir, context=context)
    assert result.status is RuleExecutionStatus.APPLIED
    assert len(result.created_persisting_effects) == 2
    assert len({effect.effect_id for effect in result.created_persisting_effects}) == 2
    assert [payload["effect_index"] for payload in result.effect_payloads] == [0, 1]
    restored_ir = RuleIR.from_payload(rule_ir.to_payload())
    _, fresh = _scene()
    replayed = execute_rule_ir(rule_ir=restored_ir, context=fresh)
    assert replayed.to_payload() == result.to_payload()


def test_full_clause_identity_distinguishes_equal_suffixes() -> None:
    rule_ir, context = _scene()
    clause = rule_ir.clauses[0]
    rule_ir = replace(
        rule_ir,
        clauses=(
            replace(clause, clause_id="order42:first:grant"),
            replace(clause, clause_id="order42:second:grant"),
        ),
    )
    result = execute_rule_ir(rule_ir=rule_ir, context=context)
    assert result.status is RuleExecutionStatus.APPLIED
    assert len({effect.effect_id for effect in result.created_persisting_effects}) == 2


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("game_id", "another-game"),
        ("player_id", "player-b"),
        ("battle_round", 2),
        ("phase", BattlePhase.SHOOTING),
        ("active_player_id", "player-b"),
        ("timing_window_id", "another-window"),
        ("source_unit_instance_id", "army-alpha:second"),
        ("source_model_instance_id", "army-alpha:second:core-character-leader:001"),
        ("target_unit_instance_ids", ("army-alpha:second",)),
        ("target_player_id", "player-b"),
        ("trigger_payload", {"decision_result_id": "another-recorded-activation"}),
    ],
)
def test_identity_binds_recorded_activation_context(field: str, value: object) -> None:
    rule_ir, context = _scene()

    def derive(current: RuleExecutionContext) -> str:
        return generic_rule_persisting_effect_id(
            rule_ir=rule_ir,
            clause=rule_ir.clauses[0],
            effect_index=0,
            target_unit_instance_ids=context.target_unit_instance_ids,
            context=current,
        )

    identity = derive(context)
    changed = derive(replace(context, **cast(dict[str, Any], {field: value})))
    assert identity != changed
    assert identity == derive(replace(context, state=None, event_log=EventLog()))
    assert identity == derive(replace(context, record_persisting_effects=False))


@pytest.mark.parametrize("index", [-1, 1, True, "0"])
def test_identity_rejects_invalid_effect_slots(index: object) -> None:
    rule_ir, context = _scene()
    with pytest.raises(GameLifecycleError, match="valid effect slot"):
        generic_rule_persisting_effect_id(
            rule_ir=rule_ir,
            clause=rule_ir.clauses[0],
            effect_index=cast(int, index),
            context=context,
            target_unit_instance_ids=context.target_unit_instance_ids,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("rule_ir", None, "typed source IR"),
        ("clause", None, "typed source IR"),
        ("context", None, "RuleExecutionContext"),
        ("targets", ["army-alpha:first"], "inventory is invalid"),
        ("targets", ("",), "inventory is invalid"),
        ("targets", (42,), "inventory is invalid"),
        ("targets", ("army-alpha:first", "army-alpha:first"), "inventory is duplicated"),
    ],
)
def test_identity_rejects_malformed_authority(field: str, value: object, message: str) -> None:
    rule_ir, context = _scene()
    with pytest.raises(GameLifecycleError, match=message):
        generic_rule_persisting_effect_id(
            rule_ir=cast(RuleIR, value) if field == "rule_ir" else rule_ir,
            clause=cast(RuleClause, value) if field == "clause" else rule_ir.clauses[0],
            effect_index=0,
            context=cast(RuleExecutionContext, value) if field == "context" else context,
            target_unit_instance_ids=cast(tuple[str, ...], value)
            if field == "targets"
            else context.target_unit_instance_ids,
        )


def test_identity_requires_loaded_clause_and_canonicalizes_effect_target_set() -> None:
    rule_ir, context = _scene()
    with pytest.raises(GameLifecycleError, match="loaded source clause"):
        generic_rule_persisting_effect_id(
            rule_ir=rule_ir,
            clause=replace(rule_ir.clauses[0], clause_id="another-source:grant"),
            effect_index=0,
            context=context,
            target_unit_instance_ids=context.target_unit_instance_ids,
        )
    targets = ("army-alpha:first", "army-alpha:second")
    identities = {
        generic_rule_persisting_effect_id(
            rule_ir=rule_ir,
            clause=rule_ir.clauses[0],
            effect_index=0,
            context=context,
            target_unit_instance_ids=order,
        )
        for order in (targets, tuple(reversed(targets)))
    }
    assert len(identities) == 1


__all__: list[str] = []
__all__ += ["ObjectiveRuleScope", "Pose", "RuleSourceText", "compile_rule_source_text"]
__all__ += ["fight_lifecycle", "keyword_source"]
