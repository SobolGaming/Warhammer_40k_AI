from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.phase15d_fight_resolution_helpers import melee_fixture, melee_proposal, melee_request
from tests.random_melee_helpers import (
    declaration_payload,
    melee_boundary,
    random_melee_session,
    single_target_commitment_payload,
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.fight_resolution import (
    MeleeTargetAllocation,
    MeleeWeaponDeclaration,
    validate_melee_declaration_rules,
)
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.geometry.pose import Pose


def test_random_melee_commits_weapon_before_generating_attacks() -> None:
    session = random_melee_session()
    request = melee_boundary(session)
    assert request.decision_type == "select_melee_weapon"
    assert not any(
        event.event_type == "random_characteristic_rolled"
        for event in session.lifecycle.decision_controller.event_log.records
    )
    status = session.submit_option(
        request_id=request.request_id,
        option_id=request.options[0].option_id,
        result_id="commit-weapon",
    )
    assert status.decision_request is not None
    assert status.decision_request.decision_type == "submit_melee_declaration"
    assert (
        sum(
            event.event_type == "random_characteristic_rolled"
            for event in session.lifecycle.decision_controller.event_log.records
        )
        == 1
    )


def _committed() -> tuple[LocalGameSession, DecisionRequest, dict[str, JsonValue]]:
    session = random_melee_session()
    request = melee_boundary(session)
    status = session.submit_option(
        request_id=request.request_id,
        option_id=request.options[0].option_id,
        result_id="commit-weapon",
    )
    assert status.decision_request is not None
    request = status.decision_request
    body = cast(dict[str, JsonValue], request.payload)
    commitment = cast(dict[str, JsonValue], body["melee_weapon_commitment"])
    weapons = cast(list[dict[str, JsonValue]], commitment["weapons"])
    assert len(weapons) == 1
    return session, request, weapons[0]


def _split(
    request: DecisionRequest, budget: dict[str, JsonValue], counts: list[int]
) -> dict[str, JsonValue]:
    payload = declaration_payload(request)
    payload["declarations"] = [
        {
            "attacker_model_instance_id": budget["model_instance_id"],
            **{
                key: budget[key]
                for key in ("wargear_id", "weapon_instance_id", "weapon_profile_id")
            },
            "target_allocations": [
                {"target_unit_instance_id": f"army-beta:target-{suffix}", "attacks": count}
                for suffix, count in zip(("a", "b"), counts, strict=False)
            ],
        }
    ]
    return payload


@pytest.mark.parametrize("invalid", ["overspend", "zero", "bool", "profile", "weapon", "stale"])
def test_invalid_splits_preserve_commitment_and_rng(invalid: str) -> None:
    session, request, budget = _committed()
    count = cast(int, budget["base_attacks"])
    payload = _split(request, budget, [count, 1])
    declarations = cast(list[dict[str, JsonValue]], payload["declarations"])
    if invalid == "zero":
        payload = _split(request, budget, [0, count])
    elif invalid == "bool":
        allocations = cast(list[dict[str, JsonValue]], declarations[0]["target_allocations"])
        allocations[0]["attacks"] = True
    elif invalid == "profile":
        declarations[0]["weapon_profile_id"] = "wrong-profile"
    elif invalid == "weapon":
        declarations[0]["weapon_instance_id"] = "wrong-weapon"
    elif invalid == "stale":
        payload["proposal_request_id"] = "old-request"
    before = session.lifecycle.to_payload()
    status = session.submit_parameterized_payload(
        request_id=request.request_id, result_id="invalid-split", payload=payload
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before


def test_recorded_split_conserves_stored_roll_and_restores_and_replays() -> None:
    session, request, budget = _committed()
    count = cast(int, budget["base_attacks"])
    assert count > 1
    pending = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(pending)))
    assert restored.to_persistence_payload() == pending
    for viewer in ("player-a", "player-b"):
        session.view(viewer_player_id=viewer)
    payload = _split(request, budget, [count - 1, 1])
    status = session.submit_parameterized_payload(
        request_id=request.request_id, result_id="valid-split", payload=payload
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    state = session.lifecycle.state
    assert state is not None
    assert state.fight_phase_state is not None
    sequence = state.fight_phase_state.attack_sequence
    assert sequence is not None
    assert [pool.attacks for pool in sequence.attack_pools] == [count - 1, 1]
    assert {pool.weapon_instance_id for pool in sequence.attack_pools} == {
        cast(str, budget["weapon_instance_id"])
    }
    assert (
        sum(
            event.event_type == "random_characteristic_rolled"
            for event in session.lifecycle.decision_controller.event_log.records
        )
        == 1
    )
    checkpoint = session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(
            json.loads(json.dumps(checkpoint))
        ).to_persistence_payload()
        == checkpoint
    )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order92-split"))
        .run()
        .reproduced_exactly
    )


