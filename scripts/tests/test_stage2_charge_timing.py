"""Focused tests of the Stage 2 operator's timing and receipt boundaries."""

import json
import signal
from io import StringIO
from time import monotonic, sleep
from types import SimpleNamespace

import pytest
from scripts import stage2_charge_timing as timing
from scripts import stage2_preservation_timing as late


@pytest.mark.stubbed
@pytest.mark.skipif(not hasattr(signal, "setitimer"), reason="Requires the POSIX operator timer.")
def test_early_charge_deadline_covers_generation_and_validation(monkeypatch):
    experiment = object.__new__(timing.TimingExperiment)
    experiment.stage = "early"
    experiment.t0 = monotonic()
    campaign_deadline = experiment.t0 + 20
    experiment.preparation_deadline = campaign_deadline
    experiment.journal = StringIO()
    reached = []

    def prepare(_session, _context, **_limits):
        reached.append("generation")
        sleep(0.1)
        reached.append("validation")
        sleep(3.0)

    monkeypatch.setattr(timing, "prepare_ground_charge_policy", prepare)
    monkeypatch.setattr(timing, "MAX_EARLY_WALL_SECONDS", 0.5)
    previous_handler = signal.signal(signal.SIGALRM, late.stop_on_timeout)
    try:
        with pytest.raises(late.Blocker, match="Frozen per-call timeout"):
            experiment.prepare_early_charge(None, None)
    finally:
        signal.signal(signal.SIGALRM, previous_handler)

    assert reached == ["generation", "validation"]
    start, interrupted = map(json.loads, experiment.journal.getvalue().splitlines())
    assert start["op"] == interrupted["op"] == "b2_generate_and_validate_charge"
    assert 0.0 < start["cap_seconds"] <= 0.5
    assert interrupted["state"] == "interrupted"
    assert experiment.preparation_deadline == campaign_deadline


@pytest.mark.stubbed
@pytest.mark.parametrize(("number", "actor"), [(67, "player-b"), (68, "player-a")])
def test_early_fight_round_drift_seals_typed_frontier(monkeypatch, tmp_path, number, actor):
    archive_request = {
        "actor_id": actor,
        "decision_type": "select_fight_activation",
        "payload": {"battle_round": 3, "phase": "fight", "active_player_id": "player-b"},
    }
    live_request = {
        **archive_request,
        "payload": {**archive_request["payload"], "battle_round": 2},
    }
    context = SimpleNamespace(request=live_request)
    experiment = object.__new__(timing.TimingExperiment)
    experiment.root = tmp_path
    experiment.t0 = monotonic()
    experiment.result = {
        "unmatchable": {},
        "declared_references": timing.declared_references(),
        "coverage": {},
    }
    boundaries = []
    monkeypatch.setattr(
        experiment, "boundary", lambda label, _session, *, proof: boundaries.append((label, proof))
    )
    with pytest.raises(timing.Unmatchable, match=f"Archived Fight row {number}") as raised:
        timing.bind_early_fight_reference(
            context, number, {"request": archive_request, "result": {}}
        )

    experiment.unmatched("early", None, raised.value)
    saved = late.read(tmp_path / "result.json")
    receipt = saved["unmatchable"]["early"]
    assert receipt["reason"] == "early_fight_archive_unbindable"
    assert "Archived round 3, issued round 2" in receipt["detail"]
    assert "Request drift: battle_round" in receipt["detail"]
    assert boundaries == [("early-frontier", True)]
    assert saved["report_stage"] == "unmatchable_frontier"
