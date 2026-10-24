"""All three literal 19.04 source rows, including source death and revival."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section19_fixtures import attached_scene, grant_definitions, has_lethal
from warhammer40k_core.engine.ability_presence import ability_presence
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.healing import (
    HealingEffect,
    HealingStepKind,
    apply_healing_model_decision,
    resolve_healing_until_blocked,
)
from warhammer40k_core.engine.reserves import (
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReserveOrigin,
    ReserveState,
)


@pytest.mark.parametrize(
    ("role", "wargear"),
    [("bodyguard", False), ("leader", False), ("support", False), ("leader", True)],
)
def test_each_table_source_applies_until_last_source_model_then_returns_on_real_revival(
    section19_definitions: Section02Definitions,
    role: str,
    wargear: bool,
) -> None:
    s = attached_scene(
        grant_definitions(section19_definitions, role, wargear=wargear), support=True
    )
    source = s.component(role)
    # Source lifetime is isolated from geometry: declared attached reserve group,
    # with one final source casualty. The actual revival decision mutates health.
    assert s.state.battlefield_state is not None
    board = s.state.battlefield_state
    for component in s.view.components:
        board = board.without_unit_placement(component.unit.unit_instance_id)
    s.state.replace_battlefield_state(board)
    s.state.record_reserve_state(
        ReserveState(
            "owner",
            s.view.unit_instance_id,
            ReserveOrigin.DECLARE_BATTLE_FORMATIONS,
            ReserveKind.STRATEGIC_RESERVES,
            "declare_battle_formations",
            None,
            None,
            ReserveDestructionTimingPolicy.core_rules_default(),
        )
    )
    assert all(has_lethal(s, m.model_instance_id) for m in s.view.alive_models())
    if len(source.own_models) > 1:
        s.set_living(role, 1)
        assert all(has_lethal(s, m.model_instance_id) for m in s.view.alive_models())
    s.set_living(role, 0)
    assert all(not has_lethal(s, m.model_instance_id) for m in s.view.alive_models())
    assert not set(source.own_model_ids()) & set(
        ability_presence(state=s.state, rules_unit=s.view).active_model_ids
    )
    effect = HealingEffect(
        "constructed:s19:revive",
        s.view.unit_instance_id,
        1,
        "opponent",
        source_rule_id="constructed:s19:revival-permission",
        source_context={"revive_destroyed_models_only": True, "revive_model_full_health": True},
    )
    decisions = DecisionController()
    effect, req = resolve_healing_until_blocked(
        state=s.state,
        decisions=decisions,
        ruleset_descriptor=s.state.runtime_ruleset_descriptor(),
        effect=effect,
    )
    assert req is not None
    selected = next(o for o in req.options if source.own_model_ids()[0] in str(o.payload))
    effect, req = apply_healing_model_decision(
        state=s.state,
        decisions=decisions,
        ruleset_descriptor=s.state.runtime_ruleset_descriptor(),
        effect=effect,
        result=DecisionResult.for_request(
            result_id="s19:revived", request=req, selected_option_id=selected.option_id
        ),
    )
    assert req is None
    assert effect.is_complete()
    assert effect.resolved_steps[0].step_kind is HealingStepKind.REVIVE_MODEL_IN_RESERVES
    assert effect.resolved_steps[0].model_instance_id == source.own_model_ids()[0]
    assert all(has_lethal(s, m.model_instance_id) for m in s.view.alive_models())
    assert s.view.attached_unit == s.formation
