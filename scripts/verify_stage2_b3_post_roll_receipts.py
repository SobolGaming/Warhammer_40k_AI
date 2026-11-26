"""Verify retained B3 comparisons without executing gameplay."""

from __future__ import annotations

import argparse
import json
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).resolve().parents[1] / "docs/stage2/b3-post-roll-finite-receipt.json"
PRESERVATION = FIXTURE.with_name("b3-objective-preservation-receipt.json")
CLOSEOUT = "stage2-b3-closeout-evidence"
GENERATED = "stage2-generated-b3-evidence"
AUTHORED = "stage2-score-evidence-final"


def require(condition: bool, context: str) -> None:
    if not condition:
        raise ValueError(context)


def decisions(checkpoint: dict[str, Any]) -> dict[str, Any]:
    return checkpoint["lifecycle"]["decisions"]


def endpoint(
    checkpoint: dict[str, Any],
    replay: dict[str, Any],
    control_id: str,
    objective_id: str,
) -> dict[str, Any]:
    ledger = decisions(checkpoint)
    count = [len(ledger["records"]), len(ledger["event_log"])]
    event_hash = checkpoint["event_log_hash"]
    require(
        replay["status"] == "reproduced"
        and replay["diagnostics"] == []
        and [replay["reproduced_decision_count"], replay["reproduced_event_count"]] == count
        and replay["final_event_log_hash"] == event_hash,
        "Independent ordinary replay does not match the checkpoint.",
    )
    state = checkpoint["lifecycle"]["state"]
    control = next(
        row for row in state["objective_control_records"] if row["record_id"] == control_id
    )
    objective = next(row for row in control["results"] if row["objective_id"] == objective_id)
    return {
        "checkpoint": checkpoint["content_hash"],
        "event_log_hash": event_hash,
        "rng_state_hash": checkpoint["rng_state_hash"],
        "counts_decisions_events_rng": [*count, checkpoint["rng_state"]["draw_count"]],
        "pending_request": ledger["queue"]["pending_requests"][0]["request_id"],
        "vp": {row["player_id"]: row["victory_points"] for row in state["victory_point_ledgers"]},
        "objective_status": objective["status"],
        "controlled_by": objective["controlled_by_player_id"],
    }


def authenticate(root: Path, files: dict[str, str]) -> dict[str, Any]:
    packet: dict[str, Any] = {}
    for name, digest in files.items():
        raw = (root / name).read_bytes()
        require(sha256(raw).hexdigest() == digest, f"Raw receipt SHA-256 mismatch: {name}")
        is_view_dump = name.endswith("-views.json") and not name.endswith("-replay-views.json")
        if name.endswith(".json") and not is_view_dump:
            packet[name] = json.loads(raw)
        elif name == "producer.txt":
            packet[name] = raw.decode().splitlines()
    return packet


