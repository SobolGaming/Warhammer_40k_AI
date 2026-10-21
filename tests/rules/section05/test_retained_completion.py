"""A real retained melee attack precedes destruction cleanup, including Deadly Demise."""

import copy
from dataclasses import replace
from typing import cast

import pytest

from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
from tests.retained_attack_helpers import pending_retained_attack
from tests.support.section02_consumers import attack_pool
from tests.support.section02_fixtures import LORD_EXULTANT, Section02Definitions
from tests.support.section05_retention import retain, terminal_retention
from tests.support.section05_sequence import payloads
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.attack_completion_authority import (
    completed_attack_sequence,
)
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    attack_sequence_hit_roll_spec,
    resolve_attack_sequence_until_blocked,
)
from warhammer40k_core.engine.attack_sequence_model import AttackSequenceHooks
from warhammer40k_core.engine.damage_allocation import unit_by_id
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.lifecycle_state_queries import active_attack_sequence_for_state
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.retained_demise_removal import (
    finalize_attack_casualty,
    require_retained_attack_removed_cause,
)
from warhammer40k_core.engine.retained_destruction_cleanup import (
    begin_retained_destruction_cleanup,
)
from warhammer40k_core.engine.retained_destruction_state import retained_destructions
from warhammer40k_core.engine.retained_model_presence import (
    model_is_present_on_battlefield,
)
from warhammer40k_core.engine.weapon_instances import (
    equipped_weapon_profile_instances_for_model,
)


@pytest.mark.parametrize("demise", [False, True])
def test_real_retained_melee_finishes_before_removal(
    section05_definitions: Section02Definitions, demise: bool
) -> None:
    d = section05_definitions
    state, target, decisions, request = terminal_retention(
        d, demise=demise, distance=2.0, melee=True
    )
    retain(state, decisions, request)
    mid = target.own_model_ids()[0]
    retained = unit_by_id(state=state, unit_instance_id=target.unit_instance_id)
    enemy = unit_by_id(state=state, unit_instance_id="section02:subject")
    physical = next(
        w
        for w in equipped_weapon_profile_instances_for_model(
            model=retained.own_models[0], army_catalog=d.package.army_catalog
        )
        if w.wargear_id == f"{LORD_EXULTANT}:close-combat-weapon"
    )
    pool = replace(
        attack_pool(retained, enemy, physical.weapon_profile, physical.wargear_id),
        weapon_instance_id=physical.weapon_instance_id,
    )
    sequence = AttackSequence(
        "s05:retained-fight",
        "opponent",
        target.unit_instance_id,
        (pool,),
        source_phase=BattlePhase.FIGHT,
    )
    dice = DiceRollManager("physical-misses")
    results = tuple(
        dice.roll_fixed(
            attack_sequence_hit_roll_spec(
                weapon_profile_id=pool.weapon_profile_id,
                attack_context_id=f"s05:retained-fight:pool-001:attack-{i:03d}",
                attacker_player_id="opponent",
            ),
            (1,),
        ).original_result
        for i in range(1, pool.attacks + 1)
    )
    assert model_is_present_on_battlefield(state=state, model_instance_id=mid)
    assert not payloads(decisions, "model_destroyed")
    remaining, _, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "s05:retained-fight",
            event_log=decisions.event_log,
            injected_results=results,
        ),
    )
    assert remaining is None
    assert status is None
    assert completed_attack_sequence(
        event_records=decisions.event_log.records, sequence_id=sequence.sequence_id
    ).is_complete
    assert model_is_present_on_battlefield(state=state, model_instance_id=mid)
    assert not payloads(decisions, "model_destroyed")
    assert (
        begin_retained_destruction_cleanup(
            state=state,
            decisions=decisions,
            reason="unit_fight_completed",
            unit_instance_id=target.unit_instance_id,
        )
        is None
    )
    assert not model_is_present_on_battlefield(state=state, model_instance_id=mid)
    events = decisions.event_log.records
    completed = next(i for i, e in enumerate(events) if e.event_type == "attack_sequence_completed")
    removed = next(i for i, e in enumerate(events) if e.event_type == "model_destroyed")
    assert completed < removed
    if demise:
        reaction = next(
            i for i, e in enumerate(events) if e.event_type == "destruction_reaction_resolved"
        )
        # Adopted FAQ20: complete Fight, remove this casualty, then Deadly Demise.
        assert completed < removed < reaction