def _all_committed(session: LocalGameSession) -> tuple[DecisionRequest, list[dict[str, JsonValue]]]:
    request = melee_boundary(session)
    index = 0
    while request.decision_type == "select_melee_weapon":
        assert not any(
            e.event_type == "random_characteristic_rolled"
            for e in session.lifecycle.decision_controller.event_log.records
        )
        status = session.submit_option(
            request_id=request.request_id,
            option_id=next(
                option.option_id for option in request.options if option.payload is not None
            ),
            result_id=f"commit-{index}",
        )
        assert status.decision_request is not None
        request = status.decision_request
        index += 1
    body = cast(dict[str, JsonValue], request.payload)
    commitment = cast(dict[str, JsonValue], body["melee_weapon_commitment"])
    return request, cast(list[dict[str, JsonValue]], commitment["weapons"])


@pytest.mark.parametrize(("extra", "models"), [(True, 1), (False, 2), (True, 2)])
def test_all_weapons_commit_before_dice_and_each_budget_is_conserved(
    extra: bool, models: int
) -> None:
    session = random_melee_session(extra=extra, attacker_models=models)
    request, budgets = _all_committed(session)
    assert len(budgets) == models * (2 if extra else 1)
    assert len({cast(str, b["weapon_instance_id"]) for b in budgets}) == len(budgets)
    assert len(
        {cast(str, cast(dict[str, JsonValue], b["roll"])["scope_id"]) for b in budgets}
    ) == len(budgets)
    payload = declaration_payload(request)
    payload["declarations"] = [
        cast(
            list[JsonValue],
            _split(request, budget, [cast(int, budget["base_attacks"])])["declarations"],
        )[0]
        for budget in budgets
    ]
    declarations = cast(list[dict[str, JsonValue]], payload["declarations"])
    first = cast(list[dict[str, JsonValue]], declarations[0]["target_allocations"])[0]
    second = cast(list[dict[str, JsonValue]], declarations[1]["target_allocations"])[0]
    first["attacks"] = cast(int, first["attacks"]) + 1
    second["attacks"] = cast(int, second["attacks"]) - 1
    before = session.lifecycle.to_payload()
    status = session.submit_parameterized_payload(
        request_id=request.request_id, result_id="wrong-owner-total", payload=payload
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    first["attacks"] = budgets[0]["base_attacks"]
    second["attacks"] = budgets[1]["base_attacks"]
    status = session.submit_parameterized_payload(
        request_id=request.request_id, result_id="conserved", payload=payload
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    state = session.lifecycle.state
    assert state is not None
    assert state.fight_phase_state is not None
    sequence = state.fight_phase_state.attack_sequence
    assert sequence is not None
    assert sum(pool.attacks for pool in sequence.attack_pools) == sum(
        cast(int, budget["base_attacks"]) for budget in budgets
    )
    assert {pool.weapon_instance_id for pool in sequence.attack_pools} == {
        cast(str, budget["weapon_instance_id"]) for budget in budgets
    }
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="multi-weapon"))
        .run()
        .reproduced_exactly
    )


def test_multiple_profiles_commit_exactly_one_without_exposing_another_profile() -> None:
    session = random_melee_session(profiles=True)
    request, budgets = _all_committed(session)
    assert len(budgets) == 1
    proposal = cast(
        dict[str, JsonValue], cast(dict[str, JsonValue], request.payload)["proposal_request"]
    )
    rows = cast(list[dict[str, JsonValue]], proposal["available_weapons"])
    assert len(rows) == 1
    assert rows[0]["weapon_profile_id"] == budgets[0]["weapon_profile_id"]
    session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="one-profile",
        payload=_split(request, budgets[0], [cast(int, budgets[0]["base_attacks"])]),
    )
    checkpoint = session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(
            json.loads(json.dumps(checkpoint))
        ).to_persistence_payload()
        == checkpoint
    )


