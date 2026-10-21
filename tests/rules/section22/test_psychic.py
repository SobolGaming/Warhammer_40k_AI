"""Once-per-phase identity uses native PSYKER bodies and explicit Core inputs."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section22_fixtures import context, pair, rule
from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.psychic_ability_usage import psychic_uses
from warhammer40k_core.engine.rule_execution import RuleExecutionStatus, execute_rule_ir


@pytest.mark.parametrize("change", ["none", "instance", "ability", "phase", "turn", "round"])
def test_psychic_use_is_by_ability_rules_unit_and_actual_phase(
    section22_definitions: Section02Definitions, change: str
) -> None:
    state, source, _ = pair(section22_definitions, psychic=True)
    log = EventLog()
    ir = rule("Might (Psychic level 1): Add 1 to hit rolls.", identity="might")
    first = execute_rule_ir(rule_ir=ir, context=context(state, source, log))
    assert first.status is RuleExecutionStatus.APPLIED
    assert len(psychic_uses(log)) == 1
    if change == "instance":
        ir = replace(ir, rule_id="constructed:s22:another-physical-instance")
    elif change == "ability":
        ir = replace(ir, rule_id="constructed:s22:different", source_id="constructed:s22:different")
    elif change == "phase":
        state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    elif change == "turn":
        state.active_player_id = "opponent"
    elif change == "round":
        state.battle_round = 2
    before = (state.to_payload(), log.to_payload())
    again = execute_rule_ir(rule_ir=ir, context=context(state, source, log))
    denied = change in {"none", "instance"}
    assert (again.status is RuleExecutionStatus.INVALID) is denied
    if denied:
        assert again.reason == "psychic_ability_used_this_phase"
        assert (state.to_payload(), log.to_payload()) == before
    assert len(psychic_uses(log)) == (1 if denied else 2)


@pytest.mark.parametrize("psychic", [False, True])
def test_only_levelled_psyker_ability_uses_the_restriction(
    section22_definitions: Section02Definitions, psychic: bool
) -> None:
    state, source, _ = pair(section22_definitions, psychic=psychic)
    log = EventLog()
    unlevelled = rule("Add 1 to hit rolls.")
    for _ in range(2):
        result = execute_rule_ir(rule_ir=unlevelled, context=context(state, source, log))
        assert result.status is RuleExecutionStatus.APPLIED
    assert psychic_uses(log) == ()
    levelled = rule("Gift (Psychic level 2): Add 1 to hit rolls.")
    before = (state.to_payload(), log.to_payload())
    result = execute_rule_ir(rule_ir=levelled, context=context(state, source, log))
    assert (result.status is RuleExecutionStatus.APPLIED) is psychic
    if not psychic:
        assert result.reason == "psychic_ability_requires_psyker"
        assert (state.to_payload(), log.to_payload()) == before


def test_attached_components_share_use_and_actual_psyker_casualty_removes_eligibility(
    section22_definitions: Section02Definitions,
) -> None:
    from tests.support.section19_fixtures import attached_scene, destroy
    from warhammer40k_core.engine.decision_controller import DecisionController

    s = attached_scene(section22_definitions, support=True)
    assert s.support is not None
    log = EventLog()
    ir = rule("Might (Psychic level 1): Add 1 to hit rolls.", identity="attached-might")
    first = execute_rule_ir(rule_ir=ir, context=context(s.state, s.support, log))
    assert first.status is RuleExecutionStatus.APPLIED
    before = (s.state.to_payload(), log.to_payload())
    repeated = execute_rule_ir(
        rule_ir=replace(ir, rule_id="constructed:s22:duplicate-component"),
        context=context(s.state, s.leader, log),
    )
    assert repeated.reason == "psychic_ability_used_this_phase"
    assert (s.state.to_payload(), log.to_payload()) == before
    assert psychic_uses(log)[0].rules_unit_instance_id == s.view.unit_instance_id
    destroy(s, DecisionController(), s.support.own_model_ids()[0])
    assert "PSYKER" not in s.view.keywords
    different = replace(ir, source_id="constructed:s22:different-ability")
    result = execute_rule_ir(rule_ir=different, context=context(s.state, s.leader, log))
    assert result.reason == "psychic_ability_requires_psyker"


@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.parametrize("retained", [False, True])
@pytest.mark.parametrize("explicit_model", [False, True])
def test_retained_psyker_levelled_use_preserves_physical_presence_and_once_per_phase(
    section22_definitions: Section02Definitions,
    attached: bool,
    retained: bool,
    explicit_model: bool,
) -> None:
    from tests.fight_on_death_helpers import retain_destroyed_model_for_fixture
    from tests.support.section19_fixtures import attached_scene
    from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    if attached:
        s = attached_scene(section22_definitions, support=True)
        assert s.support is not None
        state, source = s.state, s.support
    else:
        state, source, _ = pair(section22_definitions, psychic=True)
    assert state.battlefield_state is not None
    saved = state.battlefield_state.model_placement_by_id(source.own_model_ids()[0])
    decisions = DecisionController()
    apply_damage_to_model(
        state=state,
        target_unit_instance_id=source.unit_instance_id,
        model_instance_id=source.own_model_ids()[0],
        damage=source.own_models[0].current_wounds,
        damage_kind=DamageKind.NORMAL,
        remove_destroyed_model=not retained,
    )
    if retained:
        phase = state.current_battle_phase
        assert phase is not None
        retain_destroyed_model_for_fixture(
            state=state,
            placement=saved,
            effect_id="constructed:s22:retained-level",
            source_rule_id="constructed:s22:fod",
            source_phase=phase,
            decisions=decisions,
        )
    view = rules_unit_view_by_id(state=state, unit_instance_id=source.unit_instance_id)
    assert ("PSYKER" in view.keywords) is retained
    assert (source.own_model_ids()[0] in view.retained_model_ids) is retained
    ir = rule("Might (Psychic level 1): Add 1 to hit rolls.", identity="retained-level")
    ctx = context(state, source, decisions.event_log)
    if not explicit_model:
        ctx = replace(ctx, source_model_instance_id=None)
    before = (state.to_payload(), decisions.to_payload())
    first = execute_rule_ir(rule_ir=ir, context=ctx)
    assert (first.status is RuleExecutionStatus.APPLIED) is retained
    if retained:
        after = (state.to_payload(), decisions.to_payload())
        repeated = execute_rule_ir(rule_ir=ir, context=ctx)
        assert repeated.reason == "psychic_ability_used_this_phase"
        assert (state.to_payload(), decisions.to_payload()) == after
        assert len(psychic_uses(decisions.event_log)) == 1
    else:
        assert first.reason == "psychic_ability_requires_psyker"
        assert (state.to_payload(), decisions.to_payload()) == before
