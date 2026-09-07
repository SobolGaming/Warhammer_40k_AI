from __future__ import annotations

from dataclasses import replace

import pytest
from tests.phase13b_shooting_declaration_helpers import (
    _attack_pool_for_test,
    _first_weapon_profile,
    _shooting_lifecycle,
    _state,
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.attack_sequence import _psychic_attack_modifier_ignore_request
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.rule_ir_weapon_modifiers import rule_ir_modified_weapon_profile
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.shooting_targets import (
    BENEFIT_OF_COVER_RULE_ID,
    PLUNGING_FIRE_RULE_ID,
)


def test_cancelling_cover_and_plunging_fire_preserve_psychic_choice() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    attacker, defender = units["intercessor-1"], units["enemy"]
    profile = replace(_first_weapon_profile(lifecycle, attacker), keywords=(WeaponKeyword.PSYCHIC,))
    pool = replace(
        _attack_pool_for_test(
            attacker=attacker, defender=defender, weapon_profile=profile, attacks=1
        ),
        targeting_rule_ids=(BENEFIT_OF_COVER_RULE_ID, PLUNGING_FIRE_RULE_ID),
    )
    request = _psychic_attack_modifier_ignore_request(
        state=_state(lifecycle),
        pool=pool,
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_context_id="psychic-identity:pool-001:attack-001",
        source_phase=BattlePhase.SHOOTING,
        runtime_modifier_registry=RuntimeModifierRegistry(),
    )
    assert request is not None, "Individual modifiers must survive a cancelling net total."
    assert isinstance(request.payload, dict)
    assert isinstance(request.payload["modifiers"], list)
    assert len(request.payload["modifiers"]) == 2


@pytest.mark.parametrize("deltas", [(-1, 1), (1, -1)])
def test_weapon_skill_operations_combine_before_bounds(deltas: tuple[int, int]) -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    profile = replace(
        _first_weapon_profile(lifecycle, units["intercessor-1"]),
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 2),
    )
    for delta in deltas:
        profile = rule_ir_modified_weapon_profile(
            parameters={"characteristic": "ballistic_skill", "delta": delta},
            profile=profile,
            source_id=f"psychic-identity:skill:{delta}",
            modifier_id=f"psychic-identity:skill:{delta}",
        )
    assert profile.skill.final == 2
    assert len(profile.skill.applied_modifier_ids) == 2


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
def test_facade_individual_subset_preserves_sources_restore_and_replay(phase: BattlePhase) -> None:
    from tests.psychic_modifier_helpers import (
        pending_request,
        psychic_session,
        reach_psychic_request,
    )

    from warhammer40k_core.adapters.event_stream import EventStreamCursor
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.attack_sequence_psychic_modifiers import selection_from_payload
    from warhammer40k_core.engine.event_log import canonical_json
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus

    session = psychic_session(phase)
    request = reach_psychic_request(session)
    initial = selection_from_payload(request.payload)
    assert len(initial.modifiers) == 4
    assert initial.hit_roll_modifier == initial.skill_modifier == 0
    # Ignore a positive hit and a detrimental skill term; this subset is neither
    # the beneficial nor detrimental whole-set shortcut.
    wanted = {initial.modifiers[0].modifier_id, initial.modifiers[3].modifier_id}
    while True:
        pending = selection_from_payload(request.payload)
        current = pending.modifiers[len(pending.decided_modifier_ids)]
        count = len(pending.decided_modifier_ids) + 1
        ignored = tuple(
            sorted(
                set(pending.ignored_modifier_ids)
                | ({current.modifier_id} if current.modifier_id in wanted else set())
            )
        )
        option = next(
            option
            for option in request.options
            if (answer := selection_from_payload(option.payload)).decided_modifier_ids
            == tuple(item.modifier_id for item in pending.modifiers[:count])
            and answer.ignored_modifier_ids == ignored
        )
        status = session.submit_option(
            request_id=request.request_id,
            result_id=f"{request.request_id}:individual",
            option_id=option.option_id,
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
        persisted = session.to_persistence_payload()
        restored = LocalGameSession.from_persistence_payload(persisted)
        assert restored.to_persistence_payload() == persisted
        for viewer in ("player-a", "player-b"):
            assert "effect_snapshot_sha256" not in canonical_json(
                session.view(viewer_player_id=viewer)
            )
            assert "psychic_modifier_history_origin" not in canonical_json(
                session.view(viewer_player_id=viewer)
            )
        if count == 4:
            break
        session = restored
        request = pending_request(session)
        assert request.decision_type == "select_psychic_attack_modifier_ignores"
    hits: list[dict[str, JsonValue]] = []
    for _ in range(15):
        hits = [
            event.payload
            for event in session.lifecycle.decision_controller.event_log.records
            if event.event_type == "attack_sequence_step"
            and isinstance(event.payload, dict)
            and event.payload.get("step") == "hit"
        ]
        if hits:
            break
        request = pending_request(session)
        option = next(
            (
                option
                for option in request.options
                if "decline" in option.option_id or "keep" in option.option_id
            ),
            request.options[0],
        )
        session.submit_option(
            request_id=request.request_id,
            result_id=f"{request.request_id}:resolve",
            option_id=option.option_id,
        )
    assert len(hits) == 1
    hit = hits[0]
    assert isinstance(hit, dict)
    payload = hit["payload"]
    assert isinstance(payload, dict)
    selected = selection_from_payload(payload["psychic_modifier_selection"])
    assert set(selected.ignored_modifier_ids) == wanted
    assert payload["modifier"] == -2
    assert payload["capped_modifier"] == -1  # cap applies only after selection
    assert payload["target_number"] == max(2, initial.skill_base - 1)
    for viewer in ("player-a", "player-b"):
        delta = session.events_since(EventStreamCursor(), viewer_player_id=viewer)
        assert "psychic_modifier_selection" in canonical_json(delta)
        assert "effect_snapshot_sha256" not in canonical_json(delta)
    final_payload = session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(final_payload).to_persistence_payload()
        == final_payload
    )
    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id=f"psychic-{phase.value}")
    )
    assert replay.run().status is ReplayRunStatus.REPRODUCED


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
@pytest.mark.parametrize("effect_id", ["a-hit", "c-skill"])
def test_same_total_source_swap_is_rejected_before_pop(phase: BattlePhase, effect_id: str) -> None:
    from tests.psychic_modifier_helpers import psychic_session, reach_psychic_request

    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session = psychic_session(phase)
    request = reach_psychic_request(session)
    state = session.lifecycle.state
    assert state is not None
    (effect,) = state.remove_persisting_effects_by_id((effect_id,))
    state.record_persisting_effect(replace(effect, effect_id=f"{effect_id}:replacement"))
    before = session.lifecycle.to_payload()
    status = session.submit_option(
        request_id=request.request_id, option_id="keep-all-modifiers", result_id="stale-source"
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before


@pytest.mark.parametrize(
    "mutation", ["duplicate", "foreign", "bool", "operand", "context", "extra"]
)
def test_malformed_psychic_choice_cannot_consume_pending_request(mutation: str) -> None:
    from copy import deepcopy
    from typing import cast

    from tests.psychic_modifier_helpers import psychic_session, reach_psychic_request

    from warhammer40k_core.engine.decision_result import DecisionResult
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session = psychic_session(BattlePhase.SHOOTING)
    request = reach_psychic_request(session)
    result = DecisionResult.for_request(
        request=request, selected_option_id="ignore-all-modifiers", result_id="malformed"
    )
    payload = cast(dict[str, JsonValue], deepcopy(result.payload))
    if mutation == "duplicate":
        ids = cast(list[JsonValue], payload["ignored_modifier_ids"])
        ids.append(ids[0])
    elif mutation == "foreign":
        payload["ignored_modifier_ids"] = ["foreign:source"]
    elif mutation == "bool":
        payload["effective_hit_roll_modifier"] = False
    elif mutation == "operand":
        mods = cast(list[dict[str, JsonValue]], payload["modifiers"])
        cast(dict[str, JsonValue], mods[0]["modifier"])["operand"] = 9
    elif mutation == "context":
        payload["attack_context_id"] = "foreign:attack"
    else:
        payload["unexpected"] = True
    before = session.lifecycle.to_payload()
    status = session.lifecycle.submit_decision(replace(result, payload=payload))
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before


def test_every_source_subset_is_reachable_without_enumerating_a_power_set() -> None:
    from dataclasses import replace

    from tests.psychic_modifier_helpers import psychic_session, reach_psychic_request

    from warhammer40k_core.engine.attack_sequence_psychic_modifiers import (
        _psychic_attack_modifier_ignore_options,
        selection_from_payload,
    )

    pending = selection_from_payload(
        reach_psychic_request(psychic_session(BattlePhase.SHOOTING)).payload
    )
    frontier = [pending]
    complete: set[tuple[str, ...]] = set()
    while frontier:
        current = frontier.pop()
        options = _psychic_attack_modifier_ignore_options(selection=current, context={})
        assert len(options) <= 6
        for option in options:
            answer = selection_from_payload(option.payload)
            if answer.complete:
                complete.add(answer.ignored_modifier_ids)
            else:
                frontier.append(replace(answer, option_id="pending"))
    assert len(complete) == 2 ** len(pending.modifiers)
    # Two independent +1 sources must retain distinct identity even when either
    # ignored subset produces exactly the same effective hit modifier.
    from warhammer40k_core.core.modifiers import RollModifier
    from warhammer40k_core.engine.psychic_modifier_selection import AttackModifierSnapshot

    paired = replace(
        pending,
        modifiers=(
            AttackModifierSnapshot("hit_roll", RollModifier("a", 1, source_id="same:source")),
            AttackModifierSnapshot("hit_roll", RollModifier("b", 1, source_id="same:source")),
        ),
    )
    options = _psychic_attack_modifier_ignore_options(selection=paired, context={})
    assert any(option.option_id.startswith("ignore-modifier:") for option in options)


@pytest.mark.parametrize("fault", ["source", "cursor", "options", "missing_request", "actor"])
def test_pending_partial_restore_rejects_source_and_history_drift(fault: str) -> None:
    from typing import Any, cast

    from tests.psychic_modifier_helpers import psychic_session, reach_psychic_request

    from warhammer40k_core.engine.decision_request import DecisionError
    from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
    from warhammer40k_core.engine.phase import GameLifecycleError

    session = psychic_session(BattlePhase.SHOOTING)
    request = reach_psychic_request(session)
    option = next(
        option for option in request.options if option.option_id.startswith("keep-modifier:")
    )
    session.submit_option(
        request_id=request.request_id, result_id="partial", option_id=option.option_id
    )
    payload = cast(dict[str, Any], session.lifecycle.to_payload())
    pending = payload["decisions"]["queue"]["pending_requests"][0]
    if fault == "source":
        pending["payload"]["modifiers"][0]["modifier"]["source_id"] = "foreign:source"
    elif fault == "cursor":
        payload["decisions"]["records"][-1]["request"]["payload"]["decided_modifier_ids"] = [
            "foreign"
        ]
    elif fault == "options":
        pending["options"][0]["payload"]["hit_roll_modifier"] = False
    elif fault == "actor":
        pending["actor_id"] = "player-b"
    else:
        payload["decisions"]["queue"]["pending_requests"] = []
    with pytest.raises((GameLifecycleError, DecisionError)):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, payload))