@pytest.mark.parametrize("split", [False, True])
def test_random_cleave_is_a_single_target_bonus_never_a_splittable_budget(split: bool) -> None:
    session = random_melee_session(cleave=True)
    request, budgets = _all_committed(session)
    budget = budgets[0]
    count = cast(int, budget["base_attacks"])
    assert count > 1
    counts = [count - 1, 1] if split else [count + 2]
    payload = _split(request, budget, counts)
    if split:
        before = session.lifecycle.to_payload()
        invalid = _split(request, budget, [count + 1, 1])
        assert (
            session.submit_parameterized_payload(
                request_id=request.request_id, result_id="split-cleave", payload=invalid
            ).status_kind
            is LifecycleStatusKind.INVALID
        )
        assert session.lifecycle.to_payload() == before
    status = session.submit_parameterized_payload(
        request_id=request.request_id, result_id="cleave", payload=payload
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    state = session.lifecycle.state
    assert state is not None
    assert state.fight_phase_state is not None
    sequence = state.fight_phase_state.attack_sequence
    assert sequence is not None
    assert [pool.attacks for pool in sequence.attack_pools] == counts
    assert (
        sum(
            e.event_type == "random_characteristic_rolled"
            for e in session.lifecycle.decision_controller.event_log.records
        )
        == 1
    )


@pytest.mark.parametrize(
    "field", ["base_attacks", "weapon_instance_id", "convention_id", "missing_roll", "duplicate"]
)
def test_restore_rejects_changed_commitment_authority(field: str) -> None:
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    session, _, _ = _committed()
    snapshot = session.lifecycle.to_payload()
    events = snapshot["decisions"]["event_log"]
    event = next(e for e in events if e["event_type"] == "melee_weapons_committed")
    body = cast(dict[str, JsonValue], event["payload"])
    weapons = cast(list[dict[str, JsonValue]], body["weapons"])
    if field == "base_attacks":
        weapons[0][field] = cast(int, weapons[0][field]) + 1
    elif field == "weapon_instance_id":
        weapons[0][field] = "different-physical-weapon"
    elif field == "convention_id":
        body[field] = "invented-convention"
    elif field == "missing_roll":
        weapons[0]["roll"] = None
    else:
        weapons.append(weapons[0])
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(snapshot)


@pytest.mark.parametrize("decline", [False, True])
def test_replacement_moves_only_the_unresolved_allocation_and_never_rerolls(decline: bool) -> None:
    from tests.core_stratagem_helpers import _replace_unit_poses

    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.replay import ReplayArtifact
    from warhammer40k_core.geometry.pose import Pose

    session, request, budget = _committed()
    count = cast(int, budget["base_attacks"])
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="replace-split",
        payload=_split(request, budget, [count - 1, 1]),
    )
    assert status.decision_request is not None
    request = status.decision_request
    assert request.decision_type == "select_resolve_target_unit"
    state = session.lifecycle.state
    assert state is not None
    _replace_unit_poses(state, unit_instance_id="army-beta:target-a", poses=(Pose.at(50, 50),))
    initial = session.lifecycle.to_payload()
    status = session.submit_option(
        request_id=request.request_id,
        option_id=request.options[0].option_id,
        result_id="select-resolution",
    )
    assert status.decision_request is not None
    request = status.decision_request
    assert request.decision_type == "select_target_replacement"
    pending = session.lifecycle.to_payload()
    session = LocalGameSession(GameLifecycle.from_payload(pending))
    assert session.lifecycle.to_payload() == pending
    session.submit_option(
        request_id=request.request_id,
        option_id="decline_target_replacement" if decline else "target:army-beta:target-b",
        result_id="replace-target",
    )
    event = next(
        e
        for e in session.lifecycle.decision_controller.event_log.records
        if e.event_type == "target_replacement_resolved"
    )
    body = cast(dict[str, JsonValue], event.payload)
    pools = cast(list[dict[str, JsonValue]], body["attack_pools"])
    assert [pool["attacks"] for pool in pools] == [count - 1, 1]
    assert body["forgone_pool_indices"] == ([0] if decline else [])
    assert (
        sum(
            e.event_type == "random_characteristic_rolled"
            for e in session.lifecycle.decision_controller.event_log.records
        )
        == 1
    )
    checkpoint = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint
    artifact = ReplayArtifact.capture(
        artifact_id="melee-replacement",
        final_lifecycle=session.lifecycle,
        initial_lifecycle_payload=initial,
    )
    assert ReplayRunner.from_payload(artifact.to_payload()).run().reproduced_exactly


