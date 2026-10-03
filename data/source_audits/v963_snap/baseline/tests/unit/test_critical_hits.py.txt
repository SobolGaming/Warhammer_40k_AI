from __future__ import annotations

from dataclasses import replace

import pytest
from tests.critical_hit_helpers import hit_roll

from warhammer40k_core.engine.attack_sequence import HitRoll
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError


@pytest.mark.parametrize("mode", ["normal", "snap", "overwatch", "indirect", "observed_indirect"])
@pytest.mark.parametrize("raw", range(1, 7))
@pytest.mark.parametrize("modifier", [-3, 0, 3])
def test_critical_hits_respect_raw_faces_and_mode_floors(
    mode: str, raw: int, modifier: int
) -> None:
    hit = hit_roll(raw=raw, mode=mode, modifier=modifier)
    threshold = 6 if mode in {"snap", "overwatch", "indirect"} else 4
    critical = raw >= threshold
    expected = critical or (
        mode == "normal" and raw != 1 and max(1, raw + max(-1, min(1, modifier))) >= 5
    )
    assert hit.critical is critical
    assert hit.successful is expected
    assert hit.unmodified_roll == raw
    assert hit.final_roll == max(1, raw + max(-1, min(1, modifier)))
    assert HitRoll.from_payload(hit.to_payload()) == hit


@pytest.mark.parametrize("mode", ["snap", "overwatch"])
@pytest.mark.parametrize("status", ["critical_hit_threshold", "minimum_unmodified_hit_success"])
def test_snap_ignores_generic_threshold_but_accepts_explicit_permission(
    mode: str, status: str
) -> None:
    ordinary = hit_roll(raw=4, mode=mode, status=status)
    explicit = hit_roll(raw=4, mode=mode, status=status, explicit_snap=True)
    assert not ordinary.successful
    assert not ordinary.critical
    assert explicit.successful
    assert explicit.critical is (status == "critical_hit_threshold")


def test_melee_uses_the_same_critical_success_authority() -> None:
    hit = hit_roll(raw=4, modifier=-1, phase=BattlePhase.FIGHT)
    assert hit.successful
    assert hit.critical


def test_torrent_does_not_invent_a_critical_roll() -> None:
    hit = hit_roll(raw=4, torrent=True)
    assert hit.skipped
    assert hit.successful
    assert not hit.critical


