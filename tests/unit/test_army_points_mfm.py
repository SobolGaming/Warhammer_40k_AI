from dataclasses import replace

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.content_scope import CatalogContentScope
from warhammer40k_core.core.datasheet import (
    AttachmentEligibility,
    AttachmentRole,
    BaseSizeDefinition,
    DatasheetDefinition,
    DatasheetKeywordSet,
    DatasheetWargearOption,
    ModelProfileDefinition,
    UnitCompositionDefinition,
)
from warhammer40k_core.core.detachment import (
    DetachmentDefinition,
    EnhancementDefinition,
)
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset import RulesetId
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.engine.army_mustering import (
    ArmyMusterRequest,
    EnhancementAssignment,
)
from warhammer40k_core.engine.army_points import (
    ArmyPointsError,
    MfmArmyPointCalculation,
    MfmEnhancementPointLine,
    MfmUnitPointLine,
    calculate_mfm_army_points,
    catalog_with_mfm_leader_allowances,
    mfm_roster_unit_point_values,
)
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.rules.mfm_source import (
    MfmDetachmentRecord,
    MfmEnhancementRecord,
    MfmFactionRecord,
    MfmLeaderAllowance,
    MfmSourcePackage,
    MfmUnitCostBracket,
    MfmUnitCostRow,
    MfmUnitRecord,
    MfmWargearCost,
)


def test_calculate_mfm_army_points_handles_variable_add_on_wargear_and_enhancements() -> None:
    catalog = _catalog()
    request = ArmyMusterRequest(
        army_id="army-one",
        player_id="player-one",
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="test-faction",
            detachment_ids=("test-detachment",),
            enhancement_ids=("test-enhancement",),
        ),
        unit_selections=(
            _unit_selection("variable-one", "variable-unit", (("variable-model", 1),)),
            _unit_selection("variable-two", "variable-unit", (("variable-model", 1),)),
            _unit_selection("defiler-one", "defiler", (("defiler", 1),)),
            _unit_selection(
                "outrider-one",
                "outrider-squad",
                (("invader-atv", 1), ("outrider", 3)),
            ),
        ),
        enhancement_assignments=(
            EnhancementAssignment(
                enhancement_id="test-enhancement",
                target_unit_selection_id="variable-one",
                source_id="test:enhancement-assignment",
            ),
        ),
    )

    calculation = calculate_mfm_army_points(
        catalog=catalog,
        request=request,
        source_package=_mfm_package(),
    )

    assert calculation.total_points == 650
    assert [
        (line.unit_selection_id, line.base_points, line.wargear_points, line.total_points)
        for line in calculation.unit_lines
    ] == [
        ("defiler-one", 270, 20, 290),
        ("outrider-one", 125, 0, 125),
        ("variable-one", 100, 0, 100),
        ("variable-two", 120, 0, 120),
    ]
    assert [
        (line.enhancement_id, line.target_unit_selection_id, line.points)
        for line in calculation.enhancement_lines
    ] == [("test-enhancement", "variable-one", 15)]
    assert [
        (point.unit_selection_id, point.points)
        for point in mfm_roster_unit_point_values(
            catalog=catalog,
            request=request,
            source_package=_mfm_package(),
        )
    ] == [
        ("defiler-one", 290),
        ("outrider-one", 125),
        ("variable-one", 100),
        ("variable-two", 120),
    ]


def test_calculate_mfm_army_points_matches_composite_named_model_rows() -> None:
    catalog = _catalog()
    request = ArmyMusterRequest(
        army_id="army-one",
        player_id="player-one",
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="test-faction",
            detachment_ids=("test-detachment",),
            enhancement_ids=(),
        ),
        unit_selections=(
            _unit_selection(
                "headtakers-one",
                "wolf-guard-headtakers",
                (("hunting-wolves", 3), ("wolf-guard-headtakers", 3)),
            ),
        ),
        enhancement_assignments=(),
    )

    calculation = calculate_mfm_army_points(
        catalog=catalog,
        request=request,
        source_package=_mfm_package(),
    )

    assert calculation.total_points == 115
    assert [
        (line.unit_selection_id, line.base_points, line.total_points)
        for line in calculation.unit_lines
    ] == [("headtakers-one", 115, 115)]


