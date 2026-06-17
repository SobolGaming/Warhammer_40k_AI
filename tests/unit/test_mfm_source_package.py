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
    parse_model_count_label,
    parse_points_label,
    unit_cost_bracket_bounds,
    unit_cost_row_label_details,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.mfm_2026_06 import (
    source_package,
)


def test_mfm_source_package_excludes_unsupported_factions_and_sections() -> None:
    package = source_package()

    assert len(package.factions) == 28
    assert "chaos-titan-legions" not in {faction.faction_id for faction in package.factions}
    assert "titan-legions" not in {faction.faction_id for faction in package.factions}

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


def test_mfm_source_package_preserves_world_eaters_defiler_special_pricing() -> None:
    defiler = source_package().faction_by_id("world-eaters").unit_by_id("units-defiler")

    assert [
        (bracket.label, [(row.label, row.points) for row in bracket.rows])
        for bracket in defiler.cost_brackets
    ] == [
        ("YOUR 1ST UNIT COSTS", [("1 model", 270)]),
        ("YOUR 2ND + UNIT COSTS", [("1 model", 300)]),
    ]
    assert [(cost.name, cost.points_per_item) for cost in defiler.wargear_costs] == [
        ("Hades lascannon", 10),
        ("Heavy reaper autocannon", 10),
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
        [("5 models", 100), ("10 models", 200)],
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
        <div id="S:0">270 pts</div>
        <div id="S:1">LEADER</div>
        <div>
          <h3>DETACHMENTS</h3>
          <div class="flex flex-col space-y-1 m-1">
            <div class="flex flex-row justify-between px-1 py-0.5 text-white">
              <span>Test Detachment</span><span>3DP</span>
            </div>
            <div>PURGE THE FOE</div>
            <div class="space-y-1">
              <div>ENHANCEMENTS</div>
              <ul>
                <div>
                  <li>
                    <div><span>Test Enhancement</span><span>15 pts</span></div>
                    <div><span>LEADER:</span><span>Eightbound</span></div>
                  </li>
                </div>
              </ul>
            </div>
          </div>
          <h3>UNITS</h3>
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
