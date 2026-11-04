import json
import math

import fitz
import numpy as np
from shapely.geometry import Point, Polygon
from source_context import NEW, OLD, REF
from source_context import ROOT as D

old = fitz.open(OLD)
new = fitz.open(NEW)
aff = REF["coordinate_frame"]["pdf_to_battlefield_affine"]


def xy(p):
    return (
        p[0] * aff["x_inches"]["scale"] + aff["x_inches"]["offset"],
        p[1] * aff["y_inches"]["scale"] + aff["y_inches"]["offset"],
    )


def color(a, b):
    return a is not None and max(abs(x - y) for x, y in zip(a, b, strict=True)) < 2e-6


def polygon(d):
    pts = []
    for item in d["items"]:
        if item[0] == "l":
            pts.extend([xy(item[1]), xy(item[2])])
        elif item[0] == "c":
            a, b, c, e = item[1:]
            for i in range(21):
                t = i / 20
                pts.append(
                    xy(
                        (
                            (1 - t) ** 3 * a.x
                            + 3 * (1 - t) ** 2 * t * b.x
                            + 3 * (1 - t) * t * t * c.x
                            + t**3 * e.x,
                            (1 - t) ** 3 * a.y
                            + 3 * (1 - t) ** 2 * t * b.y
                            + 3 * (1 - t) * t * t * c.y
                            + t**3 * e.y,
                        )
                    )
                )
        else:
            raise ValueError(item)
    return Polygon(pts)


def extract(doc, n):
    p = doc[n - 1]
    ds = p.get_drawings()
    areas = [
        (i, d, polygon(d))
        for i, d in enumerate(ds)
        if color(d["fill"], (0.820203, 0.826001, 0.832288))
    ]
    gray = [
        (i, d)
        for i, d in enumerate(ds)
        if color(d["fill"], (0.5028, 0.510033, 0.520073))
        and 10 < d["rect"].width < 25
        and 275 < d["rect"].y0 < 740
    ]
    result = []
    for i, d in gray:
        if len(d["items"]) != 4:
            continue
        r = d["rect"]
        c = ((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
        close = [
            (j, e)
            for j, e in gray
            if j != i
            and math.dist(c, ((e["rect"].x0 + e["rect"].x1) / 2, (e["rect"].y0 + e["rect"].y1) / 2))
            < 1
        ]
        im = p.get_pixmap(matrix=fitz.Matrix(4, 4), clip=r, alpha=False)
        a = np.frombuffer(im.samples, np.uint8).reshape(im.height, im.width, im.n)
        visible = int(
            np.count_nonzero(np.max(np.abs(a.astype(int) - np.array([128, 130, 133])), axis=2) <= 4)
        )
        point = Point(xy(c))
        nearest = sorted(
            [(poly.distance(point), j, poly) for j, e, poly in areas], key=lambda x: x[0]
        )[:3]
        result.append(
            {
                "source_drawing_index": i,
                "source_seqno": d["seqno"],
                "source_center_points": c,
                "source_rect": list(r),
                "kind": "separate" if close else "single",
                "gray_detail_indices": [j for j, e in close],
                "gray_visible_pixels": visible,
                "nearest_area_drawing_indices": [j for dist, j, poly in nearest[:2]],
                "nearest_distances_inches": [dist for dist, j, poly in nearest],
                "pair_source_gap_inches": nearest[0][2].distance(nearest[1][2]),
                "third_distance_margin_inches": nearest[2][0] - nearest[1][0],
            }
        )
    return result


rows = []
for n in range(9, 54):
    a, b = extract(old, n), extract(new, n)
    rows.append({"page": n, "july": a, "october": b})
report = {
    "source_sha256": "187253a9b6ea377f5e44d1148454bd042b165b03bb5c45c51a5880762bf56dc2",
    "method": (
        "Base gray four-curve circles; second coincident gray detail marks Sepa"
        "rate, otherwise Single. Final4x raster graypixel check rejects fully o"
        "bscured circles. Pair association independently uses nearest2 actual s"
        "ource outline polygons; ambiguous pairs require review. Curves sampled"
        "20segments for distance, not runtime authority."
    ),
    "pages": rows,
}
(D / "contacts.json").write_text(json.dumps(report, indent=2))
for r in rows:
    print(
        r["page"],
        [
            (
                x["kind"],
                x["source_seqno"],
                x["gray_visible_pixels"],
                round(x["pair_source_gap_inches"], 4),
                round(x["third_distance_margin_inches"], 3),
            )
            for x in r["october"]
        ],
    )