def test_calculate_mfm_army_points_maps_section_qualified_records_by_unit_name() -> None:
    catalog = _catalog()
    request = ArmyMusterRequest(
        army_id="army-one",
        player_id="player-one",
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="test-faction",
            detachment_ids=("test-detachment",),
            enhancement_ids=(),
        ),
        unit_selections=(_unit_selection("alias-one", "alias-datasheet", (("alias-unit", 1),)),),
        enhancement_assignments=(),
    )

    calculation = calculate_mfm_army_points(
        catalog=catalog,
        request=request,
        source_package=_mfm_package(),
    )

    assert calculation.total_points == 55
    assert calculation.unit_lines[0].unit_selection_id == "alias-one"


def test_catalog_with_mfm_leader_allowances_replaces_stale_catalog_leader_targets() -> None:
    catalog = _catalog()

    overlay = catalog_with_mfm_leader_allowances(
        catalog=catalog,
        faction_id="test-faction",
        source_package=_mfm_package(),
    )

    leader = overlay.datasheet_by_id("leader")
    leader_eligibilities = tuple(
        eligibility
        for eligibility in leader.attachment_eligibilities
        if eligibility.role is AttachmentRole.LEADER
    )
    assert len(leader_eligibilities) == 1
    assert leader_eligibilities[0].allowed_bodyguard_datasheet_ids == ("bodyguard-b",)
    assert leader_eligibilities[0].source_id == "test-mfm:faction:test-faction:unit:leader:leader"
    assert overlay.datasheet_by_id("foreign-unit") == catalog.datasheet_by_id("foreign-unit")


def test_mfm_army_point_lines_reject_invalid_structured_values() -> None:
    with pytest.raises(ArmyPointsError):
        MfmUnitPointLine(
            unit_selection_id="unit-one",
            datasheet_id="variable-unit",
            mfm_unit_record_id="variable-unit",
            mfm_unit_id="variable-unit",
            unit_number=1,
            model_count=1,
            base_points=10,
            wargear_points=5,
            total_points=10,
            source_ids=("test:source",),
        )

    line = MfmUnitPointLine(
        unit_selection_id="unit-one",
        datasheet_id="variable-unit",
        mfm_unit_record_id="variable-unit",
        mfm_unit_id="variable-unit",
        unit_number=1,
        model_count=1,
        base_points=10,
        wargear_points=5,
        total_points=15,
        source_ids=("test:source",),
    )
    enhancement_line = MfmEnhancementPointLine(
        enhancement_id="test-enhancement",
        target_unit_selection_id="unit-one",
        points=15,
        source_id="test-enhancement",
    )

    with pytest.raises(ArmyPointsError):
        MfmArmyPointCalculation(unit_lines=())
    with pytest.raises(ArmyPointsError):
        MfmArmyPointCalculation(unit_lines=(line, line))
    with pytest.raises(ArmyPointsError):
        MfmArmyPointCalculation(
            unit_lines=(line,),
            enhancement_lines=(enhancement_line, enhancement_line),
        )


def test_calculate_mfm_army_points_rejects_catalog_identity_drift() -> None:
    catalog = _catalog()
    request = ArmyMusterRequest(
        army_id="army-one",
        player_id="player-one",
        catalog_id="different-catalog",
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="test-faction",
            detachment_ids=("test-detachment",),
            enhancement_ids=(),
        ),
        unit_selections=(
            _unit_selection("variable-one", "variable-unit", (("variable-model", 1),)),
        ),
        enhancement_assignments=(),
    )

    with pytest.raises(ArmyPointsError):
        calculate_mfm_army_points(
            catalog=catalog,
            request=request,
            source_package=_mfm_package(),
        )


def test_calculate_mfm_army_points_rejects_missing_enhancement_target() -> None:
    catalog = _catalog()
    request = ArmyMusterRequest(
        army_id="army-one",
        player_id="player-one",
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="test-faction",
            detachment_ids=("test-detachment",),
            enhancement_ids=("test-enhancement",),
        ),
        unit_selections=(
            _unit_selection("variable-one", "variable-unit", (("variable-model", 1),)),
        ),
        enhancement_assignments=(
            EnhancementAssignment(
                enhancement_id="test-enhancement",
                target_unit_selection_id="missing-unit",
                source_id="test:enhancement-assignment",
            ),
        ),
    )

    with pytest.raises(ArmyPointsError):
        calculate_mfm_army_points(
            catalog=catalog,
            request=request,
            source_package=_mfm_package(),
        )


