"""Build a review candidate from current PDF occurrences; never runtime data.

The July audit supplies project IDs, canonical modeled shapes, and registrations.
Current PDF vectors, images and glyphs supply every observed pose and binding.
Final placement remains the separately reviewed generator's responsibility.
"""

import copy
import hashlib
import json
import math
from collections import Counter
from decimal import ROUND_HALF_UP, Decimal

import fitz
import numpy as np
from shapely import affinity
from shapely.geometry import Point, Polygon
from source_context import NEW as PDF
from source_context import REF, ROOT

reference = REF
observed = json.loads((ROOT / "current-refined-correspondence.json").read_text())
contacts = json.loads((ROOT / "contacts.json").read_text())
doc = fitz.open(PDF)
result = copy.deepcopy(reference)
frame = reference["coordinate_frame"]["pdf_to_battlefield_affine"]
sx, ox = frame["x_inches"]["scale"], frame["x_inches"]["offset"]
sy, oy = frame["y_inches"]["scale"], frame["y_inches"]["offset"]
archetypes = {a["archetype_id"]: a for a in reference["reviewed_feature_archetypes"]}
templates = {
    a["footprint_template_id"]: a["polygon_vertices_inches"]
    for a in reference["footprint_templates"]
}
assetcache = {}


def q(x, grid=0.05):
    return float(
        (Decimal(str(x)) / Decimal(str(grid))).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        * Decimal(str(grid))
    )


def world(p):
    return np.array([float(p[0]) * sx + ox, float(p[1]) * sy + oy])


def pdf(p):
    return np.array([(float(p[0]) - ox) / sx, (float(p[1]) - oy) / sy])


def r(v):
    if isinstance(v, (tuple, list, np.ndarray)):
        return [r(x) for x in v]
    return round(float(v), 9)


def pathpoints(d):
    return np.array([p for item in d["items"] for p in item[1:]])


def center(i):
    b = i["bbox"]
    return [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]


def asset(xref):
    if xref not in assetcache:
        a = doc.extract_image(xref)
        m = a["smask"]
        assetcache[xref] = {
            "source_pdf_image_xref": xref,
            "image_sha256": hashlib.sha256(a["image"]).hexdigest(),
            "pixel_width": a["width"],
            "pixel_height": a["height"],
            "soft_mask_xref": m,
            "soft_mask_sha256": hashlib.sha256(doc.extract_image(m)["image"]).hexdigest()
            if m
            else None,
        }
    return assetcache[xref]


def imagepose(i):
    a, b, c, d, _e, _f = i["transform"]
    determinant = a * d - b * c
    return {
        "battlefield_center_inches": r(world(center(i))),
        "battlefield_image_x_axis_rotation_degrees": round(
            math.degrees(math.atan2(b * sy, a * sx)), 6
        ),
        "battlefield_width_axis_span_inches": round(math.hypot(a * sx, b * sy), 6),
        "battlefield_height_axis_span_inches": round(math.hypot(c * sx, d * sy), 6),
        "orientation_reversing_image_y_up_to_battlefield_frame": determinant < 0,
        "source_pdf_affine_determinant": round(determinant, 9),
        "battlefield_affine_determinant": round(determinant * sx * sy, 9),
    }


def polygon_world(points):
    return Polygon([world(p) for p in points])


def signed_area(points):
    return (
        sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:] + points[:1], strict=True))
        / 2
    )


