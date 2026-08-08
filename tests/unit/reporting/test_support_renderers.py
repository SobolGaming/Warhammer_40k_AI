# pyright: reportPrivateUsage=false
from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools.aeldari_39k_pro_audit import (
    AUDIT_PATH as AELDARI_AUDIT_PATH,
)
from tools.aeldari_39k_pro_audit import (
    aeldari_thirty_nine_k_pro_audit,
    load_aeldari_thirty_nine_k_pro_audit,
)
from tools.emperors_children_39k_pro_audit import (
    AUDIT_PATH,
    emperors_children_thirty_nine_k_pro_audit,
    load_emperors_children_thirty_nine_k_pro_audit,
)
from tools.faction_pack_datasheet_review import faction_pack_datasheet_review
from tools.generate_ability_support_matrix import (
    _ability_datasheet_pairs_text,
    _inline_code_list,
    _markdown_text,
    ability_support_matrix_rows,
    faction_support_markdown_files,
    runtime_content_semantic_coverage_payload,
    support_matrix_markdown,
)

from warhammer40k_core.engine.ability_coverage import (
    ability_coverage_category_rows,
    ability_coverage_category_rows_payload,
    ability_coverage_rows_payload,
)


def test_global_support_renderer_preserves_section_order_and_runtime_inventory() -> None:
    ability_rows = ability_support_matrix_rows()
    category_rows = ability_coverage_category_rows(ability_rows)
    markdown = support_matrix_markdown(
        ability_coverage_category_rows_payload(category_rows),
        ability_rows=ability_coverage_rows_payload(ability_rows),
        runtime_semantic_coverage=runtime_content_semantic_coverage_payload(),
    )

    headings = (
        "## Runtime Content Semantic Coverage",
        "## Mustering / List Construction Support",
        "## Factions",
        "## Runtime Hook Inventory",
    )
    assert all(heading in markdown for heading in headings)
    assert tuple(markdown.index(heading) for heading in headings) == tuple(
        sorted(markdown.index(heading) for heading in headings)
    )

    represented_consumer_ids = {
        consumer_id for row in ability_rows for consumer_id in row.runtime_consumer_ids
    }
    assert represented_consumer_ids
    assert all(f"`{consumer_id}`" in markdown for consumer_id in represented_consumer_ids)


def test_faction_support_renderer_preserves_section_order() -> None:
    aeldari = faction_support_markdown_files()["aeldari.md"]
    emperors_children = faction_support_markdown_files()["emperors-children.md"]

    assert aeldari.startswith("# Aeldari Support Matrix\n")
    assert aeldari.index("## Detachment Rule Support") < aeldari.index(
        "## Datasheet component coverage"
    )
    assert (
        aeldari.index("## Semantic Support Snapshot")
        < aeldari.index("## Detachment Rule Support")
        < aeldari.index("## Datasheet Source Review")
        < aeldari.index("## Secondary-reference Audit")
        < aeldari.index("## Datasheet component coverage")
    )
    assert "Corsair Coterie — Relentless Raiders" in aeldari
    assert "Armoured Warhost — Skilled Crews" in aeldari
    assert "15 detachments, 52 Enhancements, and 78 Stratagems" in aeldari
    assert "| Detachment rules | 15 | 2 | 0 | 13 |" in aeldari
    assert "| Enhancements | 52 | 6 | 0 | 46 |" in aeldari
    assert "| Stratagems | 78 | 9 | 0 | 69 |" in aeldari
    assert "https://39k.pro/faction/-utUCEwvtbI" in aeldari
    assert aeldari.count("https://39k.pro/detachment/") == 15
    assert "Guileful Strategist" not in aeldari
    assert "Harmonisation Matrix" not in aeldari
    assert "## Faction Pack Review" in emperors_children
    assert "Elegant Brutes | Yes | Physical PDF page 2" in emperors_children
    assert "Frenzied Host | Yes | Physical PDF page 3" in emperors_children
    assert "Spectacle of Slaughter | Yes | Physical PDF page 4" in emperors_children
    assert "Court of the Phoenician | No - reprinted/updated" in emperors_children
    assert "Cacophonic Accompaniment<br>Frenzied Ferocity Upgrade" in emperors_children
    assert "Possessive Mania<br>Agonised Cacophony<br>Absolute Sensory Overload" in (
        emperors_children
    )
    assert "are not yet present in the structured Phase17E artifacts" in emperors_children
    assert "## Semantic Support Snapshot" in emperors_children
    assert (
        emperors_children.index("## Faction Pack Review")
        < emperors_children.index("## Semantic Support Snapshot")
        < emperors_children.index("## Detachment Rule Support")
        < emperors_children.index("## Datasheet Source Review")
        < emperors_children.index("## Secondary-reference Audit")
        < emperors_children.index("## Datasheet component coverage")
        < emperors_children.index("## Cross-source Semantic Equivalence")
    )
    assert "Court of the Phoenician | **Implemented**" in emperors_children
    assert "| Core | 31 | 31 assignments matched |" in emperors_children
    assert "| Faction | 23 | 23 assignments matched |" in emperors_children
    assert "| Datasheet | 35 | 34 assignments matched;" in emperors_children
    assert "`ec-flawless-blades-blissblade-attacks`" in emperors_children
    assert "`ec-tormentors-power-sword-strength`" in emperors_children
    assert "`ec-infractors-power-sword-strength`" in emperors_children
    assert emperors_children.count("| `ec-heldrake-profile` | Heldrake |") == 3
    assert "`ec-heldrake-remove-aircraft`" in emperors_children
    assert "`ec-chaos-land-raider-frame`" in emperors_children
    assert "`ec-chaos-rhino-frame`" in emperors_children
    assert "https://39k.pro/faction/uyQevAixq5I" in emperors_children
    assert emperors_children.count("https://39k.pro/datasheet/") == 23
    assert "emperors_children_2026_07_31.audit.json" in emperors_children
    assert "e114f25710a8fbc2089ca2bf02fe578cb5d7ed541f1671ee8c1a6405e124ac8a" in (emperors_children)
    assert "100 have observed provider relationships" in emperors_children
    assert "http://39k.pro" not in emperors_children
    assert "### Unit Datasheet Source Treatments" not in emperors_children
    assert "### Datasheet Ability Details" not in emperors_children
    support_markdown = emperors_children.split("## Datasheet component coverage", 1)[1]
    assert "### Emperor's Children" in support_markdown
    assert "### Vehicles and Daemon Engines" in support_markdown
    assert "### Slaanesh Daemons" in support_markdown
    expected_header = (
        "| Datasheet | Source basis | IR coverage | Supported semantics | "
        "IR semantics still needed | Bridge / catalog blockers |"
    )
    assert support_markdown.count(expected_header) == 3
    review = faction_pack_datasheet_review("emperors-children")
    assert len(review.rows) == 23
    for row in review.rows:
        assert row.datasheet_id is not None
        assert support_markdown.count(f"| {row.datasheet_name} (`{row.datasheet_id}`) |") == 1
    assert (
        "No Prey Can Evade Advance and Charge re-rolls and Monarch of the Hunt deterministic"
        not in emperors_children
    )
    assert "Both datasheet abilities are engine-consumed" in emperors_children
    assert "Chaos Daemons — Shalaxi Helbane — Monarch of the Hunt" in emperors_children
    assert "Emperor's Children — Shalaxi Helbane — Monarch of the Hunt" in emperors_children
    assert "## Detachment Rule Coverage Rows" not in emperors_children