def test_catalog_with_mfm_leader_allowances_rejects_missing_bodyguard_mapping() -> None:
    catalog = _catalog()
    package = _mfm_package()
    faction = package.faction_by_id("test-faction")
    bad_units = tuple(
        replace(
            unit,
            leader_allowance=MfmLeaderAllowance(
                allowed_bodyguard_unit_ids=("missing-bodyguard",),
                allowed_bodyguard_names=("Missing Bodyguard",),
                source_id="test-mfm:faction:test-faction:unit:leader:leader",
            ),
        )
        if unit.unit_id == "leader"
        else unit
        for unit in faction.units
    )
    bad_package = replace(package, factions=(replace(faction, units=bad_units),))

    with pytest.raises(ArmyPointsError):
        catalog_with_mfm_leader_allowances(
            catalog=catalog,
            faction_id="test-faction",
            source_package=bad_package,
        )


def _catalog() -> ArmyCatalog:
    ruleset_id = RulesetId.warhammer_40000_eleventh(version="mfm-test")
    faction = FactionDefinition(
        faction_id="test-faction",
        name="Test Faction",
        faction_keywords=("TEST",),
        source_ids=("test:faction",),
    )
    other_faction = FactionDefinition(
        faction_id="other-faction",
        name="Other Faction",
        faction_keywords=("OTHER",),
        source_ids=("test:other-faction",),
    )
    datasheets = (
        _datasheet(
            datasheet_id="variable-unit",
            name="Variable Unit",
            profiles=(("variable-model", "Variable Unit", 1, 1),),
        ),
        _datasheet(
            datasheet_id="defiler",
            name="Defiler",
            profiles=(("defiler", "Defiler", 1, 1),),
            wargear_options=(
                DatasheetWargearOption(
                    option_id="defiler:hades",
                    model_profile_id="defiler",
                    default_wargear_ids=("hades-lascannon",),
                    allowed_wargear_ids=("hades-lascannon",),
                    min_selections=1,
                    max_selections=1,
                ),
                DatasheetWargearOption(
                    option_id="defiler:reaper",
                    model_profile_id="defiler",
                    default_wargear_ids=("heavy-reaper-autocannon",),
                    allowed_wargear_ids=("heavy-reaper-autocannon",),
                    min_selections=1,
                    max_selections=1,
                ),
            ),
        ),
        _datasheet(
            datasheet_id="outrider-squad",
            name="Outrider Squad",
            profiles=(("invader-atv", "Invader ATV", 1, 1), ("outrider", "Outrider", 3, 3)),
        ),
        _datasheet(
            datasheet_id="wolf-guard-headtakers",
            name="Wolf Guard Headtakers",
            profiles=(
                ("hunting-wolves", "Hunting Wolves", 3, 3),
                ("wolf-guard-headtakers", "Wolf Guard Headtakers", 3, 3),
            ),
        ),
        _datasheet(
            datasheet_id="alias-datasheet",
            name="Alias Unit",
            profiles=(("alias-unit", "Alias Unit", 1, 1),),
        ),
        _datasheet(
            datasheet_id="leader",
            name="Leader",
            profiles=(("leader", "Leader", 1, 1),),
            attachment_eligibilities=(
                AttachmentEligibility(
                    role=AttachmentRole.LEADER,
                    allowed_bodyguard_datasheet_ids=("bodyguard-a",),
                    source_id="stale:leader",
                ),
            ),
        ),
        _datasheet(
            datasheet_id="bodyguard-a",
            name="Bodyguard A",
            profiles=(("bodyguard-a", "Bodyguard A", 1, 1),),
        ),
        _datasheet(
            datasheet_id="bodyguard-b",
            name="Bodyguard B",
            profiles=(("bodyguard-b", "Bodyguard B", 1, 1),),
        ),
        _datasheet(
            datasheet_id="foreign-unit",
            name="Foreign Unit",
            profiles=(("foreign-unit", "Foreign Unit", 1, 1),),
            faction_keywords=("OTHER",),
        ),
    )
    return ArmyCatalog(
        catalog_id="test-catalog",
        ruleset_id=ruleset_id,
        source_package_id="test-catalog-source",
        datasheets=datasheets,
        wargear=(
            Wargear(wargear_id="hades-lascannon", name="Hades lascannon"),
            Wargear(wargear_id="heavy-reaper-autocannon", name="Heavy reaper autocannon"),
        ),
        factions=(faction, other_faction),
        detachments=(
            DetachmentDefinition(
                detachment_id="test-detachment",
                name="Test Detachment",
                faction_id=faction.faction_id,
                detachment_point_cost=3,
                unit_datasheet_ids=tuple(
                    datasheet.datasheet_id
                    for datasheet in datasheets
                    if "TEST" in datasheet.keywords.faction_keywords
                ),
                force_disposition_ids=("test-force",),
                enhancement_ids=("test-enhancement",),
                source_ids=("test:detachment",),
            ),
        ),
        enhancements=(
            EnhancementDefinition(
                enhancement_id="test-enhancement",
                name="Test Enhancement",
                source_id="catalog:test-enhancement",
                content_scope=CatalogContentScope.MATCHED_PLAY,
                points=999,
            ),
        ),
        source_ids=("test:catalog",),
    )


