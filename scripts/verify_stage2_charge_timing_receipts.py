"""Authenticate the retained Stage 2 B2/B3 receipt without running a game."""

import argparse
import json
import signal
import sys
from collections import defaultdict
from hashlib import file_digest, sha256
from itertools import product
from pathlib import Path

from scripts import stage2_preservation_timing as late
from scripts.stage2_charge_timing import declared_references, frozen_e_rows

RAW_MANIFEST = "c90f850529aadc9c03cd57edd1cb916c85955de6301752e3061a8707e7381b83"
SUMMARY = "1a8df3da22c3139fa687e04ddc296a040298a44f8cdbfdfca936fa46ae9a771d"
PR733_MANIFEST = "30e00f019d1b422dd1596d0bc3b9cc51f34a56741dc32adc60d797c98589aefa"
PR733_REVIEW_MANIFEST = "5ee88f7040630f00bdf2ea4ff5694d655559f913337541af05b76667a02b0f0a"
VERIFY_SECONDS = 180
STRICT_FIELDS = {
    "both_player_views_and_visible_events",
    "decisions_events_artifact",
    "lifecycle",
    "rng",
    "save_payload",
}


def file_sha256(path):
    late.need(path.is_file() and not path.is_symlink(), f"Missing regular receipt file {path}.")
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def read_manifest(path, expected):
    with path.open("rb") as stream:
        packed = stream.read(65_537)
    late.need(
        len(packed) <= 65_536 and sha256(packed).hexdigest() == expected,
        f"Manifest SHA-256 mismatch for {path}.",
    )
    entries = {}
    for line in packed.decode("ascii").splitlines():
        digest, filename = line.split("  ", 1)
        filename = filename.removeprefix("./")
        parts = Path(filename).parts
        late.need(
            len(digest) == 64
            and parts
            and not Path(filename).is_absolute()
            and ".." not in parts
            and filename not in entries,
            f"Invalid sealed manifest entry in {path}.",
        )
        entries[filename] = digest
    return entries


def authenticate_raw(root):
    manifest = read_manifest(root / "SHA256SUMS", RAW_MANIFEST)
    entries = {path.name for path in root.iterdir() if path.name != "SHA256SUMS"}
    late.need(
        entries == manifest.keys(), "Raw receipt inventory does not match its sealed manifest."
    )
    for name, digest in manifest.items():
        late.need(file_sha256(root / name) == digest, f"Raw receipt SHA-256 mismatch for {name}.")
    return manifest


def read_json(path):
    return json.loads(path.read_bytes())


def authenticate_json(path, digest):
    data = path.read_bytes()
    late.need(sha256(data).hexdigest() == digest, f"Receipt SHA-256 mismatch for {path}.")
    return json.loads(data)


def require_strict(proof, label):
    late.need(
        proof.keys() == STRICT_FIELDS and all(value is True for value in proof.values()),
        f"Incomplete strict proof for {label}.",
    )


def require_replay(replay, checkpoint, label):
    decisions = checkpoint["lifecycle"]["decisions"]
    late.need(
        replay["status"] == "reproduced"
        and replay["diagnostics"] == []
        and replay["reproduced_decision_count"] == len(decisions["records"])
        and replay["reproduced_event_count"] == len(decisions["event_log"])
        and replay["final_event_log_hash"] == checkpoint["event_log_hash"],
        f"Ordinary replay proof differs for {label}.",
    )


def authenticate_pr733(root, raw, prior):
    experiment = prior / "experiment"
    correction = prior / "review-correction"
    original = read_manifest(experiment / "frozen-run-SHA256SUMS", PR733_MANIFEST)
    reviewed = read_manifest(correction / "SHA256SUMS", PR733_REVIEW_MANIFEST)
    historical = set()
    for schedule, position, action in product(
        ("delayed", "decline"), ("preserve", "spend"), ("omit", "shoot")
    ):
        label = f"{schedule}-{position}-{action}"
        old = f"{position}-{'charge' if schedule == 'delayed' else 'decline'}-{action}"
        for suffix in ("checkpoint", "views"):
            late.need(
                raw[f"{label}-{suffix}.json"] == original[f"{old}-{suffix}.json"],
                f"Original #733 {suffix} differs for {label}.",
            )
        strict_name = f"{old}-replay-proof.json"
        replay_name = f"{old}-ordinary-replay.json"
        review_name = f"{old}-exact-head-proof.json"
        strict = authenticate_json(experiment / strict_name, original[strict_name])
        replay = authenticate_json(experiment / replay_name, original[replay_name])
        exact = authenticate_json(correction / review_name, reviewed[f"reproducer/{review_name}"])
        checkpoint = read_json(root / f"{label}-checkpoint.json")
        require_strict(strict, label)
        require_replay(replay, checkpoint, label)
        late.need(
            exact["checkpoint_payload_equal"] is True
            and exact["both_views_equal"] is True
            and exact["checkpoint_id"] == checkpoint["content_hash"]
            and exact["strict_save_restore"] == strict
            and exact["ordinary_full_replay"] == replay,
            f"Exact-head #733 proof differs for {label}.",
        )
        historical.add(label)
    return historical