@pytest.mark.parametrize("fault", ["arithmetic", "provenance", "empty", "duplicate"])
def test_runtime_skill_profile_round_trip_rejects_lost_or_drifted_operations(fault: str) -> None:
    from typing import Any, cast

    from warhammer40k_core.core.modifiers import ModifierError
    from warhammer40k_core.core.weapon_profiles import (
        WeaponProfile,
        WeaponProfileError,
        WeaponProfilePayload,
    )
    from warhammer40k_core.core.weapon_skill_modifiers import with_weapon_skill_modifier

    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    profile = with_weapon_skill_modifier(
        _first_weapon_profile(lifecycle, units["intercessor-1"]),
        modifier_id="skill:one",
        source_id="source:one",
        delta=1,
    )
    assert WeaponProfile.from_payload(profile.to_payload()) == profile
    payload = cast(dict[str, Any], profile.to_payload())
    if fault == "arithmetic":
        payload["skill"]["final"] = 6
    elif fault == "provenance":
        del payload["skill_modifiers"]
    elif fault == "empty":
        payload["skill_modifiers"] = []
    else:
        payload["skill_modifiers"].append(payload["skill_modifiers"][0])
    with pytest.raises((WeaponProfileError, ModifierError)):
        WeaponProfile.from_payload(cast(WeaponProfilePayload, payload))


