"""Apply explicit reviewed terrain associations; illustration distance is not semantics."""

import hashlib
import json

from source_context import REPO, ROOT

TABLE = REPO / "data/source_audits/event_companion_2026_10/reviewed-objective-associations.json"
EXPECTED_TABLE_SHA256 = "a01e515f43fc4b6c2097a7b2fb5f42024d4979f7a688a3297b34cd911e86f92a"
STABLE = REPO / (
    "data/source_audits/event_companion_2026_06/"
    "phase17n_event_companion_stable_runtime_identity_map.json"
)
EXPECTED_STABLE_SHA256 = "742ab841d1ec1e696f4a5c0e3f2e8c251203d510bf1da85fb30af88023cb64f3"

table_bytes = TABLE.read_bytes()
if hashlib.sha256(table_bytes).hexdigest() != EXPECTED_TABLE_SHA256:
    raise ValueError("Reviewed objective association table drifted.")
table = json.loads(table_bytes)
rows = {row["source_objective_id"]: row for row in table["rows"]}
if len(rows) != len(table["rows"]) or len(rows) != 249 or not table["all_terrain_linked"]:
    raise ValueError("Reviewed objective association inventory drifted.")
candidate_path = ROOT / "october-extraction-candidate.json"
candidate = json.loads(candidate_path.read_text())
if candidate["source"]["pdf_sha256"] != table["source_sha256"]:
    raise ValueError("Objective associations use a different source PDF.")
stable_bytes = STABLE.read_bytes()
if hashlib.sha256(stable_bytes).hexdigest() != EXPECTED_STABLE_SHA256:
    raise ValueError("Objective association stable identity input drifted.")
stable = json.loads(stable_bytes)
area_ids = {
    key: value["stable_runtime_terrain_area_id"]
    for layout in stable["layouts"]
    for key, value in layout["terrain_area_evidence"].items()
}
objective_ids = {
    key: value["stable_runtime_objective_id"]
    for layout in stable["layouts"]
    for key, value in layout["objective_evidence"].items()
}
bindings = {}
seen = set()
for layout in candidate["layouts"]:
    areas = {area["area_id"] for area in layout["terrain_areas"]}
    single_groups = {
        frozenset(pair["area_ids"])
        for pair in layout["source_contact_pairs"]
        if pair["kinds"] == ["single"]
    }
    for objective in layout["objectives"]:
        identity = objective["objective_id"]
        row = rows[identity]
        if (row["source_pdf_page"], row["role"], row["source_glyph_seqno"]) != (
            layout["source_pdf_page_number"],
            objective["role"],
            objective["source_seqno"],
        ):
            raise ValueError("Reviewed objective glyph/page/role context drifted.")
        semantic = row["semantic_source_terrain_area_ids"]
        if not semantic or len(semantic) != len(set(semantic)) or not set(semantic) <= areas:
            raise ValueError("Reviewed terrain association references invalid areas.")
        if len(semantic) > 1 and frozenset(semantic) not in single_groups:
            raise ValueError("Reviewed terrain association must be one explicit Single group.")
        objective["semantic_source_terrain_area_ids"] = semantic
        if row["is_center_rule_correction"]:
            anchor = row["reviewed_runtime_reference_inches"]
            support = row["reviewed_anchor_support_source_area_ids"]
            basis = row["reviewed_anchor_basis"]
        else:
            anchor = objective["battlefield_center_quantized_0_01_inches"]
            support = [
                identity
                for identity, distance in zip(
                    objective["nearest_area_ids"],
                    objective["distances_to_area_polygons_inches"],
                    strict=True,
                )
                if identity in semantic and distance <= 0.05 + 1e-9
            ]
            basis = "observed_glyph_reference_within_reviewed_terrain_group"
        if not support or not set(support) <= set(semantic):
            raise ValueError("Reviewed objective reference requires explicit group support.")
        objective["runtime_reference_inches"] = anchor
        objective["runtime_reference_support_area_ids"] = support
        objective["runtime_reference_basis"] = basis
        seen.add(identity)
        bindings[objective_ids.get(identity, identity)] = {
            "terrain_area_ids": sorted(area_ids.get(area, area) for area in semantic),
            "runtime_reference_inches": anchor,
            "illustration_center_inches": objective["battlefield_center_quantized_0_01_inches"],
            "runtime_reference_basis": basis,
        }
if seen != rows.keys() or sum(len(row["terrain_area_ids"]) for row in bindings.values()) != 270:
    raise ValueError("Reviewed objective association coverage drifted.")
candidate["objective_association_review_sha256"] = EXPECTED_TABLE_SHA256
candidate_path.write_text(json.dumps(candidate, indent=2) + "\n")
runtime = {
    "schema": "reviewed-event-objective-terrain-associations-v1",
    "source_pdf_sha256": table["source_sha256"],
    "source_review_sha256": EXPECTED_TABLE_SHA256,
    "objectives": dict(sorted(bindings.items())),
}
(ROOT / "event-companion-objective-associations.json").write_text(
    json.dumps(runtime, indent=2) + "\n"
)
