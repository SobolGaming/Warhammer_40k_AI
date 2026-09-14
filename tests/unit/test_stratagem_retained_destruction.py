"""Authenticated direct and collateral reactions own suspended Stratagem packets."""

import pytest
from tests.stratagem_retention_helpers import (
    finish_stratagem_reactions,
    offered_stratagem_reaction,
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.damage_allocation import DECLINE_DESTRUCTION_REACTION_OPTION_ID
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.retained_destruction_state import retained_destructions
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    retained_attack_sources_2026_09 as retained_sources,
)


@pytest.mark.parametrize("stratagem", ["crushing-impact", "explosives"])
@pytest.mark.parametrize("accept", [False, True])
def test_stratagem_retained_reaction_checkpoints_restore_and_replay(
    stratagem: str,
    accept: bool,
) -> None:
    session, request = offered_stratagem_reaction(stratagem)
    state = session.lifecycle.state
    assert state is not None
    record = next(
        r for r in retained_destructions(state=state) if r.request_id == request.request_id
    )
    assert record.eligible_sources[0].source_rule_id == retained_sources.FOR_THE_CHAPTER_SOURCE_ID
    saved = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(saved)
    assert restored.to_persistence_payload() == saved
    option_id = (
        next(
            option.option_id
            for option in request.options
            if option.option_id != DECLINE_DESTRUCTION_REACTION_OPTION_ID
        )
        if accept
        else DECLINE_DESTRUCTION_REACTION_OPTION_ID
    )
    for current in (session, restored):
        status = current.submit_option(
            request_id=request.request_id,
            option_id=option_id,
            result_id="r48-001:reaction",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
    assert restored.to_persistence_payload() == session.to_persistence_payload()
    selected = restored.to_persistence_payload()
    resumed = LocalGameSession.from_persistence_payload(selected)
    assert resumed.to_persistence_payload() == selected
    if accept:
        state = resumed.lifecycle.state
        assert state is not None
        assert any(
            r.result_id == "r48-001:reaction" and r.is_retained
            for r in retained_destructions(state=state)
        )
    assert (
        ReplayRunner.from_payload(resumed.replay_artifact(artifact_id="r48-001:replay"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )
    finish_stratagem_reactions(resumed)
    assert resumed.lifecycle.state is not None
    assert retained_destructions(state=resumed.lifecycle.state) == ()
    completed = resumed.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(completed).to_persistence_payload() == completed
    )
    events = resumed.lifecycle.decision_controller.event_log.records
    assert sum(e.event_type == f"{stratagem.replace('-', '_')}_resolved" for e in events) == 1
    assert (
        ReplayRunner.from_payload(resumed.replay_artifact(artifact_id="r48-001:completed-replay"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )
    if accept:
        from warhammer40k_core.engine.event_log import EventLog
        from warhammer40k_core.engine.mortal_wound_destruction_routing import (
            MODEL_COMPLETED,
            pending_rule_mortal_wound_destructions,
        )
        from warhammer40k_core.engine.phase import GameLifecycleError

        receipt = next(e for e in reversed(events) if e.event_type == MODEL_COMPLETED)
        assert isinstance(receipt.payload, dict)
        for altered in (
            receipt.payload,
            {**receipt.payload, "application_id": "unrelated-packet"},
            {**receipt.payload, "model_instance_id": "unrelated-casualty"},
        ):
            log = EventLog.from_payload(
                resumed.lifecycle.decision_controller.event_log.to_payload()
            )
            log.append(MODEL_COMPLETED, altered)
            with pytest.raises(GameLifecycleError, match="completion order drifted"):
                pending_rule_mortal_wound_destructions(log.records)


@pytest.mark.parametrize("stratagem", ["crushing-impact", "explosives"])
@pytest.mark.parametrize("depth", [1, 2])
@pytest.mark.parametrize("accept", [False, True])
def test_nested_stratagem_retention_restores_ancestry_and_replays(
    stratagem: str,
    depth: int,
    accept: bool,
) -> None:
    from warhammer40k_core.engine.retained_destruction_state import destruction_cause_ancestor_ids

    session, request = offered_stratagem_reaction(stratagem, collateral_depth=depth)
    state = session.lifecycle.state
    assert state is not None
    retained = next(
        r for r in retained_destructions(state=state) if r.request_id == request.request_id
    )
    ancestors = destruction_cause_ancestor_ids(state=state, cause_id=retained.cause_id)
    assert len(ancestors) == depth
    assert retained.eligible_sources[0].source_rule_id == retained_sources.FOR_THE_CHAPTER_SOURCE_ID
    saved = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(saved)
    assert restored.to_persistence_payload() == saved
    option_id = (
        next(
            option.option_id
            for option in request.options
            if option.option_id != DECLINE_DESTRUCTION_REACTION_OPTION_ID
        )
        if accept
        else DECLINE_DESTRUCTION_REACTION_OPTION_ID
    )
    for current in (session, restored):
        status = current.submit_option(
            request_id=request.request_id, option_id=option_id, result_id="r48-002:reaction"
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
    assert restored.to_persistence_payload() == session.to_persistence_payload()
    selected = restored.to_persistence_payload()
    resumed = LocalGameSession.from_persistence_payload(selected)
    assert resumed.to_persistence_payload() == selected
    assert (
        ReplayRunner.from_payload(resumed.replay_artifact(artifact_id="r48-002:pending-replay"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )
    finish_stratagem_reactions(resumed)
    assert resumed.lifecycle.state is not None
    assert retained_destructions(state=resumed.lifecycle.state) == ()
    completed = resumed.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(completed).to_persistence_payload() == completed
    )
    assert (
        ReplayRunner.from_payload(resumed.replay_artifact(artifact_id="r48-002:completed-replay"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("stratagem", ["crushing-impact", "explosives"])
@pytest.mark.parametrize("drift", ["missing_parent", "wrong_parent", "packet", "source", "death"])
def test_nested_retention_rejects_unauthenticated_packet_ancestry(
    stratagem: str, drift: str
) -> None:
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    session, request = offered_stratagem_reaction(stratagem, collateral_depth=2)
    state = session.lifecycle.state
    assert state is not None
    retained = next(
        r for r in retained_destructions(state=state) if r.request_id == request.request_id
    )
    checkpoint = session.lifecycle.to_payload()
    saved_state = checkpoint["state"]
    assert saved_state is not None
    causes = saved_state["model_destruction_cause_authorities"]
    child = next(cause for cause in causes if cause["cause_id"] == retained.cause_id)
    parent = next(cause for cause in causes if cause["cause_id"] in child["parent_cause_ids"])
    root = next(cause for cause in causes if cause["cause_id"] in parent["parent_cause_ids"])
    if drift == "missing_parent":
        child["parent_cause_ids"] = []
    elif drift == "wrong_parent":
        # An existing earlier cause is still invalid when it is not the
        # collateral producer authenticated by the child cause's history.
        child["parent_cause_ids"] = [root["cause_id"]]
    elif drift in {"packet", "source"}:
        root["producer_context"]["source_result_id" if drift == "packet" else "source_rule_id"] = (
            "unrelated"
        )
    else:
        root["logical_death_event"]["event_id"] = "unrelated"
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(checkpoint)


@pytest.mark.parametrize("stratagem", ["crushing-impact", "explosives"])
def test_stratagem_accepted_retention_requires_its_authenticated_selection(stratagem: str) -> None:
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    session, request = offered_stratagem_reaction(stratagem)
    option = next(
        option
        for option in request.options
        if option.option_id != DECLINE_DESTRUCTION_REACTION_OPTION_ID
    )
    session.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id="r48-001:accepted"
    )
    payload = session.lifecycle.to_payload()
    event = next(
        event
        for event in payload["decisions"]["event_log"]
        if event["event_type"] == "fight_on_death_retention_selected"
    )
    body = event["payload"]
    assert isinstance(body, dict)
    body["result_id"] = "unrelated-acceptance"
    with pytest.raises(GameLifecycleError, match="exact decision"):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize("stratagem", ["crushing-impact", "explosives"])
@pytest.mark.parametrize(
    "drift", ["packet", "source", "logical_death", "record", "opening", "request"]
)
def test_stratagem_retained_reaction_rejects_unauthenticated_ownership(
    stratagem: str,
    drift: str,
) -> None:
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    session, request = offered_stratagem_reaction(stratagem)
    checkpoint = session.lifecycle.to_payload()
    current_state = session.lifecycle.state
    assert current_state is not None
    owner = next(
        r for r in retained_destructions(state=current_state) if r.request_id == request.request_id
    )
    state = checkpoint["state"]
    assert state is not None
    effects = state["persisting_effects"]
    effect = next(effect for effect in effects if effect["effect_id"] == owner.effect_id)
    body = effect["effect_payload"]
    assert isinstance(body, dict)
    record = body["destruction"]
    assert isinstance(record, dict)
    context = record["owner_context"]
    assert isinstance(context, dict)
    if drift in {"packet", "source"}:
        context["source_result_id" if drift == "packet" else "source_rule_id"] = "unrelated"
    elif drift == "logical_death":
        record["logical_death_event_id"] = "unrelated"
    elif drift == "record":
        effects.remove(effect)
    elif drift == "opening":
        event = next(
            event
            for event in checkpoint["decisions"]["event_log"]
            if event["event_type"] == "fight_on_death_retention_opened"
            and isinstance(event["payload"], dict)
            and isinstance(event["payload"]["destruction"], dict)
            and event["payload"]["destruction"]["cause_id"] == owner.cause_id
        )
        event["event_type"] = "altered_retention_opening"
    else:
        pending = checkpoint["decisions"]["queue"]["pending_requests"]
        reaction = next(item for item in pending if item["request_id"] == request.request_id)
        payload = reaction["payload"]
        assert isinstance(payload, dict)
        context = payload["destruction_context"]
        assert isinstance(context, dict)
        context["retention_sha256"] = "0" * 64
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(checkpoint)
