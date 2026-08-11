from __future__ import annotations

# The three page-29 exceptions are the unique minimum-distance feasible centers
# from 867 exhaustive +/-0.40-inch grid candidates; they have <=4.44e-16 square
# inches outside, zero sibling overlap, and no declared component contacts. The
# two page-23 exceptions are likewise the unique one-step minima among 578 grid
# candidates; they have zero outside area and preserve zero-gap contact with their
# declared industrial-crate composite sibling. The matching page-38/page-45
# exceptions are each the unique one-step minimum among 289 candidates: outside
# area falls from 0.04625 to zero, sibling overlap remains zero, and the 1.825-inch
# sibling gap is unchanged.
REVIEWED_FIXED_COMPONENT_CENTERS = {
    "disruption-vs-disruption-layout-3-terrain-area-02-component-01": (10.90, 53.45),
    "purge-the-foe-vs-disruption-layout-3-terrain-area-04-component-01": (37.85, 41.35),
    "purge-the-foe-vs-disruption-layout-3-terrain-area-07-component-01": (27.05, 27.55),
    "purge-the-foe-vs-disruption-layout-3-terrain-area-13-component-01": (6.10, 18.50),
    "take-and-hold-vs-priority-assets-layout-3-terrain-area-08-component-03": (35.40, 35.60),
    "take-and-hold-vs-priority-assets-layout-3-terrain-area-09-component-02": (8.50, 24.30),
    "reconnaissance-vs-reconnaissance-layout-1-terrain-area-02-component-01": (
        10.90,
        53.45,
    ),
}

_LAYOUT_FAMILIES = (
    (
        "take-and-hold",
        "take-and-hold",
        9,
        ("primary-battlefield-dominance", "primary-battlefield-dominance"),
        (1, 2, 3),
    ),
    (
        "take-and-hold",
        "purge-the-foe",
        12,
        ("primary-immovable-object", "primary-unstoppable-force"),
        (4, 3, 5),
    ),
    (
        "take-and-hold",
        "disruption",
        15,
        ("primary-determined-acquisition", "primary-death-trap"),
        (4, 6, 5),
    ),
    (
        "take-and-hold",
        "reconnaissance",
        18,
        ("primary-purge-and-secure", "primary-reconnaissance-sweep"),
        (1, 2, 3),
    ),
    (
        "take-and-hold",
        "priority-assets",
        21,
        ("primary-inescapable-dominion", "primary-secure-asset"),
        (6, 5, 2),
    ),
    (
        "purge-the-foe",
        "purge-the-foe",
        24,
        ("primary-meatgrinder", "primary-meatgrinder"),
        (3, 1, 4),
    ),
    (
        "purge-the-foe",
        "disruption",
        27,
        ("primary-punishment", "primary-delaying-action"),
        (3, 1, 4),
    ),
    (
        "purge-the-foe",
        "reconnaissance",
        30,
        ("primary-consecrate", "primary-triangulation"),
        (5, 2, 6),
    ),
    (
        "purge-the-foe",
        "priority-assets",
        33,
        ("primary-destroyers-wrath", "primary-vital-link"),
        (2, 3, 5),
    ),
    (
        "disruption",
        "disruption",
        36,
        ("primary-outmaneuver", "primary-outmaneuver"),
        (6, 1, 4),
    ),
    (
        "disruption",
        "reconnaissance",
        39,
        ("primary-smoke-and-mirrors", "primary-surveil-the-foe"),
        (1, 2, 3),
    ),
    (
        "disruption",
        "priority-assets",
        42,
        ("primary-locate-and-deny", "primary-extract-relic"),
        (4, 1, 3),
    ),
    (
        "reconnaissance",
        "reconnaissance",
        45,
        ("primary-gather-intel", "primary-gather-intel"),
        (4, 6, 1),
    ),
    (
        "reconnaissance",
        "priority-assets",
        48,
        ("primary-search-and-scour", "primary-vanguard-operation"),
        (6, 1, 4),
    ),
    (
        "priority-assets",
        "priority-assets",
        51,
        ("primary-sabotage", "primary-sabotage"),
        (4, 6, 1),
    ),
)
LAYOUT_CONFIG_BY_PAGE = {
    first_page + variant_index: (
        f"{left_id}-vs-{right_id}-layout-{variant_index + 1}",
        (left_id, right_id),
        missions,
        templates[variant_index],
    )
    for left_id, right_id, first_page, missions, templates in _LAYOUT_FAMILIES
    for variant_index in range(3)
}
DISPLAY_NAME = {
    "take-and-hold": "Take and Hold",
    "purge-the-foe": "Purge the Foe",
    "disruption": "Disruption",
    "reconnaissance": "Reconnaissance",
    "priority-assets": "Priority Assets",
}
PRIMARY_MISSION_DISPLAY_NAME = {
    "primary-battlefield-dominance": "Battlefield Dominance",
    "primary-immovable-object": "Immovable Object",
    "primary-unstoppable-force": "Unstoppable Force",
    "primary-determined-acquisition": "Determined Acquisition",
    "primary-death-trap": "Death Trap",
    "primary-purge-and-secure": "Purge and Secure",
    "primary-reconnaissance-sweep": "Reconnaissance Sweep",
    "primary-inescapable-dominion": "Inescapable Dominion",
    "primary-secure-asset": "Secure Asset",
    "primary-meatgrinder": "Meatgrinder",
    "primary-punishment": "Punishment",
    "primary-delaying-action": "Delaying Action",
    "primary-consecrate": "Consecrate",
    "primary-triangulation": "Triangulation",
    "primary-destroyers-wrath": "Destroyer's Wrath",
    "primary-vital-link": "Vital Link",
    "primary-outmaneuver": "Outmanoeuvre",
    "primary-smoke-and-mirrors": "Smoke and Mirrors",
    "primary-surveil-the-foe": "Surveil the Foe",
    "primary-locate-and-deny": "Locate and Deny",
    "primary-extract-relic": "Extract Relic",
    "primary-gather-intel": "Gather Intel",
    "primary-search-and-scour": "Search and Scour",
    "primary-vanguard-operation": "Vanguard Operation",
    "primary-sabotage": "Sabotage",
}
ARCHETYPE_IDS = (
    "dense-downed-hovercraft",
    "light-long-barricade",
    "dense-industrial-crates",
    "light-end-barricade",
    "ruins-cd",
    "ruins-gh",
    "ruins-ef",
    "ruins-ab",
    "light-corner-ab",
    "light-corner-cd",
    "light-corner-ef",
    "light-corner-gh",
    "dense-tall-crates",
    "dense-long-pipes",
)
SOURCE_COORDINATE_FRAME = {
    "pdf_background_image_xref": 5490,
    "pdf_background_image_sha256": (
        "2eda9e45dadd328907dba59ca1f6630e816571e2bcfc20b1f5bf97f0c8b8772a"
    ),
    "pdf_background_bounds": {
        "x0_points": 127.690826,
        "y0_points": 276.662323,
        "x1_points": 468.448334,
        "y1_points": 741.498596,
    },
    "battlefield_width_inches": 44.0,
    "battlefield_depth_inches": 60.0,
    "battlefield_origin": "bottom_left",
    "battlefield_orientation": "x_right_along_44_inch_edge_y_up_along_60_inch_edge",
    "coordinate_precision_decimal_places": 6,
    "terrain_placement_increment_inches": 0.05,
    "runtime_exact_seam_closure_precision_decimal_places": 12,
}
