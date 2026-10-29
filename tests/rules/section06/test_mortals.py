"""06.02: native wounds, all four tiers, actual decisions and Select Model triggers."""

from dataclasses import replace
from typing import cast

import pytest

from tests.support.section01_fixtures import minimal_state, place_units
from tests.support.section02_fixtures import LORD_EXULTANT, Section02Definitions
from tests.support.section04_fixtures import combat_state
from tests.support.section05_fixtures import replace_unit
from tests.support.section05_sequence import payloads
from tests.support.section06_fixtures import mortal_progress
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.damage_allocation import (
    FeelNoPainSource,
    feel_no_pain_roll_spec,
    model_by_id,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.mortal_wound_allocation_permissions import (
    mortal_wound_allocation_permission_effect,
)
from warhammer40k_core.engine.mortal_wound_model_allocation import (
    continue_mortal_wound_application,
    mortal_wound_priority_selection,
    resolve_mortal_wound_model_decision,
)
from warhammer40k_core.engine.unit_strength_inventory import starting_strength_records_for_army


@pytest.mark.parametrize("wounds", [1, 4, 5, 8])
def test_single_native_character_each_wound_and_overkill(
    section06_definitions: Section02Definitions,
    wounds: int,
) -> None:
    d = section06_definitions
    target = d.unit(LORD_EXULTANT)
    state = combat_state(d, target)
    decisions = DecisionController()
    result = continue_mortal_wound_application(
        state=state,
        decisions=decisions,
        request_id="s06:request",
        progress=mortal_progress(state, target.unit_instance_id, wounds),
    )
    app = result.application
    assert app is not None
    assert result.request is None
    assert len(app.applications) == min(5, wounds)
    assert [a.wounds_lost for a in app.applications] == [1] * min(5, wounds)
    assert app.remaining_mortal_wounds_lost == max(0, wounds - 5)
    model = model_by_id(state=state, model_instance_id=target.own_model_ids()[0])
    assert model.current_wounds == max(0, 5 - wounds)
    assert model.is_alive is (wounds < 5)
    allocated = payloads(decisions, "mortal_wound_model_allocated")
    assert [a["wound_index"] for a in allocated] == list(range(1, min(5, wounds) + 1))
    assert {cast(str, a["selected_model_id"]) for a in allocated} == set(target.own_model_ids())
    assert len(payloads(decisions, "model_destroyed")) == int(wounds >= 5)


@pytest.mark.parametrize(
    "tier", ["wounded_non_character", "non_character", "wounded_character", "character"]
)
def test_native_attached_mortal_priority_tiers(
    section06_definitions: Section02Definitions,
    tier: str,
) -> None:
    d = section06_definitions
    body = d.unit(identity="body")
    leader = d.unit(LORD_EXULTANT, identity="leader")
    other = d.unit(LORD_EXULTANT, identity="other-leader")
    # Two native leaders form an explicit allocator contract; faction permissions are not claimed.
    if tier == "wounded_non_character":
        body = replace(
            body, own_models=(replace(body.own_models[0], wounds_remaining=1), *body.own_models[1:])
        )
    if tier in {"wounded_non_character", "non_character", "wounded_character"}:
        leader = replace(leader, own_models=(replace(leader.own_models[0], wounds_remaining=3),))
    state = minimal_state(d, body, leader, other)
    formation = AttachedUnitFormation(
        "attached-unit:section02:s06",
        body.unit_instance_id,
        (leader.unit_instance_id, other.unit_instance_id),
        component_unit_instance_ids=tuple(
            sorted((body.unit_instance_id, leader.unit_instance_id, other.unit_instance_id))
        ),
        source_id="constructed:s06:attachment",
        attachment_source_ids=("constructed:s06:two-leaders",),
    )
    state.army_definitions[0] = replace(state.army_definitions[0], attached_units=(formation,))
    state.starting_strength_records[:] = starting_strength_records_for_army(
        state.army_definitions[0]
    )
    place_units(state)
    if tier in {"wounded_character", "character"}:
        body = replace(
            body, own_models=tuple(replace(m, wounds_remaining=0) for m in body.own_models)
        )
        replace_unit(state, body)
        assert state.battlefield_state is not None
        state.replace_battlefield_state(
            state.battlefield_state.without_unit_placement(body.unit_instance_id)
        )
    ids, priority = mortal_wound_priority_selection(
        state=state, target_unit_instance_id=formation.attached_unit_instance_id
    )
    expected = {
        "wounded_non_character": (body.own_model_ids()[0],),
        "non_character": body.own_model_ids(),
        "wounded_character": leader.own_model_ids(),
        "character": (*leader.own_model_ids(), *other.own_model_ids()),
    }[tier]
    assert set(ids) == set(expected)
    assert priority.value == tier


@pytest.mark.parametrize("choice", [0, -1])
def test_controlling_player_choice_then_spillover(
    section06_definitions: Section02Definitions, choice: int
) -> None:
    d = section06_definitions
    target = d.unit()
    state = combat_state(d, target)
    decisions = DecisionController()
    routed = continue_mortal_wound_application(
        state=state,
        decisions=decisions,
        request_id="s06:choose",
        progress=mortal_progress(state, target.unit_instance_id, 3),
    )
    request = routed.request
    assert request is not None
    assert request.actor_id == "owner"
    assert {o.option_id for o in request.options} == set(target.own_model_ids())
    assert all(
        model_by_id(state=state, model_instance_id=m).current_wounds == 2
        for m in target.own_model_ids()
    )
    chosen = request.options[choice].option_id
    decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="s06:choice", request=request, selected_option_id=chosen
    )
    decisions.submit_result(result)
    routed = resolve_mortal_wound_model_decision(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
        next_request_id="s06:next",
    )
    assert not model_by_id(state=state, model_instance_id=chosen).is_alive
    assert routed.request is not None
    assert chosen not in {o.option_id for o in routed.request.options}
    assert routed.progress.remaining_mortal_wounds == 1
    occurrences = payloads(decisions, "mortal_wound_model_allocated")
    assert [o["selected_model_id"] for o in occurrences] == [chosen, chosen]
    assert occurrences[0]["selection_disposition"] == "player_decision"
    assert occurrences[1]["priority_tier"] == "wounded_non_character"
    request = routed.request
    next_chosen = request.options[-1].option_id
    decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="s06:second", request=request, selected_option_id=next_chosen
    )
    decisions.submit_result(result)
    finished = resolve_mortal_wound_model_decision(
        state=state, decisions=decisions, request=request, result=result, next_request_id="s06:done"
    )
    assert finished.request is None
    assert finished.application is not None
    assert [a.model_instance_id for a in finished.application.applications] == [
        chosen,
        chosen,
        next_chosen,
    ]
    assert model_by_id(state=state, model_instance_id=next_chosen).current_wounds == 1