def test_emperors_children_39k_pro_audit_retains_assignment_level_evidence() -> None:
    audit = emperors_children_thirty_nine_k_pro_audit()

    assert len(audit.datasheets) == 23
    assert len(audit.assignments) == 101
    assert len({row.observed_provider_url for row in audit.datasheets}) == 23
    provider_datasheet_ids_by_source = {
        row.source_datasheet_id: row.observed_provider_url.rsplit("/", 1)[-1]
        for row in audit.datasheets
    }
    assert all(
        row.observed_provider_datasheet_id
        == provider_datasheet_ids_by_source[row.source_datasheet_id]
        for row in audit.assignments
    )
    assert all(
        row.source_datasheet_name.replace("\u2019", "'").casefold()
        == row.observed_provider_name.replace("\u2019", "'").casefold()
        for row in audit.datasheets
    )
    assert audit.ability_category_rows() == (
        ("Core", 31, "31 assignments matched"),
        ("Faction", 23, "23 assignments matched"),
        ("Datasheet", 35, "34 assignments matched; 1 retained provider relationship discrepancy"),
        ("Wargear", 7, "7 assignments matched"),
        ("Daemon Primarch choice", 3, "3 assignments matched"),
        ("Datasheet sidebar rule", 2, "2 assignments matched"),
    )
    assert tuple(
        (row.source_assignment_id, row.source_assignment_name, row.match_status)
        for row in audit.assignment_discrepancies
    ) == (("000004077:6", "Serpentine", "provider_definition_unassigned"),)
    qualified_assignments = {
        row.source_assignment_id: (
            row.source_assignment_name,
            row.source_qualifiers,
            row.observed_provider_qualifiers,
        )
        for row in audit.assignments
        if row.source_qualifiers
    }
    assert qualified_assignments == {
        "000004077:9": ("Enthralling Hypnosis (Aura)", ("Aura",), ("Aura",)),
        "000004085:3": ("Warped Interference (Psychic)", ("Psychic",), ("Psychic",)),
        "000004085:4": ("Wracking Agonies (Psychic)", ("Psychic",), ("Psychic",)),
        "000004086:4": ("Excessive Vigour (Aura)", ("Aura",), ("Aura",)),
        "000004097:4": ("Daemon Lord of Slaanesh (Aura)", ("Aura",), ("Aura",)),
    }
    assert len(audit.datasheet_deltas) == 12
    assert all(row.evidence_sha256 for row in audit.datasheet_deltas)
    assert all(
        row.observed_provider_datasheet_id in provider_datasheet_ids_by_source.values()
        for row in audit.datasheet_deltas
    )