def test_hit_restore_rejects_critical_and_face_drift() -> None:
    hit = hit_roll(raw=4)
    with pytest.raises(GameLifecycleError):
        replace(hit, critical=False)
    with pytest.raises(GameLifecycleError):
        replace(hit, unmodified_roll=5)
    with pytest.raises(GameLifecycleError):
        replace(hit, final_roll=6)


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
@pytest.mark.parametrize(
    "forgery",
    ["critical", "source", "missing_event", "wrong_attack", "duplicate_event", "wrong_weapon"],
)
def test_hit_restore_requires_owning_recorded_hit(phase: BattlePhase, forgery: str) -> None:
    from typing import cast

    from tests.critical_hit_helpers import hit_authority_checkpoint

    from warhammer40k_core.engine.attack_sequence_model import AttackSequencePayload
    from warhammer40k_core.engine.event_log import JsonValue
    from warhammer40k_core.engine.lifecycle import GameLifecycle

    session = hit_authority_checkpoint(phase=phase)
    checkpoint = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint
    state = checkpoint["state"]
    assert state is not None
    host = (
        state["shooting_phase_state"]
        if phase is BattlePhase.SHOOTING
        else state["fight_phase_state"]
    )
    assert host is not None
    sequence = cast(AttackSequencePayload, host["attack_sequence"])
    pending = sequence["pending_grouped_damage"]
    assert pending is not None
    context = next(
        die["attack_context"]
        for die in pending["sorted_save_dice"]
        if die["attack_context"]["hit_roll"]["unmodified_roll"] == 5
    )
    hit = context["hit_roll"]
    assert not hit["critical"]
    assert hit["successful"]
    if forgery == "critical":
        hit["critical_threshold"] = 5
        hit["critical_is_threshold"] = True
        hit["critical"] = True
    elif forgery == "source":
        hit["threshold_source_ids"].append("invented:critical-source")
    else:
        event = next(
            event
            for event in checkpoint["decisions"]["event_log"]
            if event["event_type"] == "attack_sequence_step"
            and cast(dict[str, JsonValue], event["payload"])["step"] == "hit"
            and cast(dict[str, JsonValue], event["payload"])["attack_context_id"]
            == context["attack_context_id"]
        )
        if forgery == "missing_event":
            cast(dict[str, JsonValue], event["payload"])["step"] = "critical_hit"
        elif forgery == "wrong_attack":
            cast(dict[str, JsonValue], event["payload"])["attack_context_id"] = "another-attack"
        elif forgery == "wrong_weapon":
            recorded = cast(dict[str, JsonValue], event["payload"])
            cast(dict[str, JsonValue], recorded["payload"])["weapon_profile_id"] = "another-weapon"
        else:
            from copy import deepcopy

            wound_event = next(
                row
                for row in checkpoint["decisions"]["event_log"]
                if row["event_type"] == "attack_sequence_step"
                and cast(dict[str, JsonValue], row["payload"])["step"] == "wound"
                and cast(dict[str, JsonValue], row["payload"])["attack_context_id"]
                == context["attack_context_id"]
            )
            wound_event["payload"] = deepcopy(event["payload"])
    with pytest.raises(GameLifecycleError, match=r"[Hh]it.*(authority|recorded|context)"):
        GameLifecycle.from_payload(checkpoint)


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
@pytest.mark.parametrize("forgery", ["threshold", "source"])
def test_pending_hit_drift_rejected_before_restore_and_submission(
    phase: BattlePhase, forgery: str
) -> None:
    from typing import cast

    from tests.critical_hit_helpers import hit_authority_checkpoint

    from warhammer40k_core.engine.event_log import JsonValue
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session = hit_authority_checkpoint(phase=phase)
    controller = session.lifecycle.decision_controller
    request = controller.queue.pending_requests[0]
    payload = cast(dict[str, JsonValue], request.payload)
    lost_wound = cast(dict[str, JsonValue], payload["lost_wound_context"])
    context = cast(dict[str, JsonValue], lost_wound["attack_context"])
    hit = cast(dict[str, JsonValue], context["hit_roll"])
    if forgery == "threshold":
        hit["critical_threshold"] = 5
        hit["critical_is_threshold"] = True
        hit["critical"] = cast(int, hit["unmodified_roll"]) >= 5
    else:
        cast(list[JsonValue], hit["threshold_source_ids"]).append("invented:critical-source")
    before = session.lifecycle.to_payload()
    with pytest.raises(GameLifecycleError, match="Hit authority"):
        GameLifecycle.from_payload(before)
    status = session.submit_option(
        request_id=request.request_id, result_id="r43:forged-hit", option_id="decline"
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert (
        cast(dict[str, JsonValue], status.payload)["invalid_reason"] == "attack_hit_authority_drift"
    )
    assert session.lifecycle.to_payload() == before


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
def test_critical_consumers_through_facade_restore_and_replay(
    phase: BattlePhase,
) -> None:
    from typing import cast

    from tests.critical_hit_helpers import critical_hit_session
    from tests.psychic_modifier_helpers import pending_request, submit_fixture_request

    from warhammer40k_core.adapters.event_stream import EventStreamCursor
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.event_log import JsonValue
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus

    session = critical_hit_session(phase=phase)
    pending_request(session)
    initial = session.lifecycle.to_payload()
    completed = False
    used = False
    for _ in range(100):
        request = pending_request(session)
        checkpoint = session.to_persistence_payload()
        restored = LocalGameSession.from_persistence_payload(checkpoint)
        assert restored.to_persistence_payload() == checkpoint
        for viewer in ("player-a", "player-b"):
            assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        option = next(
            (
                option
                for option in request.options
                if option.option_id == "use-stratagem:000009746003:target:army-alpha:intercessor-1"
            ),
            None,
        )
        if option is not None:
            session.submit_option(
                request_id=request.request_id,
                result_id="order43:activate",
                option_id=option.option_id,
            )
            used = True
        elif request.decision_type == "submit_stratagem_target_proposal":
            from warhammer40k_core.engine.stratagems import stratagem_decline_payload

            session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"{request.request_id}:decline",
                payload=stratagem_decline_payload(),
            )
        elif request.decision_type == "select_stratagem":
            session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:decline",
                option_id=next(
                    option.option_id for option in request.options if "decline" in option.option_id
                ),
            )
        else:
            submit_fixture_request(session, request)
        if any(
            event.event_type == "attack_sequence_completed"
            for event in session.lifecycle.decision_controller.event_log.records
        ):
            completed = True
            break
    assert completed
    assert used is (phase is BattlePhase.SHOOTING)
    steps = [
        cast(dict[str, JsonValue], e.payload)
        for e in session.lifecycle.decision_controller.event_log.records
        if e.event_type == "attack_sequence_step"
    ]
    hits = [cast(dict[str, JsonValue], e["payload"]) for e in steps if e["step"] == "hit"]
    assert hits
    assert any(hit["unmodified_roll"] in (4, 5) for hit in hits)
    for hit in hits:
        raw = cast(int, hit["unmodified_roll"])
        assert hit["critical"] is (raw >= 5)
        assert hit["successful"] is (raw >= 5)
        assert hit["generated_hits"] == (2 if raw >= 5 else 1)
        assert hit["critical_threshold"] == 5
        assert hit["threshold_source_ids"]
    assert any(
        cast(dict[str, JsonValue], e["payload"]).get("skipped") is True
        for e in steps
        if e["step"] == "wound"
    )
    assert any(
        cast(dict[str, JsonValue], e["payload"]).get("skipped") is False
        for e in steps
        if e["step"] == "wound"
    )
    artifact = ReplayArtifact.capture(
        artifact_id="order43", initial_lifecycle_payload=initial, final_lifecycle=session.lifecycle
    )
    replay = ReplayRunner.from_payload(artifact.to_payload()).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay
    restored = LocalGameSession.from_persistence_payload(session.to_persistence_payload())
    for viewer in ("player-a", "player-b"):
        assert restored.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)