def test_attached_unit_commits_physical_components_and_keeps_canonical_actor() -> None:
    session = random_melee_session(attached=True)
    request, budgets = _all_committed(session)
    payload = declaration_payload(request)
    assert payload["unit_instance_id"] == "attached-unit:army-alpha:bodyguard"
    payload["declarations"] = [
        cast(
            list[JsonValue],
            _split(request, budget, [cast(int, budget["base_attacks"])])["declarations"],
        )[0]
        for budget in budgets
    ]
    status = session.submit_parameterized_payload(
        request_id=request.request_id, result_id="attached", payload=payload
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    checkpoint = session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(
            json.loads(json.dumps(checkpoint))
        ).to_persistence_payload()
        == checkpoint
    )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="attached-random-melee"))
        .run()
        .reproduced_exactly
    )


@pytest.mark.parametrize("cleave", [False, True])
def test_split_completes_through_shared_attack_decisions_and_replays(cleave: bool) -> None:
    from tests.psychic_modifier_helpers import submit_fixture_request

    session = random_melee_session(cleave=cleave)
    request, budgets = _all_committed(session)
    budget = budgets[0]
    count = cast(int, budget["base_attacks"])
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="complete-split",
        payload=_split(request, budget, [count + 2] if cleave else [count - 1, 1]),
    )
    for _ in range(100):
        if any(
            e.event_type == "melee_attack_sequence_completed"
            for e in session.lifecycle.decision_controller.event_log.records
        ):
            break
        assert status.decision_request is not None
        request = status.decision_request
        submit_fixture_request(session, request)
        status = session.advance_until_decision_or_terminal()
    else:
        raise AssertionError("Committed split did not complete.")
    checkpoint = session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(
            json.loads(json.dumps(checkpoint))
        ).to_persistence_payload()
        == checkpoint
    )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="completed-split"))
        .run()
        .reproduced_exactly
    )


@pytest.mark.parametrize("delta", [-10, 2])
def test_generic_attacks_modifiers_derive_counts_without_changing_physical_roll(delta: int) -> None:
    from dataclasses import replace

    from tests.generic_modifier_helpers import generic_effect

    from warhammer40k_core.engine.effects import EffectExpiration
    from warhammer40k_core.engine.phase import BattlePhase

    session = random_melee_session()
    state = session.lifecycle.state
    assert state is not None
    effect = generic_effect(
        effect_id="order92-attacks",
        owner_player_id="player-a",
        target_unit_instance_ids=("army-alpha:attacker",),
        target_kind="this_unit",
        effect_kind="modify_characteristic",
        parameters={"characteristic": "attacks", "delta": delta},
    )
    body = cast(dict[str, JsonValue], effect.effect_payload)
    context = cast(dict[str, JsonValue], body["context"])
    state.record_persisting_effect(
        replace(
            effect,
            started_phase=BattlePhase.FIGHT,
            expiration=EffectExpiration.end_of_battle(),
            effect_payload={**body, "context": {**context, "phase": "fight"}},
        )
    )
    request, budgets = _all_committed(session)
    budget = budgets[0]
    total = max(1, cast(int, budget["base_attacks"]) + delta)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="modified-budget",
        payload=_split(request, budget, [total]),
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    event = next(
        e
        for e in session.lifecycle.decision_controller.event_log.records
        if e.event_type == "melee_declaration_accepted"
    )
    pools = cast(
        list[dict[str, JsonValue]], cast(dict[str, JsonValue], event.payload)["attack_pools"]
    )
    assert pools[0]["attacks"] == total
    assert cast(dict[str, JsonValue], budget["roll"])["value"] == budget["base_attacks"]


