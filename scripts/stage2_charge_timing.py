"""Compare one native B2 Charge attempt with the delayed B3 response in Stage 2."""

import argparse
import signal
from functools import partial
from pathlib import Path
from time import monotonic

import orjson

from scripts import stage2_preservation_timing as late
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.setup_smoke import canonical_setup_prebattle_smoke_config
from warhammer40k_core.ai.finite_candidates import FiniteCandidateSet
from warhammer40k_core.ai.ground_charge_candidates import GroundChargeExhaustedError
from warhammer40k_core.ai.ground_charge_policy import (
    GroundChargeValidationExhaustedError,
    prepare_ground_charge_policy,
)
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyError, payload_digest
from warhammer40k_core.engine.stratagems import stratagem_decline_payload

B, S, E = late.B, late.S, late.E
SCHEDULES = ("early", "delayed", "decline")
POSITIONS = ("preserve", "spend")
E_ACTIONS = ("omit", "shoot")
COMPLETE_CHARGE = "complete_charge_phase"
SELECT_TARGETS = "select_charge_targets"
PREFIX_LENGTH = 43
PREFIX_EVENTS = 423
MAX_EARLY_PROPOSALS = 4
MAX_EARLY_WORK = 600_000
MAX_EARLY_WALL_SECONDS = 120


class Unmatchable(Exception):
    """A required reference offer is absent or materially changed."""

    def __init__(self, reason, detail):
        super().__init__(detail)
        self.reason = reason


def declared_references():
    keys = {"b2-attempt", "b2-decline"}
    for schedule in SCHEDULES:
        keys.add(f"{schedule}-spend:{S}")
        for position in POSITIONS:
            arm = f"{schedule}-{position}"
            keys.update((f"{arm}:S", f"{arm}:{E}"))
            keys.update(f"{arm}-{action}:E-shooting" for action in E_ACTIONS)
    return dict.fromkeys(sorted(keys), "unreached")


def audit_actor_views(session, audience):
    native = session.lifecycle.pending_decision_request()
    packed = orjson.dumps(audience)
    late.need(late.SEED.encode() not in packed, "Private seed value reached a player view.")
    late.need(b'"private_rng_seed"' not in packed, "Private seed field reached a player view.")
    if native is None:
        return {"private_seed_absent": True, "pending_actor": None}
    actor = native.actor_id
    other = next(player for player in late.PLAYERS if player != actor)
    context = PlayerDecisionContext.from_view(audience[actor]["view"], choice_seed=0)
    late.need(context.route.actor_id == actor, "Actor context bound to a different player.")
    try:
        PlayerDecisionContext.from_view(audience[other]["view"], choice_seed=0)
    except PolicyError:
        return {
            "private_seed_absent": True,
            "pending_actor": actor,
            "other_player_cannot_bind": True,
            "other_player_pending_metadata": audience[other]["view"]["pending_decision"]
            is not None,
        }
    raise late.Blocker("Non-actor acquired a bound action context.")


def frozen_e_rows(checkpoint):
    queue = checkpoint["lifecycle"]["decisions"]["queue"]
    offers = [
        item["payload"]["proposal_request"]
        for item in queue["pending_requests"]
        if item["decision_type"] == late.SHOOTING
    ]
    late.need(len(offers) == 1, "Archived E declaration request absent.")
    offer = offers[0]
    late.need(offer["unit_instance_id"] == E, "Archived shooter changed.")
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
    ]


def bind_early_fight_reference(context, number, reference):
    """Classify a changed archived Fight offer before submitting any action."""
    try:
        return late.archived_action(context, reference)
    except late.Blocker as error:
        raise Unmatchable(
            "early_fight_archive_unbindable",
            f"Archived Fight row {number} cannot bind at B2. "
            f"Archived round {reference['request']['payload'].get('battle_round')}, "
            f"issued round {context.request['payload'].get('battle_round')}. {error}",
        ) from error


def charge_history(session, round_number):
    relevant = {
        "charge_roll_resolved",
        "charge_no_move_possible",
        "charge_move_completed",
        "charge_move_declined",
        "charge_targets_selected",
    }
    return [
        event.to_payload()
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type in relevant
        and isinstance(event.payload, dict)
        and event.payload.get("unit_instance_id") == B
        and (
            event.payload.get("battle_round") == round_number
            or event.payload.get("roll_result", {}).get("request", {}).get("battle_round")
            == round_number
        )
    ]


