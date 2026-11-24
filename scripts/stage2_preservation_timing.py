"""Frozen development-only A3 preservation comparison on ordinary engine authority."""

import argparse
import hashlib
import signal
from dataclasses import asdict
from pathlib import Path
from time import monotonic, process_time

import orjson

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.replay import submit_replay_record
from warhammer40k_core.adapters.setup_smoke import canonical_setup_prebattle_smoke_config
from warhammer40k_core.ai.finite_candidates import FiniteCandidateSet
from warhammer40k_core.ai.normal_shooting_policy import generate_normal_shooting_candidates
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, payload_digest
from warhammer40k_core.build_identity import verified_engine_build_identity
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.engine.stratagems import stratagem_decline_payload

SELECT = "select_movement_action"
CHARGE = "select_charging_unit"
PROPOSAL = "submit_movement_proposal"
OPTIONAL = "submit_stratagem_target_proposal"
SHOOTING = "submit_shooting_declaration"
REFERENCE_SHOOTING_POLICY_ID = "ordinary-normal-shooting-focus-v1"
ANCHOR = "9cad766fcb5e277137e78267f986cf03ede57da3e33adce8fbb9f49f9b54b8e0"
SEED = "0fda2ab092cec5bf66a11a4d130e40b9b0de3c246a93df5e3ebded4d284ca0e3"


def options(public):
    return {row["option_id"]: row["payload"] for row in public["options"]}


def observed_models(context, unit):
    return {
        row["model_instance_id"]: row["pose"]
        for row in context.observation["battlefield_view"]["authoritative"]["models_by_id"].values()
        if row["rules_unit_instance_id"] == unit
        and row["state"] == "placed"
        and row["owner_player_id"] == context.route.actor_id
    }


def translated(context, unit, dy):
    offer = context.request["payload"]["proposal_request"]
    need(
        offer["unit_instance_id"] == unit and offer["proposal_kind"] == "normal_move",
        "Expected ordinary column Normal Move.",
    )
    movers = observed_models(context, unit)
    need(len(movers) == (3 if unit == E else 5), "Unexpected model inventory.")
    paths = []
    for model in sorted(movers, key=lambda model: movers[model]["position"]["y_inches"]):
        pose = movers[model]
        point = pose["position"]
        move = context.observation["model_display_by_id"][model]["current_characteristics"]["M"]
        need(
            point["z_inches"] == 0 and move["final"] >= abs(dy), "Unexpected physical M or height."
        )

        # Preserve the archived rounding order because waypoints enter the decision history.
        paths.append(
            {
                "model_id": model,
                "poses": [
                    {
                        "position": {
                            "x": point["x_inches"],
                            "y": point["y_inches"] + dy * index / 10,
                            "z": 0.0,
                        },
                        "facing": {"degrees": pose["facing_degrees"]},
                    }
                    for index in range(11)
                ],
            }
        )
    return context.propose(
        {
            "proposal_request_id": context.request["request_id"],
            "proposal_kind": "normal_move",
            "unit_instance_id": unit,
            "movement_phase_action": "normal_move",
            "movement_mode": "normal",
            "witness": {"model_paths": paths},
        }
    )


def reference_bearers(context):
    offer = context.request["payload"]["proposal_request"]
    need(
        offer["unit_instance_id"] == E and offer["selected_shooting_type"] == "normal",
        "Expected E's ordinary Normal Shooting.",
    )
    legal = {
        (row["weapon_instance_id"], row["weapon_profile_id"])
        for row in offer["target_candidates"]
        if row["target_unit_instance_id"] == B
        and row["is_legal"]
        and "normal" in row["shooting_types"]
        and not row["required_weapon_ability_selections"]
    }
    return [
        {
            "attacker_model_instance_id": weapon["model_instance_id"],
            "weapon_instance_id": weapon["weapon_instance_id"],
            "wargear_id": weapon["wargear_id"],
            "weapon_profile_id": weapon["weapon_profile_id"],
            "target_unit_instance_id": B,
            "shooting_type": "normal",
            "selected_weapon_ability_ids": [],
            "firing_deck_source_unit_instance_id": None,
            "firing_deck_source_model_instance_id": None,
        }
        for weapon in offer["available_weapons"]
        if (weapon["weapon_instance_id"], weapon["weapon_profile_id"]) in legal
    ]