def _datasheet(
    *,
    datasheet_id: str,
    name: str,
    profiles: tuple[tuple[str, str, int, int], ...],
    wargear_options: tuple[DatasheetWargearOption, ...] = (),
    attachment_eligibilities: tuple[AttachmentEligibility, ...] = (),
    faction_keywords: tuple[str, ...] = ("TEST",),
) -> DatasheetDefinition:
    return DatasheetDefinition(
        datasheet_id=datasheet_id,
        name=name,
        content_scope=CatalogContentScope.MATCHED_PLAY,
        keywords=DatasheetKeywordSet(keywords=("INFANTRY",), faction_keywords=faction_keywords),
        model_profiles=tuple(
            ModelProfileDefinition(
                model_profile_id=model_profile_id,
                name=model_name,
                characteristics=_characteristics(),
                base_size=BaseSizeDefinition.circular(32.0),
                source_ids=(f"test:{datasheet_id}:{model_profile_id}",),
            )
            for model_profile_id, model_name, _min_models, _max_models in profiles
        ),
        composition=tuple(
            UnitCompositionDefinition(
                model_profile_id=model_profile_id,
                min_models=min_models,
                max_models=max_models,
            )
            for model_profile_id, _model_name, min_models, max_models in profiles
        ),
        wargear_options=wargear_options,
        attachment_eligibilities=attachment_eligibilities,
        source_ids=(f"test:{datasheet_id}",),
    )


def _unit_selection(
    unit_selection_id: str,
    datasheet_id: str,
    profile_counts: tuple[tuple[str, int], ...],
) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=tuple(
            ModelProfileSelection(model_profile_id=model_profile_id, model_count=count)
            for model_profile_id, count in profile_counts
        ),
    )


def _mfm_package() -> MfmSourcePackage:
    faction = MfmFactionRecord(
        faction_id="test-faction",
        raw_name="Test Faction",
        url_path="/en/test-faction",
        detachments=(
            MfmDetachmentRecord(
                detachment_id="test-detachment",
                raw_name="Test Detachment",
                force_disposition_id="test-force",
                detachment_point_cost=3,
                enhancements=(
                    MfmEnhancementRecord(
                        enhancement_id="test-enhancement",
                        raw_name="Test Enhancement",
                        points=15,
                        is_upgrade=False,
                        source_id="test-mfm:faction:test-faction:detachment:test-detachment:enhancement:test-enhancement",
                    ),
                ),
                source_id="test-mfm:faction:test-faction:detachment:test-detachment",
            ),
        ),
        units=(
            _mfm_unit(
                raw_name="Variable Unit",
                rows_1=(("1 model", 100),),
                rows_2=(("1 model", 120),),
            ),
            _mfm_unit(
                raw_name="Defiler",
                rows_1=(("1 model", 270),),
                wargear_costs=(
                    MfmWargearCost(
                        raw_name="per Hades lascannon",
                        points_per_item=10,
                        source_id="test-mfm:faction:test-faction:unit:defiler:wargear:hades-lascannon",
                    ),
                    MfmWargearCost(
                        raw_name="per Heavy reaper autocannon",
                        points_per_item=10,
                        source_id="test-mfm:faction:test-faction:unit:defiler:wargear:heavy-reaper-autocannon",
                    ),
                    MfmWargearCost(
                        raw_name="per Optional gun",
                        points_per_item=5,
                        source_id="test-mfm:faction:test-faction:unit:defiler:wargear:optional-gun",
                    ),
                ),
            ),
            _mfm_unit(
                raw_name="Outrider Squad",
                rows_1=(("3 models", 80), ("+ 1 Invader ATV", 45)),
            ),
            _mfm_unit(
                raw_name="Wolf Guard Headtakers",
                rows_1=(("3 Wolf Guard Headtakers, 3 Hunting Wolves", 115),),
            ),
            _mfm_unit(
                raw_name="Alias Unit",
                record_id="units-alias-unit",
                rows_1=(("1 model", 55),),
            ),
            _mfm_unit(
                raw_name="Leader",
                rows_1=(("1 model", 50),),
                leader_allowance=MfmLeaderAllowance(
                    allowed_bodyguard_unit_ids=("bodyguard-b",),
                    allowed_bodyguard_names=("Bodyguard B",),
                    source_id="test-mfm:faction:test-faction:unit:leader:leader",
                ),
            ),
            _mfm_unit(raw_name="Bodyguard A", rows_1=(("1 model", 50),)),
            _mfm_unit(raw_name="Bodyguard B", rows_1=(("1 model", 50),)),
        ),
        source_id="test-mfm:faction:test-faction",
    )
    return MfmSourcePackage(
        source_package_id="test-mfm",
        source_title="Test MFM",
        source_version="v1",
        source_date="2026-06-17",
        source_url="https://mfm.warhammer-community.com/en/",
        excluded_faction_ids=(),
        factions=(faction,),
    )