def verify(root: Path, fixture: dict[str, Any]) -> None:
    packet = authenticate(root, fixture["raw_sha256"])

    generated = packet[f"{GENERATED}/result.json"]
    campaign = fixture["generated_campaign"]
    require(
        campaign["qualifying_landed_pair"] == generated["qualifying_pair"] is None,
        "Qualifying generated landed pair differs from the authenticated source.",
    )

    comparison = fixture["comparison"]
    closeout = packet[f"{CLOSEOUT}/result.json"]
    protocol = closeout["protocol"]
    fork = packet[f"{CLOSEOUT}/fork-checkpoint.json"]
    anchor = packet[f"{AUTHORED}/common-checkpoint.json"]
    (pending,) = decisions(fork)["queue"]["pending_requests"]
    require(
        [pending[key] for key in ("request_id", "actor_id", "decision_type")]
        == [comparison["request"], comparison["actor"], "select_charge_targets"]
        and [option["option_id"] for option in pending["options"]]
        == [candidate["id"] for candidate in comparison["finite_candidates"]]
        and closeout["finite_candidates"] == comparison["finite_candidates"]
        and closeout["finite_references"] == comparison["finite_references"]
        and closeout["fork_actor_view"] == comparison["fork_actor_view"]
        and fork["content_hash"] == closeout["fork_checkpoint"] == comparison["fork_checkpoint"]
        and protocol["frozen_natural_roll"]
        == generated["natural_roll"]
        == comparison["natural_roll"]
        and protocol["base"] == generated["main"] == fixture["evidence_revision"]
        and protocol["archived_origin"] == fixture["archived_origin"]["checkpoint"]
        and protocol["archived_origin_sha256"] == fixture["archived_origin"]["raw_sha256"]
        and protocol["horizon"] == comparison["horizon"],
        "Finite request, candidate inventory or provenance differs.",
    )

    fork_rng = fork["rng_state"]
    fork_rows = decisions(fork)["records"]
    anchor_rows = decisions(anchor)["records"]
    take_id, decline_id = [option["option_id"] for option in pending["options"]]
    require(
        closeout["take_targets_exact_anchor_reproduction"] is True
        and anchor["content_hash"] == generated["common_checkpoint"] == comparison["take_anchor"]
        and generated["view_sha256"] == comparison["charge_actor_view"]
        and anchor_rows[:-1] == fork_rows
        and [len(fork_rows), len(decisions(fork)["event_log"]), fork_rng["draw_count"]]
        == comparison["fork_counts_decisions_events_rng"]
        and fork["event_log_hash"] == comparison["fork_event_log_hash"]
        and anchor_rows[-1]["request"] == pending
        and anchor_rows[-1]["result"]["selected_option_id"] == take_id,
        "The finite take does not join the generated Charge anchor.",
    )

    control = closeout["take_targets_generated_charge"]
    candidate = generated["trials"]["active"][0]
    proposal = packet[f"{GENERATED}/proposals.json"][0]
    require(
        generated["generator"] == campaign["generator"]
        and generated["counts"] == campaign["counts"]
        and generated["candidate_inventory_sha256"] == campaign["candidate_inventory_sha256"]
        and candidate["id"] == proposal["id"] == control["id"] == campaign["candidate_id"]
        and candidate["index"] == proposal["index"] == campaign["candidate_index"]
        and candidate["charge"] == "accepted"
        and candidate["response"] == "scored"
        and candidate["vp"] == control["vp"] == comparison["take"]["vp"]
        and generated["proofs"]["generated-01"] == control["proof"],
        "Generated continuation inventory, native admission, score or proof differs.",
    )

    for key, stem, prefix in (
        ("take", f"{GENERATED}/generated-01", anchor_rows),
        ("decline", f"{CLOSEOUT}/decline-targets", fork_rows),
        ("authored_landed_reference", f"{AUTHORED}/clear", anchor_rows),
    ):
        saved = packet[f"{stem}-checkpoint.json"]
        strict = packet[f"{stem}-strict-proof.json"]
        expected = comparison[key] if key != "authored_landed_reference" else fixture[key]
        rows = decisions(saved)["records"]
        (expected_pending,) = decisions(saved)["queue"]["pending_requests"]
        require(
            rows[: len(prefix)] == prefix
            and saved["rng_state"]["seed"] == fork_rng["seed"]
            and saved["rng_state"]["draw_count"] == fork_rng["draw_count"]
            and saved["rng_state"]["history"][: len(fork_rng["history"])] == fork_rng["history"]
            and saved["lifecycle"]["state"]["battle_round"] == 4
            and expected_pending["actor_id"] == "player-a"
            and expected_pending["decision_type"] == "select_movement_unit"
            and strict == fixture["required_proof"],
            f"Prefix, RNG, horizon or strict proof differs for {key}.",
        )
        require(
            endpoint(
                saved,
                packet[f"{stem}-ordinary-replay.json"],
                comparison["scoring_checkpoint"],
                comparison["objective"],
            )
            == expected,
            f"Score, checkpoint or replay binding differs for {key}.",
        )
        if key == "decline":
            require(
                rows[len(prefix)]["request"] == pending
                and rows[len(prefix)]["result"]["selected_option_id"] == decline_id
                and closeout["decline_targets"]["native_optional_declines"]
                == comparison["decline_optional_descriptors"],
                "Decline is not the other native option at the finite request.",
            )
        if key == "take":
            charge = rows[len(prefix)]
            proposal_payload = {
                **proposal["proposal"],
                "proposal_request_id": comparison["charge_move_request"],
            }
            require(
                charge["request"]["request_id"] == comparison["charge_move_request"]
                and charge["result"]["result_id"] == "stage2-generated-b3:charge"
                and charge["result"]["payload"] == proposal_payload
                and saved["content_hash"] == control["proof"]["checkpoint"]
                and saved["event_log_hash"] == control["proof"]["event_log_hash"]
                and any(
                    event["event_type"] == "charge_move_completed"
                    and event["payload"]["result_id"] == "stage2-generated-b3:charge"
                    for event in decisions(saved)["event_log"]
                ),
                "Generated proposal is not a completed native Charge Move.",
            )
    require(
        closeout["sample_seconds"] == fixture["sample_seconds"]
        and closeout["proof"] == control["proof"]["checks"] == fixture["required_proof"],
        "Component samples or proof flags differ from the retained receipts.",
    )


