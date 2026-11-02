from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from tools.ability_support_sources import ability_support_index_inputs, load_source_artifacts
from tools.aeldari_datasheet_semantic_coverage import SOURCE_JSON_DIR
from tools.build_faction_source_governance import validate_official_artifacts
from tools.generate_ability_support_matrix import ABILITY_SUPPORT_DATASHEET_IDS
from tools.generate_aeldari_banshee_eldrad_source import generated_overlay_pack

from warhammer40k_core.rules.source_overlay import apply_source_release_overlays
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    aeldari_banshee_eldrad_2026_11 as current,
)
from warhammer40k_core.rules.wahapedia_invulnerable_save_bridge import (
    conditional_invulnerable_save_bridge_for_model_row,
)
from warhammer40k_core.rules.wahapedia_model_profile_mapping import (
    conditional_invulnerable_save_for_model_rows,
)
from warhammer40k_core.rules.wahapedia_schema import WahapediaJsonArtifact

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def original_sources() -> tuple[WahapediaJsonArtifact, ...]:
    return load_source_artifacts(SOURCE_JSON_DIR)


def test_bounded_f00_capture_authority_and_generator() -> None:
    assert len(ABILITY_SUPPORT_DATASHEET_IDS) == 60
    assert not {"000000584", "000000589", "000000590"} & set(ABILITY_SUPPORT_DATASHEET_IDS)
    audit = current.source_audit()
    assert set(audit.selected_source_ids) == {
        "faction-app:aeldari:datasheet:howling-banshees",
        "faction-app:aeldari:datasheet:eldrad-ulthran",
    }
    source = ROOT / "data/source_audits/aeldari_banshee_eldrad_2026_11"
    assert (source / "source.audit.json").read_bytes() == Path(current.__file__).with_name(
        current.AUDIT_ARTIFACT_NAME
    ).read_bytes()
    captures = json.loads((source / "browser-captures.json").read_bytes())
    for row in audit.observations:
        slug = row.source_url.rsplit("/", 1)[1]
        assert row.captured_text == captures[slug]["captured_text"]
    validate_official_artifacts(audit)
    package = current.source_package()
    assert all(
        record.semantic_execution_status == "not_certified"
        for record in package.source_evidence_catalog.records
    )
    assert generated_overlay_pack().to_payload() == current.overlay_pack().to_payload()
    inputs = set(ability_support_index_inputs(SOURCE_JSON_DIR))
    assert Path(current.__file__).with_name(current.AUDIT_ARTIFACT_NAME) in inputs
    assert Path(current.__file__).with_name(current.ARTIFACT_NAME) in inputs


def test_only_obsolete_eldrad_edge_is_superseded(
    original_sources: tuple[WahapediaJsonArtifact, ...],
) -> None:
    before = original_sources
    after = apply_source_release_overlays(
        source_artifacts=before,
        release_manifest=current.source_release_manifest(),
        overlay_packs=(current.overlay_pack(),),
    )
    changes: list[tuple[str, str]] = []
    for left, right in zip(before, after, strict=True):
        assert left.source_table == right.source_table
        assert len(left.rows) == len(right.rows)
        for old, new in zip(left.rows, right.rows, strict=True):
            if old != new:
                changes.append((old.source_table, old.source_row_id))
                fields = new.runtime_fields_payload()
                for key in (
                    "core_v2_superseded_by",
                    "core_v2_superseded_reason",
                    "core_v2_superseded_source_reference",
                ):
                    assert fields.pop(key)
                assert fields == old.runtime_fields_payload()
            else:
                assert old.to_payload() == new.to_payload()
    assert changes == [("Datasheets_leader", "000000568:000000584:108")]
    leaders = next(a for a in after if a.source_table == "Datasheets_leader")
    active = [
        r.runtime_fields_payload()
        for r in leaders.rows
        if r.runtime_fields_payload().get("leader_id") == "000000568"
        and not r.runtime_fields_payload().get("core_v2_superseded_by")
    ]
    assert {r["attached_id"] for r in active} == {"000000589", "000000590"}


def test_shared_bridge_merges_only_homogeneous_all_model_rows(
    original_sources: tuple[WahapediaJsonArtifact, ...],
) -> None:
    table = next(a for a in original_sources if a.source_table == "Datasheets_models")
    rows = tuple(
        r for r in table.rows if r.runtime_fields_payload().get("datasheet_id") == "000000594"
    )
    # Historical raw model descriptions already agree with the current complete page.
    assert len(rows) == 2
    bridge = conditional_invulnerable_save_for_model_rows(
        datasheet_id="000000594", model_source_rows=rows, error_type=ValueError
    )
    assert bridge is not None
    assert bridge.base_invulnerable_save == "5"
    assert bridge.source_ids == tuple(r.stable_source_id() for r in rows)
    assert bridge.rule_ir.clauses[0].effects[0].parameters[-1].value == 4
    for description in ("", "This invulnerable save is improved to 3+ against melee attacks."):
        altered = replace(
            rows[1],
            fields=tuple((k, description if k == "inv_sv_descr" else v) for k, v in rows[1].fields),
        )
        with pytest.raises(ValueError, match="differing profiles"):
            conditional_invulnerable_save_for_model_rows(
                datasheet_id="000000594",
                model_source_rows=(rows[0], altered),
                error_type=ValueError,
            )


@pytest.mark.parametrize(
    "description",
    [
        "This invulnerable save is improved to 5+ against melee attacks.",
        "This invulnerable save is improved to 6+ against melee attacks.",
    ],
)
def test_conditional_improvement_must_be_better(
    original_sources: tuple[WahapediaJsonArtifact, ...], description: str
) -> None:
    table = next(a for a in original_sources if a.source_table == "Datasheets_models")
    row = next(r for r in table.rows if r.source_row_id == "000000594:1")
    altered = replace(
        row, fields=tuple((k, description if k == "inv_sv_descr" else v) for k, v in row.fields)
    )
    with pytest.raises(ValueError, match="better than its base"):
        conditional_invulnerable_save_bridge_for_model_row(
            datasheet_id="000000594", model_source_row=altered
        )
