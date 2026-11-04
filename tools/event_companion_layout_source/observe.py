"""Raw PDF observations and explicit historical occurrence correspondence.

This is source inspection, not runtime geometry or certification.
"""

import hashlib
import json

import fitz
import numpy as np
from scipy.optimize import linear_sum_assignment
from source_context import NEW, OLD, REF, ROOT

BOARD = fitz.Rect(REF["coordinate_frame"]["source_board_rect_points"])
FILL = REF["footprint_detection"]["visible_vector_fill_rgb"]
COLORS = {
    "attacker_home": (0.61796, 0.039963, 0.05568),
    "defender_home": (0, 0.240604, 0.408362),
    "central": (0, 0.451789, 0.37763),
    "expansion": (0.128344, 0.570916, 0.517968),
}
ASSET_HASHES = {
    r["archetype_id"]: {a["image_sha256"] for a in r["source_assets"]}
    for r in REF["reviewed_feature_archetypes"]
}
IMAGE_CACHE = {}


def norm(v):
    if isinstance(v, (fitz.Point, fitz.Rect, fitz.Quad)):
        return [round(x, 9) for x in v]
    if isinstance(v, (list, tuple)):
        return [norm(x) for x in v]
    if isinstance(v, dict):
        return {k: norm(x) for k, x in v.items()}
    if isinstance(v, bytes):
        return v.hex()
    return v


def close(a, b):
    return (
        a is not None
        and len(a) == len(b)
        and max(abs(x - y) for x, y in zip(a, b, strict=True)) < 2e-6
    )