def verify_preservation(root: Path, fixture: dict[str, Any]) -> None:
    packet = authenticate(root, fixture["raw_sha256"])
    result = packet["result.json"]
    producer = fixture["producer"]
    stamp = packet["producer.txt"]
    require(
        stamp[0].split() == [producer["commit"], producer["tree"], producer["parent"]]
        and stamp[1] == producer["python"]
        and stamp[2] == producer["build"]
        and [line.split()[0] for line in stamp[3:]] == producer["harness_sha256"],
        "Exact producer stamp differs.",
    )

    fork = packet["fork-checkpoint.json"]
    fork_ledger = decisions(fork)
    (pending,) = fork_ledger["queue"]["pending_requests"]
    common = fixture["fork"]
    roll = next(
        event["payload"]
        for event in reversed(fork_ledger["event_log"])
        if event["event_type"] == "charge_roll_resolved"
    )
    option_ids = [option["option_id"] for option in pending["options"]]
    require(
        fork["content_hash"] == result["fork"] == common["checkpoint"]
        and result["fork_actor_view"] == common["actor_view"]
        and result["fork_counts"]
        == common["counts"]
        == [
            len(fork_ledger["records"]),
            len(fork_ledger["event_log"]),
            fork["rng_state"]["draw_count"],
        ]
        and [pending["request_id"], pending["actor_id"], pending["decision_type"]]
        == [common["request"], "player-b", "select_charge_targets"]
        and option_ids == result["finite_ids"] == common["finite_ids"]
        and roll["roll_result"]["modified_roll"]["unmodified"]["component_values"]
        == result["post_roll"]["dice"]
        == common["dice"]
        and roll["maximum_distance_inches"] == result["post_roll"]["budget"] == common["budget"]
        and result["protocol"] == packet["protocol.json"] == fixture["protocol"]
        and result["objective_before_fork"] == common["objective_before_fork"],
        "Frozen native input, rolls, options or protocol differs.",
    )

    generated = fixture["generated"]
    preparation = result["charge_preparation"]
    require(
        preparation == generated["preparation"]
        and preparation["validations"][0]["status"] == "invalid"
        and preparation["validations"][1]["status"] == "waiting_for_decision"
        and preparation["validations"][1]["candidate_id"] == preparation["selected"]
        and generated["viewer_payload_sha256"]
        != fixture["authored_reference"]["viewer_payload_sha256"],
        "Generated native probe verdicts or distinct proposal identity differ.",
    )
    for arm, option_id in zip(("charge", "decline"), option_ids, strict=True):
        saved = packet[f"{arm}-checkpoint.json"]
        ledger = decisions(saved)
        actions = packet[f"{arm}-ledger.json"]
        tail = ledger["records"][len(fork_ledger["records"]) :]
        (seal,) = ledger["queue"]["pending_requests"]
        fork_rng = fork["rng_state"]
        arm_rng = saved["rng_state"]
        evidence = result["arms"][arm]
        expected = fixture["native"][arm]
        ordinary = packet[f"{arm}-ordinary-replay.json"]
        projected = packet[f"{arm}-ordinary-replay-views.json"]
        require(
            ledger["records"][: len(fork_ledger["records"])] == fork_ledger["records"]
            and ledger["event_log"][: len(fork_ledger["event_log"])] == fork_ledger["event_log"]
            and arm_rng["seed"] == fork_rng["seed"]
            and arm_rng["draw_count"] == fork_rng["draw_count"]
            and arm_rng["history"][: len(fork_rng["history"])] == fork_rng["history"]
            and tail == [action["committed_record"] for action in actions]
            and tail[0]["request"] == pending
            and tail[0]["result"]["selected_option_id"] == option_id
            and saved["lifecycle"]["state"]["battle_round"] == 4
            and [seal["actor_id"], seal["decision_type"]] == ["player-a", "select_movement_unit"]
            and evidence["status"] == "scored",
            f"Native prefix, continuation or sealed scoring horizon differs: {arm}.",
        )
        require(
            endpoint(saved, ordinary, fixture["scoring_checkpoint"], fixture["objective"])
            == expected["endpoint"]
            and packet[f"{arm}-strict-proof.json"]
            == result["proofs"][arm]
            == fixture["required_proof"]
            and projected == expected["projected_replay"]
            and projected["replay"] == ordinary
            and projected["rng_equal"] is True
            and projected["both_views_and_event_streams_equal"] is True,
            f"Endpoint, strict restore or independent replay differs: {arm}.",
        )
        state = saved["lifecycle"]["state"]
        control = next(
            row
            for row in state["objective_control_records"]
            if row["record_id"] == fixture["scoring_checkpoint"]
        )
        objective = next(
            row for row in control["results"] if row["objective_id"] == fixture["objective"]
        )
        require(
            objective == expected["objective"] == evidence["objective"]
            and {row["player_id"]: row["transactions"] for row in state["victory_point_ledgers"]}
            == expected["transactions"]
            == evidence["transactions"],
            f"Native objective contributors or scoring transaction differs: {arm}.",
        )
        reaction_index = 2 if arm == "charge" else 1
        reaction = tail[reaction_index]
        window = reaction["request"]["payload"]["reaction_window"]["timing_window"]
        require(
            reaction["request"]["actor_id"] == "player-a"
            and window["descriptor"]["descriptor_id"]
            == "core-heroic-intervention-end-opponent-charge"
            and reaction["result"]["payload"] == {"submission_kind": "decline_stratagem_window"},
            f"Fixed Heroic Intervention decline differs: {arm}.",
        )
        fight = [row["result"] for row in tail[reaction_index + 1 :]]
        require(
            [
                [row["actor_id"], row["decision_type"], row["payload"].get("proposal_kind")]
                for row in fight
            ]
            == expected["fight_response"]
            and all("witness" not in row["payload"] for row in fight),
            f"Fixed stationary Fight response differs: {arm}.",
        )
        if arm == "charge":
            action = actions[1]
            viewer_payload = action["viewer_action"]["proposal_json"].encode()
            native_result = action["committed_record"]["result"]
            require(
                sha256(viewer_payload).hexdigest() == generated["viewer_payload_sha256"]
                and native_result["result_id"] == "preservation:generated-charge"
                and native_result["payload"]
                == {
                    **json.loads(viewer_payload),
                    "proposal_request_id": action["native_request"]["request_id"],
                }
                and any(
                    event["event_type"] == "charge_move_completed"
                    and event["payload"]["result_id"] == native_result["result_id"]
                    for event in ledger["event_log"]
                ),
                "Generated proposal is not the completed native Charge Move.",
            )
    require(
        fixture["native"]["decline"]["endpoint"]["vp"]["player-b"]
        - fixture["native"]["charge"]["endpoint"]["vp"]["player-b"]
        == result["preservation_delta_b_vp"]
        == fixture["preservation_delta_b_vp"],
        "Preservation VP delta differs.",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--receipts", required=True, type=Path, help="Root of the archived B3 receipts"
    )
    parser.add_argument(
        "--preservation", action="store_true", help="Verify the separate 5+5 preservation receipt"
    )
    args = parser.parse_args()
    try:
        payload = (PRESERVATION if args.preservation else FIXTURE).read_bytes()
        check = verify_preservation if args.preservation else verify
        check(args.receipts, json.loads(payload))
    except (OSError, ValueError, KeyError, IndexError, StopIteration, TypeError) as error:
        print(f"B3 receipt verification failed: {error}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
