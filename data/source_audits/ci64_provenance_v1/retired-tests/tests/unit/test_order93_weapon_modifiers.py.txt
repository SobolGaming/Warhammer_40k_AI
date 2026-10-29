from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from tests.generic_modifier_helpers import generic_effect
from tests.order93_modifier_helpers import modifier_session
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.random_profile_values import RandomProfileValue
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    RangeProfile,
    RangeProfileKind,
    WeaponProfile,
)
from warhammer40k_core.engine.effects import EffectExpiration
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind


@pytest.mark.parametrize("random_attacks", [False, True])
@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
def test_attacks_selection_precedes_declaration_and_preserves_source_operations(
    phase: BattlePhase,
    random_attacks: bool,
) -> None:
    session = modifier_session(
        phase,
        weapon_profile_transform=(
            (
                lambda profile: replace(
                    profile, attack_profile=AttackProfile.dice(DiceExpression(1, 6))
                )
            )
            if random_attacks
            else None
        ),
    )
    state = session.lifecycle.state
    assert state is not None
    for name, delta in (("a-attacks", 2), ("b-attacks", -2)):
        effect = generic_effect(
            effect_id=name,
            owner_player_id="player-a",
            target_unit_instance_ids=("army-alpha:intercessor-1",),
            target_kind="this_unit",
            effect_kind="modify_characteristic",
            parameters={"characteristic": "attacks", "delta": delta},
        )
        payload = cast(dict[str, JsonValue], effect.effect_payload)
        context = cast(dict[str, JsonValue], payload["context"])
        state.record_persisting_effect(
            replace(
                effect,
                started_phase=phase,
                effect_payload={**payload, "context": {**context, "phase": phase.value}},
                expiration=EffectExpiration.end_phase(
                    battle_round=1, phase=phase, player_id="player-a"
                ),
            )
        )
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(session.lifecycle.to_payload()))
    selected = False
    for _ in range(45):
        request = pending_request(session)
        if request.decision_type == "select_modifier_ignores":
            payload = cast(dict[str, JsonValue], request.payload)
            subject = cast(dict[str, JsonValue], payload["subject"])
            if subject["kind"] == "attacks_characteristic":
                selected = True
                operation_rows = cast(list[dict[str, JsonValue]], payload["modifiers"])
                decided = cast(list[str], payload["decided_modifier_ids"])
                operation = cast(dict[str, JsonValue], operation_rows[len(decided)]["operation"])
                prefix = "ignore:" if cast(int, operation["operand"]) < 0 else "keep:"
                matching = tuple(
                    option for option in request.options if option.option_id.startswith(prefix)
                )
                option = (
                    matching[0]
                    if matching
                    else next(
                        option
                        for option in request.options
                        if option.option_id == prefix.rstrip(":") + "-remaining"
                    )
                )
                status = session.submit_option(
                    request_id=request.request_id,
                    result_id=f"{request.request_id}:source-choice",
                    option_id=option.option_id,
                )
                assert status.status_kind is not LifecycleStatusKind.INVALID, status
                continue
        if request.decision_type in {"submit_shooting_declaration", "submit_melee_declaration"}:
            assert selected, "A modifiers must be chosen before declaration or A dice."
            assert (
                GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
                == session.lifecycle.to_payload()
            )
            submit_fixture_request(session, request)
            current = session.lifecycle.state
            assert current is not None
            owner = (
                current.shooting_phase_state
                if phase is BattlePhase.SHOOTING
                else current.fight_phase_state
            )
            assert owner is not None
            sequence = owner.attack_sequence
            assert sequence is not None
            profile = sequence.attack_pools[0].weapon_profile.attack_profile
            if random_attacks:
                assert profile.dice_expression == DiceExpression(1, 6)
                assert profile.resolve_value(4) == 6
            else:
                assert profile.fixed_attacks == 3
            assert len(profile.modifiers) == 2
            assert len(profile.ignored_modifier_ids) == 1
            return
        submit_fixture_request(session, request)
    raise AssertionError("No weapon declaration boundary found.")