correspondence = []
for layout, old, obs, eyes in zip(
    result["layouts"], reference["layouts"], observed["layouts"], contacts["pages"], strict=True
):
    page = layout["source_pdf_page_number"]
    p = doc[page - 1]
    draws = p.get_drawings()
    bboxlog = p.get_bboxlog()
    by_id = {a["id"]: a for a in obs["areas"]}
    polygons = {a["id"]: polygon_world(a["new_polygon_points"]) for a in obs["areas"]}
    areas = {a["area_id"]: a for a in layout["terrain_areas"]}
    records = {
        "page": page,
        "layout_id": layout["layout_id"],
        "footprints": [],
        "components": [],
        "objectives": [],
        "contacts": [],
    }
    for a, oa in zip(layout["terrain_areas"], old["terrain_areas"], strict=True):
        ob = by_id[a["area_id"]]
        before, after = ob["old"], ob["new"]
        poly = polygons[a["area_id"]]
        pa, pb = pathpoints(before), pathpoints(after)
        mat = np.linalg.lstsq(np.column_stack([pa, np.ones(len(pa))]), pb, rcond=None)[0]
        residual = float(
            np.max(np.linalg.norm(np.column_stack([pa, np.ones(len(pa))]) @ mat - pb, axis=1))
        )
        if residual > 0.002:
            raise ValueError((page, a["area_id"], residual))
        linear = np.diag([sx, sy]) @ mat[:2].T @ np.diag([1 / sx, 1 / sy])
        det = float(np.linalg.det(linear))
        changed = max(np.max(abs(pa - pb)), 0) > 1e-4
        imgbounds = bboxlog[after["seqno"] + 1]
        assert imgbounds[0] == "fill-image", (page, a["area_id"], imgbounds)
        imatches = [
            (i, x)
            for i, x in enumerate(obs["images_new"])
            if max(abs(v - w) for v, w in zip(x["bbox"], imgbounds[1], strict=True)) < 0.002
        ]
        assert len(imatches) == 1, (page, a["area_id"], imatches)
        ii, img = imatches[0]
        ip = imagepose(img)
        aa = asset(img["xref"])
        a["source_area_image"] = {
            "page_image_index_zero_based": ii,
            "xref": img["xref"],
            "bbox_points": r(img["bbox"]),
            "affine_normalized_image_to_points": r(img["transform"]),
            **ip,
            "source_image_sha256": aa["image_sha256"],
            "source_soft_mask_sha256": aa["soft_mask_sha256"],
        }
        lines = [
            (i, world(it[1]), world(it[2])) for i, it in enumerate(after["items"]) if it[0] == "l"
        ]
        longest = max(lines, key=lambda item: np.linalg.norm(item[2] - item[1]))
        li, ls, le = longest
        delta = le - ls
        a["source_vector_path"] = {
            "extended_drawing_index_zero_based": after["extended_index"],
            "seqno": after["seqno"],
            "item_count": len(after["items"]),
            "fill_rgb": r(after["fill"]),
            "rect_points": r(after["rect"]),
            "signed_area_inches2": round(
                signed_area([list(world(pt)) for pt in ob["new_polygon_points"]]), 6
            ),
            "longest_explicit_line": {
                "item_index_zero_based": li,
                "start_inches": r(ls),
                "end_inches": r(le),
                "length_inches": round(float(np.linalg.norm(delta)), 6),
                "start_to_end_rotation_degrees": round(
                    math.degrees(math.atan2(delta[1], delta[0])), 6
                ),
            },
        }
        a["source_polygon"] = {
            "centroid_inches": r(poly.centroid.coords[0]),
            "bounds_inches": r(poly.bounds),
        }
        if changed:
            old_transform = oa["runtime_orientation_review"]["local_transform"]
            local = (
                ("identity" if old_transform == "mirror_y_axis" else "mirror_y_axis")
                if det < 0
                else old_transform
            )
            a["runtime_orientation_review"] = {
                "local_transform": local,
                "local_transform_basis": "source_area_affine_determinant",
            }
            for c in a["pose_recipe"]["candidates"]:
                prior = np.array(
                    [
                        c.get("anchor_x_inches_unquantized", c["anchor_x_inches"]),
                        c.get("anchor_y_inches_unquantized", c["anchor_y_inches"]),
                    ]
                )
                nxt = world(np.append(pdf(prior), 1) @ mat)
                ang = math.radians(c["rotation_degrees"])
                v = linear @ np.array([math.cos(ang), math.sin(ang)])
                rotation = (math.degrees(math.atan2(v[1], v[0])) + (180 if det < 0 else 0)) % 360
                c.update(
                    anchor_x_inches_unquantized=round(nxt[0], 9),
                    anchor_y_inches_unquantized=round(nxt[1], 9),
                    anchor_x_inches=q(nxt[0]),
                    anchor_y_inches=q(nxt[1]),
                    rotation_degrees=round(rotation, 6),
                )
            selected = next(
                c
                for c in a["pose_recipe"]["candidates"]
                if c["candidate_index"] == a["pose_recipe"]["selected_candidate_index"]
            )
            a["pose_recipe"].update(
                local_transform=local,
                selected_candidate=copy.deepcopy(selected),
                **{
                    k: selected[k]
                    for k in ("anchor_x_inches", "anchor_y_inches", "rotation_degrees")
                },
            )
            a["pose_recipe"]["method"] = (
                "prior reviewed modeled-footprint registration transported by current f"
                "ull vector affine; residual refers to original model registration"
            )
            a["pose_recipe"]["review_note"] = (
                "Current vector registration is independently observed; this is a sourc"
                "e-pose candidate, not an approved final runtime correction."
            )
        if page in (24, 25, 26):
            local = (
                "mirror_y_axis"
                if ip["orientation_reversing_image_y_up_to_battlefield_frame"]
                else "identity"
            )
            vertices = templates[a["footprint_template_id"]]
            first = np.array(vertices[0])
            shape = Polygon(np.array(vertices) - first)
            if local == "mirror_y_axis":
                shape = affinity.scale(shape, xfact=-1, yfact=1, origin=(0, 0))
            candidates = []
            for ci in range(4):
                angle = (ip["battlefield_image_x_axis_rotation_degrees"] + ci * 90) % 360
                rotated = affinity.rotate(shape, angle, origin=(0, 0))
                anchor = np.array(poly.centroid.coords[0]) - np.array(rotated.centroid.coords[0])
                qx, qy = q(anchor[0]), q(anchor[1])
                modeled = affinity.translate(rotated, xoff=qx, yoff=qy)
                distances = [
                    modeled.boundary.interpolate(t, normalized=True).distance(poly.boundary)
                    for t in np.linspace(0, 1, 128)
                ]
                distances += [
                    poly.boundary.interpolate(t, normalized=True).distance(modeled.boundary)
                    for t in np.linspace(0, 1, 128)
                ]
                candidates.append(
                    {
                        "candidate_index": ci,
                        "anchor_x_inches_unquantized": round(anchor[0], 9),
                        "anchor_y_inches_unquantized": round(anchor[1], 9),
                        "anchor_x_inches": qx,
                        "anchor_y_inches": qy,
                        "rotation_degrees": round(angle, 6),
                        "fit_residual_inches": round(float(np.mean(distances)), 6),
                    }
                )
            candidates.sort(key=lambda c: (c["fit_residual_inches"], c["candidate_index"]))
            selected = candidates[0]
            a["runtime_orientation_review"] = {
                "local_transform": local,
                "local_transform_basis": "source_area_affine_determinant",
            }
            a["pose_recipe"] = {
                "method": (
                    "current four-way source-image-axis registration; modeled footprint cen"
                    "troid aligned to observed current outline centroid; 128+128 symmetric "
                    "boundary samples"
                ),
                "local_transform": local,
                **{
                    k: selected[k]
                    for k in (
                        "anchor_x_inches",
                        "anchor_y_inches",
                        "rotation_degrees",
                        "fit_residual_inches",
                    )
                },
                "quantized_anchor_increment_inches": 0.05,
                "selected_candidate_index": selected["candidate_index"],
                "equivalent_candidate_indices_within_0_001_inches": [
                    c["candidate_index"]
                    for c in candidates
                    if c["fit_residual_inches"] - selected["fit_residual_inches"] <= 0.001
                ],
                "selected_candidate": copy.deepcopy(selected),
                "candidates": candidates,
                "review_note": (
                    "Retires historical forced-symmetry exemplar registration. All16source "
                    "pieces independently registered from current observations."
                ),
            }
        records["footprints"].append(
            {
                "id": a["area_id"],
                "old_seqno": before["seqno"],
                "new_seqno": after["seqno"],
                "same_vector": not changed,
                "affine_old_pdf_to_current_pdf": r(mat),
                "maximum_vector_registration_residual_points": round(residual, 9),
                "determinant": round(det, 9),
                "local_transform": a["runtime_orientation_review"]["local_transform"],
                "identity_basis": ob["identity_basis"],
            }
        )
    # Current components are assigned to family-compatible source footprint slots,
    # preserving matching archetype ordinals and recording replaced slot contents.
    comps = {c["component_id"]: c for c in layout["terrain_components"]}
    for observed_component in obs["components"]:
        c = comps[observed_component["id"]]
        img = observed_component["new"]
        ip = imagepose(img)
        c.update(
            source_xref=img["xref"],
            canonical_xref=0,
            archetype_id=observed_component["archetype_id"],
            density=archetypes[observed_component["archetype_id"]]["classification"],
            page_image_index_zero_based=observed_component["image_index"],
            source_bbox_points=r(img["bbox"]),
            source_affine_normalized_image_to_points=r(img["transform"]),
        )
        c.update(
            {
                k: v
                for k, v in ip.items()
                if k not in ("source_pdf_affine_determinant", "battlefield_affine_determinant")
            }
        )
        c["battlefield_center_quantized_0_05_inches"] = [
            q(v) for v in ip["battlefield_center_inches"]
        ]
        parent = areas[c["parent_area_id"]]
        parent_sign = (
            -1 if parent["runtime_orientation_review"]["local_transform"] == "mirror_y_axis" else 1
        )
        component_sign = -1 if ip["orientation_reversing_image_y_up_to_battlefield_frame"] else 1
        relative = parent_sign * component_sign
        c["local_orientation_relative_to_parent"] = {
            "parent_area_determinant_sign": parent_sign,
            "component_image_y_up_to_battlefield_determinant_sign": component_sign,
            "relative_determinant_sign": relative,
            "local_transform": "mirror_y_axis" if relative < 0 else "identity",
            "local_transform_basis": "source_parent_relative_affine_determinant",
        }
        records["components"].append(
            {
                "id": c["component_id"],
                "old_archetype_id": observed_component["old_archetype_id"],
                "current_archetype_id": c["archetype_id"],
                "current_source_image_xref": img["xref"],
                "source_center_to_assigned_polygon_distance_inches": round(
                    observed_component["parent_center_distance_points"] * max(sx, -sy), 9
                ),
                "identity_basis": (
                    "project footprint-slot identity; archetype changes are explicit replac"
                    "ements at that slot"
                ),
            }
        )
    for a in layout["terrain_areas"]:
        cs = [c for c in layout["terrain_components"] if c["parent_area_id"] == a["area_id"]]
        kinds = {c["density"] for c in cs}
        a["classification"] = next(iter(kinds)) if len(kinds) == 1 else "mixed"
        a["component_ids"] = [c["component_id"] for c in cs]
        partner = areas[a["point_symmetry_partner_area_id"]]
        a["point_symmetry_residual_inches"] = round(
            float(
                np.linalg.norm(
                    np.array(a["source_polygon"]["centroid_inches"])
                    + np.array(partner["source_polygon"]["centroid_inches"])
                    - [44, 60]
                )
            ),
            6,
        )
    # Source symmetry is correspondence evidence, never synthesized placement.
    for c in layout["terrain_components"]:
        options = [
            other
            for other in layout["terrain_components"]
            if other["component_id"] != c["component_id"]
            and other["archetype_id"] == c["archetype_id"]
        ]
        if not options:
            c["point_symmetry_partner_component_id"] = None
            c["point_symmetry_center_residual_inches"] = None
            continue
        partner = min(
            options,
            key=lambda other: np.linalg.norm(
                np.array(c["battlefield_center_inches"])
                + np.array(other["battlefield_center_inches"])
                - [44, 60]
            ),
        )
        c["point_symmetry_partner_component_id"] = partner["component_id"]
        c["point_symmetry_center_residual_inches"] = round(
            float(
                np.linalg.norm(
                    np.array(c["battlefield_center_inches"])
                    + np.array(partner["battlefield_center_inches"])
                    - [44, 60]
                )
            ),
            6,
        )
    # Every coloured marker, including small diamond variants, is reobserved.
    objectives = []
    for item in obs["objectives"]:
        n = item["new"]
        b = n["rect"]
        cp = [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]
        wp = world(cp)
        role = n["role"]
        identity = item["id"] or f"{layout['layout_id']}-{role.replace('_', '-')}-02"
        near = sorted(polygons, key=lambda key: (polygons[key].distance(Point(wp)), key))[:2]
        objectives.append(
            {
                "objective_id": identity,
                "role": role,
                "fill_rgb": r(n["fill"]),
                "source_drawing_index_zero_based": n["drawing_index"],
                "source_seqno": n["seqno"],
                "source_bbox_points": r(b),
                "source_center_points": r(cp),
                "battlefield_center_inches": r(wp),
                "battlefield_center_quantized_0_01_inches": [q(v, 0.01) for v in wp],
                "nearest_area_ids": near,
                "distances_to_area_polygons_inches": [
                    round(polygons[key].distance(Point(wp)), 6) for key in near
                ],
            }
        )
        records["objectives"].append(
            {
                "old_id": item["id"],
                "current_id": identity,
                "role": role,
                "current_seqno": n["seqno"],
                "identity_basis": (
                    "project continuity convention: same-role minimum displacement; append "
                    "central-02 for additional marker"
                ),
            }
        )
    layout["objectives"] = objectives
    # Each visible icon gets a stable project ID by the actual footprint pair.
    bydraw = dict(enumerate(draws))
    area_by_seq = {a["source_vector_path"]["seqno"]: a["area_id"] for a in layout["terrain_areas"]}
    previous_pairs = {
        frozenset(pair["area_ids"]): pair["icon_ids"][0] for pair in old["source_contact_pairs"]
    }
    next_index = (
        max(int(icon["icon_id"].rsplit("-", 1)[1]) for icon in old["eye_contact_icons"]) + 1
    )
    layout["eye_contact_icons"] = []
    layout["source_contact_pairs"] = []
    for icon in eyes["october"]:
        if icon["gray_visible_pixels"] == 0:
            assert page == 35
            assert icon["source_seqno"] == 46
            continue
        ids = sorted(area_by_seq[bydraw[i]["seqno"]] for i in icon["nearest_area_drawing_indices"])
        identity = previous_pairs.get(frozenset(ids))
        if identity is None:
            identity = f"{layout['layout_id']}-terrain-contact-icon-{next_index:02d}"
            next_index += 1
        indices = [icon["source_drawing_index"], *icon["gray_detail_indices"]]
        cp = icon["source_center_points"]
        wp = world(cp)
        gap = polygons[ids[0]].distance(polygons[ids[1]])
        layout["eye_contact_icons"].append(
            {
                "icon_id": identity,
                "kind": icon["kind"],
                "source_drawing_indices_zero_based": indices,
                "source_seqnos": [bydraw[i]["seqno"] for i in indices],
                "source_center_points": r(cp),
                "battlefield_center_inches": r(wp),
                "battlefield_center_quantized_0_05_inches": [q(v) for v in wp],
                "nearest_area_ids": ids,
                "distances_to_area_polygons_inches": [
                    round(polygons[key].distance(Point(wp)), 6) for key in ids
                ],
                "source_pair_gap_inches": round(gap, 6),
            }
        )
        layout["source_contact_pairs"].append(
            {
                "area_ids": ids,
                "icon_ids": [identity],
                "kinds": [icon["kind"]],
                "source_pair_gap_inches": round(gap, 6),
            }
        )
        records["contacts"].append(
            {
                "id": identity,
                "kind": icon["kind"],
                "area_ids": ids,
                "visible_gray_pixels_at_4x": icon["gray_visible_pixels"],
                "current_seqno": icon["source_seqno"],
            }
        )
    audits = layout["audits"]
    audits.update(
        objective_count=len(objectives),
        objective_role_counts=dict(sorted(Counter(o["role"] for o in objectives).items())),
        eye_icon_count=len(layout["eye_contact_icons"]),
        eye_icon_kind_counts=dict(
            sorted(Counter(i["kind"] for i in layout["eye_contact_icons"]).items())
        ),
        icon_derived_contact_pair_count=len(layout["source_contact_pairs"]),
        maximum_icon_derived_source_pair_gap_inches=max(
            p["source_pair_gap_inches"] for p in layout["source_contact_pairs"]
        ),
    )
    correspondence.append(records)