@pytest.fixture(scope="module")
def retained_demise_fnp_checkpoint() -> tuple[LocalGameSession, str]:
    session, mid = pending_retained_attack(deadly_demise=True, cleanup_feel_no_pain=True)
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id,
        result_id="external:b2-accept-retention",
        option_id="order-30-fight-on-death",
    )
    for _ in range(45):
        request = pending_request(session)
        if request.decision_type == "select_feel_no_pain":
            return session, mid
        submit_fixture_request(session, request)
    raise AssertionError("Native retained Deadly Demise did not request FNP.")


@pytest.mark.parametrize("select_source", [False, True])
def test_faq20_removed_demise_fnp_restores_forks_replays_and_continues(
    retained_demise_fnp_checkpoint: tuple[LocalGameSession, str], select_source: bool
) -> None:
    original, mid = retained_demise_fnp_checkpoint
    checkpoint = original.lifecycle.to_payload()
    restored = LocalGameSession(lifecycle=GameLifecycle.from_payload(copy.deepcopy(checkpoint)))
    branches = (restored, restored.fork())
    final_payloads: list[GameLifecyclePayload] = []
    for session in branches:
        state = session.lifecycle.state
        assert state is not None
        assert state.battlefield_state is not None
        assert mid in state.battlefield_state.removed_model_ids
        assert mid not in state.battlefield_state.placed_model_ids()
        request = pending_request(session)
        choice = next(
            o for o in request.options if (o.option_id == "order-30-fnp") == select_source
        )
        result = DecisionResult.for_request(
            request=request, result_id="faq20:fnp", selected_option_id=choice.option_id
        )
        session.submit_option(
            request_id=request.request_id, result_id=result.result_id, option_id=choice.option_id
        )
        for _ in range(35):
            events = session.lifecycle.decision_controller.event_log.records
            if payloads(
                session.lifecycle.decision_controller, "fight_on_death_destruction_completed"
            ):
                break
            submit_fixture_request(session, pending_request(session))
        else:
            raise AssertionError("Retained demise continuation did not finish.")
        final = session.lifecycle.to_payload()
        assert GameLifecycle.from_payload(final).to_payload() == final
        assert (
            sum(
                e.event_type == "model_destroyed"
                and isinstance(e.payload, dict)
                and e.payload.get("model_instance_id") == mid
                for e in events
            )
            == 1
        )
        removed = next(
            i
            for i, e in enumerate(events)
            if e.event_type == "model_destroyed"
            and isinstance(e.payload, dict)
            and e.payload.get("model_instance_id") == mid
        )
        requested = next(
            i
            for i, e in enumerate(events)
            if e.event_type == "decision_requested"
            and isinstance(e.payload, dict)
            and e.payload.get("request_id") == request.request_id
        )
        completed = next(
            i
            for i, e in enumerate(events)
            if e.event_type == "fight_on_death_destruction_completed"
        )
        assert removed < requested < completed
        assert not retained_destructions(state=state)
        artifact = ReplayArtifact.capture(
            artifact_id=f"faq20:removed-fnp:{select_source}",
            initial_lifecycle_payload=checkpoint,
            final_lifecycle=session.lifecycle,
        )
        replay = ReplayRunner.from_payload(artifact.to_payload()).run()
        assert replay.status is ReplayRunStatus.REPRODUCED, replay
        final_payloads.append(final)
        # A repeated result has no authority after its request was consumed.
        with pytest.raises(DecisionError):
            session.lifecycle.submit_decision(result)
        assert session.lifecycle.to_payload() == final
    assert final_payloads[0] == final_payloads[1]
    assert original.lifecycle.to_payload() == checkpoint


