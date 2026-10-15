from __future__ import annotations

from typing import cast

from tests.shared.category_migration.order97_facade_evidence import (
    HEAVY_RULE_ID,
    BattlePhase,
    JsonValue,
    LifecycleStatusKind,
    LocalGameSession,
    MovementProposalPayload,
    MovementProposalRequest,
    PathWitness,
    Pose,
    _proposal_from_request,
    assert_heavy_checkpoint,
    assert_persistence_viewers_replay,
    clause_session,
    complete_heavy_attack,
    heavy_session,
    isclose,
    json,
    leading_first_translation_paths,
    move_heavy_unit,
    pending_request,
    pytest,
    reach_second_player_movement,
    sqrt,
    submit_fixture_request,
    validate_json_value,
)


@pytest.mark.parametrize("advance", [False, True])
@pytest.mark.parametrize("distance", [1.0, 3.0, 3.1])
def test_d09_native_heavy_short_move_and_long_move(advance: bool, distance: float) -> None:
    session = heavy_session()
    move_heavy_unit(session, advance=advance, distance=distance)
    session = assert_heavy_checkpoint(session)
    pools = complete_heavy_attack(session, advance=advance)
    restored = assert_heavy_checkpoint(session)
    expected = int(distance <= 3.0)
    assert pools
    assert all(pool["hit_roll_modifier"] == expected for pool in pools)
    assert all(
        (HEAVY_RULE_ID in cast(list[str], pool["targeting_rule_ids"])) is bool(expected)
        for pool in pools
    )
    hits = [
        event.payload
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "attack_sequence_step"
        and isinstance(event.payload, dict)
        and event.payload.get("step") == "hit"
    ]
    assert hits
    for hit in hits:
        assert isinstance(hit, dict)
        roll = cast(dict[str, JsonValue], hit["payload"])
        assert roll["capped_modifier"] == expected
        assert roll["final_roll"] == cast(int, roll["unmodified_roll"]) + expected
    before = session.to_persistence_payload()
    for branch in (restored, session.fork()):
        request = pending_request(branch)
        assert request.options
        options = [
            option
            for option in request.options
            if option.option_id.startswith("complete_") or "decline" in option.option_id
        ]
        option = options[0] if options else request.options[0]
        status = branch.submit_option(
            request_id=request.request_id,
            option_id=option.option_id,
            result_id="d09-continue",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
        assert session.to_persistence_payload() == before
        assert_heavy_checkpoint(branch)


@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.parametrize("second_player", [False, True])
@pytest.mark.parametrize("returning_model", [False, True])
def test_d09_every_physical_model_counts_return_path(
    attached: bool,
    second_player: bool,
    returning_model: bool,
) -> None:
    session = heavy_session(attached=attached)
    if second_player:
        reach_second_player_movement(session)
    move_heavy_unit(session, advance=True, distance=1.0, returning_model=returning_model)
    restored = assert_heavy_checkpoint(session)
    pools = complete_heavy_attack(restored, advance=True)
    assert pools
    expected = int(not returning_model)
    assert all(pool["hit_roll_modifier"] == expected for pool in pools)
    assert all(
        (HEAVY_RULE_ID in cast(list[str], pool["targeting_rule_ids"])) is bool(expected)
        for pool in pools
    )
    assert_heavy_checkpoint(restored)


__all__: list[str] = []
__all__ += ["BattlePhase", "LocalGameSession", "MovementProposalPayload"]
__all__ += ["MovementProposalRequest", "PathWitness", "Pose", "_proposal_from_request"]
__all__ += ["assert_persistence_viewers_replay", "clause_session", "isclose", "json"]
__all__ += ["leading_first_translation_paths", "sqrt", "submit_fixture_request"]
__all__ += ["validate_json_value"]