@pytest.fixture(scope="module")
def psychic_source_payload() -> dict[str, JsonValue]:
    from tests.psychic_modifier_helpers import psychic_session, reach_psychic_request

    payload = reach_psychic_request(psychic_session(BattlePhase.SHOOTING)).payload
    assert isinstance(payload, dict)
    return payload


@pytest.mark.parametrize(
    "fault",
    [
        "missing_base",
        "bool_base",
        "characteristic",
        "modifiers_not_list",
        "unknown_kind",
        "missing_source",
        "extra_operation_field",
        "wrong_scope",
        "duplicate_source",
        "unordered",
        "unknown_top_field",
        "foreign_ignored",
        "duplicate_ignored",
        "bad_cursor",
        "bad_ids",
        "bad_option_id",
        "bad_phase",
        "bad_digest",
        "bad_source_rules",
        "bad_arithmetic",
    ],
)
def test_psychic_source_record_decoder_rejects_malformed_evidence(
    psychic_source_payload: dict[str, JsonValue],
    fault: str,
) -> None:
    from copy import deepcopy
    from typing import Any, cast

    from warhammer40k_core.core.modifiers import ModifierError
    from warhammer40k_core.engine.attack_sequence_psychic_modifiers import selection_from_payload
    from warhammer40k_core.engine.phase import GameLifecycleError

    payload = cast(dict[str, Any], deepcopy(psychic_source_payload))
    if fault == "missing_base":
        del payload["skill_base"]
    elif fault == "bool_base":
        payload["skill_base"] = True
    elif fault == "characteristic":
        payload["skill_characteristic"] = "strength"
    elif fault == "modifiers_not_list":
        payload["modifiers"] = {}
    elif fault == "unknown_kind":
        payload["modifiers"][0]["kind"] = "foreign"
    elif fault == "missing_source":
        payload["modifiers"][0]["modifier"]["source_id"] = None
    elif fault == "extra_operation_field":
        payload["modifiers"][0]["modifier"]["hidden_default"] = 0
    elif fault == "wrong_scope":
        payload["modifiers"][2]["modifier"]["scope"]["characteristics"] = ["weapon_skill"]
    elif fault == "duplicate_source":
        payload["modifiers"].append(payload["modifiers"][0])
    elif fault == "unordered":
        payload["modifiers"].reverse()
    elif fault == "unknown_top_field":
        payload["invented"] = 0
    elif fault == "foreign_ignored":
        payload["ignored_modifier_ids"] = ["foreign"]
    elif fault == "duplicate_ignored":
        payload["ignored_modifier_ids"] = ["foreign", "foreign"]
    elif fault == "bad_cursor":
        payload["decided_modifier_ids"] = ["foreign"]
    elif fault == "bad_ids":
        payload["ignored_modifier_ids"] = [1]
    elif fault == "bad_option_id":
        payload["option_id"] = ""
    elif fault == "bad_phase":
        payload["source_phase"] = "command"
    elif fault == "bad_digest":
        payload["effect_snapshot_sha256"] = "g" * 64
    elif fault == "bad_source_rules":
        payload["source_rule_ids"] = ["foreign"]
    else:
        payload["skill_modifier"] = False
    with pytest.raises((GameLifecycleError, ModifierError)):
        selection_from_payload(payload)