# Rebind the same explicitly modeled archetypes to current assets. Models remain
# reviewed engine assumptions, not dimensions inferred from raster imagery.
for a in result["reviewed_feature_archetypes"]:
    used = {
        c["source_xref"]
        for layout_record in result["layouts"]
        for c in layout_record["terrain_components"]
        if c["archetype_id"] == a["archetype_id"]
    }
    xrefs = []
    for prior_asset in archetypes[a["archetype_id"]]["source_assets"]:
        xrefs.extend(
            x
            for x in sorted(used)
            if asset(x)["image_sha256"] == prior_asset["image_sha256"] and x not in xrefs
        )
    xrefs.extend(x for x in sorted(used) if x not in xrefs)
    a["source_assets"] = [asset(xref) for xref in xrefs]
    a["modeling_basis"] += (
        " October migration: current source-instance imagery/affines reobserved"
        "; shared physical model retained as a project modeling assumption, not"
        " remeasured from the raster."
    )
    if a["archetype_id"] == "dense-tall-crates":
        a["modeling_basis"] += (
            " New current alias xref356 is51x87px: its left48columns match the cano"
            "nical48x87mask99.8803%; the source image-midpoint convention is retain"
            "ed, with a1.5px/0.046267835in offset from the canonicalfeature midpoin"
            "t. Final runtime containment is independently required; raster art is "
            "not a physical-dimension authority."
        )
    for layout_record in result["layouts"]:
        for c in layout_record["terrain_components"]:
            if c["archetype_id"] == a["archetype_id"]:
                c["canonical_xref"] = xrefs[0]
