"""Run the frozen Stage 4 diagram inventory through pre-outcome native intake."""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from hashlib import sha256
from pathlib import Path
from time import monotonic

from scripts import stage4_layout_intake as intake

bench = intake.bench
evaluation = intake.evaluation
RECIPE = intake.RECIPE.with_name("stage4-layout-batch-recipe.json")
RECEIPT_SCHEMA = "stage4-movement-batch-receipt-v1"
HISTORICAL_SCORED_RECEIPTS = (
    bench.RECEIPT,
    bench.WEST_RECEIPT,
    bench.RECEIPT.with_name("stage4-split-objective-receipt.json"),
    bench.RECEIPT.with_name("stage4-native-shooting-receipt.json"),
)
WORKER_FAILURES = {"preflight_wall_cap", "preflight_worker_failed"}
TYPES = ("empty", "contested", "held")
TARGET_SIZE = 8
MIN_PER_TYPE = 2
PREFIX_KEYS = ("origin_sha256", "event_prefix_sha256", "decision_prefix_sha256")
PAGES = range(9, 54)


def load_plan() -> bench.Row:
    plan = json.loads(
        RECIPE.read_text(encoding="utf-8"), object_pairs_hook=evaluation._unique_object
    )
    intake.need(
        plan["schema"] == "stage4-movement-batch-v1"
        and plan["page9_recipe_sha256"] == bench.payload_digest(intake.load_recipe())
        and type(plan["batch_wall_seconds"]) is int
        and 0 < plan["batch_wall_seconds"] <= 2400
        and [row["page"] for row in plan["pages"]] == list(PAGES),
        "batch_plan_drift",
    )
    return plan


def recipe_for(proposal: bench.Row, base: bench.Row) -> bench.Row:
    if proposal["page"] == 9:
        intake.need(proposal == {"page": 9}, "page_9_recipe_drift")
        return base
    shape = {
        "page",
        "layout",
        "pairing",
        "primary_missions",
        "target",
        "deployment",
        "routes",
        "round_one_moves",
        "proposed_origin",
    }
    intake.need(set(proposal) == shape, "candidate_recipe_fields")
    intake.need(
        set(proposal["deployment"]) == set(base["roles"].values())
        and set(proposal["routes"]) == set(base["routes"])
        and set(proposal["round_one_moves"]) <= {base["roles"]["follow"], base["roles"]["opponent"]}
        and proposal["proposed_origin"] in TYPES,
        "candidate_recipe_drift",
    )
    for direction in (*proposal["routes"].values(), *proposal["round_one_moves"].values()):
        intake.need(
            len(direction) == 2
            and all(type(value) is int for value in direction)
            and any(direction),
            "invalid_frozen_direction",
        )
    return {
        **base,
        **{key: proposal[key] for key in shape - {"page"}},
        "source_page": proposal["page"],
    }


def emit(row: bench.Row) -> None:
    print(json.dumps(row), flush=True)


def run_page(page: int) -> None:
    plan = load_plan()
    recipe = recipe_for(plan["pages"][page - 9], intake.load_recipe())
    layouts, development, _ = intake.development_inventory()
    setup, _ = intake.source_candidate(recipe, layouts[recipe["layout"]], development)
    for index in (1, 2):
        seed = sha256(f"{recipe['seed_namespace']}/{index}".encode()).hexdigest()
        evidence = {"seed_index": index, "startup_seed_hex": seed}
        started = monotonic()
        try:
            intake.preflight(recipe, setup, seed, evidence, on_origin=emit)
        except intake.IntakeGap as gap:
            evidence.update(status="ineligible", reason=gap.code, **gap.details)
        except intake.ScreenMovementGap as gap:
            evidence.update(status="ineligible", reason=gap.reason.value)
        except intake.NATIVE_PREFLIGHT_ERRORS:
            evidence.update(status="ineligible", reason="native_preflight_failed")
        else:
            evidence.update(status="eligible")
        emit({**evidence, "wall_seconds": round(monotonic() - started, 3)})


