import json
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

import pytest

from warhammer40k_core.rules.mfm_source import (
    MfmDetachmentRecord,
    MfmEnhancementRecord,
    MfmFactionRecord,
    MfmIndexFaction,
    MfmLeaderAllowance,
    MfmSourceError,
    MfmSourcePackage,
    MfmUnitCostBracket,
    MfmUnitCostRow,
    MfmUnitRecord,
    MfmWargearCost,
    parse_mfm_faction_html,
    parse_mfm_index_html,
    parse_mfm_version_html,
    parse_model_count_label,
    parse_points_label,
    unit_cost_bracket_bounds,
    unit_cost_row_label_details,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.mfm_2026_07 import (
    SOURCE_PAYLOAD_CHECKSUM_SHA256,
    faction_record,
    source_package,
    supported_faction_ids,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.mfm_2026_07._artifacts import (
    mfm_package_artifact_from_json_bytes,
)

_ROOT = Path(__file__).resolve().parents[2]
_MFM_REVIEW = _ROOT / "data" / "source_manifests" / "mfm_2026_07_review.json"


def test_mfm_source_package_excludes_unsupported_factions_and_sections() -> None:
    package = source_package()

    assert len(package.factions) == 28
    assert len(supported_faction_ids()) == 28
    assert "chaos-titan-legions" not in {faction.faction_id for faction in package.factions}
    assert "titan-legions" not in {faction.faction_id for faction in package.factions}
    assert "chaos-titan-legions" not in set(supported_faction_ids())
    assert "titan-legions" not in set(supported_faction_ids())
    assert package.source_version == "v1.1"
    assert package.source_date == "2026-07-22"

    unsupported_sections = {
        "combat-patrol",
        "crusade",
        "forge-world",
        "forge-worlds",
        "kill-team",
        "legends",
    }
    assert not [
        (faction.faction_id, unit.record_id, unit.source_section_id)
        for faction in package.factions
        for unit in faction.units
        if unit.source_section_id in unsupported_sections
    ]


def test_mfm_source_package_loads_versioned_json_artifacts() -> None:
    package = source_package()
    package_resources = files(
        "warhammer40k_core.rules.source_packages.warhammer_40000_11th.mfm_2026_07"
    )
    faction_artifacts = tuple(
        sorted(
            path.name
            for path in package_resources.joinpath("artifacts", "factions").iterdir()
            if path.name.endswith(".json")
        )
    )

    assert package_resources.joinpath("artifacts", "package.json").is_file()
    assert not package_resources.joinpath("space_marines.py").is_file()
    assert faction_artifacts == tuple(
        f"{faction_id}.json" for faction_id in supported_faction_ids()
    )
    assert package.source_payload_checksum_sha256() == SOURCE_PAYLOAD_CHECKSUM_SHA256


def test_mfm_source_package_covers_detachment_rules_and_both_attachment_roles() -> None:
    package = source_package()

    assert not [
        (faction.faction_id, detachment.detachment_id)
        for faction in package.factions
        for detachment in faction.detachments
        if detachment.detachment_point_cost is None or detachment.force_disposition_id is None
    ]
    assert (
        sum(
            unit.leader_allowance is not None
            for faction in package.factions
            for unit in faction.units
        )
        == 317
    )
    assert (
        sum(
            unit.support_allowance is not None
            for faction in package.factions
            for unit in faction.units
        )
        == 69
    )
    castellan = package.faction_by_id("black-templars").unit_by_id("units-castellan")
    assert castellan.leader_allowance is None
    assert castellan.support_allowance is not None
    assert castellan.support_allowance.allowed_bodyguard_unit_ids == (
        "assault-intercessor-squad",
        "crusader-squad",
        "infernus-squad",
        "intercessor-squad",
        "sternguard-veteran-squad",
        "sword-brethren-squad",
    )


def test_mfm_update_review_covers_every_supported_faction_and_is_current() -> None:
    package = source_package()
    review = json.loads(_MFM_REVIEW.read_text(encoding="utf-8"))

    assert review["current_source_package_id"] == package.source_package_id
    assert (
        review["current_source_payload_checksum_sha256"] == package.source_payload_checksum_sha256()
    )
    assert review["reviewed_faction_ids"] == list(supported_faction_ids())
    assert review["excluded_faction_ids"] == ["chaos-titan-legions", "titan-legions"]
    assert review["summary"]["reviewed_faction_count"] == 28
    assert review["summary"]["changed_faction_count"] == 28
    subprocess.run(
        [sys.executable, "tools/build_mfm_update_review.py", "--check"],
        cwd=_ROOT,
        check=True,
    )


def test_mfm_source_package_artifact_manifest_fails_fast_for_schema_drift() -> None:
    payload: dict[str, object] = {
        "artifact_schema": "stale-schema",
        "source_package_id": "gw-11e-mfm-2026-07",
        "source_title": "Warhammer 40,000: Munitorum Field Manual",
        "source_version": "v1.1",
        "source_date": "2026-07-22",
        "source_url": "https://mfm.warhammer-community.com/en/",
        "excluded_faction_ids": [],
        "faction_artifacts": {"orks": "factions/orks.json"},
        "source_payload_checksum_sha256": "0" * 64,
    }

    with pytest.raises(MfmSourceError, match="schema"):
        mfm_package_artifact_from_json_bytes(json.dumps(payload).encode("utf-8"))


def test_mfm_source_package_preserves_world_eaters_defiler_special_pricing() -> None:
    world_eaters = faction_record("world-eaters")
    assert faction_record("world-eaters") is world_eaters
    defiler = world_eaters.unit_by_id("units-defiler")

    assert [
        (bracket.label, [(row.label, row.points) for row in bracket.rows])
        for bracket in defiler.cost_brackets
    ] == [
        ("YOUR 1ST UNIT COSTS", [("1 model", 270)]),
        ("YOUR 2ND + UNIT COSTS", [("1 model", 310)]),
    ]
    assert [(cost.name, cost.points_per_item) for cost in defiler.wargear_costs] == [
        ("Hades lascannon", 15),
        ("Heavy reaper autocannon", 15),
    ]


def test_mfm_source_package_uses_section_qualified_records_for_duplicate_unit_names() -> None:
    imperial_agents = source_package().faction_by_id("imperial-agents")

    records = imperial_agents.unit_records_by_unit_id("deathwatch-kill-team")

    assert [(record.record_id, record.source_section_id) for record in records] == [
        (
            "every-model-has-the-imperium-keyword-deathwatch-kill-team",
            "every-model-has-the-imperium-keyword",
        ),
        ("units-deathwatch-kill-team", "units"),
    ]
    assert [
        [(row.label, row.points) for bracket in record.cost_brackets for row in bracket.rows]
        for record in records
    ] == [
        [("5 models", 100), ("10 models", 190)],
        [("5 models", 100), ("10 models", 190)],
    ]


def test_mfm_source_package_lookups_are_fail_fast_for_missing_or_ambiguous_ids() -> None:
    package = source_package()
    imperial_agents = package.faction_by_id("imperial-agents")
    world_eaters = package.faction_by_id("world-eaters")

    with pytest.raises(MfmSourceError):
        imperial_agents.unit_by_id("deathwatch-kill-team")
    with pytest.raises(MfmSourceError):
        world_eaters.unit_by_id("missing-unit")
    with pytest.raises(MfmSourceError):
        world_eaters.unit_by_record_id("missing-record")
    with pytest.raises(MfmSourceError):
        world_eaters.enhancement_by_id("missing-enhancement")
    with pytest.raises(MfmSourceError):
        package.faction_by_id("missing-faction")


def test_mfm_unit_cost_row_preserves_composite_named_model_components() -> None:
    row = MfmUnitCostRow(
        raw_label="3 Wolf Guard Headtakers, 3 Hunting Wolves",
        points=115,
        source_id="test:row",
    )

    assert row.model_count == 6
    assert row.model_component_counts == (3, 3)
    assert row.model_component_ids == ("wolf-guard-headtakers", "hunting-wolves")


def test_mfm_unit_cost_helpers_parse_range_open_and_count_labels() -> None:
    assert unit_cost_bracket_bounds("YOUR 1ST TO 2ND UNITS COSTS") == (1, 2)
    assert unit_cost_bracket_bounds("YOUR 3RD + UNIT COSTS") == (3, None)
    assert parse_model_count_label("12 models") == 12
    assert parse_points_label("▼ (-5) 15 pts") == 15
    assert parse_points_label("▲ (+10) 1,005 pts") == 1005


def test_mfm_version_parser_requires_one_explicit_version() -> None:
    assert parse_mfm_version_html("<html><body><h2>v1.1</h2></body></html>") == "v1.1"
    for html in (
        "<html><body><h2>current</h2></body></html>",
        "<html><body><h2>v1.0</h2><h2>v1.1</h2></body></html>",
    ):
        with pytest.raises(MfmSourceError, match="version"):
            parse_mfm_version_html(html)


def test_mfm_unit_cost_helpers_reject_invalid_labels() -> None:
    with pytest.raises(MfmSourceError):
        unit_cost_bracket_bounds("YOUR 2ND TO 1ST UNITS COSTS")
    with pytest.raises(MfmSourceError):
        unit_cost_bracket_bounds("YOUR UNKNOWN UNIT COSTS")
    with pytest.raises(MfmSourceError):
        parse_points_label("free")
    with pytest.raises(MfmSourceError):
        parse_model_count_label("one model")
    with pytest.raises(MfmSourceError):
        unit_cost_row_label_details("not a model row")


def test_mfm_structured_payloads_reject_stale_normalized_fields() -> None:
    row = MfmUnitCostRow(raw_label="1 model", points=10, source_id="test:row")
    row_payload = row.to_payload()
    row_payload["model_count"] = 2
    with pytest.raises(MfmSourceError):
        MfmUnitCostRow.from_payload(row_payload)

    cost = MfmWargearCost(
        raw_name="per Hades lascannon",
        points_per_item=10,
        source_id="test:wargear",
    )
    cost_payload = cost.to_payload()
    cost_payload["wargear_id"] = "stale-wargear"
    with pytest.raises(MfmSourceError):
        MfmWargearCost.from_payload(cost_payload)

    bracket = MfmUnitCostBracket(
        raw_label="YOUR UNIT COSTS",
        unit_number_min=1,
        unit_number_max=None,
        rows=(row,),
        source_id="test:bracket",
    )
    unit = MfmUnitRecord(
        record_id="test-unit",
        unit_id="test-unit",
        raw_name="Test Unit",
        source_section_id=None,
        source_section_name=None,
        cost_brackets=(bracket,),
        source_id="test:unit",
    )
    unit_payload = unit.to_payload()
    unit_payload["name"] = "Stale Unit"
    with pytest.raises(MfmSourceError):
        MfmUnitRecord.from_payload(unit_payload)

    leader = MfmLeaderAllowance(
        allowed_bodyguard_unit_ids=("test-unit",),
        allowed_bodyguard_names=("Test Unit",),
        source_id="test:leader",
    )
    enhancement = MfmEnhancementRecord(
        enhancement_id="test-enhancement",
        raw_name="Test Enhancement (Upgrade)",
        points=15,
        is_upgrade=True,
        leader_allowance=leader,
        source_id="test:enhancement",
    )
    enhancement_payload = enhancement.to_payload()
    enhancement_payload["name"] = "Stale Enhancement"
    with pytest.raises(MfmSourceError):
        MfmEnhancementRecord.from_payload(enhancement_payload)

    detachment = MfmDetachmentRecord(
        detachment_id="test-detachment",
        raw_name="Test Detachment",
        force_disposition_id="test-force",
        detachment_point_cost=3,
        enhancements=(enhancement,),
        source_id="test:detachment",
    )
    detachment_payload = detachment.to_payload()
    detachment_payload["name"] = "Stale Detachment"
    with pytest.raises(MfmSourceError):
        MfmDetachmentRecord.from_payload(detachment_payload)

    faction = MfmFactionRecord(
        faction_id="test-faction",
        raw_name="Test Faction",
        url_path="/en/test-faction",
        detachments=(detachment,),
        units=(unit,),
        source_id="test:faction",
    )
    faction_payload = faction.to_payload()
    faction_payload["name"] = "Stale Faction"
    with pytest.raises(MfmSourceError):
        MfmFactionRecord.from_payload(faction_payload)

    package = MfmSourcePackage(
        source_package_id="test-mfm",
        source_title="Test MFM",
        source_version="v1",
        source_date="2026-06-17",
        source_url="https://mfm.warhammer-community.com/en/",
        excluded_faction_ids=(),
        factions=(faction,),
    )
    package_payload = package.to_payload()
    package_payload["source_payload_checksum_sha256"] = "stale"
    with pytest.raises(MfmSourceError):
        MfmSourcePackage.from_payload(package_payload)


def test_mfm_source_package_payload_round_trips_generated_data() -> None:
    package = source_package()

    reloaded = MfmSourcePackage.from_payload(package.to_payload())

    assert reloaded.source_payload_checksum_sha256() == package.source_payload_checksum_sha256()
    assert reloaded.faction_by_id("world-eaters").unit_by_id("units-defiler").name == "DEFILER"


def test_mfm_parser_reads_index_units_detachments_wargear_and_leader_allowances() -> None:
    factions = parse_mfm_index_html(
        """
        <html><body>
            <a href="/en/world-eaters">World Eaters</a>
            <a href="/en/world-eaters">World Eaters</a>
        </body></html>
        """
    )
    faction = factions[0]

    record = parse_mfm_faction_html(
        html=_sample_faction_html(),
        faction=faction,
        source_package_id="test-mfm",
    )

    assert MfmIndexFaction.from_payload(faction.to_payload()) == faction
    assert record.faction_id == "world-eaters"
    assert record.detachments[0].enhancements[0].points == 15
    assert record.detachments[0].enhancements[0].leader_allowance is not None
    assert record.detachments[0].enhancements[0].leader_allowance.allowed_bodyguard_unit_ids == (
        "eightbound",
    )
    defiler = record.unit_by_id("units-defiler")
    assert defiler.cost_bracket_for_unit_number(1).points_for_model_count(1) == 270
    assert [(cost.name, cost.points_per_item) for cost in defiler.wargear_costs] == [
        ("Hades lascannon", 10)
    ]
    assert defiler.leader_allowance is not None
    assert defiler.leader_allowance.allowed_bodyguard_unit_ids == ("jakhals",)
    template_leader_unit = record.unit_by_id("units-template-leader-unit")
    assert template_leader_unit.leader_allowance is None
    support_unit = record.unit_by_id("units-support-unit")
    assert support_unit.support_allowance is not None
    assert support_unit.support_allowance.allowed_bodyguard_unit_ids == ("jakhals",)
    assert not [unit for unit in record.units if unit.source_section_id == "legends"]


def test_mfm_parser_rejects_malformed_rows_and_streamed_templates() -> None:
    faction = MfmIndexFaction(
        faction_id="world-eaters",
        raw_name="World Eaters",
        url_path="/en/world-eaters",
    )
    for html in (
        "",
        _faction_html_with_unit_section(
            """
            <div class="flex flex-col space-y-1 m-1">
              <div class="px-1 py-0.5 bg-slate-500 font-bold text-xl text-white">
                Missing Costs
              </div>
            </div>
            """
        ),
        _faction_html_with_unit_section(
            """
            <div class="flex flex-col space-y-1 m-1">
              <div class="px-1 py-0.5 bg-slate-500 font-bold text-xl text-white">
                Bad Row
              </div>
              <div class="space-y-1">
                <div>YOUR UNIT COSTS</div>
                <ul><li><span>invalid row</span><span>10 pts</span></li></ul>
              </div>
            </div>
            """
        ),
        _faction_html_with_unit_section(
            """
            <div class="flex flex-col space-y-1 m-1">
              <div class="px-1 py-0.5 bg-slate-500 font-bold text-xl text-white">
                Empty Costs
              </div>
              <div class="space-y-1">
                <div>YOUR UNIT COSTS</div>
                <ul></ul>
              </div>
            </div>
            """
        ),
        _faction_html_with_unit_section(
            """
            <div class="flex flex-col space-y-1 m-1">
              <div class="px-1 py-0.5 bg-slate-500 font-bold text-xl text-white">
                Missing Template
              </div>
              <div class="space-y-1">
                <div>YOUR UNIT COSTS</div>
                <ul><template id="P:99"></template></ul>
              </div>
            </div>
            """
        ),
    ):
        with pytest.raises(MfmSourceError):
            parse_mfm_faction_html(
                html=html,
                faction=faction,
                source_package_id="test-mfm",
            )


def _sample_faction_html() -> str:
    return """
    <html>
      <body>
        <h2>v1.1</h2>
        <div id="S:0">270 pts</div>
        <div id="S:1">LEADER</div>
        <div>
          <h3>DETACHMENTS</h3>
          <div class="flex flex-col space-y-1 m-1">
            <div class="flex flex-row justify-between px-1 py-0.5 text-white">
              <span>Test Detachment</span><span>3DP ▼</span>
            </div>
            <div>PURGE THE FOE</div>
            <div class="space-y-1">
              <div>ENHANCEMENTS</div>
              <ul>
                <div>
                  <li>
                    <div><span>Test Enhancement</span><span>▼ (-5) 15 pts</span></div>
                    <div><span>LEADER:</span><span>Eightbound</span></div>
                  </li>
                </div>
              </ul>
            </div>
          </div>
          <h3>UNITS</h3>
          <div class="flex flex-col space-y-1 m-1">
            <div class="flex flex-row justify-between px-1 py-0.5 bg-red-500 font-bold text-white">
              <span class="text-xl keep-all">DEFILER</span><span>▲</span>
            </div>
            <div class="space-y-1">
              <div>YOUR 1ST UNIT COSTS</div>
              <ul>
                <li><span>1 model</span><template id="P:0"></template></li>
              </ul>
            </div>
            <div class="space-y-1">
              <div>WARGEAR OPTIONS</div>
              <ul>
                <li><span>per Hades lascannon</span><span>10 pts</span></li>
              </ul>
            </div>
          </div>
          <div class="flex flex-col space-y-1 m-1">
            <div class="px-1 py-0.5 bg-slate-500 font-bold text-xl text-white">
              DEFILER
            </div>
            <div class="space-y-1">
              <div>YOUR 1ST UNIT COSTS</div>
              <ul>
                <li><span>1 model</span><template id="P:0"></template></li>
              </ul>
            </div>
            <div class="space-y-1">
              <div>WARGEAR OPTIONS</div>
              <ul>
                <li><span>per Hades lascannon</span><span>10 pts</span></li>
              </ul>
            </div>
            <div class="space-y-1">
              <div><span>LEADER</span></div>
              <span>Jakhals</span>
            </div>
          </div>
          <div class="flex flex-col space-y-1 m-1">
            <div class="px-1 py-0.5 bg-slate-500 font-bold text-xl text-white">
              Template Leader Unit
            </div>
            <div class="space-y-1">
              <div>YOUR UNIT COSTS</div>
              <ul>
                <li><span>1 model</span><span>50 pts</span></li>
              </ul>
            </div>
            <div class="space-y-1">
              <div><span>LEADER</span></div>
              <template id="P:1"></template>
            </div>
          </div>
          <div class="flex flex-col space-y-1 m-1">
            <div class="px-1 py-0.5 bg-slate-500 font-bold text-xl text-white">
              Support Unit
            </div>
            <div class="space-y-1">
              <div>YOUR UNIT COSTS</div>
              <ul>
                <li><span>1 model</span><span>45 pts</span></li>
              </ul>
            </div>
            <div class="space-y-1">
              <div><span>SUPPORT</span></div>
              <span>Jakhals</span>
            </div>
          </div>
          <h3>LEGENDS</h3>
          <div class="flex flex-col space-y-1 m-1">
            <div class="px-1 py-0.5 bg-slate-500 font-bold text-xl text-white">
              Old Unit
            </div>
            <div class="space-y-1">
              <div>YOUR UNIT COSTS</div>
              <ul>
                <li><span>1 model</span><span>10 pts</span></li>
              </ul>
            </div>
          </div>
        </div>
      </body>
    </html>
    """


def _faction_html_with_unit_section(body: str) -> str:
    return f"""
    <html>
      <body>
        <div id="S:0">10 pts</div>
        <div>
          <h3>UNITS</h3>
          {body}
        </div>
      </body>
    </html>
    """
