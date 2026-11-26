"""11th Edition Gather Attack Dice and Command Re-roll for native Shooting."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section09_fixtures import events
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.phase import BattlePhase


@pytest.mark.parametrize("accept", [False, True])
def test_native_random_attacks_choose_then_gather_and_reroll(
    section10_definitions: Section02Definitions, accept: bool
) -> None:
    from typing import cast

    from tests.phase13b_shooting_declaration_helpers import _grant_command_reroll_cp
    from tests.support.section04_fixtures import choose, pending, weapon_rows
    from tests.support.section10_fixtures import SPINNER, case, declaration_request, submit
    from warhammer40k_core.engine.event_log import JsonValue

    session, state, unit = case(section10_definitions, SPINNER, distance=12)
    for _ in range(2):
        _grant_command_reroll_cp(state, player_id="owner")
    request = declaration_request(session, unit, "normal")
    rows = [
        next(row for row in weapon_rows(request) if row["wargear_id"] == f"{SPINNER}:{kind}")
        for kind in ("doomweaver", "twin-shuriken-catapult")
    ]
    submit(session, rows, ["enemy:target", "enemy:target"], "normal", result_id="ranged-count")
    request = pending(session)
    assert request.decision_type == "select_attack_weapon_group"
    assert len(request.options) == 2
    assert not events(session, "random_characteristic_rolled")
    assert not events(session, "attack_sequence_step")
    groups = {
        option.option_id: cast(
            dict[str, JsonValue], cast(dict[str, JsonValue], option.payload)["gathered_group"]
        )
        for option in request.options
    }
    random_group_id = next(key for key, group in groups.items() if group["total_attacks"] == 0)
    fixed_count = next(
        group["total_attacks"] for key, group in groups.items() if key != random_group_id
    )
    assert type(fixed_count) is int
    assert fixed_count > 0
    choose(session, request, random_group_id)
    _answer_ranged_count(session, accept=accept, components=1, round_trip=False)
    [gathered] = events(session, "ranged_attack_counts_gathered")
    assert gathered["group_id"] == random_group_id


@pytest.mark.parametrize("components", [1, 2])
def test_random_attack_count_window_restores_and_replays(components: int) -> None:
    from dataclasses import replace

    from tests.phase13b_shooting_declaration_helpers import (
        _catalog_with_replaced_bolt_profiles,
        _compact_shooting_lifecycle,
        _grant_command_reroll_cp,
        _weapon_profile_by_wargear,
    )
    from tests.support.section04_fixtures import (
        pending,
        shooting_payload,
        shooting_request,
        weapon_rows,
    )
    from warhammer40k_core.core.dice import DiceExpression
    from warhammer40k_core.core.weapon_profiles import AttackProfile
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus

    # A muster-valid canonical fixture drives the same native declaration and
    # random count code and permits exact restoration of the roster.
    rifle = _weapon_profile_by_wargear(
        wargear_id="core-bolt-rifle", weapon_profile_id="core-bolt-rifle:standard"
    )
    profile = replace(rifle, attack_profile=AttackProfile.dice(DiceExpression(components, 6, 3)))
    lifecycle, units = _compact_shooting_lifecycle(
        game_id=f"ranged-count-replay-{components}",
        catalog=_catalog_with_replaced_bolt_profiles((profile,)),
    )
    state = lifecycle.state
    assert state is not None
    for _ in range(2):
        _grant_command_reroll_cp(state, player_id="player-a")
    session = LocalGameSession(GameLifecycle.from_payload(lifecycle.to_payload()))
    session.advance_until_decision_or_terminal()
    request = shooting_request(session, units["intercessor-1"].unit_instance_id)
    session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="ranged-count-replay-declare",
        payload=shooting_payload(
            request, weapon_rows(request)[:1], [units["enemy"].unit_instance_id]
        ),
    )
    assert pending(session).decision_type == "use_stratagem"
    checkpoint = session.to_persistence_payload()
    for accept in (False, True):
        restored = LocalGameSession.from_persistence_payload(checkpoint)
        assert restored.to_persistence_payload() == checkpoint
        for viewer in ("player-a", "player-b"):
            assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        restored = _answer_ranged_count(
            restored, accept=accept, components=components, round_trip=True
        )
        replay = ReplayRunner.from_payload(
            restored.replay_artifact(artifact_id="ranged-count")
        ).run()
        assert replay.status is ReplayRunStatus.REPRODUCED, replay
        if accept:
            live = _answer_ranged_count(
                session, accept=True, components=components, round_trip=False
            )
            assert live.to_persistence_payload() == restored.to_persistence_payload()


def _answer_ranged_count(
    session: LocalGameSession, *, accept: bool, components: int, round_trip: bool
) -> LocalGameSession:
    from typing import cast

    from tests.support.section04_fixtures import pending
    from warhammer40k_core.adapters.access_control import ViewerContext
    from warhammer40k_core.adapters.event_stream import EventStreamCursor
    from warhammer40k_core.core.dice import (
        DiceRollResult,
        DiceRollResultPayload,
        DiceRollState,
        DiceRollStatePayload,
    )
    from warhammer40k_core.engine.event_log import (
        EventRecordPayload,
        JsonValue,
        canonical_json,
        validate_json_value,
    )
    from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind

    def page_events(
        current: LocalGameSession, viewer: ViewerContext, cursor: EventStreamCursor
    ) -> list[EventRecordPayload]:
        records: list[EventRecordPayload] = []
        while True:
            page = current.event_page_for_context(cursor, viewer=viewer, visible_limit=8)
            assert page["cursor"] == cursor.value
            assert page["next_cursor"] == cursor.value + len(page["events"])
            records.extend(page["events"])
            if not page["has_more"]:
                return records
            assert page["events"]
            cursor = EventStreamCursor(page["next_cursor"])

    request = pending(session)
    assert request.decision_type == "use_stratagem"
    assert request.actor_id is not None
    actor_id = request.actor_id
    before = session.lifecycle.state
    assert before is not None
    assert before.command_point_total(actor_id) == 2
    [original] = events(session, "random_characteristic_rolled")
    assert original["timing"] == "per_weapon"
    assert not events(session, "ranged_attack_counts_gathered")
    assert not events(session, "attack_sequence_step")
    original_roll = DiceRollState.from_payload(cast(DiceRollStatePayload, original["roll_state"]))
    assert len(original_roll.current_values) == components
    owner = ViewerContext.for_player(actor_id)
    opponent_id = next(player_id for player_id in before.player_ids if player_id != actor_id)
    opponent_viewer = ViewerContext.for_player(opponent_id)
    cursors = {
        viewer: EventStreamCursor(
            session.events_since_for_context(EventStreamCursor(), viewer=viewer)["next_cursor"]
        )
        for viewer in (owner, opponent_viewer)
    }
    public = session.view_for_context(viewer=owner)["pending_decision"]
    assert public is not None
    assert public["decision_type"] == "use_stratagem"
    assert public["request_id"] != request.request_id
    option = next(
        row["option_id"]
        for row in public["options"]
        if ("command-reroll" in row["option_id"]) == accept
    )
    status = session.submit_viewer_option(
        viewer=owner,
        request_id=public["request_id"],
        option_id=option,
        result_id=f"ranged-count-stratagem-{accept}",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    if accept and components == 2:
        request = pending(session)
        assert request.decision_type == "select_dice_reroll"
        assert [o.option_id for o in request.options] == ["reroll:0", "reroll:1"]
        public = session.view_for_context(viewer=owner)["pending_decision"]
        assert public is not None
        assert public["decision_type"] == "select_dice_reroll"
        assert public["request_id"] != request.request_id
        assert [row["option_id"] for row in public["options"]] == ["reroll:0", "reroll:1"]
        payload = public["payload"]
        assert isinstance(payload, dict)
        permission = payload["permission"]
        reroll = payload["command_reroll_context"]
        assert isinstance(permission, dict)
        assert isinstance(reroll, dict)
        context = reroll["stratagem_context"]
        assert isinstance(context, dict)
        timing_window = permission["timing_window"]
        assert isinstance(timing_window, str)
        assert timing_window.startswith("view-window-")
        assert timing_window == context["timing_window_id"]
        assert original_roll.original_result.roll_id not in canonical_json(
            validate_json_value(public)
        )
        opponent = session.view(viewer_player_id=opponent_id)
        hidden = opponent["pending_decision"]
        assert hidden is not None
        assert hidden["decision_type"] == "hidden_decision"
        assert hidden["options"] == []
        selection_pages = {
            viewer: page_events(session, viewer, cursors[viewer]) for viewer in cursors
        }
        (selection,) = [
            row["payload"]
            for row in selection_pages[owner]
            if row["event_type"] == "command_reroll_selection_requested"
        ]
        assert isinstance(selection, dict)
        selection_request = selection["reroll_request"]
        assert isinstance(selection_request, dict)
        assert selection_request["request_id"] == public["request_id"]
        assert original_roll.original_result.roll_id not in canonical_json(selection_request)
        assert "command_reroll_selection_requested" not in {
            row["event_type"] for row in selection_pages[opponent_viewer]
        }
        with pytest.raises(GameLifecycleError, match="does not own the pending decision"):
            session.submit_viewer_option(
                viewer=opponent_viewer,
                request_id=public["request_id"],
                option_id=public["options"][1]["option_id"],
                result_id="opponent-ranged-count-component",
            )
        if round_trip:
            inner = session.to_persistence_payload()
            session = LocalGameSession.from_persistence_payload(inner)
            assert session.to_persistence_payload() == inner
            assert session.view_for_context(viewer=owner)["pending_decision"] == public
            assert session.view(viewer_player_id=opponent_id) == opponent
            assert {
                viewer: page_events(session, viewer, cursors[viewer]) for viewer in cursors
            } == selection_pages
        assert not events(session, "attack_sequence_step")
        status = session.submit_viewer_option(
            viewer=owner,
            request_id=public["request_id"],
            option_id=public["options"][1]["option_id"],
            result_id="ranged-count-component",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status

    assert pending(session).request_id != request.request_id
    for viewer, cursor in cursors.items():
        assert session.view_for_context(viewer=viewer)["pending_decision"] is not None
        projected = page_events(session, viewer, cursor)
        event_types = [row["event_type"] for row in projected]
        assert event_types.count("command_reroll_selection_requested") == int(
            accept and components == 2 and viewer == owner
        )
        assert event_types.count("command_reroll_resolved") == int(accept)
        assert "ranged_attack_counts_gathered" in event_types
        if accept:
            resolved = projected[event_types.index("command_reroll_resolved")]["payload"]
            assert isinstance(resolved, dict)
            assert "updated_roll_state" in resolved
            assert ("reroll_request" in resolved) is (viewer == owner)
            assert ("reroll_result" in resolved) is (viewer == owner)
            assert original_roll.original_result.roll_id not in canonical_json(resolved)
            if viewer == owner:
                result = resolved["reroll_result"]
                assert isinstance(result, dict)
                assert result["selected_option_id"] == f"reroll:{components - 1}"

    after = session.lifecycle.state
    assert after is not None
    assert [e["applied_amount"] for e in events(session, "command_points_spent")] == (
        [1] if accept else []
    )
    if after.current_battle_phase is BattlePhase.SHOOTING:
        assert after.command_point_total(actor_id) == 2 - int(accept)
    [gathered] = events(session, "ranged_attack_counts_gathered")
    [count] = cast(list[dict[str, JsonValue]], gathered["counts"])
    assert count["roll_id"] == original_roll.original_result.roll_id
    assert (
        sum(
            e["scope_id"] == original["scope_id"]
            for e in events(session, "random_characteristic_rolled")
        )
        == 1
    )
    latest = original_roll
    if accept:
        [reroll] = events(session, "command_reroll_resolved")
        latest = DiceRollState.from_payload(
            cast(DiceRollStatePayload, reroll["updated_roll_state"])
        )
        assert latest.rerolled_indices() == (components - 1,)
        assert latest.current_values[:-1] == original_roll.current_values[:-1]
    assert count["attacks"] == sum(latest.current_values) + 3
    journal = session.lifecycle.decision_controller.event_log.records
    gathered_index = next(
        i for i, e in enumerate(journal) if e.event_type == "ranged_attack_counts_gathered"
    )
    hit_index = next(
        i
        for i, e in enumerate(journal)
        if e.event_type == "dice_rolled"
        and DiceRollResult.from_payload(cast(DiceRollResultPayload, e.payload)).spec.roll_type
        == "attack_sequence.hit"
    )
    assert gathered_index < hit_index
    if after.current_battle_phase is BattlePhase.SHOOTING:
        assert any("command-reroll" in o.option_id for o in pending(session).options) is (
            not accept
        )
    else:
        assert accept
    return session


def test_native_fixed_group_resolves_before_unselected_random_attacks(
    section10_definitions: Section02Definitions,
) -> None:
    from typing import cast

    from tests.support.section04_fixtures import choose, pending, weapon_rows
    from tests.support.section10_fixtures import SPINNER, case, declaration_request, submit
    from warhammer40k_core.engine.event_log import JsonValue

    session, state, unit = case(section10_definitions, SPINNER, distance=12)
    request = declaration_request(session, unit, "normal")
    rows = [
        next(row for row in weapon_rows(request) if row["wargear_id"] == f"{SPINNER}:{kind}")
        for kind in ("doomweaver", "twin-shuriken-catapult")
    ]
    submit(session, rows, ["enemy:target", "enemy:target"], "normal", result_id="static-first")
    request = pending(session)
    assert request.decision_type == "select_attack_weapon_group"
    fixed = next(
        option
        for option in request.options
        if cast(dict[str, JsonValue], cast(dict[str, JsonValue], option.payload)["gathered_group"])[
            "total_attacks"
        ]
        != 0
    )
    choose(session, request, fixed.option_id)
    for _ in range(30):
        if events(session, "ranged_attack_counts_gathered"):
            break
        pending_request = pending(session)
        assert not any("command-reroll" in o.option_id for o in pending_request.options)
        option = next(
            (
                o.option_id
                for o in pending_request.options
                if o.option_id in {"decline", "keep", "keep_all_modifiers"}
            ),
            pending_request.options[0].option_id,
        )
        choose(session, pending_request, option)
    else:
        pytest.fail("The random group did not gather its count.")
    journal = session.lifecycle.decision_controller.event_log.records
    count_index = next(
        i for i, e in enumerate(journal) if e.event_type == "ranged_attack_counts_gathered"
    )
    first_hit_index = next(
        i
        for i, e in enumerate(journal)
        if e.event_type == "attack_sequence_step"
        and cast(dict[str, JsonValue], e.payload)["step"] == "hit"
    )
    assert first_hit_index < count_index
    assert state.command_point_total("owner") == 0


def test_native_group_rolls_separately_for_two_physical_weapons(
    section10_definitions: Section02Definitions,
) -> None:
    from dataclasses import replace

    from tests.phase13b_shooting_declaration_helpers import _grant_command_reroll_cp
    from tests.support.section04_fixtures import choose, pending, weapon_rows
    from tests.support.section10_fixtures import AVENGERS, case, declaration_request, submit
    from warhammer40k_core.core.dice import DiceExpression
    from warhammer40k_core.core.weapon_profiles import AttackProfile

    d = section10_definitions
    wargear_id = f"{AVENGERS}:avenger-shuriken-catapult"
    # Keep the native bearer and group applicability, and give this test
    # profile a random count on each of its two physical weapons.
    profile = replace(
        d.weapon(wargear_id), attack_profile=AttackProfile.dice(DiceExpression(1, 6, 3))
    )
    catalog = d.package.army_catalog
    catalog = replace(
        catalog,
        wargear=tuple(
            replace(row, weapon_profiles=(profile,)) if row.wargear_id == wargear_id else row
            for row in catalog.wargear
        ),
    )
    d = replace(d, package=replace(d.package, army_catalog=catalog))
    session, state, unit = case(d, AVENGERS, distance=12)
    _grant_command_reroll_cp(state, player_id="owner")
    request = declaration_request(session, unit, "normal")
    rows = [row for row in weapon_rows(request) if row["wargear_id"] == wargear_id][:2]
    assert len(rows) == 2
    assert rows[0]["weapon_instance_id"] != rows[1]["weapon_instance_id"]
    submit(
        session, rows, ["enemy:target", "enemy:target"], "normal", result_id="two-physical-counts"
    )
    request = pending(session)
    assert request.decision_type == "use_stratagem"
    shooting = state.shooting_phase_state
    assert shooting is not None
    sequence = shooting.attack_sequence
    assert sequence is not None
    group = sequence.current_gathered_group
    assert group is not None
    assert len(group.native_snapshots) == 2
    assert group.counts_pending
    assert len(events(session, "random_characteristic_rolled")) == 1

    choose(session, request, "decline_stratagem_window")
    request = pending(session)
    assert request.decision_type == "use_stratagem"
    assert len(events(session, "random_characteristic_rolled")) == 2
    assert not events(session, "attack_sequence_step")
    choose(
        session,
        request,
        next(o.option_id for o in request.options if "command-reroll" in o.option_id),
    )
    [gathered] = events(session, "ranged_attack_counts_gathered")
    counts = gathered["counts"]
    assert isinstance(counts, list)
    first, second = counts
    assert isinstance(first, dict)
    assert isinstance(second, dict)
    assert first["roll_id"] != second["roll_id"]
    assert [e["applied_amount"] for e in events(session, "command_points_spent")] == [1]