def preflight_page(page: int, cap: float) -> tuple[list[bench.Row], str | None]:
    command = [
        sys.executable,
        "-B",
        "-m",
        "scripts.stage4_benchmark_entry",
        "--layout-intake-page",
        str(page),
    ]
    try:
        result = subprocess.run(command, capture_output=True, check=False, timeout=cap)
    except subprocess.TimeoutExpired as exc:
        # Termination can interrupt a JSON line. Only read completed emissions.
        lines = (exc.stdout or b"").split(b"\n")[:-1]
        failure = "preflight_wall_cap"
    else:
        lines = result.stdout.splitlines()
        failure = "preflight_worker_failed" if result.returncode != 0 else None
    # Keep the verified A2 origin when the worker stops during a later menu probe.
    attempts = {}
    for line in lines:
        row = json.loads(line)
        attempts[row["seed_index"]] = row
    if failure is None:
        intake.need(
            list(attempts) == [1, 2]
            and all(row["status"] in {"eligible", "ineligible"} for row in attempts.values()),
            "incomplete_worker_receipt",
        )
    return list(attempts.values()), failure


def group_families(development: bench.Row, candidates: list[bench.Row]) -> list[list[str]]:
    pdf = development["layout_release"]["pdf_sha256"]
    return evaluation.link.evaluation_groups(
        {
            family["id"]: evaluation.split_binding_keys(family, pdf, require_trajectory=False)
            for family in [*development["families"], *candidates]
        }
    )


def choose(rows: list[bench.Row], size: int, minimum: int) -> list[bench.Row] | None:
    """Find the lexicographically first feasible list in source order."""

    def search(
        remaining: list[bench.Row], slots: int, counts: Counter[str]
    ) -> list[bench.Row] | None:
        deficits = {kind: max(0, minimum - counts[kind]) for kind in TYPES}
        if (
            any(
                len({tuple(row["pairing"]) for row in remaining if row["origin_type"] == kind})
                < deficits[kind]
                for kind in TYPES
            )
            or sum(deficits.values()) > slots
        ):
            return None
        if slots == 0:
            return []
        if (
            len({tuple(row["pairing"]) for row in remaining}) < slots
            or len({row["component"] for row in remaining}) < slots
        ):
            return None
        for index, row in enumerate(remaining):
            next_rows = [
                other
                for other in remaining[index + 1 :]
                if other["component"] != row["component"] and other["pairing"] != row["pairing"]
            ]
            tail = search(next_rows, slots - 1, counts + Counter([row["origin_type"]]))
            if tail is not None:
                return [row, *tail]
        return None

    return search(rows, size, Counter())


def candidate_disposition(
    receipt: bench.Row, attempts: list[bench.Row], failure: str | None
) -> None:
    kinds = [row["origin"]["type"] for row in attempts if "origin" in row]
    if len(kinds) == 2 and kinds[0] == kinds[1]:
        receipt["origin_type"] = kinds[0]
    if failure is not None:
        receipt.update(status="ineligible", reason=failure)
    elif len(attempts) != 2 or any(row["status"] != "eligible" for row in attempts):
        receipt.update(status="ineligible", reason="seed_preflight_failed")
    elif "origin_type" not in receipt:
        receipt.update(status="ineligible", reason="origin_type_mismatch")
    else:
        receipt.update(status="provisionally_eligible")