def verify_shooting_reference(candidate, reference):
    """Verify the frozen declaration and its ID in the registered policy format."""
    actual = orjson.loads(candidate.action.proposal_json)
    need(
        actual["declarations"] == reference,
        "Generated E volley differs from the independent reference.",
    )
    reference_id = payload_digest([REFERENCE_SHOOTING_POLICY_ID, E, reference])
    need(candidate.candidate_id == reference_id, "Generated E candidate ID differs from reference.")
    return reference_id


B = "army-beta:scout-redeploy-unit"

E = "army-alpha:deep-strike-unit"

S = "army-alpha:scout-redeploy-unit"

PLAYERS = ("player-a", "player-b")


class Blocker(Exception):
    pass


class ArchiveMismatch(Blocker):
    """An archived action does not match the live offer."""


def read(path):
    return orjson.loads(path.read_bytes())


def write(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(orjson.dumps(value, option=orjson.OPT_SORT_KEYS | orjson.OPT_INDENT_2) + b"\n")
    tmp.replace(path)


def provenance(session):
    controller = session.lifecycle.decision_controller
    return (
        [r.to_payload() for r in controller.records],
        [e.to_payload() for e in controller.event_log.records],
    )


def views(session):
    return {
        p: {
            "view": session.view(viewer_player_id=p),
            "events": session.events_since(EventStreamCursor(), viewer_player_id=p),
        }
        for p in PLAYERS
    }


def issued(session):
    native = session.lifecycle.pending_decision_request()
    if native is None:
        return None, None, None
    viewer = ViewerContext.for_player(native.actor_id)
    return native, viewer, session.view_for_context(viewer=viewer)["pending_decision"]


def phase(session):
    s = session.lifecycle.state
    return [s.battle_round, s.active_player_id, s.current_battle_phase.value]


def placement_map(raw):
    return {
        u["unit_instance_id"]: u["model_placements"]
        for a in raw["battlefield_state"]["placed_armies"]
        for u in a["unit_placements"]
    }


def unit_map(raw):
    return {u["unit_instance_id"]: u for a in raw["army_definitions"] for u in a["units"]}


PARAMETERIZED = "submit_parameterized_payload"


def need(ok, message):
    if not ok:
        raise Blocker(message)


def archived_action(context, reference):
    """Rebind frozen ordinary choices only to the correct current actor and route."""
    request = context.request
    old_request, old_result = reference["request"], reference["result"]
    if any(request[key] != old_request[key] for key in ("actor_id", "decision_type")):
        raise ArchiveMismatch(f"Expected {old_request['actor_id']} {old_request['decision_type']}.")
    for key in ("unit_instance_id", "active_player_id", "battle_round", "phase"):
        if (
            key in old_request["payload"]
            and request["payload"].get(key) != old_request["payload"][key]
        ):
            raise ArchiveMismatch(f"Request drift: {key}.")

    selected = old_result["selected_option_id"]
    if selected != PARAMETERIZED:
        live = options(request)
        if selected not in live:
            raise ArchiveMismatch(f"Archived choice unavailable: {selected}.")
        original = options(old_request)[selected]
        for key in (
            "unit_instance_id",
            "target_ids",
            "movement_phase_action",
            "fall_back_mode",
            "shooting_type",
            "ordering_band",
            "fight_type",
        ):
            if key in original and live[selected].get(key) != original[key]:
                raise ArchiveMismatch(f"Option drift: {key}.")
        return context.select_option(selected)
    if request["decision_type"] == OPTIONAL:
        if not request["payload"]["declinable"]:
            raise ArchiveMismatch("Compulsory reaction cannot be declined.")
        return context.propose(stratagem_decline_payload())
    need(request["decision_type"] == PROPOSAL, "Unplanned archived proposal.")
    payload = old_result["payload"]
    offer = request["payload"].get("proposal_request") or context.observation["pending_proposal"]
    for key in ("proposal_kind", "unit_instance_id", "movement_phase_action"):
        if offer[key] != payload[key]:
            raise ArchiveMismatch(f"Archived proposal drift: {key}.")
    return context.propose({**payload, "proposal_request_id": offer["request_id"]})


def metrics(cp):
    s = cp["lifecycle"]["state"]
    units = unit_map(s)
    placed = placement_map(s)
    material = {}
    for uid in (S, B, E, "army-alpha:strategic-reserve-unit"):
        alive = {
            m["model_instance_id"]: m["wounds_remaining"]
            for m in units[uid]["own_models"]
            if m["wounds_remaining"] > 0
        }
        material[uid] = {
            "survivors": len(alive),
            "wounds": sum(alive.values()),
            "living_models": alive,
            "placements": placed[uid],
            "battle_shocked": uid in s["battle_shocked_unit_ids"],
        }
    return {
        "material": material,
        "cp": {x["player_id"]: x["command_points"] for x in s["command_point_ledgers"]},
        "vp": {x["player_id"]: x["victory_points"] for x in s["victory_point_ledgers"]},
        "control": s["objective_control_records"][-1],
        "counts": [
            len(cp["lifecycle"]["decisions"]["records"]),
            len(cp["lifecycle"]["decisions"]["event_log"]),
            cp["rng_state"]["draw_count"],
        ],
    }


DECLINE_IDS = {"decline", "keep", "keep_all_modifiers", "decline_stratagem_window"}

REQUIRED_SELECTION = {
    "select_damage_allocation_model",
    "select_allocation_order",
    "select_attack_weapon_group",
    "select_post_roll_attack_pool",
    "select_mortal_wound_model",
}


def policy(public):
    kind = public["decision_type"]
    options = sorted(o["option_id"] for o in public["options"])
    if kind == "use_stratagem":
        declines = [o for o in options if o in DECLINE_IDS or o.endswith(":decline")]
        need(len(declines) == 1, "No unique issued historical optional decline or keep action.")
        return declines[0], "decline optional reaction or keep natural result"
    if kind in REQUIRED_SELECTION and options:
        return options[
            0
        ], "archived first offered option ID for mandatory attack group or allocation"
    if kind == "select_resolve_target_unit" and len(options) == 1:
        need(
            public["options"][0]["payload"]["target_unit_instance_id"] == B,
            "Attack target changed from B.",
        )
        return options[0], "only issued B target"
    raise Blocker(f"Unrecognized mandatory or optional continuation {kind}.")


ANCHOR_FILE_HASH = "db0ce61487d207b2aab28026cde469a15296f498775b5201e27a65193929ee2d"
RETREAT_FILE_HASH = "c1bea5f657bfdbef054f9f9c361a6655a318496d5ccbd68b39235215355b96b3"
RETREAT_CHECKPOINT = "34349f7a00ee3dff835d343c2201057f5314a3fb8e9830fcaf377e43db4d92a8"


def verified_input(path, file_hash, checkpoint):
    data = path.read_bytes()
    need(hashlib.sha256(data).hexdigest() == file_hash, f"Archive bytes differ: {path}")
    result = orjson.loads(data)
    need(
        result["content_hash"] == checkpoint and result["rng_state"]["seed"] == SEED,
        f"Frozen archive identity differs: {path}",
    )
    return result


class Experiment:
    def __init__(self, root, anchor, retreat):
        self.root = root
        self.stage = "prepare"
        self.t0 = monotonic()
        self.preparation_deadline = self.t0 + 300
        self.anchor = verified_input(anchor, ANCHOR_FILE_HASH, ANCHOR)
        source = verified_input(retreat, RETREAT_FILE_HASH, RETREAT_CHECKPOINT)
        self.rows = self.anchor["lifecycle"]["decisions"]["records"]
        reference = source["lifecycle"]["decisions"]["records"]
        need(
            len(self.rows) == 70 and reference[:70] == self.rows,
            "Frozen checkpoints do not share the accepted 70-decision prefix.",
        )
        self.numbered = {
            int(row["request"]["request_id"].rsplit("-", 1)[1]): row for row in reference
        }
        self.result = {
            "experiment": "stage2-a3-preservation-b3-charge-v1",
            "source_checkpoints": {"anchor": ANCHOR, "retreat": RETREAT_CHECKPOINT},
            "source_hashes": {"anchor": ANCHOR_FILE_HASH, "retreat": RETREAT_FILE_HASH},
            "producer_build": verified_engine_build_identity().build_id,
            "arms": {},
            "provenance": {},
            "coverage": {},
            "errors": {},
            "responses": {},
            "native_call_cap_seconds": 180,
            "overall_cap_seconds": 1800,
            "primary_local_payoff": "A VP minus B VP at first post-E A4 Shooting selection",
        }
        self.journal = (root / "timing.jsonl").open("x", buffering=1)
        self.actions = (root / "actions.jsonl").open("x", buffering=1)

    def log(self, stream, **row):
        entry = {"stage": self.stage, "elapsed": monotonic() - self.t0, **row}
        stream.write(orjson.dumps(entry).decode("utf-8") + "\n")

    def status(self, result):
        status = result.status_kind.value
        need(status not in {"invalid", "unsupported"}, f"Native {status}: {result.message}")

    def next_public(self, session, *, advance=True):
        native, viewer, public = self.call("read_issued_view", lambda: issued(session))
        if native is None and advance:
            self.status(self.call("advance_to_issued", session.advance_until_decision_or_terminal))
            native, viewer, public = self.call("read_issued_view", lambda: issued(session))
        return viewer, public

    def seal(self, label, session):
        p = self.call("save_current_checkpoint", session.to_persistence_payload)
        v = self.call("capture_both_views_and_visible_events", lambda: views(session))
        write(self.root / f"{label}-checkpoint.json", p)
        write(self.root / f"{label}-views.json", v)
        return p, v

    def compare_exact(self, label, s):
        saved = read(self.root / f"{label}-checkpoint.json")
        now = self.call("compare_replayed_checkpoint", s.to_persistence_payload)
        expected_views = read(self.root / f"{label}-views.json")
        now_views = self.call("compare_both_replayed_views", lambda: views(s))
        checks = {
            "lifecycle": now["lifecycle"] == saved["lifecycle"],
            "rng": now["rng_state"] == saved["rng_state"],
            "decisions_events_artifact": now["replay_artifact"] == saved["replay_artifact"],
            "save_payload": now == saved,
            "both_player_views_and_visible_events": now_views == expected_views,
        }
        write(self.root / f"{label}-replay-proof.json", checks)
        need(all(checks.values()), f"Replay parity differs: {label}: {checks}.")
        self.result["provenance"][label] = checks

    def native_replay(self, session, rows, start):
        for i, row in enumerate(rows, start):
            if (
                session.decision_record_count() == i
                and session.lifecycle.pending_decision_request() is None
            ):
                self.status(self.call("replay_advance", session.advance_until_decision_or_terminal))
            if session.decision_record_count() == i:
                request = session.lifecycle.pending_decision_request()
                need(
                    request is not None and request.to_payload() == row["request"],
                    "Issued replay request drift.",
                )
                self.status(
                    self.call(
                        "replay_native_record",
                        lambda row=row: submit_replay_record(
                            session=session, record=DecisionRecord.from_payload(row)
                        ),
                    )
                )
            need(
                session.decision_record_count() > i
                and session.lifecycle.decision_controller.records[i].to_payload() == row,
                "Committed replay record drift.",
            )

    def call(self, kind, operation):
        started, cpu = monotonic(), process_time()
        deadline = min(self.preparation_deadline, self.t0 + 1800)
        cap = min(180, deadline - started)
        need(cap > 0, "Frozen preparation or overall bound exhausted.")
        self.log(self.journal, op=kind, state="start", cap_seconds=cap)
        signal.setitimer(signal.ITIMER_REAL, cap)
        finished = False
        try:
            result = operation()
            finished = True
            return result
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            self.log(
                self.journal,
                op=kind,
                state="return" if finished else "interrupted",
                seconds=monotonic() - started,
                cpu_seconds=process_time() - cpu,
            )

    def source(self, session, number, current=None):
        if current is None:
            _, _, context = self.context(session)
        else:
            context = self.player_context(session, current[0])
        action = self.call(
            "bind_archived_action", lambda: archived_action(context, self.numbered[number])
        )
        self.commit_action(session, action, self.record_id(number))

    def player_context(self, session, viewer):
        view = self.call("actor_projection", lambda: session.view_for_context(viewer=viewer))
        return self.call(
            "actor_context", lambda: PlayerDecisionContext.from_view(view, choice_seed=0)
        )

    def context(self, session):
        viewer, public = self.next_public(session)
        need(public is not None, "Missing ordinary actor request.")
        return viewer, public, self.player_context(session, viewer)

    def commit_action(self, session, action, tag, *, allow_invalid=False):
        kwargs = {
            "viewer": ViewerContext.for_player(action.actor_id),
            "request_id": action.request_id,
            "result_id": tag,
        }
        self.log(self.actions, submitted=asdict(action), result_id=tag)
        if action.option_id is not None:
            status = self.call(
                "submit_finite",
                lambda: session.submit_viewer_option(**kwargs, option_id=action.option_id),
            )
        else:
            status = self.call(
                "submit_parameterized",
                lambda: session.submit_viewer_parameterized_payload(
                    **kwargs, payload=orjson.loads(action.proposal_json)
                ),
            )
        self.log(self.actions, returned=status.to_payload())
        if not (allow_invalid and status.status_kind.value == "invalid"):
            self.status(status)
        return status

    def common(self):
        session = LocalGameSession()
        auth = self.anchor["lifecycle"]["config"]
        cfg = self.call(
            "make_native_config",
            lambda: canonical_setup_prebattle_smoke_config(
                game_id=auth["game_id"], private_rng_seed=SEED
            ),
        )
        need(cfg.to_payload() == auth, "Ordinary config drift.")
        self.status(self.call("start_native_game", lambda: session.start(cfg)))
        self.status(self.call("issue_initial_request", session.advance_until_decision_or_terminal))
        need(
            session.lifecycle.to_payload() == self.anchor["initial_replay_lifecycle"],
            "Ordinary initial origin drift.",
        )
        self.native_replay(session, self.rows[:45], 0)
        _, public = self.next_public(session)
        need(
            public["decision_type"] == SELECT
            and phase(session) == [3, "player-a", "movement"]
            and public["payload"]["unit_instance_id"] == S
            and session.lifecycle.pending_decision_request().request_id
            == "decision-request-000046",
            "Fixed A3 S boundary was not issued.",
        )
        rows, events = provenance(session)
        need(
            rows == self.rows[:45]
            and events == self.anchor["lifecycle"]["decisions"]["event_log"][: len(events)],
            "Fixed historical accepted prefix differs.",
        )
        self.result["common"] = {"decisions": len(rows), "events": len(events), "pending": public}
        print("COMMON", len(rows), len(events), flush=True)
        return session

    def record_id(self, number):
        return self.numbered[number]["result"]["result_id"]

    def translate(self, session, number, unit, change):
        _, _, context = self.context(session)
        reference = self.numbered[number]["result"]["payload"]
        action = self.call("straight_path_generation", lambda: translated(context, unit, change))
        proposal = orjson.loads(action.proposal_json)
        native_paths = reference["witness"]["model_paths"]
        actor_paths = proposal["witness"]["model_paths"]
        need(len(native_paths) == len(actor_paths), "Independent reference inventory differs.")
        for old, new in zip(native_paths, actor_paths, strict=True):
            need(
                old["model_id"] == new["model_id"]
                and old["poses"][0] == new["poses"][0]
                and old["poses"][-1] == new["poses"][-1],
                "Reference path endpoints/order differ.",
            )
        need(actor_paths == native_paths, "Generated full witness differs from frozen reference.")
        self.commit_action(session, action, self.record_id(number))
        self.result["coverage"][self.stage + ":" + unit] = {
            "reference_id": payload_digest(reference["witness"]),
            "candidate_id": payload_digest(proposal["witness"]),
            "native_accepted": True,
            "comparison": "same straight geometry and sequential model order",
        }

    def position(self, session, spend):
        _viewer, _public, context = self.context(session)
        finite = self.call("finite_generation", lambda: FiniteCandidateSet.from_context(context))
        option = "normal_move" if spend else "remain_stationary"
        self.commit_action(session, finite.select(context, option), self.record_id(46))
        self.result["coverage"][self.stage + ":S"] = {
            "reference_id": option,
            "candidate_id": option,
            "native_accepted": True,
            "issued_candidates": finite.candidate_ids,
        }
        if spend:
            self.translate(session, 47, S, -6.0)
        for number in range(48, 61):
            current = self.next_public(session)
            _, request = current
            old = self.numbered[number]["request"]
            if number in (54, 55) and (request["actor_id"], request["decision_type"]) != (
                old["actor_id"],
                old["decision_type"],
            ):
                self.log(self.actions, naturally_unissued_archived_step=number)
                continue
            self.source(session, number, current)

    def response(self, session, charge):
        viewer, public, context = self.context(session)
        note = {"pending": public, "natural_charge_attempt": charge}
        self.result["responses"][self.stage] = note
        if public["decision_type"] == CHARGE:
            if not charge or B not in options(public):
                self.commit_action(
                    session,
                    context.select_option("complete_charge_phase"),
                    "timing:b3:complete-charge",
                )
            else:
                for number in (61, 62):
                    self.source(session, number)
                viewer, public, context = self.context(session)
                roll_events = [
                    event.to_payload()
                    for event in session.lifecycle.decision_controller.event_log.records
                    if event.event_type in ("charge_roll_resolved", "charge_no_move_possible")
                    and event.payload["roll_result"]["request"]["battle_round"] == 3
                    and event.payload["unit_instance_id"] == B
                ]
                note["native_charge_events"] = roll_events
                if public["decision_type"] == "select_charge_targets":
                    self.source(session, 63, (viewer, public))
                    self.charge_witness(session, note)
                else:
                    need(
                        [event["event_type"] for event in roll_events]
                        == ["charge_roll_resolved", "charge_no_move_possible"],
                        "Unissued Charge target has no native no-move result.",
                    )
                    print("CHARGE", self.stage, "native no move possible", flush=True)

        viewer, public, context = self.context(session)
        if public["decision_type"] == OPTIONAL:
            need(
                public["payload"]["declinable"]
                and "core:heroic-intervention" in orjson.dumps(public).decode(),
                "Unplanned B3 reaction.",
            )
            self.commit_action(
                session,
                context.propose(stratagem_decline_payload()),
                "timing:b3:heroic-decline",
            )
        _, public = self.next_public(session)
        need(
            phase(session) == [4, "player-a", "movement"]
            and public["decision_type"] == "select_movement_unit",
            "First ordinary A4 Movement horizon was not reached.",
        )
        cp = self.call("local_a4_entry_snapshot", session.to_persistence_payload)
        write(self.root / f"{self.stage}-a4-entry.json", metrics(cp))

    def charge_witness(self, session, note):
        _viewer, public, context = self.context(session)
        issued = public["payload"]["proposal_request"]
        need(
            public["decision_type"] == PROPOSAL and issued["proposal_kind"] == "charge_move",
            "Expected the native B3 Charge Move.",
        )
        note["natural_roll"] = issued["context"]["charge_roll"]
        ref = self.numbered[64]["result"]["payload"]
        action = context.propose({**ref, "proposal_request_id": issued["request_id"]})
        starts = observed_models(context, B)
        for path in ref["witness"]["model_paths"]:
            start = path["poses"][0]
            live = starts[path["model_id"]]
            need(
                live["facing_degrees"] == start["facing"]["degrees"]
                and all(
                    live["position"][f"{axis}_inches"] == start["position"][axis] for axis in "xyz"
                ),
                "Matched B3 charge start drift.",
            )
        result = self.commit_action(session, action, self.record_id(64), allow_invalid=True)
        note["witness_result"] = result.to_payload()
        print("CHARGE", self.stage, result.status_kind.value, flush=True)
        if result.status_kind.value == "invalid":
            _viewer, public, context = self.context(session)
            fresh = public["payload"]["proposal_request"]
            need(
                fresh["proposal_kind"] == "charge_move"
                and fresh["request_id"] != issued["request_id"],
                "Native rejection did not yield a Charge Move retry.",
            )
            decline = {key: value for key, value in ref.items() if key != "witness"}
            decline.update(
                proposal_request_id=fresh["request_id"], charge_target_unit_instance_ids=[]
            )
            self.commit_action(session, context.propose(decline), "timing:b3:decline-move")
        else:
            for number in range(65, 71):
                self.source(session, number)

    def prepare_e(self, session):
        self.source(session, 71)
        _viewer, public, context = self.context(session)
        if "fall_back:desperate_escape" in options(public):
            self.source(session, 72)
            self.source(session, 73)
            current = self.next_public(session)
            if current[1]["decision_type"] == "select_mortal_wound_model":
                self.source(session, 74, current)
        else:
            self.commit_action(
                session,
                context.select_option("remain_stationary"),
                "timing:a4:unengaged-s-hold",
            )
        for number in (76, 77):
            self.source(session, number)
        self.translate(session, 78, E, -6.0)
        for number in (79, 80):
            self.source(session, number)
        current = self.next_public(session)
        if current[1]["decision_type"] == OPTIONAL:
            self.source(session, 81, current)
        for number in (82, 83):
            self.source(session, number)
        _, public = self.next_public(session)
        need(
            public["decision_type"] in (SHOOTING, "select_shooting_unit"), "Unexpected E boundary."
        )
        write(self.root / f"{self.stage}-e-offer.json", public)

    def e_shoot(self, session, shoot):
        _viewer, public, context = self.context(session)
        if public["decision_type"] == SHOOTING:
            reference = reference_bearers(context) if shoot else []
            need(not shoot or reference, "No native B target reference was offered.")
            candidates = self.call(
                "E_shooting_generation", lambda: generate_normal_shooting_candidates(context)
            )
            target = B if shoot else None
            chosen = [
                candidate for candidate in candidates if candidate.target_unit_instance_id == target
            ]
            need(len(chosen) == 1, "Generated E action misses independent reference.")
            candidate = chosen[0]
            reference_id = verify_shooting_reference(candidate, reference)
            self.commit_action(
                session,
                candidate.action,
                "timing:e:shoot" if shoot else "timing:e:omit",
            )
            self.result["coverage"][self.stage + ":E-shooting"] = {
                "reference_id": reference_id,
                "candidate_id": candidate.candidate_id,
                "reference_declaration_digest": payload_digest(reference),
                "native_accepted": True,
                "weapons": len(reference),
            }
            for index in range(36):
                _viewer, public, context = self.context(session)
                if public["decision_type"] == "select_shooting_unit":
                    break
                if public["decision_type"] == OPTIONAL:
                    need(
                        public["payload"]["declinable"],
                        "Unexpected mandatory reaction during shooting.",
                    )
                    action = context.propose(stratagem_decline_payload())
                else:
                    option, _ = policy(public)
                    action = context.select_option(option)
                self.commit_action(session, action, f"timing:e:resolve:{index:02d}")
            else:
                raise Blocker("E shooting exceeded 36 ordinary resolutions.")
        else:
            self.result["coverage"][self.stage + ":E-shooting"] = {
                "availability": "native no declaration"
            }
        need(
            phase(session) == [4, "player-a", "shooting"]
            and public["decision_type"] == "select_shooting_unit"
            and E not in options(public),
            "Expected first post-E A4 Shooting unit offer.",
        )
        checkpoint, _ = self.seal(self.stage, session)
        measured = metrics(checkpoint)
        measured["A_minus_B_vp"] = measured["vp"]["player-a"] - measured["vp"]["player-b"]
        measured["shooting_state"] = checkpoint["lifecycle"]["state"]["shooting_phase_state"]
        measured["checkpoint_id"] = checkpoint["content_hash"]
        self.result["arms"][self.stage] = measured
        write(self.root / f"{self.stage}-metrics.json", measured)
        print("HORIZON", self.stage, measured["vp"], flush=True)

    def strict(self, label):
        self.stage = label
        checkpoint = read(self.root / f"{label}-checkpoint.json")
        restored = self.call(
            "strict_JSON_restore",
            lambda: LocalGameSession.from_persistence_payload(
                read(self.root / f"{self.stage}-checkpoint.json")
            ),
        )
        self.compare_exact(self.stage, restored)
        replay = self.call(
            "ordinary_full_replay",
            lambda: ReplayRunner.from_payload(checkpoint["replay_artifact"]).run(),
        )
        write(self.root / f"{self.stage}-ordinary-replay.json", replay.to_payload())
        need(
            replay.reproduced_exactly
            and replay.final_event_log_hash == checkpoint["event_log_hash"],
            "Ordinary replay did not reproduce exact history.",
        )
        self.result["arms"][label]["strict"] = True
        print("REPLAY", label, flush=True)

    def execute(self):
        common = self.common()
        self.seal("common", common)
        for spend in (True, False):
            name = "spend" if spend else "preserve"
            self.stage = name
            self.preparation_deadline = monotonic() + 300
            try:
                position = self.call("fork_common", common.fork)
                self.position(position, spend)
            except Blocker as exc:
                self.gap(exc)
                continue
            for charge in (True, False):
                arm = name + ("-charge" if charge else "-decline")
                self.stage = arm
                self.preparation_deadline = monotonic() + 300
                try:
                    prepared = self.call("fork_B3", position.fork)
                    self.response(prepared, charge)
                    self.prepare_e(prepared)
                except Blocker as exc:
                    self.gap(exc)
                    continue
                for shoot in (False, True):
                    self.stage = arm + ("-shoot" if shoot else "-omit")
                    self.preparation_deadline = self.t0 + 1800
                    try:
                        final = self.call("fork_E_offer", prepared.fork)
                        self.e_shoot(final, shoot)
                    except Blocker as exc:
                        self.gap(exc)
        for label in self.result["arms"]:
            try:
                self.strict(label)
            except Blocker as exc:
                self.gap(exc)
        self.report_core_coverage()
        return 2 if self.result["errors"] else 0

    def report_core_coverage(self):
        coverage = self.result["coverage"]
        expected = {"preserve:S", "spend:S", f"spend:{S}"}
        for position in ("preserve", "spend"):
            for response in ("charge", "decline"):
                prefix = f"{position}-{response}"
                expected.add(f"{prefix}:{E}")
                expected.add(f"{prefix}-shoot:E-shooting")
                expected.add(f"{prefix}-omit:E-shooting")
        accepted = {key for key, row in coverage.items() if row.get("native_accepted")}
        unavailable = {key for key, row in coverage.items() if row.get("availability")}
        matched = accepted & expected
        self.result["core_coverage"] = {
            "declared_reference_steps": len(expected),
            "native_accepted_generated_matches": len(matched),
            "distinct_accepted_reference_contents": len(
                {coverage[key]["reference_id"] for key in matched}
            ),
            "native_unissued": sorted(unavailable & expected),
            "unresolved_reference_steps": sorted(expected - accepted - unavailable),
        }

    def gap(self, error):
        self.result["errors"][self.stage] = str(error)
        print("GAP", self.stage, str(error), flush=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, error, traceback):
        if isinstance(error, Blocker):
            self.gap(error)
        self.result["elapsed_seconds"] = monotonic() - self.t0
        write(self.root / "result.json", self.result)
        self.actions.close()
        self.journal.close()


def stop_on_timeout(_signal, _frame):
    raise Blocker("Frozen per-call timeout.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anchor", type=Path, required=True, help="Sealed B3 charge archive")
    parser.add_argument(
        "--retreat", type=Path, required=True, help="Sealed A4 E declaration archive"
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="Create a fresh receipt directory"
    )
    args = parser.parse_args()
    args.output.mkdir()
    signal.signal(signal.SIGALRM, stop_on_timeout)
    with Experiment(args.output, args.anchor, args.retreat) as experiment:
        try:
            return experiment.execute()
        except Blocker as error:
            experiment.gap(error)
            return 2


if __name__ == "__main__":
    raise SystemExit(main())