@pytest.fixture(scope="module", params=[BattlePhase.SHOOTING, BattlePhase.FIGHT])
def completed_psychic_session(request: pytest.FixtureRequest) -> LocalGameSession:
    from tests.psychic_modifier_helpers import complete_psychic_attack, psychic_session

    session = psychic_session(request.param)
    complete_psychic_attack(session)
    return session


@pytest.mark.parametrize("fault", ["hit_source", "skill_source", "pool", "effects", "actor"])
def test_completed_history_rejects_coordinated_same_total_forgery(
    completed_psychic_session: LocalGameSession, fault: str
) -> None:
    from copy import deepcopy
    from typing import Any, cast

    from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
    from warhammer40k_core.engine.phase import GameLifecycleError

    payload = cast(dict[str, Any], deepcopy(completed_psychic_session.lifecycle.to_payload()))
    records = payload["decisions"]["records"]
    psychic = next(
        record
        for record in records
        if record["request"]["decision_type"] == "select_psychic_attack_modifier_ignores"
    )
    modifier_index = 1 if fault == "hit_source" else 3
    modifier_id = psychic["request"]["payload"]["modifiers"][modifier_index]["modifier"][
        "modifier_id"
    ]

    def corrupt(value: JsonValue) -> None:
        if isinstance(value, list):
            for item in value:
                corrupt(item)
        elif isinstance(value, dict):
            data = value
            if "modifiers" in data and "decided_modifier_ids" in data:
                if fault in {"hit_source", "skill_source"}:
                    for item in cast(list[dict[str, JsonValue]], data["modifiers"]):
                        modifier = cast(dict[str, JsonValue], item["modifier"])
                        if modifier["modifier_id"] == modifier_id:
                            modifier["source_id"] = "forged:historical-source"
                elif fault in {"pool", "effects"}:
                    key = "pool_sha256" if fault == "pool" else "effect_snapshot_sha256"
                    if key in data:
                        data[key] = "0" * 64
            if fault == "actor" and "actor_id" in data:
                data["actor_id"] = "player-b"
            for item in data.values():
                corrupt(item)

    corrupt(psychic)
    for event in payload["decisions"]["event_log"]:
        event_payload = event["payload"]
        if (
            (
                event["event_type"] == "decision_requested"
                and event_payload.get("request_id") == psychic["request"]["request_id"]
            )
            or (
                event["event_type"] == "decision_recorded"
                and event_payload.get("record_id") == psychic["record_id"]
            )
            or (
                event["event_type"] == "attack_sequence_step" and event_payload.get("step") == "hit"
            )
        ):
            corrupt(event_payload)
    with pytest.raises(GameLifecycleError, match=r"Psychic.*historical|historical.*Psychic"):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, payload))
    from warhammer40k_core.engine.replay import ReplayArtifact

    with pytest.raises(GameLifecycleError, match=r"Psychic.*historical|historical.*Psychic"):
        ReplayArtifact.capture(
            artifact_id="forged-completed-initial-prefix",
            initial_lifecycle_payload=cast(GameLifecyclePayload, payload),
            final_lifecycle=completed_psychic_session.lifecycle,
        )