def center(d):
    r = fitz.Rect(d["rect"] if "rect" in d else d["bbox"])
    return np.array([(r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2])


def points(d):
    out = []
    for item in d["items"]:
        if item[0] in ("l", "c"):
            out.extend(list(x) for x in item[1:])
        elif item[0] == "re":
            r = item[1]
            out.extend([list(r.tl), list(r.tr), list(r.br), list(r.bl)])
        elif item[0] == "qu":
            out.extend(list(x) for x in item[1])
        else:
            raise ValueError(item)
    return np.array(out)


def affine(a, b):
    pa, pb = points(a), points(b)
    if pa.shape != pb.shape:
        raise ValueError("nonmatching path")
    mat, _res, _rank, _s = np.linalg.lstsq(np.column_stack([pa, np.ones(len(pa))]), pb, rcond=None)
    return {
        "matrix": mat.tolist(),
        "max_residual_points": float(
            np.max(np.linalg.norm(np.column_stack([pa, np.ones(len(pa))]) @ mat - pb, axis=1))
        ),
        "determinant": float(np.linalg.det(mat[:2])),
    }


def footprints(page):
    return [
        dict(d, extended_index=i)
        for i, d in enumerate(page.get_drawings(extended=True))
        if close(d.get("fill"), FILL)
    ]


def image_info(doc, page):
    rows = page.get_image_info(xrefs=True, hashes=True)
    for x in rows:
        key = (doc.name, x["xref"])
        if key not in IMAGE_CACHE:
            asset = doc.extract_image(x["xref"])
            smask = asset["smask"]
            IMAGE_CACHE[key] = (
                hashlib.sha256(asset["image"]).hexdigest(),
                smask,
                hashlib.sha256(doc.extract_image(smask)["image"]).hexdigest() if smask else None,
            )
        raw, smask, mask = IMAGE_CACHE[key]
        x["raw_sha256"] = raw
        x["smask"] = smask
        x["mask_sha256"] = mask
    return rows


def objectives(page):
    out = []
    for i, d in enumerate(page.get_drawings()):
        r = d["rect"]
        if not BOARD.contains(r) or not (20 < r.width < 30 and 20 < r.height < 30):
            continue
        for role, rgb in COLORS.items():
            if close(d["fill"], rgb):
                out.append(dict(d, drawing_index=i, role=role))
    return out


old, new = fitz.open(OLD), fitz.open(NEW)
rows = []
for layout_record in REF["layouts"]:
    p = layout_record["source_pdf_page_number"]
    op, np_ = old[p - 1], new[p - 1]
    of, nf = footprints(op), footprints(np_)
    assert len(of) == len(nf) == 16
    byseq = {x["seqno"]: x for x in of}
    costs = np.array(
        [
            [
                np.linalg.norm(center(byseq[a["source_vector_path"]["seqno"]]) - center(b))
                if len(byseq[a["source_vector_path"]["seqno"]]["items"]) == len(b["items"])
                else 1e9
                for b in nf
            ]
            for a in layout_record["terrain_areas"]
        ]
    )
    ia, ib = linear_sum_assignment(costs)
    areas = []
    for ai, bi in zip(ia, ib, strict=True):
        a = layout_record["terrain_areas"][ai]
        before = byseq[a["source_vector_path"]["seqno"]]
        after = nf[bi]
        af = affine(before, after)
        areas.append(
            {
                "id": a["area_id"],
                "old": norm(before),
                "new": norm(after),
                "affine": af,
                "center_move_points": float(costs[ai, bi]),
                "nearest_costs_points": sorted(float(x) for x in costs[ai] if x < 1e8)[:2],
            }
        )
    oi, ni = image_info(old, op), image_info(new, np_)
    comp = []
    oc = layout_record["terrain_components"]
    costs = np.full((len(oc), len(ni)), 1e9)
    for i, c in enumerate(oc):
        before = oi[c["page_image_index_zero_based"]]
        assert before["xref"] == c["source_xref"], (p, c["component_id"])
        ar = next(x for x in areas if x["id"] == c["parent_area_id"])
        expected = np.append(center(before), 1) @ np.array(ar["affine"]["matrix"])
        for j, n in enumerate(ni):
            if n["raw_sha256"] in ASSET_HASHES[c["archetype_id"]]:
                costs[i, j] = np.linalg.norm(center(n) - expected)
    ia, ib = linear_sum_assignment(costs)
    for ai, bi in zip(ia, ib, strict=True):
        c = oc[ai]
        before = oi[c["page_image_index_zero_based"]]
        after = ni[bi]
        comp.append(
            {
                "id": c["component_id"],
                "parent_id": c["parent_area_id"],
                "old": norm(before),
                "new": norm(after),
                "residual_from_transformed_parent_points": float(costs[ai, bi]),
            }
        )
    objold, objnew = objectives(op), objectives(np_)
    assert len(objold) == len(layout_record["objectives"]), (
        p,
        len(objold),
        len(layout_record["objectives"]),
    )
    obj = []
    used = set()
    costs = np.array(
        [
            [
                np.linalg.norm(np.array(o["source_center_points"]) - center(n))
                if o["role"] == n["role"]
                else 1e9
                for n in objnew
            ]
            for o in layout_record["objectives"]
        ]
    )
    ia, ib = linear_sum_assignment(costs)
    for ai, bi in zip(ia, ib, strict=True):
        o = layout_record["objectives"][ai]
        n = objnew[bi]
        used.add(int(bi))
        obj.append(
            {
                "id": o["objective_id"],
                "old_role": o["role"],
                "new": norm(n),
                "center_move_points": float(costs[ai, bi]),
            }
        )
    for i, n in enumerate(objnew):
        if i not in used:
            obj.append({"id": None, "new": norm(n)})
    rows.append(
        {
            "page": p,
            "layout_id": layout_record["layout_id"],
            "areas": areas,
            "components": comp,
            "objectives": obj,
            "images_old": norm(oi),
            "images_new": norm(ni),
        }
    )
    print(f"Observed page {p}", flush=True)
result = {
    "status": "unreviewed source occurrence correspondence; no runtime qualification",
    "old_sha256": hashlib.sha256(OLD.read_bytes()).hexdigest(),
    "new_sha256": hashlib.sha256(NEW.read_bytes()).hexdigest(),
    "layouts": rows,
}
(ROOT / "current-observations.json").write_text(json.dumps(result, indent=2) + "\n")
print(
    json.dumps(
        [
            {
                "page": r["page"],
                "area_fit_max": round(
                    max(a["affine"]["max_residual_points"] for a in r["areas"]), 5
                ),
                "component_residual_max": round(
                    max(a["residual_from_transformed_parent_points"] for a in r["components"]), 5
                ),
                "objectives": len(r["objectives"]),
                "added": sum(o["id"] is None for o in r["objectives"]),
            }
            for r in rows
        ],
        indent=2,
    )
)