@pytest.mark.parametrize(("protected", "face"), [(False, 1), (True, 1), (True, 6)])
def test_faq08_allocation_occurs_before_prevention_and_damage(
    section06_definitions: Section02Definitions,
    protected: bool,
    face: int,
) -> None:
    d = section06_definitions
    target = d.unit(LORD_EXULTANT)
    state = combat_state(d, target)
    target = replace(target, own_models=(replace(target.own_models[0], wounds_remaining=1),))
    replace_unit(state, target)
    if protected:
        # Actual generic provider seam, retaining the authenticated order117 source identity.
        state.record_persisting_effect(
            mortal_wound_allocation_permission_effect(
                state=state,
                effect_id="s06:allocation",
                source_rule_id=(
                    "gw-11e-phase17e-exact-faction-subrules-2026-27:"
                    "stratagem:adeptus-custodes:shield-host:000008394002"
                ),
                target_unit_instance_id=target.unit_instance_id,
                occasion_id="s06:provider-authorized",
                threshold=2,
            )
        )
    decisions = DecisionController()
    fixed = (
        ()
        if not protected
        else (
            DiceRollManager("s06:fixed")
            .roll_fixed(
                feel_no_pain_roll_spec(
                    source=FeelNoPainSource("s06:allocation:mortal-allocation-feel-no-pain", 2),
                    player_id="owner",
                    model_instance_id=target.own_model_ids()[0],
                    wound_index=1,
                ),
                (face,),
            )
            .original_result,
        )
    )
    routed = continue_mortal_wound_application(
        state=state,
        decisions=decisions,
        request_id="s06:trigger",
        progress=mortal_progress(state, target.unit_instance_id, 1),
        dice_manager=DiceRollManager(
            "s06:trigger", event_log=decisions.event_log, injected_results=fixed
        ),
    )
    assert routed.application is not None
    events = decisions.event_log.records
    types = [e.event_type for e in events]
    assert types.count("mortal_wound_model_allocated") == 1
    allocated = payloads(decisions, "mortal_wound_model_allocated")[0]
    assert allocated["selected_model_id"] == target.own_model_ids()[0]
    if protected:
        assert (
            types.index("mortal_wound_model_allocated")
            < types.index("mortal_wound_allocation_rule_applied")
            < types.index("dice_rolled")
        )
        assert len(routed.application.feel_no_pain_resolutions) == 1
        resolution = routed.application.feel_no_pain_resolutions[0]
        assert routed.application.ignored_mortal_wounds == resolution.ignored_wounds
        assert resolution.ignored_wounds == int(face >= 2)
        assert (
            model_by_id(state=state, model_instance_id=target.own_model_ids()[0]).current_wounds
            == resolution.ignored_wounds
        )
    else:
        assert types.index("mortal_wound_model_allocated") < types.index("model_destroyed")
        assert not model_by_id(state=state, model_instance_id=target.own_model_ids()[0]).is_alive
