"""SF16-R002/R003: real Action unit policies and distinct-unit source limits."""

from dataclasses import replace

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section16_fixtures import SPAWN
from tests.support.section16_review_fixtures import add_native_control, native_scene, offer_native
from tests.unit_keyword_helpers import with_unit_keywords

from warhammer40k_core.engine.mission_action_eligibility import (
    mission_action_unit_ineligibility_reason,
)
from warhammer40k_core.engine.mission_action_options import (
    mission_action_for_state,
    mission_action_start_options,
)
from warhammer40k_core.engine.mission_action_policies import mission_action_policy_for_id
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


def test_native_cleanse_excludes_core_eligible_spawn_beside_eligible_lord(
    section16_definitions: Section02Definitions,
) -> None:
    session, state, lord = native_scene(section16_definitions)
    spawn = add_native_control(section16_definitions, state, sheet=SPAWN)
    assert not {"INFANTRY", "BATTLELINE"}.intersection(spawn.keywords)
    assert (
        mission_action_unit_ineligibility_reason(
            state=state,
            player_id="owner",
            unit_instance_id=spawn.unit_instance_id,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
        is None
    )
    request = offer_native(session, state)
    assert any(f":{lord.unit_instance_id}:" in o.option_id for o in request.options)
    assert not any(f":{spawn.unit_instance_id}:" in o.option_id for o in request.options)
    # Changing only the explicit unit-policy premise enables the same geometry.
    eligible = with_unit_keywords(spawn, keywords=tuple(sorted({*spawn.keywords, "BATTLELINE"})))
    state.army_definitions[:] = [
        replace(
            a,
            units=tuple(
                eligible if u.unit_instance_id == spawn.unit_instance_id else u for u in a.units
            ),
        )
        for a in state.army_definitions
    ]
    options = mission_action_start_options(
        state=state,
        player_id="owner",
        action=mission_action_for_state(state=state, mission_action_id="cleanse-objective"),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert any(o.unit_instance_id == spawn.unit_instance_id for o in options)


def test_stale_action_unit_policy_loss_rejects_before_queue_pop(
    section16_definitions: Section02Definitions,
) -> None:
    session, state, lord = native_scene(section16_definitions)
    request = offer_native(session, state)
    option = next(o for o in request.options if f":{lord.unit_instance_id}:" in o.option_id)
    changed = with_unit_keywords(
        lord, keywords=tuple(k for k in lord.keywords if k not in {"INFANTRY", "BATTLELINE"})
    )
    state.army_definitions[:] = [
        replace(
            a,
            units=tuple(
                changed if u.unit_instance_id == lord.unit_instance_id else u for u in a.units
            ),
        )
        for a in state.army_definitions
    ]
    assert (
        mission_action_unit_ineligibility_reason(
            state=state,
            player_id="owner",
            unit_instance_id=lord.unit_instance_id,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
        is None
    )
    before = session.lifecycle.to_payload()
    result = session.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id="s16:r2:policy-drift"
    )
    assert result.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    assert session.lifecycle.decision_controller.queue.peek_next() == request


def test_cleanse_distinct_unit_same_target_limit_and_different_target_positive(
    section16_definitions: Section02Definitions,
) -> None:
    session, state, first = native_scene(section16_definitions)
    second = add_native_control(section16_definitions, state)
    third = add_native_control(section16_definitions, state, identity="third", same_target=False)
    req = offer_native(session, state)
    assert all(
        any(f":{u.unit_instance_id}:" in o.option_id for o in req.options)
        for u in (first, second, third)
    )
    chosen = next(o for o in req.options if f":{first.unit_instance_id}:" in o.option_id)
    result = session.submit_option(
        request_id=req.request_id, option_id=chosen.option_id, result_id="s16:r2:cleanse-first"
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID
    assert (
        mission_action_unit_ineligibility_reason(
            state=state,
            player_id="owner",
            unit_instance_id=second.unit_instance_id,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
        is None
    )
    options = mission_action_start_options(
        state=state,
        player_id="owner",
        action=mission_action_for_state(state=state, mission_action_id="cleanse-objective"),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert not any(o.unit_instance_id == second.unit_instance_id for o in options)
    assert any(o.unit_instance_id == third.unit_instance_id for o in options)
    assert all(o.target_id != state.mission_action_states[0].target_id for o in options)


def test_once_per_turn_source_limit_blocks_distinct_unit_stale_option_and_resets_next_occurrence(
    section16_definitions: Section02Definitions,
) -> None:
    session, state, first = native_scene(section16_definitions, vital_link=True)
    second = add_native_control(section16_definitions, state)
    assert mission_action_policy_for_id("maintain-control").use_limit == "once_per_turn"
    first_request = offer_native(session, state, "maintain-control")
    stale_request = offer_native(session, state, "maintain-control")
    assert all(
        any(f":{u.unit_instance_id}:" in o.option_id for o in first_request.options)
        for u in (first, second)
    )
    first_option = next(
        o for o in first_request.options if f":{first.unit_instance_id}:" in o.option_id
    )
    stale_option = next(
        o for o in stale_request.options if f":{second.unit_instance_id}:" in o.option_id
    )
    result = session.submit_option(
        request_id=first_request.request_id,
        option_id=first_option.option_id,
        result_id="s16:r2:limited-first",
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result
    assert (
        mission_action_unit_ineligibility_reason(
            state=state,
            player_id="owner",
            unit_instance_id=second.unit_instance_id,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
        is None
    )
    definition = mission_action_for_state(state=state, mission_action_id="maintain-control")
    assert (
        mission_action_start_options(
            state=state,
            player_id="owner",
            action=definition,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
        == ()
    )
    before = session.lifecycle.to_payload()
    rejected = session.submit_option(
        request_id=stale_request.request_id,
        option_id=stale_option.option_id,
        result_id="s16:r2:limit-stale",
    )
    assert rejected.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    assert session.lifecycle.decision_controller.queue.peek_next() == stale_request
    # Same preserved action history, explicitly advanced occurrence checkpoint;
    # no new mustering, prior-phase traversal or full game is implied.
    state.battle_round = 2
    assert state.mission_action_states[0].battle_round_started == 1
    assert (
        mission_action_unit_ineligibility_reason(
            state=state,
            player_id="owner",
            unit_instance_id=second.unit_instance_id,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
        is None
    )
    options = mission_action_start_options(
        state=state,
        player_id="owner",
        action=definition,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert any(o.unit_instance_id == second.unit_instance_id for o in options)