def inventory(
    plan: bench.Row, base: bench.Row
) -> tuple[bench.Row, dict[str, bench.Row], list[bench.Row]]:
    """Reconstruct every proposed vertex from the committed source recipes."""
    layouts, development, development_pages = intake.development_inventory()
    layouts_by_page = {layout.source_page: layout for layout in layouts.values()}
    pinned = {}
    receipts = []
    for proposal in plan["pages"]:
        page = proposal["page"]
        row = layouts_by_page[page]
        receipt = {
            "page": page,
            "layout": row.layout_id,
            "pairing": list(row.force_disposition_pair),
            "primary_missions": list(row.primary_missions),
        }
        receipts.append(receipt)
        if page in development_pages:
            intake.need(
                proposal == {"page": page, "exclude": "development_diagram"},
                "development_page_plan_drift",
            )
            receipt.update(status="excluded", reason="development_diagram")
            continue
        if "exclude" in proposal:
            intake.need(
                set(proposal) == {"page", "exclude"}
                and proposal["exclude"]
                in {
                    "no_frozen_construction",
                    "page_9_pairing_alternates_unproposed",
                    "development_geometry_overlap",
                },
                "unknown_plan_exclusion",
            )
            receipt.update(status="excluded", reason=proposal["exclude"])
            continue
        recipe = recipe_for(proposal, base)
        _, family = intake.source_candidate(recipe, row, development)
        receipt.update(
            target=recipe["target"],
            recipe_sha256=bench.payload_digest(recipe),
            family_id=family["id"],
        )
        pinned[family["id"]] = family

    return development, pinned, receipts


def static_development_overlaps(development: bench.Row, pinned: dict[str, bench.Row]) -> set[str]:
    development_ids = {family["id"] for family in development["families"]}
    return {
        name
        for group in group_families(development, list(pinned.values()))
        if development_ids.intersection(group)
        for name in group
    }


def bind_attempts(family: bench.Row, attempts: list[bench.Row]) -> None:
    family["trajectory_sha256"] = sorted(
        {
            row[key]
            for row in attempts
            if row.get("strict_restore_and_replay")
            for key in PREFIX_KEYS
        }
    )


def run() -> None:
    started = monotonic()
    plan = load_plan()
    base = intake.load_recipe()
    development, pinned, receipts = inventory(plan, base)
    static_exclusions = static_development_overlaps(development, pinned)
    for receipt in receipts:
        family_id = receipt.get("family_id")
        if family_id is None:
            continue
        if family_id in static_exclusions:
            receipt.update(
                status="excluded",
                reason="development_component_overlap",
                preflight_disposition="skipped_development_overlap",
            )
            continue
        remaining = plan["batch_wall_seconds"] - (monotonic() - started)
        if remaining <= 0:
            receipt.update(
                status="excluded", reason="batch_wall_cap", preflight_disposition="batch_wall_cap"
            )
            continue
        tick = monotonic()
        attempts, failure = preflight_page(
            receipt["page"], min(remaining, base["worker_wall_seconds"])
        )
        receipt.update(
            preflight_disposition=failure or "completed",
            attempts=attempts,
            wall_seconds=round(monotonic() - tick, 3),
        )
        bind_attempts(pinned[family_id], attempts)
        candidate_disposition(receipt, attempts, failure)
        if receipt["page"] == 9:
            intake.need(receipt["status"] == "provisionally_eligible", "page_9_control_failed")

    analysis = analyze(development, pinned, receipts)
    emit(
        {
            "schema": RECEIPT_SCHEMA,
            "plan_sha256": bench.payload_digest(plan),
            "engine_build_id": intake.verified_engine_build_identity().build_id,
            "candidate_generator_sha256": sha256(
                Path(intake.screen_movement_candidates.__file__).read_bytes()
            ).hexdigest(),
            "continuation_disjointness": "sealed_check_pending",
            "cohort_lock": "pending",
            "wall_seconds": round(monotonic() - started, 3),
            "pages": receipts,
            **analysis,
        }
    )