def test_completed_history_restores_and_replays_after_source_expiration(
    completed_psychic_session: LocalGameSession,
) -> None:
    from tests.psychic_modifier_helpers import pending_request, submit_fixture_request

    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus

    session = LocalGameSession.from_persistence_payload(
        completed_psychic_session.to_persistence_payload()
    )
    state = session.lifecycle.state
    assert state is not None
    original_source_ids = {"a-hit", "b-hit", "c-skill", "d-skill"}
    for _ in range(50):
        if original_source_ids.isdisjoint(effect.effect_id for effect in state.persisting_effects):
            break
        submit_fixture_request(session, pending_request(session))
    assert original_source_ids.isdisjoint(effect.effect_id for effect in state.persisting_effects)
    payload = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(payload).to_payload() == payload
    persisted = session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(persisted).to_persistence_payload() == persisted
    )
    replay = session.replay_artifact(artifact_id="expired-psychic-history")
    assert ReplayRunner.from_payload(replay).run().status is ReplayRunStatus.REPRODUCED
    # An artifact whose initial lifecycle already includes completed choices must
    # authenticate that prefix too, even when its own replay tail is empty.
    from warhammer40k_core.engine.replay import ReplayArtifact

    captured = ReplayArtifact.capture(
        artifact_id="captured-completed-psychic-prefix",
        initial_lifecycle_payload=payload,
        final_lifecycle=session.lifecycle,
    )
    assert not captured.decision_records
    assert ReplayRunner(captured).run().status is ReplayRunStatus.REPRODUCED


@pytest.mark.parametrize("fault", ["missing", "recursive", "late", "config", "prefix"])
def test_completed_history_requires_an_independent_pre_declaration_origin(
    completed_psychic_session: LocalGameSession, fault: str
) -> None:
    from copy import deepcopy
    from typing import Any, cast

    from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
    from warhammer40k_core.engine.phase import GameLifecycleError

    payload = cast(dict[str, Any], deepcopy(completed_psychic_session.lifecycle.to_payload()))
    key = "psychic_modifier_history_origin"
    if fault == "missing":
        del payload[key]
    elif fault == "recursive":
        payload[key][key] = {}
    elif fault == "late":
        late = deepcopy(payload)
        del late[key]
        payload[key] = late
    elif fault == "config":
        payload[key]["config"]["game_id"] = "forged:historical-game"
    else:
        payload[key]["decisions"]["event_log"][0]["payload"]["forged"] = True
    with pytest.raises(GameLifecycleError, match=r"Psychic.*historical|historical.*Psychic"):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, payload))