@pytest.mark.parametrize("cleave", [False, True])
@pytest.mark.parametrize("tamper", ["attacks", "model", "wargear", "profile"])
def test_restore_authenticates_omitted_single_target_counts_and_physical_source(
    cleave: bool, tamper: str
) -> None:
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    session = random_melee_session(cleave=cleave, attacker_models=2)
    request, budgets = _all_committed(session)
    payload = declaration_payload(request)
    declarations: list[JsonValue] = []
    for index, budget in enumerate(budgets):
        declaration = cast(
            list[dict[str, JsonValue]], _split(request, budget, [1])["declarations"]
        )[0]
        declaration["target_allocations"] = [
            {"target_unit_instance_id": f"army-beta:target-{'a' if index == 0 else 'b'}"}
        ]
        declarations.append(declaration)
    payload["declarations"] = declarations
    status = session.submit_parameterized_payload(
        request_id=request.request_id, result_id="omitted-counts", payload=payload
    )
    assert status.decision_request is not None
    assert status.decision_request.decision_type == "select_resolve_target_unit"
    snapshot = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(snapshot).to_payload() == snapshot
    events = snapshot["decisions"]["event_log"]
    event = next(e for e in events if e["event_type"] == "melee_declaration_accepted")
    event_pool = cast(
        list[dict[str, JsonValue]], cast(dict[str, JsonValue], event["payload"])["attack_pools"]
    )[0]
    state = cast(dict[str, JsonValue], snapshot["state"])
    fight = cast(dict[str, JsonValue], state["fight_phase_state"])
    active = cast(dict[str, JsonValue], fight["attack_sequence"])
    state_pool = cast(list[dict[str, JsonValue]], active["attack_pools"])[0]
    for pool in (event_pool, state_pool):
        if tamper == "attacks":
            pool["attacks"] = cast(int, pool["attacks"]) + 20
        elif tamper == "model":
            pool["attacker_model_instance_id"] = "invented-model"
        elif tamper == "wargear":
            pool["wargear_id"] = "invented-wargear"
        else:
            profile = cast(dict[str, JsonValue], pool["weapon_profile"])
            profile["name"] = "forged profile"
    with pytest.raises(GameLifecycleError, match="Melee pool differs"):
        GameLifecycle.from_payload(snapshot)