def recover_summary(root, retreat, historical):
    def read(path):
        return json.loads(path.read_bytes())

    def audit_action(item, result):
        assert item["submitted"]["actor_id"] in late.PLAYERS
        assert result["returned"]["status_kind"] in ("waiting_for_decision", "advanced", "terminal")
        return item["submitted"]

    def staged_actions():
        actions = defaultdict(dict)
        pending = None
        for line in (root / "actions.jsonl").read_bytes().splitlines():
            row = json.loads(line)
            if "submitted" in row:
                assert pending is None
                pending = row
            elif "returned" in row:
                assert pending["stage"] == row["stage"]
                assert pending["result_id"] not in actions[row["stage"]]
                actions[row["stage"]][pending["result_id"]] = audit_action(pending, row)
                pending = None
        assert pending is None
        return actions

    archived = late.verified_input(retreat, late.RETREAT_FILE_HASH, late.RETREAT_CHECKPOINT)
    references = {
        int(record["request"]["request_id"].rsplit("-", 1)[1]): record["result"]
        for record in archived["lifecycle"]["decisions"]["records"]
    }
    actions = staged_actions()
    expected = declared_references()
    core = {}

    def finite(key, stage, number, option):
        item = actions[stage][references[number]["result_id"]]
        assert item["option_id"] == option
        core[key] = option

    def move(key, stage, number):
        item = actions[stage][references[number]["result_id"]]
        witness = json.loads(item["proposal_json"])["witness"]
        assert witness == references[number]["payload"]["witness"]
        core[key] = late.payload_digest(witness)

    finite("b2-attempt", "early", 44, late.B)
    finite("b2-decline", "b2-decline", 44, "complete_charge_phase")
    assert (
        json.loads(actions["early"]["timing:b2:omit-move"]["proposal_json"])[
            "charge_target_unit_instance_ids"
        ]
        == []
    )
    volley = frozen_e_rows(archived)
    assert len(volley) == 3
    endpoint_metrics = {}
    fresh = set()
    frontiers = set()
    for schedule, position in product(("early", "delayed", "decline"), ("preserve", "spend")):
        stage = f"{schedule}-{position}"
        finite(
            f"{stage}:S", stage, 46, "normal_move" if position == "spend" else "remain_stationary"
        )
        if position == "spend":
            move(f"{stage}:{late.S}", stage, 47)
        move(f"{stage}:{late.E}", stage, 78)
        rows = {}
        for action in ("omit", "shoot"):
            label = f"{stage}-{action}"
            actual = json.loads(actions[label][f"timing:e:{action}"]["proposal_json"])
            declared = volley if action == "shoot" else []
            assert actual["declarations"] == declared
            core[f"{label}:E-shooting"] = late.payload_digest(
                [late.REFERENCE_SHOOTING_POLICY_ID, late.E, declared]
            )
            rows[action] = read(root / f"{label}-metrics.json")
            cp = read(root / f"{label}-checkpoint.json")
            state = cp["lifecycle"]["state"]
            requests = cp["lifecycle"]["decisions"]["queue"]["pending_requests"]
            late.need(
                len(requests) == 1
                and requests[0]["decision_type"] == "select_shooting_unit"
                and state["battle_round"] == 4
                and state["active_player_id"] == "player-a",
                f"A4 endpoint differs for {label}.",
            )
            proof, ordinary = (
                root / f"{label}-replay-proof.json",
                root / f"{label}-ordinary-replay.json",
            )
            if proof.exists() and ordinary.exists():
                assert all(read(proof).values())
                result = read(ordinary)
                assert result["status"] == "reproduced"
                assert result["final_event_log_hash"] == cp["event_log_hash"]
                fresh.add(label)
            else:
                assert label in historical
        endpoint_metrics[stage] = rows

    for boundary in (
        "common-b2",
        "delayed-a3-selection",
        "early-b2-charge-move",
        "early-a3-selection",
    ):
        cp = read(root / f"{boundary}-checkpoint.json")
        assert all(read(root / f"{boundary}-replay-proof.json").values())
        ordinary = read(root / f"{boundary}-ordinary-replay.json")
        assert ordinary["status"] == "reproduced"
        assert ordinary["final_event_log_hash"] == cp["event_log_hash"]
        frontiers.add(boundary)

    assert core.keys() == expected.keys()
    redaction = []
    for p in sorted(root.glob("*-views.json")):
        packed = p.read_bytes()
        late.need(
            late.SEED.encode() not in packed and b'"private_rng_seed"' not in packed,
            f"Private seed leaked into {p.name}.",
        )
        assert set(json.loads(packed)) == set(late.PLAYERS)
        redaction.append(p.stem.removesuffix("-views"))

    timing = defaultdict(list)
    interrupted = []
    for line in (root / "timing.jsonl").read_bytes().splitlines():
        row = json.loads(line)
        if row["state"] == "return":
            timing[row["op"]].append([row["seconds"], row["cpu_seconds"]])
        elif row["state"] == "interrupted":
            interrupted.append(row)

    def roll(label, battle_round):
        cp = read(root / f"{label}-checkpoint.json")
        events = [
            e["payload"]
            for e in cp["lifecycle"]["decisions"]["event_log"]
            if e["event_type"] == "charge_roll_resolved"
            and e["payload"]["unit_instance_id"] == late.B
            and e["payload"]["roll_result"]["request"]["battle_round"] == battle_round
        ]
        assert len(events) == 1, (label, battle_round)
        event = events[0]
        return {
            "dice": event["roll_result"]["roll_state"]["original_result"]["values"],
            "roll_source": event["roll_result"]["roll_state"]["original_result"]["source"],
            "budget": event["maximum_distance_inches"],
            "reachable_targets": event["reachable_target_distances_inches"],
        }

    summary = {
        "campaign_terminal": "outer_timeout_during_historical_replay",
        "early_witness_result": "bounded_search_no_certified_witness_followed_by_native_omission",
        "verified_fresh_frontiers": sorted(frontiers),
        "verified_fresh_endpoints": sorted(fresh),
        "verified_historical_endpoints": sorted(historical),
        "declared_candidate_matches": len(core),
        "distinct_accepted_reference_contents": len(set(core.values())),
        "candidate_ids_by_occurrence": core,
        "redaction_files_verified": redaction,
        "endpoints": endpoint_metrics,
        "native_rolls": {
            "b2": roll("early-b2-charge-move", 2),
            "b3_preserve": roll("delayed-preserve-omit", 3),
            "b3_spend": roll("delayed-spend-omit", 3),
        },
        "timing_wall_cpu_seconds": timing,
        "typed_interrupted_calls": interrupted,
    }

    return (json.dumps(summary, indent=2) + "\n").encode()


def verify(raw_root, prior, retreat):
    raw = authenticate_raw(raw_root)
    historical = authenticate_pr733(raw_root, raw, prior)
    summary = recover_summary(raw_root, retreat, historical)
    late.need(sha256(summary).hexdigest() == SUMMARY, "Recovered summary SHA-256 differs.")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw", type=Path, required=True, help="Sealed B2/B3 raw receipt directory."
    )
    parser.add_argument(
        "--pr733", type=Path, required=True, help="Retained #733 closeout directory."
    )
    parser.add_argument("--retreat", type=Path, required=True, help="Sealed Retreat checkpoint.")
    args = parser.parse_args()
    signal.signal(signal.SIGALRM, late.stop_on_timeout)
    signal.setitimer(signal.ITIMER_REAL, VERIFY_SECONDS)
    try:
        summary = verify(args.raw, args.pr733, args.retreat)
    except (OSError, late.Blocker) as error:
        print(f"Receipt verification failed. {error}", file=sys.stderr)
        return 2
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    sys.stdout.buffer.write(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
