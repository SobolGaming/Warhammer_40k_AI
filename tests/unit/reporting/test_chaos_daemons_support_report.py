from __future__ import annotations

from tools.generate_ability_support_matrix import (
    ability_support_matrix_rows,
    datasheet_support_rows,
    faction_support_markdown_files,
    leader_attachment_consumer_evidence_datasheet_ids,
    mustering_support_rows,
)

from warhammer40k_core.engine import army_mustering
from warhammer40k_core.engine.ability_coverage import (
    CORE_STEALTH_RUNTIME_CONSUMER_ID,
    SUPREME_COMMANDER_MUSTERING_CONSUMER_ID,
    AbilityCoverageSupportStage,
)

_CHAOS_DAEMONS_LEADER_DATASHEET_IDS = {
    "000001104",
    "000001106",
    "000001126",
    "000001129",
    "000001138",
    "000001455",
    "000001456",
    "000001462",
    "000001463",
    "000001464",
    "000001466",
    "000001467",
    "000001468",
    "000001469",
    "000001589",
    "000001647",
    "000001649",
    "000004100",
}


def test_chaos_daemons_report_preserves_faction_sections_and_attachment_evidence() -> None:
    markdown = faction_support_markdown_files()["chaos-daemons.md"]

    for allegiance in ("Khorne", "Tzeentch", "Nurgle", "Slaanesh", "Undivided"):
        assert f"### {allegiance}" in markdown
    assert "## Semantic Support Snapshot" in markdown
    assert "## Datasheet / Unit Support" in markdown
    assert "Leader row consumer evidence" not in markdown

    leader_evidence_ids = leader_attachment_consumer_evidence_datasheet_ids()
    assert leader_evidence_ids >= _CHAOS_DAEMONS_LEADER_DATASHEET_IDS
    assert markdown.count(
        "Source-backed Leader attachment targets are consumed by generic army mustering."
    ) == len(_CHAOS_DAEMONS_LEADER_DATASHEET_IDS)

    attachment_row = next(
        row
        for row in mustering_support_rows()
        if row.rule_id == army_mustering.ATTACHMENT_DECLARATION_MUSTERING_CONSUMER_ID
    )
    assert attachment_row.support_stage == "full"
    assert attachment_row.source_id == army_mustering.ATTACHMENT_ELIGIBILITY_SOURCE_ID


def test_chaos_daemons_report_support_rows_retain_exact_runtime_evidence() -> None:
    ability_rows = ability_support_matrix_rows()
    support_by_datasheet_id = {row.datasheet_id: row for row in datasheet_support_rows()}

    for datasheet_id in ("000001112", "000001114", "000001115", "000001148"):
        row = support_by_datasheet_id[datasheet_id]
        assert row.overall == "Playable"
        assert row.datasheet_ability_status == "Full"

    belakor_rows = {
        row.ability_name: row
        for row in ability_rows
        if row.datasheet_id == "000001148" and row.ability_name in {"Stealth", "SUPREME COMMANDER"}
    }
    assert belakor_rows["Stealth"].support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
    assert belakor_rows["Stealth"].runtime_consumer_ids == (CORE_STEALTH_RUNTIME_CONSUMER_ID,)
    assert belakor_rows["SUPREME COMMANDER"].support_stage is (
        AbilityCoverageSupportStage.ENGINE_CONSUMED
    )
    assert belakor_rows["SUPREME COMMANDER"].runtime_consumer_ids == (
        SUPREME_COMMANDER_MUSTERING_CONSUMER_ID,
    )