def _object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


@pytest.mark.parametrize(
    "tamper",
    [
        "missing_cause",
        "wrong_cause",
        "wrong_owner",
        "wrong_request",
        "wrong_damage",
        "fabricated_consumption",
        "missing_retention",
        "wrong_source",
    ],
)
def test_faq20_removed_demise_fnp_rejects_forged_checkpoint(
    retained_demise_fnp_checkpoint: tuple[LocalGameSession, str], tamper: str
) -> None:
    original, mid = retained_demise_fnp_checkpoint
    checkpoint = original.lifecycle.to_payload()
    forged = _object(copy.deepcopy(validate_json_value(checkpoint)))
    state = _object(forged["state"])
    authorities = state["model_destruction_cause_authorities"]
    assert isinstance(authorities, list)
    cause = next(_object(c) for c in authorities if _object(c)["model_instance_id"] == mid)
    decisions = _object(forged["decisions"])
    queue = _object(decisions["queue"])
    requests = queue["pending_requests"]
    assert isinstance(requests, list)
    assert len(requests) == 1
    request = _object(requests[0])
    context = _object(_object(_object(request["payload"])["lost_wound_context"])["source_context"])
    if tamper == "missing_cause":
        authorities.remove(cause)
    elif tamper == "wrong_cause":
        cause["cause_id"] = "faq20:wrong-cause"
    elif tamper == "wrong_owner":
        cause["physical_unit_instance_id"] = "army-alpha:intercessor-1"
    elif tamper == "wrong_request":
        request["actor_id"] = "player-b"
    elif tamper == "wrong_damage":
        _object(context["damage_application"])["requested_damage"] = 99
    elif tamper == "fabricated_consumption":
        cause["model_destroyed_event"] = None
    elif tamper == "missing_retention":
        effects = state["persisting_effects"]
        assert isinstance(effects, list)
        state["persisting_effects"] = [
            e
            for e in effects
            if _object(_object(e)["effect_payload"]).get("effect_kind")
            != "retained_model_destruction"
        ]
    else:
        _object(context["source"])["source_id"] = "faq20:unowned-demise"
    assert forged != validate_json_value(checkpoint)
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, forged))
    assert original.lifecycle.to_payload() == checkpoint
    assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint


def test_faq20_removed_demise_cause_reuse_is_read_only_and_expires(
    retained_demise_fnp_checkpoint: tuple[LocalGameSession, str],
) -> None:
    original, _mid = retained_demise_fnp_checkpoint
    session = original.fork()
    state = session.lifecycle.state
    assert state is not None
    sequence = active_attack_sequence_for_state(state)
    assert sequence is not None
    assert sequence.current_pending_attack_destruction is not None
    pending = sequence.current_pending_attack_destruction
    before = session.lifecycle.to_payload()
    emissions = tuple(
        finalize_attack_casualty(
            state=state,
            decisions=session.lifecycle.decision_controller,
            attack_sequence=sequence,
            damage=pending.damage_application,
            saving_throw_payload=pending.saving_throw_payload,
            feel_no_pain=pending.feel_no_pain,
            hooks=AttackSequenceHooks.empty(),
        )
        for _ in range(2)
    )
    assert emissions[0] == emissions[1]
    assert session.lifecycle.to_payload() == before
    cause = require_retained_attack_removed_cause(
        state=state, attack_sequence=sequence, damage=pending.damage_application
    )
    assert cause.model_destroyed_event is not None
    assert cause.model_destroyed_event.event_id == emissions[0].model_destroyed_event_id
    submit_fixture_request(session, pending_request(session))
    final = session.lifecycle.to_payload()
    assert not retained_destructions(state=state)
    with pytest.raises(GameLifecycleError, match="consumed cause"):
        require_retained_attack_removed_cause(
            state=state, attack_sequence=sequence, damage=pending.damage_application
        )
    assert session.lifecycle.to_payload() == final