def _mfm_unit(
    *,
    raw_name: str,
    record_id: str | None = None,
    rows_1: tuple[tuple[str, int], ...],
    rows_2: tuple[tuple[str, int], ...] = (),
    wargear_costs: tuple[MfmWargearCost, ...] = (),
    leader_allowance: MfmLeaderAllowance | None = None,
) -> MfmUnitRecord:
    unit_id = raw_name.lower().replace(" ", "-")
    unit_record_id = unit_id if record_id is None else record_id
    brackets: tuple[MfmUnitCostBracket, ...] = (
        MfmUnitCostBracket(
            raw_label="YOUR 1ST UNIT COSTS" if rows_2 else "YOUR UNIT COSTS",
            unit_number_min=1,
            unit_number_max=1 if rows_2 else None,
            rows=tuple(
                MfmUnitCostRow(
                    raw_label=label,
                    points=points,
                    source_id=f"test-mfm:faction:test-faction:unit:{unit_record_id}:cost:1:{index}",
                )
                for index, (label, points) in enumerate(rows_1, start=1)
            ),
            source_id=f"test-mfm:faction:test-faction:unit:{unit_record_id}:cost:1",
        ),
    )
    if rows_2:
        brackets = (
            *brackets,
            MfmUnitCostBracket(
                raw_label="YOUR 2ND + UNIT COSTS",
                unit_number_min=2,
                unit_number_max=None,
                rows=tuple(
                    MfmUnitCostRow(
                        raw_label=label,
                        points=points,
                        source_id=f"test-mfm:faction:test-faction:unit:{unit_record_id}:cost:2:{index}",
                    )
                    for index, (label, points) in enumerate(rows_2, start=1)
                ),
                source_id=f"test-mfm:faction:test-faction:unit:{unit_record_id}:cost:2",
            ),
        )
    return MfmUnitRecord(
        record_id=unit_record_id,
        unit_id=unit_id,
        raw_name=raw_name,
        source_section_id=None,
        source_section_name=None,
        cost_brackets=brackets,
        wargear_costs=wargear_costs,
        leader_allowance=leader_allowance,
        source_id=f"test-mfm:faction:test-faction:unit:{unit_record_id}",
    )


def _characteristics() -> tuple[CharacteristicValue, ...]:
    return (
        CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 3),
        CharacteristicValue.source_dash(Characteristic.INVULNERABLE_SAVE),
        CharacteristicValue.from_raw(Characteristic.LEADERSHIP, 7),
        CharacteristicValue.from_raw(Characteristic.MOVEMENT, 6),
        CharacteristicValue.from_raw(Characteristic.OBJECTIVE_CONTROL, 1),
        CharacteristicValue.from_raw(Characteristic.SAVE, 3),
        CharacteristicValue.from_raw(Characteristic.TOUGHNESS, 4),
        CharacteristicValue.from_raw(Characteristic.WEAPON_SKILL, 3),
        CharacteristicValue.from_raw(Characteristic.WOUNDS, 2),
    )