@pytest.mark.parametrize("raw", [3, 4, 5, 6])
@pytest.mark.parametrize("value", [1, 2, "D3"])
def test_lowered_critical_threshold_drives_sustained_hits(raw: int, value: int | str) -> None:
    from warhammer40k_core.core.weapon_profiles import AbilityDescriptor, WeaponKeyword

    hit = hit_roll(
        raw=raw,
        abilities=(AbilityDescriptor.sustained_hits(value),),
        keywords=(WeaponKeyword.SUSTAINED_HITS,),
    )
    assert hit.critical is (raw >= 4)
    if raw < 4:
        assert hit.generated_hits == 1
    elif value == "D3":
        assert 2 <= hit.generated_hits <= 4
    else:
        assert isinstance(value, int)
        assert hit.generated_hits == 1 + value


@pytest.mark.parametrize("threshold", [0, 1, 7, True, "4"])
def test_threshold_resolver_rejects_malformed_descriptors(threshold: object) -> None:
    from typing import cast

    with pytest.raises(GameLifecycleError):
        hit_roll(raw=4, threshold=cast(int, threshold))


def test_critical_sources_are_pinned_loaded_and_executable() -> None:
    from importlib.resources import files

    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_critical_hits_2026_09 as source,
    )

    raw = files(source).joinpath("artifacts/package.json").read_bytes()
    artifact = source.validate_source_artifact_bytes(raw)
    assert tuple(row.source_id for row in artifact.rules) == (
        source.CRITICAL_SUCCESS_SOURCE_ID,
        source.SNAP_CRITICAL_SOURCE_ID,
    )
    assert source.source_package().source_catalog.catalog_sha256()
    for row in artifact.rules:
        assert row.load_support_status == "loaded"
        assert row.semantic_execution_status == "executable_engine_runtime"
    with pytest.raises(source.CriticalHitsSourceError, match="drifted"):
        source.validate_source_artifact_bytes(raw + b" ")


@pytest.mark.parametrize("field", ["artifact_schema", "source_package_id", "source_version"])
def test_activation_artifact_rejects_identity_drift(
    field: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib
    import json
    from importlib.resources import files

    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        faction_stratagem_activation_2026_27 as source,
    )

    payload = json.loads(
        files("warhammer40k_core.rules.source_packages.warhammer_40000_11th")
        .joinpath("faction_stratagem_activation_2026_27.json")
        .read_bytes()
    )
    payload[field] = "drift"
    raw = json.dumps(payload).encode()
    monkeypatch.setattr(source, "EXPECTED_ARTIFACT_SHA256", hashlib.sha256(raw).hexdigest())
    with pytest.raises(ValueError, match="identity drifted"):
        source.validate_artifact_bytes(raw)


