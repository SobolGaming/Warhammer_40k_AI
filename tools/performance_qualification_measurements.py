"""Validate raw current measurements independently of prior historical applicability."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASE = "5f509724da25a2f6ded0c2739a8e7c84bdf59c91"


def applies(*, base: str, path: str) -> bool:
    return base == BASE and path.startswith("docs/performance/current/qualification40-")


def retained_inputs(
    root: Path, *, current: dict[str, str], report: dict[str, Any], family: str
) -> tuple[dict[str, str], dict[str, object] | None, str]:
    from tools import cumulative_preservation as cumulative
    from tools import performance_policy as policy
    from tools import performance_qualification_successor as stage

    # Full current admission is required before any historical/measurement view.
    live = cumulative.verify_live(root)
    inputs = stage.producing_inputs(root, current)
    freeze = stage._freeze(root)
    rows = json.loads(stage._member(root, stage.NAMESPACE + "/measurement-provenance.json", freeze))
    row = rows[family]
    if row["base_revision"] != BASE or row["head_input_digest"] != policy.canonical_digest(inputs):
        raise ValueError("Current measurement producing base/input inventory changed.")
    if report["base_revision"] != BASE or report["family"] != family:
        raise ValueError("Current measurement report has another exact base/family.")
    raw: dict[str, Any] = {}
    for side in ("base", "head"):
        raw[side] = json.loads(stage._member(root, row[side]["path"], freeze))
        if policy.canonical_digest(raw[side]) != row[side]["canonical_sha256"]:
            raise ValueError("Current raw measurement report changed.")
        if (
            report[side]["samples"] != samples_from_raw(family, raw[side])
            or report[side]["samples"] != row[side]["samples"]
        ):
            raise ValueError("Current comparison samples differ from their raw producing report.")
        if report[side]["runtime_build_id"] != row[side]["runtime_build_id"]:
            raise ValueError("Current comparison runtime differs from producing measurement.")
        if row[side]["completed"] is not True:
            raise ValueError("Current measurement was incomplete.")
        for receipt_path in row[side]["receipt_paths"]:
            receipt = json.loads(stage._member(root, receipt_path, freeze))
            if receipt["exit_code"] != 0 or receipt["timeout"] or receipt["source_drift"]:
                raise ValueError("Current measured arm failed, timed out or changed inputs.")
    binding = None
    if family == "external_contract_source_reuse":
        from tools import performance_tool_inputs_v3 as roles

        binding = roles.expected_binding(root, input_digest=policy.canonical_digest(inputs))
        if report["input_binding"] != binding:
            raise ValueError("Current complete source-token input binding changed.")
        roles.validate_generated_evidence(report["generated_output_binding"], binding)
    if cumulative.verify_live(root) != live:
        raise ValueError("Current source changed during measurement evidence admission.")
    return (
        inputs,
        binding,
        policy.canonical_digest(
            {
                "measurement_credit": "fresh-actual-pr587-current-runtime-producing-cohort",
                "base": BASE,
                "live_admission": live,
                "producing_inputs": policy.canonical_digest(inputs),
                "activation": "sole None-to-freeze literal; exact assessment derivative only",
                "raw_reports": row,
            }
        ),
    )


def samples_from_raw(family: str, raw: dict[str, Any]) -> dict[str, list[float]]:
    """Mechanical case projection of unchanged real driver outputs; never invent timings."""
    if family == "fight":
        if raw["completion_rate"] != 1:
            raise ValueError("Incomplete current Fight workload.")
        return {"complete-fight-phase": raw["samples_seconds"]}
    if family == "external_contract_source_reuse":
        if raw["completed"] is not True or len(raw["sample_results"]) != 3:
            raise ValueError("Incomplete current source-token original samples.")
        return {
            "orphan-write-independent-check": [r["testcase_seconds"] for r in raw["sample_results"]]
        }
    result = {}
    for row in raw["rows"]:
        if family in {"reconstruction", "shock_reconstruction"}:
            case = row["checkpoint"] + "/" + row["operation"]
            values = [r["seconds"] for r in row["samples"]]
            if not all(r["complete"] for r in row["samples"]):
                raise ValueError("Incomplete current reconstruction sample.")
        else:
            values = row["samples_seconds"]
            if family in {"dice", "dice_sustained"}:
                case = row["phase"] + "/" + str(row["accept"]).lower()
                if not all(
                    r["complete"] and r["normal_restore_exact"] for r in row["semantic_checks"]
                ):
                    raise ValueError("Incomplete current dice semantic/reconstruction sample.")
            elif family == "roster":
                case = str(row["unit_count"])
            elif family == "strength":
                case = row["phase"]
            elif family == "objective_control":
                case = str(row["gap"])
            else:
                case = row["case"]
        if case in result:
            raise ValueError("Duplicated current raw measurement case.")
        result[case] = values
    return result
