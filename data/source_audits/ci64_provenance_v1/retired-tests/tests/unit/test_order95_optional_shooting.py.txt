"""Selected physical weapons and ranged attacks have independent authority."""

from __future__ import annotations

import json

import pytest
from tests.empty_shooting_helpers import SHOOTER, empty_shooting_session
from tests.phase13b_shooting_declaration_helpers import _proposal_from_request

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus


@pytest.mark.parametrize("select_weapon", [False, True])
@pytest.mark.parametrize("attached", [False, True])
def test_decline_all_legal_targets_preserves_selection_without_shot(
    select_weapon: bool, attached: bool
) -> None:
    session = empty_shooting_session(reachable=True, spare=True, attached=attached)
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    assert session.lifecycle.state is not None
    unit_id = rules_unit_view_by_id(
        state=session.lifecycle.state, unit_instance_id=SHOOTER
    ).unit_instance_id
    request = session.submit_option(
        request_id=request.request_id, option_id=unit_id, result_id="order95:unit"
    ).decision_request
    assert request is not None
    request = session.submit_option(
        request_id=request.request_id, option_id="normal", result_id="order95:type"
    ).decision_request
    assert request is not None
    proposal = _proposal_from_request(request=request, target_unit_id="army-beta:enemy")
    payload = json.loads(json.dumps(proposal.to_payload()))
    for declaration in payload["declarations"]:
        declaration["target_unit_instance_id"] = None
    if not select_weapon:
        payload["declarations"] = []
    status = session.submit_parameterized_payload(
        request_id=request.request_id, payload=payload, result_id="order95:decline"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.payload
    state = session.lifecycle.state
    assert state is not None
    assert state.shooting_phase_state is not None
    assert unit_id in state.shooting_phase_state.selected_unit_ids
    assert unit_id not in state.shooting_phase_state.shot_unit_ids
    assert not state.ranged_attack_history_records
    assert not state.one_shot_weapon_use_records
    events = session.lifecycle.decision_controller.event_log.records
    assert not any(e.event_type == "unit_hidden_status_lost_after_shooting" for e in events)
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    clone = LocalGameSession.from_persistence_payload(checkpoint)
    assert clone.to_persistence_payload() == checkpoint
    for viewer in state.player_ids:
        assert clone.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert clone.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order95")).run().status
        is ReplayRunStatus.REPRODUCED
    )