@pytest.mark.parametrize("random_range", [False, True])
def test_range_selection_precedes_target_legality_and_preserves_selected_roll(
    random_range: bool,
) -> None:
    def transform(profile: WeaponProfile) -> WeaponProfile:
        if profile.range_profile.kind is RangeProfileKind.MELEE:
            return profile
        value = (
            RangeProfile.random(
                RandomProfileValue(
                    Characteristic.RANGE, DiceExpression(1, 6, 30), "source:range-dice"
                )
            )
            if random_range
            else RangeProfile.distance(36)
        )
        return replace(
            profile,
            source_ids=tuple(
                sorted({*profile.source_ids, "source:range-dice", "source:range-penalty"})
            ),
            range_profile=value,
        )

    session = modifier_session(weapon_profile_transform=transform)
    state = session.lifecycle.state
    assert state is not None
    state.record_persisting_effect(
        generic_effect(
            effect_id="range-penalty",
            owner_player_id="player-a",
            target_unit_instance_ids=("army-alpha:intercessor-1",),
            target_kind="this_unit",
            effect_kind="modify_characteristic",
            parameters={"characteristic": "range", "delta": -100},
        )
    )
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(session.lifecycle.to_payload()))
    selected = False
    for _ in range(35):
        request = pending_request(session)
        if request.decision_type == "select_modifier_ignores":
            payload = cast(dict[str, JsonValue], request.payload)
            subject = cast(dict[str, JsonValue], payload["subject"])
            if subject["kind"] == "range_characteristic":
                selected = True
                before_rolls = tuple(
                    event
                    for event in session.lifecycle.decision_controller.event_log.records
                    if event.event_type == "random_weapon_range_evaluated"
                )
                status = session.submit_option(
                    request_id=request.request_id,
                    result_id=f"{request.request_id}:restore-range",
                    option_id="ignore-remaining",
                )
                assert status.status_kind is not LifecycleStatusKind.INVALID, status
                assert (
                    tuple(
                        event
                        for event in session.lifecycle.decision_controller.event_log.records
                        if event.event_type == "random_weapon_range_evaluated"
                    )
                    == before_rolls
                )
                continue
        if request.decision_type == "submit_shooting_declaration":
            assert selected
            assert (
                GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
                == session.lifecycle.to_payload()
            )
            submit_fixture_request(session, request)
            state = session.lifecycle.state
            assert state is not None
            assert state.shooting_phase_state is not None
            sequence = state.shooting_phase_state.attack_sequence
            assert sequence is not None
            value = sequence.attack_pools[0].weapon_profile.range_profile
            assert value.distance_inches is not None
            assert value.distance_inches >= 30
            if random_range:
                assert value.random_value is not None
                assert value.random_value.ignored_modifier_ids == ("range-penalty:skill:0",)
            else:
                assert value.modifier_trace is not None
                assert value.modifier_trace.ignored_modifier_ids == ("range-penalty:skill:0",)
            return
        submit_fixture_request(session, request)
    raise AssertionError("No Range declaration boundary found.")