def analyze(
    development: bench.Row,
    pinned: dict[str, bench.Row],
    receipts: list[bench.Row],
    *,
    expected_components: object = None,
) -> bench.Row:
    development_ids = {family["id"] for family in development["families"]}
    groups = group_families(development, list(pinned.values()))
    if expected_components is not None:
        intake.need(groups == expected_components, "full_provenance_graph_mismatch")
    component_by_id = {name: group for group in groups for name in group}
    eligible = []
    for receipt in receipts:
        if "family_id" not in receipt:
            continue
        group = component_by_id[receipt["family_id"]]
        receipt["component"] = group[0]
        if development_ids.intersection(group):
            receipt.update(status="excluded", reason="development_component_overlap")
        elif receipt["status"] == "provisionally_eligible":
            eligible.append(receipt)
    chosen = choose(eligible, TARGET_SIZE, MIN_PER_TYPE)
    selected = [] if chosen is None else chosen
    selected_pages = {receipt["page"] for receipt in selected}
    for row in eligible:
        row["proposed_for_cohort"] = row["page"] in selected_pages

    split = {
        **development,
        "families": [
            *development["families"],
            *(
                family
                for name, family in pinned.items()
                if family["trajectory_sha256"]
                and not development_ids.intersection(component_by_id[name])
            ),
        ],
    }
    verified_groups = evaluation.validate_split(split)
    qualified_counts = Counter(row["origin_type"] for row in eligible)
    seed_counts = Counter(
        trial["origin"]["type"]
        for row in receipts
        for trial in row.get("attempts", [])
        if "origin" in trial
    )
    both_seed_counts = Counter(row["origin_type"] for row in receipts if "origin_type" in row)
    usable = next(
        choice
        for size in range(min(TARGET_SIZE, len(eligible)), -1, -1)
        if (choice := choose(eligible, size, 0)) is not None
    )
    return {
        "status": "provisional_cohort" if chosen is not None else "intake_gap",
        "proposed_pages": sorted(selected_pages),
        "max_pairing_and_component_distinct_up_to_eight": len(usable),
        "qualified_counts": {kind: qualified_counts[kind] for kind in TYPES},
        "reached_by_both_seeds": {kind: both_seed_counts[kind] for kind in TYPES},
        "reached_by_seed": {kind: seed_counts[kind] for kind in TYPES},
        "a2_origins_reached": sum(
            trial.get("a2_origin_reached", False)
            for row in receipts
            for trial in row.get("attempts", [])
        ),
        "components": groups,
        "verified_split_components": verified_groups,
        "split_manifest": split,
    }


def verify_file(path: Path) -> bench.Row:
    """Verify a retained preflight receipt without replay or historical score reads."""
    path = path.resolve(strict=True)
    intake.need(
        all(
            path.name.casefold() != scored.name.casefold() and not path.samefile(scored)
            for scored in HISTORICAL_SCORED_RECEIPTS
        ),
        "historical_scored_receipt_forbidden",
    )
    raw = path.read_bytes()
    receipt = json.loads(raw, object_pairs_hook=evaluation._unique_object)
    result = verify_receipt(receipt)
    return {**result, "receipt_sha256": sha256(raw).hexdigest()}


def verify_attempts(attempts: list[bench.Row], base: bench.Row) -> None:
    indices = [attempt["seed_index"] for attempt in attempts]
    intake.need(indices in ([], [1], [1, 2]), "preflight_seed_order_mismatch")
    for index, trial in zip(indices, attempts, strict=True):
        seed = sha256(f"{base['seed_namespace']}/{index}".encode()).hexdigest()
        intake.need(
            trial["startup_seed_hex"] == seed
            and trial["status"] in {"eligible", "ineligible", "origin_verified"},
            "preflight_seed_evidence_mismatch",
        )
        if trial.get("strict_restore_and_replay"):
            intake.need(
                trial["strict_restore_and_replay"] is True
                and trial["a2_origin_reached"] is True
                and all(evaluation._sha256(trial[key], key) for key in PREFIX_KEYS),
                "preflight_origin_commitment_mismatch",
            )
        if "origin" in trial:
            origin = trial["origin"]
            intake.need(
                trial.get("strict_restore_and_replay") is True
                and intake.classify_origin(origin["visible_contact_oc"], origin["controller"])
                == origin["type"],
                "preflight_origin_type_mismatch",
            )
        if trial["status"] == "eligible":
            menu = trial["menu"]
            probes = menu["probes"]
            intake.need(
                "origin" in trial
                and menu["actor_id"] == bench.A
                and {bench.HOLD, bench.NORMAL}.issubset(menu["issued_options"])
                and menu["hold"] == "accepted"
                and 0 < len(probes) <= base["native_probe_cap"]
                and [probe["id"] for probe in probes] == menu["eligible_candidates"][: len(probes)]
                and all(probe["violation"] is not None for probe in probes[:-1])
                and probes[-1] == {"id": menu["selected_screen"], "violation": None},
                "preflight_menu_evidence_mismatch",
            )


