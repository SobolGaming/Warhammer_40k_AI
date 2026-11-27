"""Link the sealed Layout C development choice to exact replay deltas."""

from __future__ import annotations

from dataclasses import dataclass

from scripts import stage4_benchmark_entry as bench
from scripts.stage4_tactical_features import (
    FINITE_COLUMNS,
    TACTICAL_COLUMNS,
    TacticalInputs,
    tactical_inputs,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.finite_candidates import FiniteCandidateSet
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, payload_digest
from warhammer40k_core.ai.semantic_features import SemanticObservation
from warhammer40k_core.engine.phases.movement_model import MovementPhaseActionKind

SEALED_SQUASH = "f61b40fdcf63ae187b3c94eb325f4dd94207ba0f"
SEALED_RECEIPT_HASH = "92b62e3115bf12c4ae19e1a603cbbbe343ef86ee998799bc4ea8cd81cb44d126"
PAIRS = (("hold-omit", "screen-omit"), ("hold-follow", "screen-follow"))


@dataclass(frozen=True, slots=True)
class FrozenChoice:
    observation: SemanticObservation
    finite: FiniteCandidateSet
    tactics: TacticalInputs
    authoritative_request_id: str

    @classmethod
    def capture(cls, session: LocalGameSession, context: PlayerDecisionContext) -> FrozenChoice:
        pending = session.lifecycle.pending_decision_request()
        bench.require(
            pending is not None
            and context == bench.actor(session)
            and context.route.actor_id == bench.A
            and context.route.decision_type == bench.MOVE_ACTION,
            "Expected the current actor's finite movement offer.",
        )
        assert pending is not None
        observation = SemanticObservation.from_context(context)
        finite = FiniteCandidateSet.from_context(context)
        stable_ids = {action.value for action in MovementPhaseActionKind}
        bench.require(
            {bench.HOLD, bench.NORMAL} <= set(finite.candidate_ids) <= stable_ids,
            "Layout C finite menu is missing a control or contains a non-generic action ID.",
        )
        return cls(observation, finite, tactical_inputs(context), pending.request_id)

    def policy_input(self) -> bench.Row:
        return {
            "model_inputs": [*self.observation.model_inputs, *self.tactics],
            "legal_action_ids": list(self.finite.candidate_ids),
        }


@dataclass(frozen=True, slots=True)
class FrozenMovementOffer:
    tactics: TacticalInputs
    request_id: str
    authoritative_request_id: str
    observation_hash: str

    @classmethod
    def capture(
        cls, session: LocalGameSession, context: PlayerDecisionContext
    ) -> FrozenMovementOffer:
        pending = session.lifecycle.pending_decision_request()
        bench.require(
            pending is not None
            and context == bench.actor(session)
            and context.request["is_parameterized"],
            "Expected a pending child movement offer.",
        )
        assert pending is not None
        return cls(
            tactical_inputs(context),
            context.request["request_id"],
            pending.request_id,
            context.observation_hash,
        )

    def policy_input(self) -> bench.Row:
        return {"model_inputs": list(self.tactics)}


def verify_seal(reference: bench.Row) -> None:
    bench.require(
        payload_digest(reference) == SEALED_RECEIPT_HASH,
        "Stage 4 development receipt differs from the seal at #765.",
    )


def verify_report(reference: bench.Row, observed: bench.Row) -> None:
    verify_seal(reference)
    expected_arms = {arm for pair in PAIRS for arm in pair}
    bench.require(
        observed.get("partition") == "development"
        and observed.get("status") == "observed"
        and set(observed.get("arms", {})) == expected_arms,
        "Expected all four observed development arms.",
    )
    bench.require(
        observed["protocol"]["horizon"] == reference["protocol"]["horizon"],
        "Mixed or stale Stage 4 horizon.",
    )
    expected = {key: value for key, value in reference.items() if key != "setup_evidence"}
    bench.require(
        payload_digest(observed) == payload_digest(expected),
        "Stage 4 origin, source, menu or replay evidence differs from the sealed receipt.",
    )


def source_diagram_key(pdf_sha256: str, page: object) -> tuple[str, str]:
    """Identify a source diagram in the Event Companion's one-diagram-per-page layout pack."""
    if type(page) is not int or page < 1:
        raise bench.BenchmarkGap("Invalid Stage 4 source diagram page.")
    return "source_diagram", f"{pdf_sha256}:{page}"


def evaluation_groups(
    families: dict[str, frozenset[tuple[str, str]]],
) -> list[list[str]]:
    """Find connected families by source, geometry or trajectory bindings."""
    components: list[tuple[set[str], frozenset[tuple[str, str]]]] = []
    for family, keys in sorted(families.items()):
        members = {family}
        remaining = []
        for prior_members, prior_keys in components:
            if prior_keys & keys:
                members.update(prior_members)
                keys |= prior_keys
            else:
                remaining.append((prior_members, prior_keys))
        components = [*remaining, (members, keys)]
    return sorted(sorted(members) for members, _ in components)


def _material(checkpoint: bench.Row, player: str) -> tuple[int, int]:
    armies = checkpoint["lifecycle"]["state"]["army_definitions"]
    wounds = [
        model["wounds_remaining"]
        for army in armies
        if army["player_id"] == player
        for unit in army["units"]
        for model in unit["own_models"]
    ]
    return sum(wound > 0 for wound in wounds), sum(wounds)


def arm_target(
    choice: FrozenChoice,
    movement_offer: FrozenMovementOffer,
    origin: bench.Row,
    endpoint: bench.Row,
    arm: bench.Row,
) -> bench.Row:
    """Use the strict endpoint checkpoint and prove its first action shares the origin."""
    start, stop = (cp["replay_artifact"] for cp in (origin, endpoint))
    prefix = start["decision_records"]
    records = stop["decision_records"]
    events = start["event_records"]
    bench.require(
        len(records) > len(prefix)
        and records[: len(prefix)] == prefix
        and stop["event_records"][: len(events)] == events
        and origin["source_identity"] == endpoint["source_identity"]
        and (endpoint["content_hash"], endpoint["event_log_hash"], len(records))
        == (arm["checkpoint"], arm["event_log"], arm["records"])
        and arm["strict_replay"] is True,
        "Stage 4 arm has a stale prefix, endpoint or source binding.",
    )
    first = records[len(prefix)]
    menu = arm["menus"][0]
    finite_id = bench.HOLD if menu["selected"] == bench.HOLD else bench.NORMAL
    request = first["request"]
    bench.require(
        (request["request_id"], request["actor_id"], request["decision_type"])
        == (choice.authoritative_request_id, choice.finite.actor_id, bench.MOVE_ACTION)
        and tuple(option["option_id"] for option in request["options"])
        == choice.finite.candidate_ids
        and first["result"]["selected_option_id"] == finite_id
        and menu["action_request_id"] == choice.finite.request_id,
        "Stage 4 arm does not start with the frozen actor choice.",
    )
    if finite_id == bench.NORMAL:
        bench.require(len(records) > len(prefix) + 1, "Screen proposal record is missing.")
        child = records[len(prefix) + 1]
        bench.require(
            child["request"]["request_id"] == movement_offer.authoritative_request_id
            and child["request"]["actor_id"] == choice.finite.actor_id
            and menu["proposal_request_id"] == movement_offer.request_id
            and menu["actor_view_hash"] == movement_offer.observation_hash,
            "Stage 4 Screen proposal does not share the captured child offer.",
        )
        proposal = child["result"]["payload"]
        shape = {key: value for key, value in proposal.items() if key != "proposal_request_id"}
        bench.require(
            menu["selected"] == "normal-move:" + payload_digest(shape)
            and any(
                probe["id"] == menu["selected"] and probe["violation"] is None
                for probe in menu["native_probes"]
            ),
            "Stage 4 Screen proposal is stale or lacks prospective native acceptance.",
        )
    start_state, stop_state = (cp["lifecycle"]["state"] for cp in (origin, endpoint))
    vp_before, vp_after = (
        {ledger["player_id"]: ledger["victory_points"] for ledger in state["victory_point_ledgers"]}
        for state in (start_state, stop_state)
    )
    result = {}
    for player, side in ((bench.A, "actor"), (bench.B, "opponent")):
        before_models, before_wounds = _material(origin, player)
        after_models, after_wounds = _material(endpoint, player)
        vp = vp_after[player] - vp_before[player]
        bench.require(vp == arm["gain_vp"][player], "Replay VP differs from the sealed arm.")
        result[side] = {
            "vp": vp,
            "living_models": after_models - before_models,
            "wounds": after_wounds - before_wounds,
        }
    return result


def _candidate_coverage(menu: bench.Row) -> bench.Row:
    committed_proposal_id = None if menu["selected"] == bench.HOLD else menu["selected"]
    coverage = {
        "role": menu["role"],
        "finite_request_id": menu["action_request_id"],
        "finite_selected_id": bench.HOLD if committed_proposal_id is None else bench.NORMAL,
        "committed_proposal_id": committed_proposal_id,
    }
    if "native_probes" in menu:
        coverage.update(
            proposal_request_id=menu["proposal_request_id"],
            observation_hash=menu["actor_view_hash"],
            raw_count=menu["raw_count"],
            ordered_raw_ids_hash=menu["raw_ids_hash"],
            geometry_excluded_count=menu["geometry_excluded"],
            cap_unprobed_ids=menu["cap_lost_ids"],
            prospective_native_accepts=[
                probe["id"] for probe in menu["native_probes"] if probe["violation"] is None
            ],
            prospective_native_rejects={
                probe["id"]: probe["violation"]
                for probe in menu["native_probes"]
                if probe["violation"] is not None
            },
        )
    return coverage


def build_link(
    reference: bench.Row,
    observed: bench.Row,
    choice: FrozenChoice,
    movement_offer: FrozenMovementOffer,
    origin: bench.Row,
    endpoints: dict[str, bench.Row],
) -> bench.Row:
    verify_report(reference, observed)
    arms = observed["arms"]
    bench.require(endpoints.keys() == arms.keys(), "Stage 4 replay checkpoint is missing an arm.")
    bench.require(
        (origin["content_hash"], origin["event_log_hash"], choice.finite.request_id)
        == tuple(observed["origin"][key] for key in ("checkpoint", "event_log", "request_id")),
        "Stage 4 pre-choice observation lacks the sealed origin binding.",
    )
    live_screen = [_candidate_coverage(arms[screen]["menus"][0]) for _, screen in PAIRS]
    bench.require(live_screen[0] == live_screen[1], "Screen proposal changed across matched arms.")
    targets = {
        name: arm_target(choice, movement_offer, origin, endpoints[name], arm)
        for name, arm in arms.items()
    }
    pairs = {}
    for control, screen in PAIRS:
        pairs[screen.removeprefix("screen-")] = {
            "hold_arm": control,
            "screen_arm": screen,
            "screen_minus_hold": {
                side: {
                    metric: value - targets[control][side][metric]
                    for metric, value in targets[screen][side].items()
                }
                for side in ("actor", "opponent")
            },
        }

    protocol = observed["protocol"]
    family = observed["group"]
    layout_source = protocol["layout_source"]
    group_keys = frozenset(
        {
            source_diagram_key(layout_source["pdf_sha256"], layout_source["page"]),
            ("scenario", family),
            ("geometry", payload_digest(sorted(protocol["linked_footprints_inches"].values()))),
            ("geometry_family", protocol["target"].removesuffix("-central-01")),
            ("trajectory", protocol["setup"]),
            ("trajectory", origin["content_hash"]),
        }
    )
    policy_input = choice.policy_input()
    movement_offer_input = movement_offer.policy_input()
    return {
        "schema": "stage4-development-policy-target-v2",
        "partition": "development",
        "training_rows": 0,
        "feature_columns": {
            "policy_input": list(FINITE_COLUMNS),
            "movement_offer_input": list(TACTICAL_COLUMNS),
        },
        "policy_input": policy_input,
        "movement_offer_input": movement_offer_input,
        "delayed_targets": {
            "units": {"vp": "VP", "living_models": "models", "wounds": "wounds"},
            "deltas_from_origin": targets,
            "matched_screen_minus_hold": pairs,
        },
        "evidence": {
            "seal_commit": SEALED_SQUASH,
            "sealed_receipt_hash": SEALED_RECEIPT_HASH,
            "family": family,
            "group_keys": sorted(group_keys),
            "evaluation_groups": evaluation_groups({family: group_keys}),
            "layout_source": protocol["layout_source"],
            "mission_source": protocol["mission_source"],
            "source_identity": origin["source_identity"],
            "setup": protocol["setup"],
            "origin": observed["origin"],
            "observation": choice.observation.to_payload(),
            "policy_input_hash": payload_digest(policy_input),
            "movement_offer_input_hash": payload_digest(movement_offer_input),
            "movement_offer_binding": {
                "request_id": movement_offer.request_id,
                "observation_hash": movement_offer.observation_hash,
            },
            "finite_menu_hash": choice.finite.content_hash,
            "finite_menu_evidence": "reproduced-from-sealed-pending-request",
            "horizon": protocol["horizon"],
            "seed": protocol["seed"],
            "frozen_policy": protocol["policy"],
            "native_cap": protocol["native_cap"],
            "arms": {
                name: {
                    "checkpoint": arm["checkpoint"],
                    "event_log": arm["event_log"],
                    "records": arm["records"],
                    "strict_replay": arm["strict_replay"],
                    "coverage": [_candidate_coverage(menu) for menu in arm["menus"]],
                }
                for name, arm in arms.items()
            },
        },
    }
