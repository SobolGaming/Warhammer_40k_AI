"""Resolve occurrence identity by footprint family and component contents."""

import json
from collections import Counter

import numpy as np
from scipy.optimize import linear_sum_assignment
from shapely.geometry import Point, Polygon
from source_context import REF, ROOT

d = json.loads((ROOT / "current-observations.json").read_text())
ref = REF
assets = {
    a["image_sha256"]: r["archetype_id"]
    for r in ref["reviewed_feature_archetypes"]
    for a in r["source_assets"]
}
archetypes = {r["archetype_id"]: r for r in ref["reviewed_feature_archetypes"]}
templates = {
    int(k): v for k, v in ref["footprint_detection"]["path_item_count_to_template_id"].items()
}
capacities = {
    r["footprint_template_id"]: r["component_capacity"] for r in ref["footprint_templates"]
}


def outline(draw):
    out = []
    for item in draw["items"]:
        if item[0] == "l":
            out.extend(item[1:])
        elif item[0] == "c":
            a, b, c, e = map(np.array, item[1:])
            out.extend(
                (
                    (1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t * t * c + t**3 * e
                ).tolist()
                for t in np.linspace(0, 1, 21)
            )
        else:
            raise ValueError(item[0])
    p = Polygon(out)
    if not p.is_valid:
        raise ValueError("bad polygon")
    return p


def center(i):
    r = i["bbox"]
    return [(r[0] + r[2]) / 2, (r[1] + r[3]) / 2]


for row, layout_record in zip(d["layouts"], ref["layouts"], strict=True):
    news = [a["new"] for a in row["areas"]]
    polys = [outline(a) for a in news]
    images = []
    for idx, i in enumerate(row["images_new"]):
        kind = assets.get(i["raw_sha256"])
        if i["xref"] == 356 and (i["width"], i["height"]) == (51, 87):
            kind = "dense-tall-crates"
        if kind is None:
            continue
        images.append({"image": i, "image_index": idx, "archetype_id": kind})
    expected = 29 if row["page"] == 9 else 30
    if len(images) != expected:
        raise ValueError((row["page"], len(images)))
    slots = [
        idx
        for idx, n in enumerate(news)
        for _ in range(
            capacities[templates[len(n["items"])]] - (1 if row["page"] == 9 and idx == 5 else 0)
        )
    ]
    costs = np.array(
        [
            [
                100 * polys[s].distance(Point(center(i["image"])))
                + np.linalg.norm(
                    np.array(center(i["image"])) - np.array(polys[s].centroid.coords[0])
                )
                if templates[len(news[s]["items"])]
                == archetypes[i["archetype_id"]]["footprint_template_id"]
                else 1e9
                for s in slots
            ]
            for i in images
        ]
    )
    ia, ib = linear_sum_assignment(costs)
    for i, j in zip(ia, ib, strict=True):
        images[i]["parent_index"] = slots[j]
        images[i]["parent_center_distance_points"] = polys[slots[j]].distance(
            Point(center(images[i]["image"]))
        )
    oldcomps = {
        a["area_id"]: Counter(
            c["archetype_id"]
            for c in layout_record["terrain_components"]
            if c["parent_area_id"] == a["area_id"]
        )
        for a in layout_record["terrain_areas"]
    }
    newcomps = {
        idx: Counter(i["archetype_id"] for i in images if i["parent_index"] == idx)
        for idx in range(16)
    }
    costs = np.array(
        [
            [
                np.linalg.norm(np.array(a["old"]["rect"][:2]) - np.array(n["rect"][:2]))
                if len(a["old"]["items"]) == len(n["items"])
                else 1e9
                for j, n in enumerate(news)
            ]
            for a in row["areas"]
        ]
    )
    ia, ib = linear_sum_assignment(costs)
    if max(costs[i, j] for i, j in zip(ia, ib, strict=True)) > 1e8:
        raise ValueError(("Unmatched area contents", row["page"], oldcomps, newcomps))
    newareas = []
    newcomponents = []
    for ai, bi in zip(ia, ib, strict=True):
        oldrow = row["areas"][ai]
        new = news[bi]
        oldrow["new"] = new
        oldrow["new_component_contents"] = dict(newcomps[bi])
        oldrow["identity_basis"] = (
            "same footprint family; minimum total source displacement, independentl"
            "y reviewed content changes recorded"
        )
        oldrow["new_polygon_points"] = list(polys[bi].exterior.coords)
        oldrow["new_image_candidates"] = [i for i in images if i["parent_index"] == bi]
        oldrow.pop("affine", None)
        newareas.append(oldrow)
        oldcs = [
            c for c in layout_record["terrain_components"] if c["parent_area_id"] == oldrow["id"]
        ]
        newcs = oldrow["new_image_candidates"]
        assert len(oldcs) == len(newcs), (row["page"], oldrow["id"])
        cc = np.array(
            [
                [
                    np.linalg.norm(
                        np.array(c["source_bbox_points"][:2]) - np.array(n["image"]["bbox"][:2])
                    )
                    + (0 if c["archetype_id"] == n["archetype_id"] else 1000)
                    for n in newcs
                ]
                for c in oldcs
            ]
        )
        ci, cj = linear_sum_assignment(cc)
        for i, j in zip(ci, cj, strict=True):
            newcomponents.append(
                {
                    "id": oldcs[i]["component_id"],
                    "old_archetype_id": oldcs[i]["archetype_id"],
                    "parent_id": oldrow["id"],
                    "archetype_id": newcs[j]["archetype_id"],
                    "new": newcs[j]["image"],
                    "image_index": newcs[j]["image_index"],
                    "parent_center_distance_points": newcs[j]["parent_center_distance_points"],
                }
            )
    row["areas"] = newareas
    row["components"] = newcomponents
    print(row["page"], max(i["parent_center_distance_points"] for i in images))
(ROOT / "current-refined-correspondence.json").write_text(json.dumps(d, indent=2) + "\n")