@pytest.mark.parametrize(
    ("text", "gate"),
    [
        (
            "When Snap Shooting, an unmodified Hit roll of 4+ scores a Critical Hit.",
            "core:snap-shooting",
        ),
        (
            "An unmodified Hit roll of 4+ scores a Critical Hit, except when Snap Shooting.",
            None,
        ),
        (
            "Each time this unit makes an attack, "
            "an unmodified Hit roll of 4+ scores a Critical Hit.",
            None,
        ),
    ],
)
def test_source_compiler_requires_positive_snap_scope(text: str, gate: str | None) -> None:
    from warhammer40k_core.rules.hit_success_threshold_parser import hit_success_threshold_effects
    from warhammer40k_core.rules.rule_ir import parameter_payload

    effects = hit_success_threshold_effects(
        clause_text=text, clause_start=0, source_keyword_sequence_parts=()
    )
    assert len(effects) == 1
    parameters = parameter_payload(effects[0].parameters)
    assert parameters["status"] == "critical_hit_threshold"
    assert parameters["critical_threshold"] == 4
    assert parameters.get("required_targeting_rule_id") == gate


@pytest.mark.parametrize(("original", "rerolled"), [(3, 4), (4, 3), (6, 5)])
def test_hit_record_uses_the_current_rerolled_face(original: int, rerolled: int) -> None:
    from warhammer40k_core.core.dice import DiceRollResult

    hit = hit_roll(raw=original)
    assert hit.roll_state is not None
    replacement = DiceRollResult.from_values(
        roll_id="order43:replacement",
        spec=hit.roll_state.original_result.spec,
        values=(rerolled,),
        source="fixed",
    )
    state = hit.roll_state.with_reroll(
        decision_id="order43:reroll-result",
        request_id="order43:reroll-request",
        selected_indices=(0,),
        replacement_result=replacement,
    )
    current = replace(
        hit,
        roll_state=state,
        unmodified_roll=rerolled,
        final_roll=rerolled,
        critical=rerolled >= 4,
        successful=rerolled >= 4,
    )
    assert current.roll_state is not None
    assert current.roll_state.original_result.total == original
    assert current.unmodified_roll == rerolled
    assert HitRoll.from_payload(current.to_payload()) == current


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
@pytest.mark.parametrize("assigned", [1, 6, 7])
def test_order84_assigned_hit_reaches_shared_critical_and_trigger_consumers(
    phase: BattlePhase,
    assigned: int,
) -> None:
    from warhammer40k_core.engine.post_roll_weapon_profile_modifiers import ResolvedAttackRollValues

    hit = hit_roll(raw=2, assigned_value=assigned, threshold=6, modifier=-1, phase=phase)
    assert hit.roll_state is not None
    assert hit.roll_state.original_result.values == (2,)
    assert hit.unmodified_roll == assigned
    assert hit.critical is (assigned >= 6)
    assert hit.successful is (assigned >= 6)
    trigger = ResolvedAttackRollValues(
        hit.unmodified_roll,
        hit.final_roll,
        hit.successful,
        hit.critical,
        hit.skipped,
    )
    assert trigger.unmodified_roll == assigned
    assert HitRoll.from_payload(hit.to_payload()) == hit


@pytest.mark.parametrize("mode", ["normal", "snap", "overwatch", "indirect"])
@pytest.mark.parametrize("assigned", [6, 7])
def test_order84_default_critical_and_snap_require_exact_six(mode: str, assigned: int) -> None:
    hit = hit_roll(raw=2, assigned_value=assigned, mode=mode, grant_threshold=False)
    assert hit.critical is (assigned == 6)
    assert hit.successful is (assigned == 6 or mode in {"normal", "indirect"})
    assert HitRoll.from_payload(hit.to_payload()) == hit


@pytest.mark.parametrize("mode", ["snap", "overwatch"])
def test_order84_explicit_snap_threshold_accepts_assigned_seven(mode: str) -> None:
    hit = hit_roll(raw=2, assigned_value=7, mode=mode, threshold=6, explicit_snap=True)
    assert hit.critical
    assert hit.successful