class TimingExperiment(late.Experiment):
    def __init__(self, root, anchor, retreat):
        super().__init__(root, anchor, retreat)
        self.preparation_deadline = self.t0 + 1800
        archived = late.verified_input(retreat, late.RETREAT_FILE_HASH, late.RETREAT_CHECKPOINT)
        self.volley = frozen_e_rows(archived)
        late.need(len(self.volley) == 3, "Frozen E volley must contain three carbines.")
        self.proof_labels = []
        self.result.update(
            experiment="stage2-b2-b3-charge-timing-v1",
            declared_references=declared_references(),
            boundaries={},
            unmatchable={},
            redaction={},
            e_reference_declarations=self.volley,
            schedules=SCHEDULES,
            maximum_endpoints=12,
            early_charge_cap={
                "raw": MAX_EARLY_PROPOSALS,
                "work": MAX_EARLY_WORK,
                "seconds": MAX_EARLY_WALL_SECONDS,
            },
        )

    def common(self):
        session = LocalGameSession()
        auth = self.anchor["lifecycle"]["config"]
        config = self.call(
            "make_native_config",
            lambda: canonical_setup_prebattle_smoke_config(
                game_id=auth["game_id"], private_rng_seed=late.SEED
            ),
        )
        late.need(config.to_payload() == auth, "Ordinary config differs from the admitted origin.")
        self.status(self.call("start_native_game", lambda: session.start(config)))
        self.status(self.call("issue_initial_request", session.advance_until_decision_or_terminal))
        late.need(
            session.lifecycle.to_payload() == self.anchor["initial_replay_lifecycle"],
            "Ordinary initial origin drift.",
        )
        self.native_replay(session, self.rows[:PREFIX_LENGTH], 0)
        _, public = self.next_public(session)
        rows, events = late.provenance(session)
        expected = self.anchor["lifecycle"]["decisions"]["event_log"]
        checks = {
            "phase": late.phase(session),
            "pending": [
                public["decision_type"],
                session.lifecycle.pending_decision_request().request_id,
            ],
            "viewer_request_id": public["request_id"],
            "options": tuple(late.options(public)),
            "accepted_records": len(rows),
            "events": len(events),
            "archived_records_equal": rows == self.rows[:PREFIX_LENGTH],
            "archived_events_equal": events == expected[: len(events)],
            "last_event": events[-1]["event_type"],
        }
        self.result["prefix_checks"] = checks
        late.need(
            checks["phase"] == [2, "player-b", "charge"]
            and checks["pending"] == [late.CHARGE, "decision-request-000044"]
            and B in checks["options"]
            and checks["archived_records_equal"]
            and len(events) == PREFIX_EVENTS
            and checks["archived_events_equal"],
            f"Native B2 pre-decline prefix drifted: {checks}.",
        )
        self.result["common"] = {
            "decisions": len(rows),
            "events": len(events),
            "pending": public,
        }
        self.boundary("common-b2", session, proof=True)
        print("COMMON", len(rows), len(events), flush=True)
        return session

    def seal(self, label, session):
        checkpoint, audience = super().seal(label, session)
        self.result["redaction"][label] = self.call(
            "audit_player_views", lambda: audit_actor_views(session, audience)
        )
        return checkpoint, audience

    def boundary(self, label, session, *, proof=False):
        checkpoint, audience = self.seal(label, session)
        details = late.metrics(checkpoint)
        details.update(
            request=next(
                (
                    player["view"]["pending_decision"]
                    for actor, player in audience.items()
                    if player["view"]["pending_decision"] is not None
                    and player["view"]["pending_decision"]["actor_id"] == actor
                ),
                None,
            ),
            native_phase=late.phase(session),
            content_hash=checkpoint["content_hash"],
            scoring_events=[
                event
                for event in checkpoint["lifecycle"]["decisions"]["event_log"]
                if "victory_points" in event["event_type"]
                or event["event_type"] == "primary_scoring_commit_checkpoint_recorded"
            ],
        )
        self.result["boundaries"][label] = details
        if proof:
            self.proof_labels.append(label)
        return details

    def finite_reference(self, session, key, option, result_id):
        _, _, context = self.context(session)
        finite = self.call("finite_generation", lambda: FiniteCandidateSet.from_context(context))
        if option not in finite.candidate_ids:
            self.result["declared_references"][key] = "native_unavailable"
            raise Unmatchable("finite_action_unavailable", f"{option} unavailable at {key}.")
        self.commit_action(session, finite.select(context, option), result_id)
        self.result["coverage"][key] = {
            "reference_id": option,
            "candidate_id": option,
            "native_accepted": True,
            "issued_candidates": finite.candidate_ids,
        }

    def early_omission(self, session):
        _, public, context = self.context(session)
        pending = public["payload"]["proposal_request"]
        late.need(pending["proposal_kind"] == "charge_move", "Expected B2 Charge Move omission.")
        template = self.numbered[64]["result"]["payload"]
        decline = {key: value for key, value in template.items() if key != "witness"}
        decline.update(
            proposal_request_id=pending["request_id"], charge_target_unit_instance_ids=[]
        )
        self.commit_action(session, context.propose(decline), "timing:b2:omit-move")

    def early_charge(self, session):
        self.finite_reference(session, "b2-attempt", B, self.record_id(44))
        _, public, context = self.context(session)
        if public["decision_type"] == "use_stratagem":
            decline, _ = late.policy(public)
            self.commit_action(session, context.select_option(decline), "timing:b2:keep-roll")
        _, public, context = self.context(session)
        receipt = self.result["responses"]["early-b2"] = {
            "charge_events": charge_history(session, 2),
            "post_roll_offer": public,
        }
        if public["decision_type"] != SELECT_TARGETS:
            late.need(
                any(e["event_type"] == "charge_no_move_possible" for e in receipt["charge_events"]),
                "B2 Charge target did not issue without native no-move evidence.",
            )
            receipt["disposition"] = "native_roll_no_move"
            return False
        target = [key for key, row in late.options(public).items() if row["target_ids"] == [S]]
        if len(target) != 1:
            raise Unmatchable("same_target_unavailable", "B2 did not issue the singleton S target.")
        self.commit_action(session, context.select_option(target[0]), "timing:b2:target-s")
        _, public, context = self.context(session)
        self.boundary("early-b2-charge-move", session, proof=True)
        late.need(public["decision_type"] == late.PROPOSAL, "B2 Charge Move was not issued.")
        try:
            prepared = self.prepare_early_charge(session, context)
        except GroundChargeValidationExhaustedError as error:
            receipt.update(
                disposition=error.reason.value,
                counts=late.asdict(error.counts),
                validations=[late.asdict(probe) for probe in error.validations],
                generation_seconds=error.generation_seconds,
                validation_seconds=error.validation_seconds,
            )
            self.early_omission(session)
            return False
        except GroundChargeExhaustedError as error:
            receipt.update(disposition=error.reason.value, counts=late.asdict(error.counts))
            self.early_omission(session)
            return False
        receipt.update(
            disposition="witness_prepared",
            counts=late.asdict(prepared.counts),
            validations=[late.asdict(probe) for probe in prepared.validations],
            generation_seconds=prepared.generation_seconds,
            validation_seconds=prepared.validation_seconds,
            selection_seconds=prepared.selection_seconds,
        )
        selected = self.call(
            "b2_select_prepared_charge",
            lambda: prepared.registration.policy.choose(context),
        )
        result = self.commit_action(session, selected, "timing:b2:charge-move", allow_invalid=True)
        receipt["witness_verdict"] = result.to_payload()
        if result.status_kind.value == "invalid":
            receipt["disposition"] = "live_witness_rejected"
            self.early_omission(session)
            return False
        receipt["charge_events"] = charge_history(session, 2)
        late.need(
            any(e["event_type"] == "charge_move_completed" for e in receipt["charge_events"]),
            "Accepted B2 witness lacks a native completion event.",
        )
        receipt["disposition"] = "native_charge_completed"
        return True

    def prepare_early_charge(self, session, context):
        # The native helper's own clock starts after generation. Apply one
        # operator deadline to the whole call and preserve the campaign bound.
        previous_deadline = self.preparation_deadline
        self.preparation_deadline = min(previous_deadline, monotonic() + MAX_EARLY_WALL_SECONDS)
        try:
            prepared = self.call(
                "b2_generate_and_validate_charge",
                lambda: prepare_ground_charge_policy(
                    session,
                    context,
                    raw_limit=MAX_EARLY_PROPOSALS,
                    geometry_limit=MAX_EARLY_WORK,
                    validation_limit=MAX_EARLY_PROPOSALS,
                    accepted_limit=1,
                    native_seconds=120,
                    per_probe_seconds=30,
                ),
            )
            late.need(
                monotonic() < self.preparation_deadline,
                "B2 Charge preparation exceeded the operator wall-time bound.",
            )
            return prepared
        finally:
            self.preparation_deadline = previous_deadline

    def finish_early(self, session, charged):
        if charged:
            self.boundary("early-b2-charged", session, proof=True)
            fight_refs = iter(range(65, 71))
            for _ in range(12):
                _, public, context = self.context(session)
                if late.phase(session) == [3, "player-a", "movement"]:
                    break
                kind = public["decision_type"]
                if kind == late.OPTIONAL and public["payload"]["declinable"]:
                    self.commit_action(
                        session,
                        context.propose(stratagem_decline_payload()),
                        "timing:b2:reaction:" + public["request_id"],
                    )
                elif kind == late.CHARGE and COMPLETE_CHARGE in late.options(public):
                    self.commit_action(
                        session,
                        context.select_option(COMPLETE_CHARGE),
                        "timing:b2:close-charge",
                    )
                else:
                    number = next(fight_refs, None)
                    if number is None or not self.same_route(public, number):
                        raise Unmatchable("early_fight_route_changed", f"Unexpected B2 {kind}.")
                    reference = self.numbered[number]
                    action = self.call(
                        "bind_archived_action",
                        partial(bind_early_fight_reference, context, number, reference),
                    )
                    self.commit_action(session, action, self.record_id(number))
            else:
                raise Unmatchable("early_fight_limit", "B2 exceeded twelve issued responses.")
        self.source(session, 45)
        self.boundary("early-a3-selection", session, proof=True)

    def same_route(self, public, number):
        old = self.numbered[number]["request"]
        return (public["actor_id"], public["decision_type"]) == (
            old["actor_id"],
            old["decision_type"],
        )

    def position(self, session, spend):
        name = self.stage
        self.finite_reference(
            session,
            f"{name}:S",
            "normal_move" if spend else "remain_stationary",
            self.record_id(46),
        )
        if spend:
            self.translate(session, 47, S, -6.0)
        for number in range(48, 61):
            current = self.next_public(session)
            _, request = current
            if not self.same_route(request, number):
                if number in (54, 55):
                    self.log(self.actions, naturally_unissued_archived_step=number)
                    continue
                raise Unmatchable(
                    "archived_response_route_changed",
                    f"Expected archived response {number}, received {request['decision_type']}.",
                )
            if number == 57 and "normal_move" not in late.options(request):
                raise Unmatchable(
                    "b3_normal_move_unavailable",
                    "The archived +1.4-inch B3 approach is unavailable.",
                )
            self.source(session, number, current)

    def market_e(self, session, label):
        _, public, context = self.context(session)
        if public["decision_type"] != late.SHOOTING:
            for action in E_ACTIONS:
                self.result["declared_references"][f"{label}-{action}:E-shooting"] = (
                    "native_unavailable"
                )
            raise Unmatchable("e_declaration_unissued", "The ordinary E declaration did not issue.")
        legal = late.reference_bearers(context)
        digest = payload_digest(public)
        self.boundary(f"{label}-e-offer", session)
        return digest, legal == self.volley

    def follow_e(self, prepared, label):
        offer_digest, same_volley = self.market_e(prepared, label)
        for action in E_ACTIONS:
            self.stage = f"{label}-{action}"
            if action == "shoot" and not same_volley:
                self.result["declared_references"][f"{self.stage}:E-shooting"] = "offer_mismatch"
                continue
            final = self.call("fork_identical_E_offer", prepared.fork)
            _, public = self.next_public(final)
            late.need(payload_digest(public) == offer_digest, "Forked E offer differs.")
            self.e_shoot(final, action == "shoot")
            self.result["arms"][self.stage]["shared_e_offer_digest"] = offer_digest
            self.proof_labels.append(self.stage)

    def unmatched(self, label, session, error):
        self.result["unmatchable"][label] = {
            "reason": error.reason,
            "detail": str(error),
        }
        self.boundary(f"{label}-frontier", session, proof=True)
        self.save_progress("unmatchable_frontier")
        print("UNMATCHABLE", label, error.reason, str(error), flush=True)

    def continuation(self, origin, schedule, position):
        label = self.stage = f"{schedule}-{position}"
        session = self.call("fork_A3_choice", origin.fork)
        try:
            self.position(session, position == "spend")
            self.boundary(f"{label}-b3-response", session)
            self.response(session, schedule == "delayed")
            self.result["responses"][label]["charge_events"] = charge_history(session, 3)
            self.boundary(f"{label}-a4-entry", session)
            self.prepare_e(session)
            self.follow_e(session, label)
        except Unmatchable as error:
            self.unmatched(label, session, error)
        except late.Blocker as error:
            self.gap(error)

    def strict(self, label):
        self.result["arms"].setdefault(label, {})
        super().strict(label)
        if label in self.result["boundaries"]:
            self.result["boundaries"][label]["strict"] = self.result["arms"].pop(label)["strict"]

    def execute(self):
        common = self.common()
        self.stage = "b2-decline"
        delayed = self.call("fork_native_B2_omission", common.fork)
        self.finite_reference(delayed, "b2-decline", COMPLETE_CHARGE, self.record_id(44))
        self.source(delayed, 45)
        _, public = self.next_public(delayed)
        rows, events = late.provenance(delayed)
        late.need(
            rows == self.rows[:45]
            and len(events) == 481
            and events == self.anchor["lifecycle"]["decisions"]["event_log"][:481]
            and delayed.lifecycle.pending_decision_request().request_id == "decision-request-000046"
            and public["decision_type"] == late.SELECT,
            "Delayed arm does not reproduce the admitted #733 origin.",
        )
        self.boundary("delayed-a3-selection", delayed, proof=True)
        self.stage = "early"
        early = self.call("fork_native_B2_attempt", common.fork)
        try:
            charged = self.early_charge(early)
            self.save_progress("early_charge_resolved")
            self.finish_early(early, charged)
        except Unmatchable as error:
            self.unmatched("early", early, error)
        except late.Blocker as error:
            self.gap(error)
        else:
            for position in POSITIONS:
                self.continuation(early, "early", position)
        for schedule in ("delayed", "decline"):
            for position in POSITIONS:
                self.continuation(delayed, schedule, position)
        self.save_progress("native_rollouts_complete")
        for label in self.proof_labels:
            try:
                self.strict(label)
            except late.Blocker as error:
                self.gap(error)
            self.save_progress("verification_in_progress")
        self.save_progress("verification_incomplete" if self.result["errors"] else "verified")
        return 2 if self.result["errors"] else 0

    def save_progress(self, stage):
        # Preserve the last completed native experiment and each proof even if
        # the watchdog cannot unwind a native call at the overall deadline.
        self.result["report_stage"] = stage
        self.result["elapsed_seconds"] = monotonic() - self.t0
        self.update_coverage()
        late.write(self.root / "result.json", self.result)

    def update_coverage(self):
        declared = self.result["declared_references"]
        for key, value in self.result["coverage"].items():
            if key in declared and value.get("native_accepted"):
                declared[key] = "matched_and_native_accepted"
        self.result["core_coverage"] = {
            "declared": len(declared),
            "counts": {
                outcome: list(declared.values()).count(outcome)
                for outcome in sorted(set(declared.values()))
            },
            "distinct_accepted_reference_contents": len(
                {
                    receipt["reference_id"]
                    for key, receipt in self.result["coverage"].items()
                    if key in declared and receipt.get("native_accepted")
                }
            ),
        }

    def __exit__(self, exc_type, error, traceback):
        self.update_coverage()
        super().__exit__(exc_type, error, traceback)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anchor", type=Path, required=True)
    parser.add_argument("--retreat", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir()
    signal.signal(signal.SIGALRM, late.stop_on_timeout)
    with TimingExperiment(args.output, args.anchor, args.retreat) as experiment:
        try:
            return experiment.execute()
        except late.Blocker as error:
            experiment.gap(error)
            return 2


if __name__ == "__main__":
    raise SystemExit(main())