def test_unengaged_random_leader_does_not_change_fixed_bodyguard_declaration() -> None:
    from tests.core_stratagem_helpers import _replace_unit_poses
    from tests.phase15c_fight_order_helpers import submit_minimal_melee_declaration

    from warhammer40k_core.geometry.pose import Pose

    session = random_melee_session(attached=True, fixed_bodyguard=True)
    state = session.lifecycle.state
    assert state is not None
    _replace_unit_poses(state, unit_instance_id="army-alpha:attacker", poses=(Pose.at(21, 16.5),))
    request = melee_boundary(session)
    assert request.decision_type == "submit_melee_declaration"
    body = cast(dict[str, JsonValue], request.payload)
    assert "melee_weapon_commitment" not in body
    rows = cast(
        list[dict[str, JsonValue]],
        cast(dict[str, JsonValue], body["proposal_request"])["available_weapons"],
    )
    assert all("melee_target_facts" not in row for row in rows)
    status = submit_minimal_melee_declaration(
        session.lifecycle, request=request, result_id="fixed-bodyguard"
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert any(
        e.event_type == "melee_declaration_accepted"
        for e in session.lifecycle.decision_controller.event_log.records
    )


# Order 112: mandatory equipped Extra Attacks selection.
@pytest.mark.parametrize("extra_only", [False, True])
@pytest.mark.parametrize("copies", [1, 2])
def test_each_physical_extra_weapon_is_required(extra_only: bool, copies: int) -> None:
    catalog, ruleset, scenario, attacker, target, _ = melee_fixture(include_extra_attacks=True)
    catalog = replace(
        catalog,
        wargear=tuple(
            replace(
                gear,
                weapon_profiles=(
                    gear.weapon_profiles[0],
                    replace(gear.weapon_profiles[0], profile_id="core-extra-blade:alternate"),
                ),
            )
            if gear.wargear_id == "core-extra-blade"
            else gear
            for gear in catalog.wargear
        ),
    )
    gear = (() if extra_only else ("core-leader-blade",)) + ("core-extra-blade",) * copies
    attacker = replace(
        attacker,
        own_models=tuple(replace(model, wargear_ids=gear) for model in attacker.own_models),
    )
    scenario = replace(
        scenario, armies=(replace(scenario.armies[0], units=(attacker,)), scenario.armies[1])
    )
    request = melee_request(catalog=catalog, ruleset=ruleset, scenario=scenario, attacker=attacker)
    declarations = tuple(
        MeleeWeaponDeclaration(
            attacker_model_instance_id=cast(str, row["model_instance_id"]),
            wargear_id=cast(str, row["wargear_id"]),
            weapon_profile_id=cast(str, row["weapon_profile_id"]),
            weapon_instance_id=cast(str, row["weapon_instance_id"]),
            target_allocations=(MeleeTargetAllocation(target.unit_instance_id),),
        )
        for row in request.available_weapons
        if isinstance(row, dict) and row["weapon_profile_id"] != "core-extra-blade:standard"
    )
    assert len(declarations) == copies + (not extra_only)
    for selected in (declarations[:-1], declarations):
        validation = validate_melee_declaration_rules(
            scenario=scenario,
            ruleset_descriptor=ruleset,
            request=request,
            proposal=melee_proposal(request=request, attacker=attacker, declarations=selected),
            army_catalog=catalog,
        )
        assert validation.is_valid is (selected == declarations)
        if selected and selected != declarations:
            assert validation.violations[0].violation_code == "melee_extra_attacks_weapon_required"


@pytest.mark.parametrize("destroyed", [False, True])
def test_ineligible_extra_bearer_does_not_require_a_declaration(destroyed: bool) -> None:
    catalog, ruleset, scenario, attacker, target, _ = melee_fixture(include_extra_attacks=True)
    primary = attacker.own_models[0]
    extra = replace(
        primary,
        model_instance_id=f"{attacker.unit_instance_id}:extra-bearer",
        wargear_ids=("core-extra-blade",),
        wounds_remaining=0 if destroyed else primary.current_wounds,
    )
    attacker = replace(attacker, own_models=(primary, extra))
    placement = scenario.battlefield_state.unit_placement_by_id(attacker.unit_instance_id)
    extra_placement = replace(
        placement.model_placements[0],
        model_instance_id=extra.model_instance_id,
        pose=Pose.at(10, 10) if destroyed else Pose.at(30, 30),
    )
    scenario = replace(
        scenario,
        armies=(replace(scenario.armies[0], units=(attacker,)), scenario.armies[1]),
        battlefield_state=scenario.battlefield_state.with_unit_placement(
            placement.with_model_placements((*placement.model_placements, extra_placement))
        ),
    )
    request = melee_request(catalog=catalog, ruleset=ruleset, scenario=scenario, attacker=attacker)
    declaration = MeleeWeaponDeclaration(
        attacker_model_instance_id=primary.model_instance_id,
        wargear_id="core-leader-blade",
        weapon_profile_id="core-leader-blade:standard",
        target_allocations=(MeleeTargetAllocation(target.unit_instance_id),),
    )
    assert validate_melee_declaration_rules(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        request=request,
        proposal=melee_proposal(request=request, attacker=attacker, declarations=(declaration,)),
        army_catalog=catalog,
    ).is_valid


@pytest.mark.parametrize("spent", [False, True])
def test_mandatory_extra_selection_obeys_physical_one_shot_availability(spent: bool) -> None:
    from warhammer40k_core.core.weapon_profiles import WeaponKeyword
    from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
    from warhammer40k_core.engine.fight_resolution import available_melee_weapons_payloads
    from warhammer40k_core.engine.phase import BattlePhase

    session = random_melee_session(random=False, extra=True)
    melee_boundary(session)
    state = session.lifecycle.state
    assert state is not None
    catalog = session.lifecycle.config.army_catalog
    assert catalog is not None
    catalog = replace(
        catalog,
        wargear=tuple(
            replace(
                gear,
                weapon_profiles=tuple(
                    replace(profile, keywords=(*profile.keywords, WeaponKeyword.ONE_SHOT))
                    for profile in gear.weapon_profiles
                ),
            )
            if gear.wargear_id == "order92-extra"
            else gear
            for gear in catalog.wargear
        ),
    )
    scenario = battlefield_scenario_for_state(state=state)
    attacker = scenario.armies[0].unit_by_id("army-alpha:attacker")
    ruleset = session.lifecycle.config.ruleset_descriptor
    request = melee_request(catalog=catalog, ruleset=ruleset, scenario=scenario, attacker=attacker)
    extra = next(
        row
        for row in request.available_weapons
        if isinstance(row, dict) and row["wargear_id"] == "order92-extra"
    )
    assert isinstance(extra, dict)
    if spent:
        state.record_one_shot_weapon_selected(
            weapon_instance_id=cast(str, extra["weapon_instance_id"]),
            model_instance_id=cast(str, extra["model_instance_id"]),
            wargear_id="order92-extra",
            weapon_profile_id=cast(str, extra["weapon_profile_id"]),
            source_phase=BattlePhase.FIGHT,
            selection_id="order112:previous-use",
        )
    request = replace(
        request,
        available_weapons=available_melee_weapons_payloads(
            scenario=scenario,
            ruleset_descriptor=ruleset,
            unit=attacker,
            army_catalog=catalog,
            state=state,
            source_decision_result_id=request.source_decision_result_id,
        ),
    )
    declaration = MeleeWeaponDeclaration(
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        wargear_id="core-leader-blade",
        weapon_profile_id="core-leader-blade:standard",
        target_allocations=(MeleeTargetAllocation("army-beta:target-a"),),
    )
    result = validate_melee_declaration_rules(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        request=request,
        proposal=melee_proposal(request=request, attacker=attacker, declarations=(declaration,)),
        army_catalog=catalog,
        state=state,
    )
    assert result.is_valid is spent
    if not spent:
        assert result.violations[0].violation_code == "melee_extra_attacks_weapon_required"


@pytest.mark.parametrize("random", [False, True])
@pytest.mark.parametrize("attached", [False, True])
def test_extra_weapons_cannot_be_skipped_and_retry_restores_and_replays(
    random: bool, attached: bool
) -> None:
    from warhammer40k_core.adapters.event_stream import EventStreamCursor

    session = random_melee_session(random=random, extra=True, attached=attached, profiles=True)
    request = melee_boundary(session)
    index = 0
    while request.decision_type == "select_melee_weapon":
        assert all(option.payload is not None for option in request.options)
        assert "skip_extra" not in {option.option_id for option in request.options}
        assert not any(
            event.event_type == "random_characteristic_rolled"
            for event in session.lifecycle.decision_controller.event_log.records
        )
        pending = session.to_persistence_payload()
        session = LocalGameSession.from_persistence_payload(json.loads(json.dumps(pending)))
        assert session.to_persistence_payload() == pending
        status = session.submit_option(
            request_id=request.request_id,
            option_id=request.options[-1].option_id,
            result_id=f"order112-commit-{index}",
        )
        assert status.decision_request is not None
        request = status.decision_request
        index += 1
    assert request.decision_type == "submit_melee_declaration"
    payload = single_target_commitment_payload(request)
    declarations = cast(list[dict[str, JsonValue]], payload["declarations"])
    # Fixed-A requests expose alternative profiles; select exactly one per weapon.
    selected: dict[str, dict[str, JsonValue]] = {}
    for declaration in declarations:
        selected[cast(str, declaration["weapon_instance_id"])] = declaration
    declarations = list(selected.values())
    assert len(declarations) == 2
    assert {row["wargear_id"] for row in declarations} == {"core-leader-blade", "order92-extra"}
    payload["declarations"] = cast(list[JsonValue], declarations)
    before = session.to_persistence_payload()
    pending = LocalGameSession.from_persistence_payload(json.loads(json.dumps(before)))
    assert pending.to_persistence_payload() == before
    invalid = dict(
        payload, declarations=[row for row in declarations if row["wargear_id"] != "order92-extra"]
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id, result_id="order112-omitted-extra", payload=invalid
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.to_persistence_payload() == before
    fork = session.fork()
    status = session.submit_parameterized_payload(
        request_id=request.request_id, result_id="order112-complete", payload=payload
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert fork.to_persistence_payload() == before
    state = session.lifecycle.state
    assert state is not None
    assert state.fight_phase_state is not None
    sequence = state.fight_phase_state.attack_sequence
    assert sequence is not None
    assert {pool.weapon_instance_id for pool in sequence.attack_pools} == set(selected)
    assert sum(
        event.event_type == "random_characteristic_rolled"
        for event in session.lifecycle.decision_controller.event_log.records
    ) == (2 if random else 0)
    accepted = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(accepted)))
    assert restored.to_persistence_payload() == accepted
    for viewer in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert restored.events_since(EventStreamCursor(), viewer_player_id=viewer) == (
            session.events_since(EventStreamCursor(), viewer_player_id=viewer)
        )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order112-extra"))
        .run()
        .reproduced_exactly
    )