current_archetypes = {a["archetype_id"]: a for a in result["reviewed_feature_archetypes"]}
for a in result["component_archetypes"]:
    canonical = current_archetypes[a["archetype_id"]]["source_assets"][0]

    def legacy_asset(sa):
        info = doc.extract_image(sa["source_pdf_image_xref"])
        mask = doc.extract_image(sa["soft_mask_xref"])
        return {
            "xref": sa["source_pdf_image_xref"],
            "extension": info["ext"],
            "pixel_width": sa["pixel_width"],
            "pixel_height": sa["pixel_height"],
            "raw_image_sha256": sa["image_sha256"],
            "soft_mask": {
                "xref": sa["soft_mask_xref"],
                "extension": mask["ext"],
                "pixel_width": mask["width"],
                "pixel_height": mask["height"],
                "raw_image_sha256": sa["soft_mask_sha256"],
            },
        }

    a["canonical_xref"] = canonical["source_pdf_image_xref"]
    a["canonical_asset"] = legacy_asset(canonical)
    a["alias_assets"] = [
        legacy_asset(sa) for sa in current_archetypes[a["archetype_id"]]["source_assets"][1:]
    ]
result["component_alias_to_canonical_xref"] = {
    str(sa["source_pdf_image_xref"]): a["source_assets"][0]["source_pdf_image_xref"]
    for a in result["reviewed_feature_archetypes"]
    for sa in a["source_assets"][1:]
}
for layout_record in result["layouts"]:
    layout_record["audits"]["component_canonical_xref_counts"] = dict(
        sorted(
            Counter(str(c["canonical_xref"]) for c in layout_record["terrain_components"]).items()
        )
    )