def verify_receipt(receipt: object) -> bench.Row:
    if not isinstance(receipt, dict) or receipt.get("schema") != RECEIPT_SCHEMA:
        raise intake.IntakeGap("not_stage4_preflight_receipt")
    plan = load_plan()
    base = intake.load_recipe()
    intake.need(
        receipt["plan_sha256"] == bench.payload_digest(plan)
        and receipt["engine_build_id"] == intake.verified_engine_build_identity().build_id
        and receipt["candidate_generator_sha256"]
        == sha256(Path(intake.screen_movement_candidates.__file__).read_bytes()).hexdigest()
        and receipt["continuation_disjointness"] == "sealed_check_pending"
        and receipt["cohort_lock"] == "pending",
        "preflight_receipt_identity_mismatch",
    )
    development, pinned, pages = inventory(plan, base)
    static_exclusions = static_development_overlaps(development, pinned)
    intake.need(
        [page["page"] for page in receipt["pages"]] == list(PAGES),
        "preflight_receipt_page_order_mismatch",
    )
    for page, retained in zip(pages, receipt["pages"], strict=True):
        family_id = page.get("family_id")
        if family_id is None:
            continue
        has_disposition = "preflight_disposition" in retained
        if family_id in static_exclusions:
            if has_disposition:
                page["preflight_disposition"] = "skipped_development_overlap"
            page.update(status="excluded", reason="development_component_overlap")
            continue

        reason = retained.get("reason")
        if has_disposition:
            disposition = retained["preflight_disposition"]
            intake.need(
                disposition in {"completed", "batch_wall_cap", *WORKER_FAILURES},
                "unknown_preflight_disposition",
            )
            page["preflight_disposition"] = disposition
        elif reason in {"batch_wall_cap", *WORKER_FAILURES}:
            disposition = reason
        elif reason == "development_component_overlap" and "attempts" not in retained:
            # Legacy receipts replaced the batch cap with the later overlap reason.
            # Static development exclusions have already been reconstructed above.
            disposition = "batch_wall_cap"
        else:
            disposition = "completed"

        if disposition == "batch_wall_cap":
            page.update(status="excluded", reason="batch_wall_cap")
            continue
        attempts = retained.get("attempts")
        intake.need(
            isinstance(attempts, list) and "wall_seconds" in retained, "missing_worker_receipt"
        )
        verify_attempts(attempts, base)
        failure = disposition if disposition in WORKER_FAILURES else None
        if failure is None and (has_disposition or reason != "development_component_overlap"):
            intake.need(
                len(attempts) == 2
                and all(trial["status"] != "origin_verified" for trial in attempts),
                "incomplete_worker_receipt",
            )
        page.update(attempts=attempts, wall_seconds=retained["wall_seconds"])
        bind_attempts(pinned[family_id], attempts)
        candidate_disposition(page, attempts, failure)
        if page["page"] == 9:
            intake.need(page["status"] == "provisionally_eligible", "page_9_control_failed")

    expected = receipt["components"]
    intake.need(isinstance(expected, list), "full_provenance_graph_mismatch")
    result = analyze(development, pinned, pages, expected_components=expected)
    intake.need(pages == receipt["pages"], "preflight_page_evidence_mismatch")
    intake.need(
        all(receipt[key] == value for key, value in result.items()), "preflight_summary_mismatch"
    )
    return {
        "verification": "exploratory_preflight_receipt",
        "publication_before_preflight": "unverified",
        "plan_sha256": receipt["plan_sha256"],
        "verified_pages": len(pages),
        "provenance_vertices": len(development["families"]) + len(pinned),
        **{
            key: result[key]
            for key in (
                "status",
                "qualified_counts",
                "proposed_pages",
                "reached_by_seed",
                "reached_by_both_seeds",
            )
        },
    }