def test_aeldari_39k_pro_audit_retains_current_exact_inventory() -> None:
    audit = aeldari_thirty_nine_k_pro_audit()

    assert len(audit.detachments) == 15
    assert audit.enhancement_count == 52
    assert audit.stratagem_count == 78
    assert audit.in_scope_datasheet_count == 70
    assert audit.exact_ability_count == audit.matched_exact_ability_count == 145
    assert len({row.provider_url for row in audit.detachments}) == 15
    assert {row.detachment_id for row in audit.detachments} >= {
        "fateful-performance",
        "serpents-brood",
        "twilight-flickers",
    }


def test_aeldari_39k_pro_audit_rejects_duplicate_detachment_urls(tmp_path: Path) -> None:
    payload = json.loads(AELDARI_AUDIT_PATH.read_text(encoding="utf-8"))
    payload["detachments"][1]["provider_url"] = payload["detachments"][0]["provider_url"]
    tampered_path = tmp_path / "duplicate-url-audit.json"
    tampered_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="detachment URLs must be unique"):
        load_aeldari_thirty_nine_k_pro_audit(tampered_path)


def test_aeldari_39k_pro_audit_rejects_official_source_hash_drift(tmp_path: Path) -> None:
    payload = json.loads(AELDARI_AUDIT_PATH.read_text(encoding="utf-8"))
    payload["official_source"]["pdf_sha256"] = "0" * 64
    tampered_path = tmp_path / "stale-official-hash-audit.json"
    tampered_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="official PDF hash is stale"):
        load_aeldari_thirty_nine_k_pro_audit(tampered_path)


def test_emperors_children_39k_pro_audit_rejects_swapped_provider_urls(tmp_path: Path) -> None:
    payload = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    first = payload["datasheets"][0]
    second = payload["datasheets"][1]
    first["observed_provider_url"], second["observed_provider_url"] = (
        second["observed_provider_url"],
        first["observed_provider_url"],
    )
    tampered_path = tmp_path / "tampered-audit.json"
    tampered_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="datasheet evidence hash drifted"):
        load_emperors_children_thirty_nine_k_pro_audit(tampered_path)


def test_emperors_children_39k_pro_audit_rejects_cross_datasheet_assignment_evidence(
    tmp_path: Path,
) -> None:
    payload = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    fulgrim_deep_strike = next(
        row for row in payload["assignments"] if row["source_assignment_id"] == "000004077:2"
    )
    terminator_deep_strike = next(
        row for row in payload["assignments"] if row["source_assignment_id"] == "000004081:1"
    )
    provider_evidence_fields = (
        "observed_provider_datasheet_id",
        "observed_provider_surface",
        "observed_provider_assignment_id",
        "observed_provider_definition_id",
        "observed_provider_name",
        "observed_provider_qualifiers",
        "evidence_sha256",
    )
    for field in provider_evidence_fields:
        fulgrim_deep_strike[field], terminator_deep_strike[field] = (
            terminator_deep_strike[field],
            fulgrim_deep_strike[field],
        )
    tampered_path = tmp_path / "cross-datasheet-assignment-audit.json"
    tampered_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="Provider parent datasheet mismatched"):
        load_emperors_children_thirty_nine_k_pro_audit(tampered_path)


def test_emperors_children_39k_pro_audit_rejects_unhashed_delta_record_change(
    tmp_path: Path,
) -> None:
    payload = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    heldrake_movement = next(
        row
        for row in payload["datasheet_deltas"]
        if row["source_operation_id"] == "ec-heldrake-profile" and row["field"] == "M"
    )
    heldrake_movement["observed_provider_record_id"] = "mv-ZCUK3B6I"
    tampered_path = tmp_path / "changed-delta-record-audit.json"
    tampered_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="delta evidence hash drifted"):
        load_emperors_children_thirty_nine_k_pro_audit(tampered_path)


def test_emperors_children_39k_pro_audit_rejects_cross_datasheet_delta_evidence(
    tmp_path: Path,
) -> None:
    payload = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    tormentor_power_sword = next(
        row
        for row in payload["datasheet_deltas"]
        if row["source_operation_id"] == "ec-tormentors-power-sword-strength"
    )
    infractor_power_sword = next(
        row
        for row in payload["datasheet_deltas"]
        if row["source_operation_id"] == "ec-infractors-power-sword-strength"
    )
    provider_evidence_fields = (
        "observed_provider_record_kind",
        "observed_provider_record_id",
        "observed_provider_datasheet_id",
        "observed_provider_value",
        "evidence_sha256",
    )
    for field in provider_evidence_fields:
        tormentor_power_sword[field], infractor_power_sword[field] = (
            infractor_power_sword[field],
            tormentor_power_sword[field],
        )
    tampered_path = tmp_path / "cross-datasheet-delta-audit.json"
    tampered_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="Provider parent datasheet mismatched"):
        load_emperors_children_thirty_nine_k_pro_audit(tampered_path)


def test_support_renderer_escapes_tables_and_renders_empty_cells() -> None:
    assert _markdown_text("Alpha | Beta") == "Alpha \\| Beta"
    assert _inline_code_list(()) == "None"
    assert _ability_datasheet_pairs_text([]) == "None"