def test_targetless_selected_one_shot_is_spent_without_attacks() -> None:
    session = empty_shooting_session(reachable=True, spare=True, keywords=(WeaponKeyword.ONE_SHOT,))
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    assert session.lifecycle.state is not None
    unit_id = rules_unit_view_by_id(
        state=session.lifecycle.state, unit_instance_id=SHOOTER
    ).unit_instance_id
    request = session.submit_option(
        request_id=request.request_id, option_id=unit_id, result_id="order95:unit"
    ).decision_request
    assert request is not None
    request = session.submit_option(
        request_id=request.request_id, option_id="normal", result_id="order95:type"
    ).decision_request
    assert request is not None
    payload = json.loads(
        json.dumps(
            _proposal_from_request(request=request, target_unit_id="army-beta:enemy").to_payload()
        )
    )
    for row in payload["declarations"]:
        row["target_unit_instance_id"] = None
    status = session.submit_parameterized_payload(
        request_id=request.request_id, payload=payload, result_id="order95:select"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.payload
    state = session.lifecycle.state
    assert state is not None
    assert len(state.one_shot_weapon_use_records) == len(payload["declarations"])
    assert not state.ranged_attack_history_records


@pytest.mark.parametrize("kind", ["normal", "assault", "indirect", "close_quarters"])
def test_optional_types_keep_action_restrictions(kind: str) -> None:
    from tests.optional_shooting_helpers import optional_payload, select_optional_shooting

    from warhammer40k_core.engine.activity_restrictions import has_activity_restriction
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    session = empty_shooting_session(
        reachable=True,
        spare=True,
        advanced=kind == "assault",
        vehicle=kind == "close_quarters",
        engaged=kind == "close_quarters",
        keywords=(WeaponKeyword.ASSAULT,)
        if kind == "assault"
        else (WeaponKeyword.INDIRECT_FIRE,)
        if kind == "indirect"
        else (),
    )
    request = select_optional_shooting(session, kind)
    payload = optional_payload(request)
    rows = payload["declarations"]
    assert isinstance(rows, list)
    for row in rows:
        assert isinstance(row, dict)
        row["shooting_type"] = kind
    status = session.submit_parameterized_payload(
        request_id=request.request_id, payload=payload, result_id="order95:no-targets"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.payload
    state = session.lifecycle.state
    assert state is not None
    assert has_activity_restriction(
        state=state,
        rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=SHOOTER),
        activity="completed_shooting",
    )
    assert session.fork().lifecycle.to_payload() == session.lifecycle.to_payload()


@pytest.mark.parametrize("mixed", [False, True])
def test_hazardous_counts_selected_weapons_including_declined_targets(mixed: bool) -> None:
    from tests.optional_shooting_helpers import (
        finish_selected_weapons,
        optional_payload,
        select_optional_shooting,
    )

    session = empty_shooting_session(
        reachable=True,
        spare=True,
        model_count=2 if mixed else 1,
        keywords=(WeaponKeyword.HAZARDOUS, WeaponKeyword.ONE_SHOT),
    )
    request = select_optional_shooting(session)
    payload = optional_payload(request, all_targetless=not mixed)
    rows = payload["declarations"]
    assert isinstance(rows, list)
    if mixed:
        assert len(rows) > 1
    status = session.submit_parameterized_payload(
        request_id=request.request_id, payload=payload, result_id="order95:hazardous"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.payload
    finish_selected_weapons(session, "order95:hazardous")
    state = session.lifecycle.state
    assert state is not None
    assert len(state.one_shot_weapon_use_records) == len(rows)
    events = session.lifecycle.decision_controller.event_log.records
    hazards = [e for e in events if e.event_type == "hazardous_test_resolved"]
    assert len(hazards) == 1
    assert isinstance(hazards[0].payload, dict)
    assert len(hazards[0].payload["hazardous_weapon_instance_ids"]) == len(rows)  # type: ignore[arg-type]
    assert bool(state.ranged_attack_history_records) is mixed
    assert session.fork().lifecycle.to_payload() == session.lifecycle.to_payload()
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order95-hazard"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("visibility_cache_key", "stale"),
        ("source_decision_result_id", "wrong"),
        ("battle_round", 2),
        ("player_id", "player-b"),
    ],
)
def test_invalid_empty_declarations_are_atomic(field: str, value: str | int) -> None:
    from tests.optional_shooting_helpers import optional_payload, select_optional_shooting

    session = empty_shooting_session(reachable=True, spare=True)
    request = select_optional_shooting(session)
    payload = optional_payload(request)
    payload["declarations"] = []
    payload[field] = value
    before = session.lifecycle.to_payload()
    status = session.submit_parameterized_payload(
        request_id=request.request_id, payload=payload, result_id="order95:invalid"
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before


@pytest.mark.parametrize("empty", [False, True])
def test_retained_shooting_can_decline_all_targets(empty: bool) -> None:
    from tests.optional_shooting_helpers import optional_payload
    from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
    from tests.retained_attack_helpers import pending_retained_attack

    from warhammer40k_core.engine.damage_allocation import DestructionReactionKind
    from warhammer40k_core.engine.replay import ReplayArtifact

    session, model_id = pending_retained_attack(
        reaction_kind=DestructionReactionKind.SHOOT_ON_DEATH
    )
    initial = session.lifecycle.to_payload()
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id,
        result_id="order95:retained",
        option_id="order-30-fight-on-death",
    )
    request = pending_request(session)
    assert request.decision_type == "submit_shooting_declaration"
    payload = optional_payload(request)
    if empty:
        payload["declarations"] = []
    status = session.submit_parameterized_payload(
        request_id=request.request_id, payload=payload, result_id="order95:retained-targets"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.payload
    for _ in range(60):
        state = session.lifecycle.state
        assert state is not None
        assert state.battlefield_state is not None
        if model_id in state.battlefield_state.removed_model_ids:
            break
        submit_fixture_request(session, pending_request(session))
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    assert model_id in state.battlefield_state.removed_model_ids
    assert not any(
        row.result_id == "order95:retained-targets" for row in state.ranged_attack_history_records
    )
    assert session.fork().lifecycle.to_payload() == session.lifecycle.to_payload()
    replay = ReplayRunner.from_payload(
        ReplayArtifact.capture(
            artifact_id="order95-retained",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        ).to_payload()
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("weapon_instance_id", "foreign-copy"),
        ("attacker_model_instance_id", "foreign-model"),
        ("wargear_id", "foreign-wargear"),
        ("shooting_type", "snap"),
        ("selected_weapon_ability_ids", ["invented-source"]),
        ("target_unit_instance_id", 17),
    ],
)
def test_invalid_targetless_weapon_is_atomic(field: str, value: object) -> None:
    from tests.optional_shooting_helpers import optional_payload, select_optional_shooting

    from warhammer40k_core.engine.event_log import validate_json_value

    session = empty_shooting_session(
        reachable=True, spare=True, keywords=(WeaponKeyword.ONE_SHOT, WeaponKeyword.HAZARDOUS)
    )
    request = select_optional_shooting(session)
    payload = optional_payload(request)
    rows = payload["declarations"]
    assert isinstance(rows, list)
    assert isinstance(rows[0], dict)
    rows[0][field] = validate_json_value(value)
    before = session.lifecycle.to_payload()
    status = session.submit_parameterized_payload(
        request_id=request.request_id, payload=payload, result_id="order95:bad-weapon"
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    assert session.fork().lifecycle.to_payload() == before


@pytest.mark.parametrize("contribute", [False, True])
@pytest.mark.parametrize("empty", [False, True])
def test_declined_targets_keep_every_firing_deck_cargo_restriction(
    contribute: bool, empty: bool
) -> None:
    from tests.firing_deck_helpers import PASSENGERS, TRANSPORT
    from tests.optional_firing_deck_helpers import optional_firing_deck_session

    from warhammer40k_core.engine.firing_deck_restrictions import firing_deck_restriction_payload

    session, request, proposal = optional_firing_deck_session(contribute=contribute)
    payload = json.loads(json.dumps(proposal.to_payload()))
    for row in payload["declarations"]:
        row["target_unit_instance_id"] = None
    if empty:
        payload["declarations"] = []
        payload["firing_deck_selection"] = None
    status = session.submit_parameterized_payload(
        request_id=request.request_id, payload=payload, result_id="order95:cargo"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.payload
    state = session.lifecycle.state
    assert state is not None
    effects = [e for e in state.persisting_effects if firing_deck_restriction_payload(e)]
    assert len(effects) == 1
    assert effects[0].target_unit_instance_ids == PASSENGERS
    assert (
        state.shooting_phase_state is None
        or TRANSPORT not in state.shooting_phase_state.shot_unit_ids
    )
    assert not state.ranged_attack_history_records
    assert session.fork().lifecycle.to_payload() == session.lifecycle.to_payload()
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order95-cargo")).run().status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("tamper", ["declaration", "executor", "one_shot", "profile"])
def test_restore_authenticates_selected_targetless_weapons(tamper: str) -> None:
    from tests.optional_shooting_helpers import optional_payload, select_optional_shooting

    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    session = empty_shooting_session(reachable=True, spare=True, keywords=(WeaponKeyword.ONE_SHOT,))
    request = select_optional_shooting(session)
    session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=optional_payload(request),
        result_id="order95:restore",
    )
    payload = json.loads(json.dumps(session.lifecycle.to_payload()))
    events = payload["decisions"]["event_log"]
    if tamper == "one_shot":
        payload["state"]["one_shot_weapon_use_records"] = []
    else:
        event = next(
            e
            for e in events
            if e["event_type"]
            == (
                "attack_sequence_completion_state_recorded"
                if tamper == "executor"
                else "shooting_declaration_accepted"
            )
        )
        if tamper == "profile":
            event["payload"]["weapons_without_attacks"][0]["source_profile"]["keywords"] = []
        else:
            event["payload"]["weapons_without_attacks"] = []
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(payload)


def test_targetless_duplicate_ability_choice_uses_offered_source_instances() -> None:
    from tests.optional_shooting_helpers import optional_payload, select_optional_shooting

    session = empty_shooting_session(
        reachable=True, spare=True, keywords=(WeaponKeyword.HAZARDOUS,), duplicate_hazardous=True
    )
    request = select_optional_shooting(session)
    assert isinstance(request.payload, dict)
    context = request.payload["proposal_request"]
    assert isinstance(context, dict)
    candidates = context["targetless_weapon_candidates"]
    assert isinstance(candidates, list)
    assert isinstance(candidates[0], dict)
    choices = candidates[0]["required_weapon_ability_selections"]
    assert isinstance(choices, list)
    assert isinstance(choices[0], dict)
    options = choices[0]["options"]
    assert isinstance(options, list)
    assert len(options) == 2
    assert isinstance(options[0], dict)
    payload = optional_payload(request)
    before = session.lifecycle.to_payload()
    status = session.submit_parameterized_payload(
        request_id=request.request_id, payload=payload, result_id="order95:missing-source"
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    rows = payload["declarations"]
    assert isinstance(rows, list)
    assert isinstance(rows[0], dict)
    rows[0]["selected_weapon_ability_ids"] = [options[0]["option_id"]]
    status = session.submit_parameterized_payload(
        request_id=request.request_id, payload=payload, result_id="order95:source"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.payload
    assert session.fork().lifecycle.to_payload() == session.lifecycle.to_payload()


def test_retained_targetless_hazardous_keeps_source_automatic_success() -> None:
    from tests.optional_shooting_helpers import optional_payload
    from tests.phase13b_shooting_declaration_helpers import _compact_shooting_lifecycle
    from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
    from tests.retained_attack_helpers import for_the_chapter_catalog

    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.retained_destruction_state import retained_destructions

    lifecycle, _ = _compact_shooting_lifecycle(
        catalog=for_the_chapter_catalog(hazardous=True),
        game_id="order43-chapter-0-order64-0",
        alpha_unit_ids=("intercessor-1", "intercessor-2"),
        enemy_model_count=3,
    )
    session = LocalGameSession(GameLifecycle.from_payload(lifecycle.to_payload()))
    for _ in range(30):
        request = pending_request(session)
        if request.decision_type == "select_destruction_reaction":
            break
        submit_fixture_request(session, request)
    else:
        raise AssertionError("Source-backed retained shooting did not start.")
    state = session.lifecycle.state
    assert state is not None
    retained = retained_destructions(state=state)[0]
    session.submit_option(
        request_id=request.request_id,
        result_id="chapter-accept",
        option_id=retained.eligible_sources[0].source_id,
    )
    request = pending_request(session)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=optional_payload(request),
        result_id="order95:retained-hazardous",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.payload
    for _ in range(40):
        state = session.lifecycle.state
        assert state is not None
        assert state.battlefield_state is not None
        assert session.fork().lifecycle.to_payload() == session.lifecycle.to_payload()
        if retained.model_instance_id in state.battlefield_state.removed_model_ids:
            break
        submit_fixture_request(session, pending_request(session))
    else:
        raise AssertionError("Retained targetless shooting did not clean up.")
    automatic = [
        event
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "retained_shooting_hazardous_automatically_passed"
    ]
    assert len(automatic) == 1
    assert isinstance(automatic[0].payload, dict)
    assert automatic[0].payload["model_instance_id"] == retained.model_instance_id
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="retained-hazardous"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )


def test_targetless_hazardous_wounds_resume_from_pending_allocation() -> None:
    from tests.optional_shooting_helpers import (
        finish_selected_weapons,
        optional_payload,
        select_optional_shooting,
    )

    session = empty_shooting_session(
        reachable=True,
        spare=True,
        model_count=3,
        keywords=(WeaponKeyword.HAZARDOUS,),
        game_id="order123-optional-keyword-identity-2",
    )
    request = select_optional_shooting(session)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=optional_payload(request),
        result_id="order95:hazard-checkpoint",
    )
    assert status.decision_request is not None
    assert status.decision_request.decision_type == "select_mortal_wound_model"
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    clone = LocalGameSession.from_persistence_payload(checkpoint)
    assert clone.to_persistence_payload() == checkpoint
    for viewer in ("player-a", "player-b"):
        assert clone.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert clone.events_since(EventStreamCursor(), viewer_player_id=viewer) == (
            session.events_since(EventStreamCursor(), viewer_player_id=viewer)
        )
    finish_selected_weapons(clone, "order95:casualty")
    state = clone.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    assert any(
        event.event_type == "hazardous_mortal_wounds_applied"
        for event in clone.lifecycle.decision_controller.event_log.records
    )
    assert not state.ranged_attack_history_records
    assert clone.fork().lifecycle.to_payload() == clone.lifecycle.to_payload()
    assert (
        ReplayRunner.from_payload(clone.replay_artifact(artifact_id="order95-casualty"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("field", ["visibility_cache_key", "proposal_request_id"])
def test_restore_rejects_correlated_empty_proposal_context_drift(field: str) -> None:
    from tests.optional_shooting_helpers import optional_payload, select_optional_shooting

    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    session = empty_shooting_session(reachable=True, spare=True)
    request = select_optional_shooting(session)
    proposal = optional_payload(request)
    proposal["declarations"] = []
    session.submit_parameterized_payload(
        request_id=request.request_id, payload=proposal, result_id="order95:empty-authority"
    )
    payload = json.loads(json.dumps(session.lifecycle.to_payload()))
    for record in payload["decisions"]["records"]:
        if record["result"]["result_id"] == "order95:empty-authority":
            record["result"]["payload"][field] = "tampered"
    for event in payload["decisions"]["event_log"]:
        if event["event_type"] == "decision_recorded":
            result = event["payload"]["result"]
            if result["result_id"] == "order95:empty-authority":
                result["payload"][field] = "tampered"
    with pytest.raises(GameLifecycleError, match="authority"):
        GameLifecycle.from_payload(payload)


def test_target_replacement_keeps_targetless_prefix_and_random_attack_count() -> None:
    from tests.target_replacement_helpers import replacement_scene

    from warhammer40k_core.engine.shooting_target_replacement import active_shooting_sequence

    lifecycle, units, initial_request = replacement_scene(mode="random", targetless_prefix=True)
    request: DecisionRequest | None = initial_request
    assert request is not None
    state = lifecycle.state
    assert state is not None
    before = active_shooting_sequence(state)
    assert before.weapons_without_attacks is not None
    assert len(before.weapons_without_attacks) == 1
    original_counts = tuple(pool.attacks for pool in before.attack_pools)
    session = LocalGameSession(lifecycle)
    status = session.submit_option(
        request_id=request.request_id,
        option_id=next(o.option_id for o in request.options if "old" in o.option_id),
        result_id="order95:resolve-moved",
    )
    request = status.decision_request
    assert request is not None
    assert request.decision_type == "select_target_replacement"
    session.submit_option(
        request_id=request.request_id,
        option_id=f"target:{units['new'].unit_instance_id}",
        result_id="order95:replace",
    )
    after = active_shooting_sequence(state)
    assert after.weapons_without_attacks == before.weapons_without_attacks
    # The new target is in Rapid Fire range; the original random A roll remains committed.
    assert tuple(pool.attacks for pool in after.attack_pools) == (
        original_counts[0] + 1,
        original_counts[1],
    )


@pytest.mark.parametrize("kind", ["empty", "targetless", "automatic", "hazardous"])
def test_no_attacks_preserves_source_loaded_selected_unit_obligations(kind: str) -> None:
    from tests.optional_shooting_helpers import dark_pact_optional_session, finish_selected_weapons
    from tests.psychic_modifier_helpers import pending_request

    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
        army_rule,
    )

    session = dark_pact_optional_session(
        automatic=kind == "automatic", hazardous=kind == "hazardous"
    )
    request: DecisionRequest | None = pending_request(session)
    assert request is not None
    request = session.submit_option(
        request_id=request.request_id, option_id="army-alpha:defiler-attacker", result_id="unit"
    ).decision_request
    assert request is not None
    request = session.submit_option(
        request_id=request.request_id,
        option_id=army_rule.SHOOTING_LETHAL_HITS_HOOK_ID,
        result_id="grant",
    ).decision_request
    assert request is not None
    status = session.submit_option(
        request_id=request.request_id, option_id="normal", result_id="type"
    )
    if kind != "automatic":
        request = status.decision_request
        assert request is not None
        proposal = _proposal_from_request(
            request=request,
            target_unit_id="army-beta:enemy",
            weapon_profile_id="000000969:excruciator-cannon:standard",
        ).to_payload()
        payload = json.loads(json.dumps(proposal))
        for row in payload["declarations"]:
            row["target_unit_instance_id"] = None
        if kind == "empty":
            payload["declarations"] = []
        status = session.submit_parameterized_payload(
            request_id=request.request_id, payload=payload, result_id="declared"
        )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert session.fork().lifecycle.to_payload() == session.lifecycle.to_payload()
    if kind == "hazardous":
        assert status.decision_request is not None
        assert status.decision_request.decision_type == "resolve_sequencing_order"
    finish_selected_weapons(session, "dark-pact")
    events = session.lifecycle.decision_controller.event_log.records
    assert sum(e.event_type == "chaos_space_marines_dark_pact_resolved" for e in events) == 1
    assert sum(e.event_type == "hazardous_test_resolved" for e in events) == (kind == "hazardous")
    state = session.lifecycle.state
    assert state is not None
    assert not state.ranged_attack_history_records
    assert session.fork().lifecycle.to_payload() == session.lifecycle.to_payload()
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order95-pact")).run().status
        is ReplayRunStatus.REPRODUCED
    )


def test_source_loaded_shadow_legion_keeps_selected_obligation_classification() -> None:
    from dataclasses import replace

    from tests.phase11c_command_phase_helpers import battle_state, phase11c_config
    from tests.unit_keyword_helpers import with_unit_keywords

    from warhammer40k_core.core.faction_aliases import CHAOS_DAEMONS_FACTION_ID
    from warhammer40k_core.engine.faction_content.runtime import (
        build_runtime_content_bundle_for_armies,
    )
    from warhammer40k_core.engine.generic_rule_ability_registry_defaults import (
        DEFAULT_GENERIC_RULE_ABILITY_REGISTRY,
    )
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        faction_shadow_legion_ir_support_2026_27 as source,
    )

    state = battle_state()
    armies = tuple(
        replace(
            army,
            detachment_selection=replace(
                army.detachment_selection,
                faction_id=CHAOS_DAEMONS_FACTION_ID,
                detachment_ids=("shadow-legion",),
            ),
            units=tuple(
                with_unit_keywords(
                    unit,
                    keywords=(*unit.keywords, "SHADOW LEGION", "UNDIVIDED"),
                    faction_keywords=("LEGIONES DAEMONICA",),
                )
                for unit in army.units
            ),
        )
        if army.player_id == "player-a"
        else army
        for army in state.army_definitions
    )
    bundle = build_runtime_content_bundle_for_armies(config=phase11c_config(), armies=armies)
    descriptors = tuple(
        row
        for row in DEFAULT_GENERIC_RULE_ABILITY_REGISTRY.attack_sequence_completed_abilities
        if row.coverage_descriptor_id == source.SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID
    )
    assert len(descriptors) == 1
    assert not descriptors[0].requires_attacks
    bindings = tuple(
        row
        for row in bundle.attack_sequence_completed_hook_registry.all_bindings()
        if row.source_id == descriptors[0].source_rule_id
    )
    assert bindings
    assert all(not binding.requires_attacks for binding in bindings)
