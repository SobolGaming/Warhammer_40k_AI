"""Bounded real EC consumers: wound-source admission and Court attack effects."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any, cast

import pytest

from tests.support.faction_batch01 import (
    INFRACTORS,
    LORD,
    RANGERS,
    Scene,
    anchor,
    events,
    locate,
    request,
    scene,
    selection,
)
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import shooting_payload, weapon_rows
from tests.support.section12_fixtures import melee_payload, move_payload
from tests.support.terrain_batch03 import (
    DEFILER,
    FULGRIM,
    MAULERFIEND,
    SINUOUS,
    breach_options,
    breach_request,
    movement_request,
    path_payload,
    submit_path,
    terrain_capability,
    terrain_scene,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.engine.runtime_modifiers import WeaponProfileModifierContext
from warhammer40k_core.engine.stratagems import (
    StratagemEligibilityContext,
    request_stratagem_use_from_index,
    stratagem_decline_payload,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.geometry.pose import Pose


def _step(s: Scene, r: DecisionRequest, i: int) -> LifecycleStatus:
    result = f"batch02:{i}"
    if r.decision_type == "submit_movement_proposal":
        return s.session.submit_parameterized_payload(
            request_id=r.request_id, payload=move_payload(r), result_id=result
        )
    if r.decision_type == "submit_stratagem_target_proposal":
        return s.session.submit_parameterized_payload(
            request_id=r.request_id, payload=stratagem_decline_payload(), result_id=result
        )
    if r.decision_type == "submit_melee_declaration":
        payload = cast(dict[str, JsonValue], melee_payload(r, attack=False))
        declarations: list[JsonValue] = []
        seen: set[str] = set()
        for row in weapon_rows(r):
            mid = cast(str, row["model_instance_id"])
            targets = cast(list[str], row["engaged_target_unit_instance_ids"])
            if mid in seen or not targets:
                continue
            seen.add(mid)
            declarations.append(
                {
                    "attacker_model_instance_id": mid,
                    "wargear_id": row["wargear_id"],
                    "weapon_profile_id": row["weapon_profile_id"],
                    "weapon_instance_id": row["weapon_instance_id"],
                    "selected_weapon_ability_ids": [],
                    "target_allocations": [{"target_unit_instance_id": targets[0]}],
                }
            )
        payload["declarations"] = declarations
        return s.session.submit_parameterized_payload(
            request_id=r.request_id, payload=payload, result_id=result
        )
    if r.decision_type == "submit_shooting_declaration":
        rows = [
            row
            for row in weapon_rows(r)
            if cast(dict[str, JsonValue], row["weapon_profile"])["name"] == "Bolt pistol"
        ]
        assert rows
        payload = cast(dict[str, JsonValue], shooting_payload(r, rows, ["foe:target"] * len(rows)))
        return s.session.submit_parameterized_payload(
            request_id=r.request_id,
            payload=payload,
            result_id=result,
        )
    assert not r.is_parameterized_submission_request(), r.decision_type
    preferred = (
        "own:body"
        if r.decision_type == "select_shooting_unit"
        else "normal"
        if r.decision_type == "select_shooting_type"
        else None
    )
    option = next(
        (o for o in r.options if o.option_id == preferred),
        next(
            (o for o in r.options if o.option_id in {"decline", "keep", "keep_all_modifiers"}),
            r.options[0],
        ),
    )
    return s.session.submit_option(
        request_id=r.request_id, option_id=option.option_id, result_id=result
    )


@pytest.mark.parametrize("within", [False, True])
@pytest.mark.parametrize("reroll", [False, True])
def test_excessive_assault_native_dice_source_and_objective_branches(
    faction_definitions: Section02Definitions, within: bool, reroll: bool
) -> None:
    d = faction_definitions
    s = scene(
        d,
        (selection(d, INFRACTORS, "body", full=True),),
        (selection(d, RANGERS, "target"),),
        phase=BattlePhase.FIGHT,
        # Preserve an observed native wound-one opportunity outside the objective.
        seed="batch02-excessive" if within else "batch02-excessive-outside:1",
    )
    assert s.state.mission_setup is not None
    marker = s.state.mission_setup.objective_markers[0]
    x, y = (marker.x_inches, marker.y_inches) if within else (19, 10)
    locate(
        s,
        "own:body",
        tuple(Pose.at(x - 3.2 + (i % 2) * 1.4, y - 2.8 + (i // 2) * 1.4) for i in range(10)),
    )
    locate(s, "foe:target", tuple(Pose.at(x, y - 2.8 + i * 1.4) for i in range(5)))
    anchor(s)
    status = s.session.advance_until_decision_or_terminal()
    for i in range(150):
        assert status.status_kind not in {
            LifecycleStatusKind.INVALID,
            LifecycleStatusKind.UNSUPPORTED,
        }, status
        r = request(status)
        p = cast(dict[str, Any], r.payload)
        if (
            r.decision_type == "select_dice_reroll"
            and isinstance(p.get("source_rule_id"), str)
            and "000004080:3" in p["source_rule_id"]
        ):
            break
        status = _step(s, r, i)
    else:
        raise AssertionError("Source-backed wound reroll was not reached")
    context = p["attack_context"]
    original = context["wound_roll_state"]["original_result"]
    physical = [e for e in events(s.session, "dice_rolled") if e.get("roll_id") == p["roll_id"]]
    assert physical == [original]
    assert original["source"] == "rng"
    assert p["current_values"] == original["values"]
    assert context["wound_roll_state"]["rerolls"] == []
    assert context["unit_instance_id"] == "own:body"
    assert context["source_payload"]["conditional_wound_reroll"] == {
        "reroll_unmodified_values": [1],
        "full_reroll_if_target_within_objective_range": True,
    }
    assert (set(p["current_values"]) != {1}) is within
    saved = s.session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(saved)
    assert restored.to_persistence_payload() == saved
    option = next(o for o in r.options if (o.option_id != "decline") == reroll)
    valid = DecisionResult.for_request(
        request=r, selected_option_id=option.option_id, result_id="batch02:chosen"
    )
    before = s.session.lifecycle.to_payload()
    assert (
        s.session.lifecycle.submit_decision(replace(valid, actor_id="opponent")).status_kind
        is LifecycleStatusKind.INVALID
    )
    assert s.session.lifecycle.to_payload() == before
    for current in (s.session, restored):
        outcome = current.submit_option(
            request_id=r.request_id, option_id=option.option_id, result_id="batch02:chosen"
        )
        assert outcome.status_kind not in {
            LifecycleStatusKind.INVALID,
            LifecycleStatusKind.UNSUPPORTED,
        }, outcome
        controller = current.lifecycle.decision_controller
        committed = [
            record for record in controller.records if record.request.request_id == r.request_id
        ]
        assert len(committed) == 1
        assert committed[0].request == r
        assert committed[0].result == valid
        pending = current.lifecycle.pending_decision_request()
        assert pending is None or pending.request_id != r.request_id

        wound_steps = [
            e
            for e in events(current, "attack_sequence_step")
            if e.get("step") == "wound"
            and e.get("attack_context_id") == context["attack_context_id"]
        ]
        assert len(wound_steps) == 1
        wound = cast(dict[str, Any], wound_steps[0]["payload"])
        resolved = cast(dict[str, Any], wound["roll_state"])
        assert resolved["original_result"] == original
        resolutions = [
            e
            for e in events(current, "dice_reroll_resolved")
            if cast(dict[str, Any], e["original_result"])["roll_id"] == original["roll_id"]
        ]
        declines = [
            e for e in events(current, "dice_reroll_declined") if e["request_id"] == r.request_id
        ]
        indices = cast(dict[str, Any], committed[0].result.payload)["selected_indices"]
        assert indices == ([0] if reroll else [])
        expected_values = list(original["values"])
        if reroll:
            assert len(resolutions) == 1
            assert declines == []
            reroll_event = cast(dict[str, Any], resolutions[0])
            assert len(reroll_event["rerolls"]) == 1
            replacement_history = reroll_event["rerolls"][0]
            assert replacement_history["decision_id"] == valid.result_id
            assert replacement_history["request_id"] == r.request_id
            assert replacement_history["selected_indices"] == indices
            replacement = replacement_history["replacement_result"]
            assert replacement["source"] == "rng"
            assert replacement["spec"]["actor_id"] == r.actor_id
            assert replacement["spec"]["roll_type"] == original["spec"]["roll_type"] + ".reroll"
            assert len(replacement["values"]) == len(indices)
            assert [
                e for e in events(current, "dice_rolled") if e["roll_id"] == replacement["roll_id"]
            ] == [replacement]
            for index, value in zip(indices, replacement["values"], strict=True):
                expected_values[index] = value
            assert reroll_event == resolved
        else:
            assert resolutions == []
            assert declines == [
                {
                    "roll_id": original["roll_id"],
                    "decision_id": valid.result_id,
                    "request_id": r.request_id,
                }
            ]
            assert resolved == context["wound_roll_state"]
            assert resolved["rerolls"] == []
        assert resolved["current_values"] == expected_values
        assert (
            resolved["current_total"]
            == sum(expected_values) + original["spec"]["expression"]["modifier"]
        )
        assert wound["unmodified_roll"] == resolved["current_total"]
        assert wound["final_roll"] == resolved["current_total"] + wound["capped_modifier"]
        assert wound["successful"] is (
            wound["unmodified_roll"] != 1 and wound["final_roll"] >= wound["target_number"]
        )
    assert restored.to_persistence_payload() == s.session.to_persistence_payload()
    assert (
        ReplayRunner.from_payload(s.session.replay_artifact(artifact_id="batch02-wound"))
        .run()
        .reproduced_exactly
    )


def test_excessive_assault_real_ranged_attack_has_no_melee_reroll(
    faction_definitions: Section02Definitions,
) -> None:
    d = faction_definitions
    s = scene(
        d,
        (selection(d, INFRACTORS, "body"),),
        (selection(d, LORD, "target"),),
        phase=BattlePhase.SHOOTING,
        seed="batch02-ranged",
    )
    locate(s, "own:body", tuple(Pose.at(10, 10 + i * 1.4) for i in range(5)))
    locate(s, "foe:target", (Pose.at(18, 10),))
    anchor(s)
    status = s.session.advance_until_decision_or_terminal()
    for i in range(150):
        assert status.status_kind not in {
            LifecycleStatusKind.INVALID,
            LifecycleStatusKind.UNSUPPORTED,
        }, status
        if s.state.current_battle_phase is not BattlePhase.SHOOTING:
            break
        status = _step(s, request(status), i)
    else:
        raise AssertionError("Native Shooting did not finish")
    records = s.session.lifecycle.decision_controller.records
    assert any(r.request.decision_type == "submit_shooting_declaration" for r in records)
    assert events(s.session, "attack_sequence_completed")
    assert not any(
        r.request.decision_type == "select_dice_reroll"
        and isinstance(r.request.payload, dict)
        and "000004080:3" in str(r.request.payload.get("source_rule_id"))
        for r in records
    )


@pytest.mark.parametrize("distance", [8, 14, 20])
def test_native_court_close_quarters_owns_ranged_distance_and_physical_profile(
    faction_definitions: Section02Definitions, distance: int
) -> None:
    d = faction_definitions
    s = scene(
        d,
        (selection(d, INFRACTORS, "body"),),
        (selection(d, LORD, "target"),),
        phase=BattlePhase.SHOOTING,
    )
    locate(s, "foe:target", (Pose.at(10 + distance, 10),))
    s.state.gain_command_points(
        player_id="owner",
        amount=1,
        source_id="batch02:constructed-cp",
        source_kind=CommandPointSourceKind.OTHER,
    )
    anchor(s)
    bundle = s.session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    context = StratagemEligibilityContext.from_state(
        state=s.state, player_id="owner", trigger_kind=TimingTriggerKind.START_PHASE
    )
    r = request(
        request_stratagem_use_from_index(
            state=s.state,
            decisions=s.session.lifecycle.decision_controller,
            index=bundle.stratagem_indexes_by_player_id["owner"],
            context=context,
            stratagem_cost_modifier_registry=bundle.stratagem_cost_modifier_registry,
        )
    )
    option = next(
        o
        for o in r.options
        if isinstance(o.payload, dict)
        and isinstance(o.payload.get("catalog_record"), dict)
        and cast(dict[str, Any], o.payload.get("catalog_record"))["definition"]["stratagem_id"]
        == "000010655005"
        and cast(dict[str, Any], o.payload.get("target_binding"))["target_unit_instance_id"]
        == "own:body"
    )
    # Capture the legitimate pending checkpoint through the public session API.
    assert request(s.session.advance_until_decision_or_terminal()) == r
    status = s.session.submit_option(
        request_id=r.request_id, option_id=option.option_id, result_id="batch02:court"
    )
    assert status.status_kind not in {
        LifecycleStatusKind.INVALID,
        LifecycleStatusKind.UNSUPPORTED,
    }, status
    use = s.state.stratagem_use_records[-1]
    assert use.stratagem_id == "000010655005"
    assert use.targeted_unit_instance_ids == ("own:body",)
    assert s.state.command_point_total("owner") == 0
    pistol = d.weapon(f"{INFRACTORS}:bolt-pistol")
    ctx = WeaponProfileModifierContext(
        s.state,
        BattlePhase.SHOOTING,
        "own:body",
        s.units["own:body"].own_model_ids()[0],
        "foe:target",
        pistol,
    )
    modified = bundle.runtime_modifier_registry.modified_weapon_profile(ctx)
    assert modified.strength.final == pistol.strength.final + int(distance <= 14)
    assert modified.armor_penetration.final == pistol.armor_penetration.final - int(distance <= 14)
    saved = s.session.to_persistence_payload()
    assert LocalGameSession.from_persistence_payload(saved).to_persistence_payload() == saved
    from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
    from warhammer40k_core.engine.effects import EffectExpirationBoundary

    s.state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.phase_end(
            battle_round=1, phase=BattlePhaseKind.SHOOTING, player_id="owner"
        )
    )
    assert bundle.runtime_modifier_registry.modified_weapon_profile(ctx) == pistol


@pytest.mark.parametrize(
    ("sheet", "height", "breach", "end_x", "action", "via_z", "accepted"),
    [
        (FULGRIM, 4.0, None, 18.0, "normal_move", 0.0, True),
        (FULGRIM, 4.001, None, 18.0, "normal_move", 0.0, False),
        (DEFILER, 8.0, None, 18.0, "normal_move", 0.0, True),
        (MAULERFIEND, 4.0, None, 18.0, "normal_move", 0.0, False),
        (MAULERFIEND, 8.0, True, 18.0, "normal_move", 0.0, True),
        (MAULERFIEND, 8.0, False, 18.0, "normal_move", 0.0, False),
        (FULGRIM, 4.0, None, 14.0, "normal_move", 0.0, False),
        (DEFILER, 8.0, None, 14.0, "normal_move", 0.0, False),
        (MAULERFIEND, 8.0, True, 14.0, "normal_move", 0.0, False),
        (FULGRIM, 4.0, None, 18.0, "advance", 0.0, True),
        (MAULERFIEND, 8.0, True, 18.0, "advance", 0.0, True),
        (MAULERFIEND, 8.0, True, 18.0, "normal_move", 1.0, False),
    ],
    ids=[
        "serpentine-inclusive-four",
        "serpentine-above-four",
        "scuttling-tall-wall",
        "mauler-no-permission",
        "sinuous-granted",
        "sinuous-declined",
        "serpentine-endpoint-blocked",
        "scuttling-endpoint-blocked",
        "sinuous-endpoint-blocked",
        "serpentine-native-advance",
        "sinuous-native-advance",
        "sinuous-vertical-transit-blocked",
    ],
)
def test_native_terrain_transit_witness_and_committed_consequences(
    terrain_definitions: Section02Definitions,
    sheet: str,
    height: float,
    breach: bool | None,
    end_x: float,
    action: str,
    via_z: float,
    accepted: bool,
    record_property: Callable[[str, str], None],
) -> None:
    s = terrain_scene(terrain_definitions, sheet, height)
    if breach is not None:
        r = breach_request(s)
        options = breach_options(r)
        assert set(options) == {"own:mover"}, "DAEMON gate must exclude Infractors and enemy"
        option = options["own:mover"] if breach else "decline_stratagem_window"
        status = s.session.submit_option(
            request_id=r.request_id, option_id=option, result_id="b03:breach"
        )
        assert status.status_kind not in {
            LifecycleStatusKind.INVALID,
            LifecycleStatusKind.UNSUPPORTED,
        }
        assert len(s.state.stratagem_use_records) == int(breach)
        assert s.state.command_point_total("owner") == int(not breach)
        if breach:
            use = s.state.stratagem_use_records[0]
            assert use.stratagem_id == SINUOUS
            assert use.targeted_unit_instance_ids == ("own:mover",)
    r = movement_request(s, action)
    capability = terrain_capability(s, "advance" if action == "advance" else "normal")
    assert capability.horizontal_terrain_feature_transit is (sheet == DEFILER or breach is True)
    assert capability.terrain_as_if_absent_height_inches == (4.0 if sheet == FULGRIM else None)
    checkpoint = (
        action == "normal_move"
        and end_x == 18
        and not via_z
        and (sheet in {FULGRIM, DEFILER} or breach is True)
    )
    sessions: tuple[LocalGameSession, ...] = (s.session,)
    if checkpoint:
        saved = s.session.to_persistence_payload()
        restored = LocalGameSession.from_persistence_payload(saved)
        forked = s.session.fork()
        assert restored.to_persistence_payload() == forked.to_persistence_payload() == saved
        # Selected shared pending checkpoints own independent mutable continuations.
        assert restored.lifecycle.state is not s.state
        assert forked.lifecycle.state is not s.state
        assert restored.lifecycle.decision_controller is not s.session.lifecycle.decision_controller
        assert forked.lifecycle.decision_controller is not s.session.lifecycle.decision_controller
        sessions = (s.session, restored, forked)
    outcomes: list[JsonValue] = []
    for session in sessions:
        state = session.lifecycle.state
        assert state is not None
        current = Scene(
            session, state, {u.unit_instance_id: u for a in state.army_definitions for u in a.units}
        )
        assert state.battlefield_state is not None
        before = state.battlefield_state
        observer = before.unit_placement_by_id("own:observer")
        count = len(session.lifecycle.decision_controller.records)
        expected_payload = path_payload(current, r, end_x, via_z=via_z)
        status = submit_path(current, r, end_x, via_z=via_z)
        committed = session.lifecycle.decision_controller.records[count:]
        assert len(committed) == 1, "The physical proposal must actually commit"
        assert committed[0].request == r
        assert committed[0].result.result_id == f"{r.request_id}:b03:path"
        assert committed[0].result.payload == expected_payload
        assert committed[0].result.request_id == r.request_id
        assert committed[0].result.actor_id == r.actor_id == "owner"
        assert committed[0].result.selected_option_id == "submit_parameterized_payload"
        from warhammer40k_core.engine.movement_proposals import MovementProposalRequest

        proposal = MovementProposalRequest.from_decision_request_payload(r.payload)
        completions = [
            e
            for e in events(session, "movement_activation_completed")
            if e.get("unit_instance_id") == "own:mover"
        ]
        assert state.battlefield_state is not None
        assert state.battlefield_state.unit_placement_by_id("own:observer") == observer
        if accepted:
            assert status.status_kind not in {
                LifecycleStatusKind.INVALID,
                LifecycleStatusKind.UNSUPPORTED,
            }, status
            assert len(completions) == 1
            assert completions[0]["request_id"] == proposal.source_decision_request_id
            assert completions[0]["result_id"] == proposal.source_decision_result_id
            assert completions[0]["proposal_request_id"] == r.request_id
            assert completions[0]["movement_phase_action"] == action
            assert completions[0]["witness"] == cast(dict[str, Any], expected_payload)["witness"]
            assert state.battlefield_state.unit_placement_by_id("own:mover").model_placements[
                0
            ].pose == Pose.at(end_x, 10)
            assert state.movement_phase_state is not None
            assert "own:mover" in state.movement_phase_state.moved_unit_ids
            pending = request(status, "select_movement_unit")
            assert "own:mover" not in {o.option_id for o in pending.options}
        else:
            assert status.status_kind is LifecycleStatusKind.INVALID, status
            assert completions == []
            assert state.battlefield_state == before
            rejected = events(session, "movement_proposal_invalid")
            assert len(rejected) == 1
            assert rejected[0]["proposal_request_id"] == r.request_id
            assert rejected[0]["result_id"] == committed[0].result.result_id
            assert rejected[0]["violation_code"] == (
                "model_cannot_be_placed_at_endpoint"
                if end_x == 14
                else "terrain_feature_transit_forbidden"
            )
            retry = session.lifecycle.pending_decision_request()
            assert retry is not None
            assert retry.decision_type == r.decision_type
            assert retry.request_id != r.request_id
            assert request(submit_path(current, retry, 9.0)).decision_type == "select_movement_unit"
            assert state.battlefield_state.unit_placement_by_id("own:mover").model_placements[
                0
            ].pose == Pose.at(9, 10)
            assert (
                len(
                    [
                        e
                        for e in events(session, "movement_activation_completed")
                        if e.get("unit_instance_id") == "own:mover"
                    ]
                )
                == 1
            )
        outcomes.append(session.to_persistence_payload())
    if checkpoint:
        assert outcomes[0] == outcomes[1] == outcomes[2]
        assert (
            LocalGameSession.from_persistence_payload(outcomes[0]).to_persistence_payload()
            == outcomes[0]
        )
        assert (
            ReplayRunner.from_payload(s.session.replay_artifact(artifact_id="batch03-terrain"))
            .run()
            .reproduced_exactly
        )
    record_property(
        "terrain_outcome",
        json.dumps(
            {
                "datasheet_id": sheet,
                "height": height,
                "breach": breach,
                "action": action,
                "via_z": via_z,
                "accepted": accepted,
                "checkpoint": checkpoint,
                "continuations": len(outcomes),
                "completions": events(s.session, "movement_activation_completed"),
                "rejections": events(s.session, "movement_proposal_invalid"),
                "decisions": [
                    d.to_payload() for d in s.session.lifecycle.decision_controller.records
                ],
            }
        ),
    )


def test_native_terrain_transit_expiry_consumption_and_strict_payload(
    terrain_definitions: Section02Definitions,
    record_property: Callable[[str, str], None],
) -> None:
    from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
    from warhammer40k_core.engine.effects import EffectExpirationBoundary
    from warhammer40k_core.engine.movement_legality import (
        MovementCapabilitySet,
        MovementLegalityError,
    )

    s = terrain_scene(terrain_definitions, MAULERFIEND, 8.0)
    r = breach_request(s)
    option = breach_options(r)["own:mover"]
    request(
        s.session.submit_option(
            request_id=r.request_id, option_id=option, result_id="b03:expiry-grant"
        )
    )
    effects = tuple(e for e in s.state.persisting_effects if SINUOUS in e.source_rule_id)
    assert len(effects) == 1
    effect = effects[0]
    assert effect.owner_player_id == "owner"
    assert effect.target_unit_instance_ids == ("own:mover",)
    assert effect.expiration.phase is BattlePhaseKind.MOVEMENT
    assert effect.expiration.player_id == "owner"
    capability = terrain_capability(s)
    assert capability.horizontal_terrain_feature_transit
    assert MovementCapabilitySet.from_payload(capability.to_payload()) == capability
    wrong = capability.to_payload()
    cast(dict[str, Any], wrong)["horizontal_terrain_feature_transit"] = 1
    with pytest.raises(MovementLegalityError, match="must be a bool"):
        MovementCapabilitySet.from_payload(wrong)
    del cast(dict[str, Any], wrong)["horizontal_terrain_feature_transit"]
    with pytest.raises(KeyError, match="horizontal_terrain_feature_transit"):
        MovementCapabilitySet.from_payload(wrong)
    # Invoke the public boundary owner at an explicit component checkpoint.
    # Automatic phase progression and replay across this constructed expiry are separate.
    assert (
        s.state.expire_persisting_effects_at_boundary(
            EffectExpirationBoundary.phase_end(
                battle_round=1, phase=BattlePhaseKind.MOVEMENT, player_id="opponent"
            )
        )
        == ()
    )
    assert terrain_capability(s).horizontal_terrain_feature_transit
    expired = s.state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.phase_end(
            battle_round=1, phase=BattlePhaseKind.MOVEMENT, player_id="owner"
        )
    )
    assert expired == effects
    assert not terrain_capability(s).horizontal_terrain_feature_transit
    r = movement_request(s)
    assert s.state.battlefield_state is not None
    before = s.state.battlefield_state
    count = len(s.session.lifecycle.decision_controller.records)
    status = submit_path(s, r, 18)
    committed = s.session.lifecycle.decision_controller.records[count:]
    assert len(committed) == 1, "The expired-permission attempt must actually commit"
    assert committed[0].request == r
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert s.state.battlefield_state == before
    rejected = events(s.session, "movement_proposal_invalid")
    assert len(rejected) == 1
    assert rejected[0]["violation_code"] == "terrain_feature_transit_forbidden"
    retry = s.session.lifecycle.pending_decision_request()
    assert retry is not None
    assert retry.request_id != r.request_id
    request(submit_path(s, retry, 9), "select_movement_unit")
    assert s.state.battlefield_state.unit_placement_by_id("own:mover").model_placements[
        0
    ].pose == Pose.at(9, 10)
    record_property(
        "expiry_outcome",
        json.dumps(
            {
                "effect": effect.to_payload(),
                "expired": [e.to_payload() for e in expired],
                "rejections": rejected,
                "completions": events(s.session, "movement_activation_completed"),
            }
        ),
    )