@pytest.mark.parametrize("characteristic", ["range", "attacks"])
def test_retarget_reenters_modifier_owner_for_changed_source_applicability(
    characteristic: str,
) -> None:
    from tests.core_stratagem_helpers import _replace_unit_poses
    from tests.phase13b_shooting_declaration_helpers import (
        _catalog_with_replaced_bolt_profiles,
        _compact_intercessor_catalog,
        _proposal_from_request,
        _shooting_lifecycle,
        _weapon_profile_by_wargear,
    )

    from warhammer40k_core.core.attributes import CharacteristicValue
    from warhammer40k_core.core.weapon_profiles import DamageProfile, WeaponKeyword
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.geometry.pose import Pose

    raw = _weapon_profile_by_wargear(wargear_id="core-bolt-rifle", weapon_profile_id=None)
    first = replace(
        raw,
        profile_id="order93:lethal-first",
        attack_profile=AttackProfile.fixed(8),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 20),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -6),
        damage_profile=DamageProfile.fixed(99),
        keywords=(WeaponKeyword.TORRENT,),
        abilities=(),
    )
    second = replace(
        raw,
        profile_id="order93:random-second",
        attack_profile=AttackProfile.dice(DiceExpression(1, 6)),
        keywords=(),
        abilities=(),
    )
    catalog = _compact_intercessor_catalog(_catalog_with_replaced_bolt_profiles((first, second)))
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("source",),
        alpha_unit_specs=(
            ("source", "core-intercessor-like-infantry", "core-intercessor-like", 2),
        ),
        enemy_unit_specs=tuple(
            (key, "core-intercessor-like-infantry", "core-intercessor-like", 1)
            for key in ("old", "new")
        ),
        catalog=catalog,
        game_id=f"order93-source-retarget-{characteristic}",
    )
    state = lifecycle.state
    assert state is not None
    for key, y in (("old", 35), ("new", 25)):
        _replace_unit_poses(
            state, unit_instance_id=units[key].unit_instance_id, poses=(Pose.at(22, y),)
        )
    source = units["source"].unit_instance_id
    for name, kind, parameters in (
        (
            "retarget-ignore",
            "grant_ability",
            {"ability": "modifier_ignore_permission", "selection": "any_or_all"},
        ),
        (
            "retarget-penalty",
            "modify_characteristic",
            {
                "characteristic": characteristic,
                "delta": -100,
                "target_constraint": "target_unit_below_starting_strength",
            },
        ),
    ):
        state.record_persisting_effect(
            generic_effect(
                effect_id=name,
                owner_player_id="player-a",
                target_unit_instance_ids=(source,),
                target_kind="this_unit",
                effect_kind=kind,
                parameters=cast(dict[str, JsonValue], parameters),
            )
        )
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))
    initial = session.lifecycle.to_payload()
    requests = 0
    declared = False
    for _ in range(70):
        request = pending_request(session)
        if request.decision_type == "submit_shooting_declaration":
            proposal = _proposal_from_request(
                request=request,
                target_unit_id=units["old"].unit_instance_id,
                weapon_profile_id=first.profile_id,
            )
            row = cast(dict[str, JsonValue], request.payload)
            weapons = cast(
                list[dict[str, JsonValue]],
                cast(dict[str, JsonValue], row["proposal_request"])["available_weapons"],
            )
            primary = proposal.declarations[0]
            other = next(
                w
                for w in weapons
                if w["model_instance_id"] != primary.attacker_model_instance_id
                and w["weapon_profile_id"] == second.profile_id
            )
            proposal = replace(
                proposal,
                declarations=(
                    primary,
                    replace(
                        primary,
                        attacker_model_instance_id=cast(str, other["model_instance_id"]),
                        weapon_instance_id=cast(str, other["weapon_instance_id"]),
                        weapon_profile_id=second.profile_id,
                    ),
                ),
            )
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id="order93:two-weapons",
                payload=validate_json_value(proposal.to_payload()),
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
            declared = True
            continue
        if request.decision_type == "select_modifier_ignores":
            assert declared
            subject = cast(
                dict[str, JsonValue], cast(dict[str, JsonValue], request.payload)["subject"]
            )
            assert subject["kind"] == f"{characteristic}_characteristic"
            requests += 1
            dice_before = tuple(
                event
                for event in session.lifecycle.decision_controller.event_log.records
                if event.event_type == "dice_rolled"
            )
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:retarget-ignore",
                option_id="ignore-remaining",
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
            assert (
                tuple(
                    event
                    for event in session.lifecycle.decision_controller.event_log.records
                    if event.event_type == "dice_rolled"
                )
                == dice_before
            )
            continue
        if request.decision_type == "select_target_replacement":
            assert requests > 0
            assert (
                GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
                == session.lifecycle.to_payload()
            )
            status = session.submit_option(
                request_id=request.request_id,
                result_id="order93:retarget-new",
                option_id=f"target:{units['new'].unit_instance_id}",
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
            assert (
                GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
                == session.lifecycle.to_payload()
            )
            from warhammer40k_core.engine.replay import (
                ReplayArtifact,
                ReplayRunner,
                ReplayRunStatus,
            )

            replay = ReplayRunner(
                ReplayArtifact.capture(
                    artifact_id=f"order93-retarget-{characteristic}",
                    final_lifecycle=session.lifecycle,
                    initial_lifecycle_payload=initial,
                )
            ).run()
            assert replay.status is ReplayRunStatus.REPRODUCED, replay
            return
        if request.decision_type == "select_attack_weapon_group":
            options = tuple(
                option
                for option in request.options
                if "order93:lethal-first" in str(option.payload)
            )
            option = options[0] if options else request.options[0]
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:first-group",
                option_id=option.option_id,
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
            continue
        submit_fixture_request(session, request)
    raise AssertionError("Changed source applicability did not reach a replacement choice.")


@pytest.mark.parametrize("attached", [False, True])
def test_fixed_melee_split_uses_selected_attacks_and_physical_owner(attached: bool) -> None:
    from tests.random_melee_helpers import declaration_payload, random_melee_session

    session = random_melee_session(random=False, fixed_attacks=1, attached=attached)
    state = session.lifecycle.state
    assert state is not None
    for name, kind, parameters in (
        (
            "split-ignore",
            "grant_ability",
            {"ability": "modifier_ignore_permission", "selection": "any_or_all"},
        ),
        ("a-split-bonus", "modify_characteristic", {"characteristic": "attacks", "delta": 2}),
        ("b-split-penalty", "modify_characteristic", {"characteristic": "attacks", "delta": -2}),
    ):
        effect = generic_effect(
            effect_id=name,
            owner_player_id="player-a",
            target_unit_instance_ids=("army-alpha:attacker",),
            target_kind="this_unit",
            effect_kind=kind,
            parameters=cast(dict[str, JsonValue], parameters),
        )
        payload = cast(dict[str, JsonValue], effect.effect_payload)
        context = cast(dict[str, JsonValue], payload["context"])
        state.record_persisting_effect(
            replace(
                effect,
                started_phase=BattlePhase.FIGHT,
                expiration=EffectExpiration.end_of_battle(),
                effect_payload={**payload, "context": {**context, "phase": "fight"}},
            )
        )
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(session.lifecycle.to_payload()))
    for _ in range(45):
        request = pending_request(session)
        if request.decision_type == "select_modifier_ignores":
            payload = cast(dict[str, JsonValue], request.payload)
            decided = cast(list[str], payload["decided_modifier_ids"])
            option_id = (
                next(
                    (
                        option.option_id
                        for option in request.options
                        if option.option_id.startswith("keep:")
                    ),
                    "ignore-remaining",
                )
                if not decided
                else "ignore-remaining"
            )
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:split-choice",
                option_id=option_id,
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
            continue
        if request.decision_type == "submit_melee_declaration":
            body = cast(dict[str, JsonValue], request.payload)
            proposal = cast(dict[str, JsonValue], body["proposal_request"])
            row = cast(list[dict[str, JsonValue]], proposal["available_weapons"])[0]
            assert row["fixed_attacks"] == 3
            assert row["maximum_declared_targets"] == 3
            payload = declaration_payload(request)
            payload["declarations"] = [
                {
                    "attacker_model_instance_id": row["model_instance_id"],
                    **{
                        key: row[key]
                        for key in ("weapon_instance_id", "wargear_id", "weapon_profile_id")
                    },
                    "target_allocations": [
                        {"target_unit_instance_id": "army-beta:target-a", "attacks": 1},
                        {"target_unit_instance_id": "army-beta:target-b", "attacks": 2},
                    ],
                }
            ]
            status = session.submit_parameterized_payload(
                request_id=request.request_id, result_id="order93:fixed-split", payload=payload
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
            assert (
                GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
                == session.lifecycle.to_payload()
            )
            return
        submit_fixture_request(session, request)
    raise AssertionError("Selected fixed Attacks did not reach melee splitting.")