result["source"].update(
    pdf_filename="eng_14-10_warhammer40000_event_companion-v1-3.pdf",
    pdf_sha256=hashlib.sha256(PDF.read_bytes()).hexdigest(),
    repo_relative_pdf_path="docs/source_rules/eng_14-10_warhammer40000_event_companion-v1-3.pdf",
    document_version="1.3",
    source_scope=(
        "Layouts key page8 and complete45diagrams pages9\u201353 only; mission cards"
        "/base-size rows retain separate historical provenance"
    ),
    visible_revision_pages=[
        r["page"] for r in correspondence if any(not a["same_vector"] for a in r["footprints"])
    ],
    visible_revision_note=(
        "Current October source observations compared with immutable July audit"
        "; all45pages reviewed including unchanged vectors and changed componen"
        "ts/glyphs/markers."
    ),
)
result["coordinate_frame"]["background_image"]["xref"] = next(
    i["xref"]
    for i in observed["layouts"][0]["images_new"]
    if i["raw_sha256"] == result["coordinate_frame"]["background_image"]["image_sha256"]
)
result["coordinate_frame"]["background_image"]["reuse_audit_pages"] = list(range(9, 54))
result["coordinate_frame"]["control_fit_maximum_residual_inches"] = None
result["coordinate_frame"]["control_fit_note"] = (
    "Retained nominal44x60 registration: exact identical background affines"
    " on all45pages; printed dimensions/canonical templates govern deployme"
    "nt. Artwork edge residuals are not a0.03in assertion. Page47 decorativ"
    "eborder differs; p53defender artwork realigned to template1."
)
allcontacts = [i for layout_record in result["layouts"] for i in layout_record["eye_contact_icons"]]
result["global_audits"].update(
    objective_count=sum(len(layout_record["objectives"]) for layout_record in result["layouts"]),
    objective_role_counts=dict(
        Counter(
            o["role"] for layout_record in result["layouts"] for o in layout_record["objectives"]
        )
    ),
    eye_icon_count=len(allcontacts),
    eye_icon_candidate_count_before_visibility_review=len(allcontacts) + 1,
    eye_icon_excluded_candidate_count=1,
    eye_icon_kind_counts=dict(Counter(i["kind"] for i in allcontacts)),
    source_contact_pair_count=len(allcontacts),
    single_terrain_area_group_count=sum(i["kind"] == "single" for i in allcontacts),
    logical_terrain_area_count=720 - sum(i["kind"] == "single" for i in allcontacts),
    validation_status="candidate_pending_runtime_and_independent_review",
    component_source_xref_counts=dict(
        Counter(
            str(c["source_xref"])
            for layout_record in result["layouts"]
            for c in layout_record["terrain_components"]
        )
    ),
)
result["deterministic_precision"]["runtime_finalization_requirements"] = (
    "Choose current source-pose candidates independently for all45layouts; "
    "apply only witnessed bounded grid/contact/containment corrections. His"
    "torical Meatgrinder exact symmetry is retired; symmetry links are sour"
    "ce correspondence only. Preserve page9source-absent component. Shared "
    "shape/height models remain explicit historical assumptions."
)
result["global_audits"]["maximum_icon_derived_source_pair_gap_inches"] = max(
    i["source_pair_gap_inches"] for i in allcontacts
)
result["global_audits"]["maximum_selected_pose_fit_residual_inches"] = max(
    a["pose_recipe"]["fit_residual_inches"] or 0
    for layout_record in result["layouts"]
    for a in layout_record["terrain_areas"]
)
result["current_source_correspondence"] = correspondence
(ROOT / "october-extraction-candidate.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result["global_audits"], indent=2))
