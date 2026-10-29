"""Physical native profile choices and explicit Core trigger contracts."""

from dataclasses import replace
from typing import cast

import pytest

from tests.support.section02_fixtures import LORD_EXULTANT, Section02Definitions
from tests.support.section04_fixtures import (
    add_enemy,
    combat_session,
    combat_state,
    declare_shooting,
    pending,
    shooting_request,
    weapon_rows,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phases.shooting_model import _default_stratagem_index
from warhammer40k_core.engine.stratagems import (
    StratagemCatalogIndex,
    StratagemCatalogRecord,
    StratagemTargetKind,
    StratagemTargetSpec,
    stratagem_window_context_from_request,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.wargear_selections import WargearSelection


def test_native_different_models_choose_distinct_profiles_of_same_weapon(
    section04_definitions: Section02Definitions, section04_mission: MissionSetup
) -> None:
    d = section04_definitions
    sheet = "000004088"
    unit = d.unit(
        sheet,
        wargear=(
            WargearSelection(
                f"{sheet}:sonic-blaster-blastmaster:option-2",
                f"{sheet}:noise-marines",
                (f"{sheet}:blastmaster",),
                selection_count=2,
            ),
        ),
    )
    state = combat_state(d, unit)
    session = combat_session(d, state, section04_mission)
    request = shooting_request(session, unit.unit_instance_id)
    rows = [r for r in weapon_rows(request) if r["wargear_id"] == f"{sheet}:blastmaster"]
    models = sorted({cast(str, r["model_instance_id"]) for r in rows})
    assert len(models) == 2
    profiles = sorted({cast(str, r["weapon_profile_id"]) for r in rows})
    assert len(profiles) == 2
    selected = [
        next(
            r for r in rows if r["model_instance_id"] == m and r["weapon_profile_id"] == profiles[i]
        )
        for i, m in enumerate(models)
    ]
    declare_shooting(session, request, selected, ["enemy:target"] * 2)
    accepted = next(
        e
        for e in session.lifecycle.decision_controller.event_log.records
        if e.event_type == "shooting_declaration_accepted"
    )
    pools = cast(
        list[dict[str, JsonValue]], cast(dict[str, JsonValue], accepted.payload)["attack_pools"]
    )
    assert [p["weapon_profile_id"] for p in pools] == profiles
    assert [p["weapon_instance_id"] for p in pools] == [r["weapon_instance_id"] for r in selected]
    assert len({cast(str, p["weapon_instance_id"]) for p in pools}) == 2
    assert [p["attacker_model_instance_id"] for p in pools] == models


@pytest.mark.parametrize("qualifies", [False, True])
def test_constructed_against_trigger_waits_for_complete_target_selection(
    section04_definitions: Section02Definitions, section04_mission: MissionSetup, qualifies: bool
) -> None:
    d = section04_definitions
    unit = d.unit(LORD_EXULTANT)
    state = combat_state(d, unit)
    add_enemy(d, state)
    template = (
        _default_stratagem_index()
        .records_for(TimingTriggerKind.AFTER_UNIT_SELECTED_AS_TARGET)[0]
        .definition
    )
    # Constructed record-only rule, with current Core timing and an explicit
    # keyword qualifier. It makes no claim to native faction stratagem support.
    definition = replace(
        template,
        stratagem_id="constructed:against",
        source_id="constructed:section04:against",
        name="Core against timing contract",
        command_point_cost=0,
        handler_id="record_only",
        target_spec=StratagemTargetSpec(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_policy_id="selected_target_unit",
            required_keywords=("INFANTRY" if qualifies else "VEHICLE",),
        ),
    )
    index = StratagemCatalogIndex.from_records(
        (StratagemCatalogRecord("constructed:against", definition),)
    )
    session = combat_session(d, state, section04_mission, stratagem_index=index)
    request = shooting_request(session, unit.unit_instance_id)
    assert not any(
        e.event_type == "unit_selected_as_target_stratagem_window_opened"
        for e in session.lifecycle.decision_controller.event_log.records
    )
    declare_shooting(session, request, weapon_rows(request)[:2], ["enemy:target", "enemy:other"])
    events = session.lifecycle.decision_controller.event_log.records
    windows = [
        e for e in events if e.event_type == "unit_selected_as_target_stratagem_window_opened"
    ]
    assert bool(windows) is qualifies
    assert not any(e.event_type == "attack_sequence_step" for e in events)
    if qualifies:
        context = stratagem_window_context_from_request(pending(session))
        payload = cast(dict[str, JsonValue], context.trigger_payload)
        assert payload["selected_target_unit_instance_ids"] == ["enemy:other", "enemy:target"]
        assert context.player_id == "opponent"
        assert events.index(
            next(e for e in events if e.event_type == "shooting_declaration_accepted")
        ) < events.index(windows[0])
        assert len(pending(session).options) == 3
