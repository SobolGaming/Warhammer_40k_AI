from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, TypedDict

if TYPE_CHECKING or __package__:
    from tools.faction_pack_datasheet_review import (
        FactionPackDatasheetReview,
        FactionPackDatasheetReviewRow,
        faction_pack_datasheet_reviews,
    )
else:
    from faction_pack_datasheet_review import (
        FactionPackDatasheetReview,
        FactionPackDatasheetReviewRow,
        faction_pack_datasheet_reviews,
    )

from warhammer40k_core.engine.semantic_equivalence import (
    CrossSourceSemanticAudit,
    SemanticContentKind,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import mfm_2026_07

SCHEMA_VERSION = "maulerfiend-cross-faction-support-v2"
FAMILY_ID = "warhammer_40000_11th:datasheet-family:maulerfiend"

_EXPECTED_VARIANT_RULE_NAMES = {
    ("chaos-space-marines", "000000968"): ("Siege Crawler",),
    ("emperors-children", "000004091"): ("Glutton for Punishment",),
    ("thousand-sons", "000001029"): ("Snarling Protector",),
    ("world-eaters", "000002639"): ("Savage Exaltation", "The Scent of Blood"),
}
_DEATH_GUARD_FACTION_ID = "death-guard"
_EXPECTED_CURRENT_POINTS = {
    ("chaos-space-marines", "000000968"): ((1, None, 1, 130),),
    ("emperors-children", "000004091"): ((1, 2, 1, 120), (3, None, 1, 130)),
    ("thousand-sons", "000001029"): ((1, 2, 1, 120), (3, None, 1, 130)),
    ("world-eaters", "000002639"): ((1, 2, 1, 140), (3, None, 1, 150)),
}


@dataclass(frozen=True, slots=True)
class _GenericMechanic:
    mechanic_id: str
    scope: str
    evidence: tuple[str, ...]
    certification_limit: str


_GENERIC_MECHANICS = (
    _GenericMechanic(
        mechanic_id="counted-wargear-replacement",
        scope="content_neutral_engine_mechanic",
        evidence=(
            "src/warhammer40k_core/rules/wahapedia_bridge.py:_bridge_single_replacement_option",
            "src/warhammer40k_core/engine/unit_factory.py:_apply_replace_wargear_effect_to_models",
            "tests/unit/test_phase17a_wahapedia_source_mirror.py:"
            "test_phase17a_maulerfiend_counted_replacement_is_generic_across_source_variants",
        ),
        certification_limit=(
            "The parser and unit factory preserve the counted replacement for all four exact "
            "current-source variants; that reuse does not certify their faction-local rules "
            "bundles."
        ),
    ),
    _GenericMechanic(
        mechanic_id="deterministic-weapon-copy-identity",
        scope="content_neutral_engine_mechanic",
        evidence=(
            "src/warhammer40k_core/engine/weapon_instances.py:equipped_weapon_instances_for_model",
            "src/warhammer40k_core/engine/weapon_instances.py:weapon_instance_id_for_copy",
            "tests/unit/test_phase17a_wahapedia_source_mirror.py:"
            "test_phase17a_maulerfiend_counted_replacement_is_generic_across_source_variants",
        ),
        certification_limit=(
            "Both equipped copies receive stable identities for all four exact current-source "
            "variants; identity support alone does not certify faction-local ability execution."
        ),
    ),
    _GenericMechanic(
        mechanic_id="shooting-weapon-copy-contract",
        scope="content_neutral_adapter_and_replay_mechanic",
        evidence=(
            "tests/unit/test_phase17_emperors_children_datasheet_overlay.py:"
            "test_maulerfiend_magma_cutter_copies_resolve_independently_and_replay",
            "tests/unit/test_phase17_emperors_children_datasheet_overlay.py:"
            "test_maulerfiend_magma_cutter_copies_can_split_legal_targets",
        ),
        certification_limit=(
            "The shared request, declaration, attack-pool, decision-record, and replay "
            "contract is exercised against all four exact current Maulerfiend datasheet IDs, "
            "including same-target declarations, split targets, and duplicate-copy rejection."
        ),
    ),
)


class DatasheetSupportEvidence(Protocol):
    @property
    def faction_id(self) -> str: ...

    @property
    def datasheet_id(self) -> str: ...

    @property
    def overall(self) -> str: ...

    @property
    def catalog_status(self) -> str: ...

    @property
    def model_geometry_status(self) -> str: ...

    @property
    def wargear_status(self) -> str: ...

    @property
    def weapon_keyword_status(self) -> str: ...

    @property
    def datasheet_ability_status(self) -> str: ...

    @property
    def faction_interaction_status(self) -> str: ...

    @property
    def tests_evidence(self) -> str: ...


class GenericMechanicPayload(TypedDict):
    mechanic_id: str
    scope: str
    evidence: list[str]
    certification_limit: str


class FactionLocalRulePayload(TypedDict):
    rule_name: str
    execution_status: str
    support_transfer: str
    runtime_consumer_ids: list[str]
    source_row_ids: list[str]


class ComponentSupportPayload(TypedDict):
    overall: str
    catalog_status: str
    model_geometry_status: str
    wargear_status: str
    weapon_keyword_status: str
    datasheet_ability_status: str
    faction_interaction_status: str
    tests_evidence: str


class CurrentPointsBracketPayload(TypedDict):
    unit_number_min: int
    unit_number_max: int | None
    model_count: int
    points: int
    source_ids: list[str]


class CurrentPointsPayload(TypedDict):
    source_package_id: str
    source_payload_checksum_sha256: str
    faction_id: str
    datasheet_id: str
    mfm_unit_id: str
    brackets: list[CurrentPointsBracketPayload]


class MaulerfiendVariantPayload(TypedDict):
    key: str
    faction_id: str
    faction_name: str
    datasheet_id: str
    datasheet_name: str
    source_treatment: str
    source_reference: str | None
    identity_scope: str
    reusable_generic_mechanic_ids: list[str]
    component_support: ComponentSupportPayload | None
    current_points: CurrentPointsPayload
    faction_local_rules: list[FactionLocalRulePayload]
    support_conclusion: str


class AbsentFactionPayload(TypedDict):
    faction_id: str
    faction_name: str
    status: str
    evidence: str


class MaulerfiendCrossFactionSupportPayload(TypedDict):
    schema_version: str
    family_id: str
    family_name: str
    identity_policy: str
    generic_mechanics: list[GenericMechanicPayload]
    rows: list[MaulerfiendVariantPayload]
    absent_factions: list[AbsentFactionPayload]


def maulerfiend_cross_faction_support(
    *,
    datasheet_support_rows: Iterable[DatasheetSupportEvidence],
    semantic_audit: CrossSourceSemanticAudit,
) -> MaulerfiendCrossFactionSupportPayload:
    if type(semantic_audit) is not CrossSourceSemanticAudit:
        raise ValueError("Maulerfiend support evidence requires a typed semantic audit.")

    reviewed_variants: dict[
        tuple[str, str],
        tuple[FactionPackDatasheetReview, FactionPackDatasheetReviewRow],
    ] = {}
    review_by_faction_id = {
        review.faction_id: review for review in faction_pack_datasheet_reviews()
    }
    for review in review_by_faction_id.values():
        for review_row in review.rows:
            if review_row.datasheet_name != "Maulerfiend":
                continue
            if review_row.datasheet_id is None:
                raise ValueError("Maulerfiend review rows must have a source datasheet ID.")
            key = (review.faction_id, review_row.datasheet_id)
            if key in reviewed_variants:
                raise ValueError("Maulerfiend review keys must be unique.")
            reviewed_variants[key] = (review, review_row)
    if set(reviewed_variants) != set(_EXPECTED_VARIANT_RULE_NAMES):
        raise ValueError("Maulerfiend current-source faction variants drifted.")

    expected_mfm_faction_ids = {
        faction_id for faction_id, _datasheet_id in _EXPECTED_VARIANT_RULE_NAMES
    }
    current_mfm_faction_ids = {
        faction_id
        for faction_id in mfm_2026_07.supported_faction_ids()
        if any(
            unit.source_section_id == "units" and unit.name.casefold() == "maulerfiend"
            for unit in mfm_2026_07.faction_record(faction_id).units
        )
    }
    if current_mfm_faction_ids != expected_mfm_faction_ids:
        raise ValueError("Maulerfiend current MFM faction inventory drifted.")

    death_guard_review = review_by_faction_id.get(_DEATH_GUARD_FACTION_ID)
    if death_guard_review is None:
        raise ValueError("Maulerfiend support evidence requires the Death Guard review.")
    if any(row.datasheet_name == "Maulerfiend" for row in death_guard_review.rows):
        raise ValueError("Death Guard unexpectedly contains a current Maulerfiend review row.")

    support_by_key: dict[tuple[str, str], DatasheetSupportEvidence] = {}
    for support_row in datasheet_support_rows:
        support_key = (support_row.faction_id, support_row.datasheet_id)
        if support_key not in reviewed_variants:
            continue
        if support_key in support_by_key:
            raise ValueError("Maulerfiend component-support keys must be unique.")
        support_by_key[support_key] = support_row

    mechanic_ids = [mechanic.mechanic_id for mechanic in _GENERIC_MECHANICS]
    rows: list[MaulerfiendVariantPayload] = []
    for key in sorted(reviewed_variants):
        review, review_row = reviewed_variants[key]
        datasheet_id = review_row.datasheet_id
        if datasheet_id is None:
            raise ValueError("Maulerfiend review rows must retain their source datasheet ID.")
        semantic_members = tuple(
            sorted(
                (
                    member
                    for member in semantic_audit.members
                    if member.content_kind is SemanticContentKind.DATASHEET_ABILITY
                    and member.faction_id == review.faction_id
                    and member.owner_id == datasheet_id
                ),
                key=lambda member: (member.rule_name.casefold(), member.member_id),
            )
        )
        if (
            tuple(member.rule_name for member in semantic_members)
            != (_EXPECTED_VARIANT_RULE_NAMES[key])
        ):
            raise ValueError("Maulerfiend faction-local source rules drifted.")
        component_row = support_by_key.get(key)
        component_support = (
            None
            if component_row is None
            else ComponentSupportPayload(
                overall=component_row.overall,
                catalog_status=component_row.catalog_status,
                model_geometry_status=component_row.model_geometry_status,
                wargear_status=component_row.wargear_status,
                weapon_keyword_status=component_row.weapon_keyword_status,
                datasheet_ability_status=component_row.datasheet_ability_status,
                faction_interaction_status=component_row.faction_interaction_status,
                tests_evidence=component_row.tests_evidence,
            )
        )
        support_conclusion = (
            (
                f"Exact faction datasheet has {component_row.overall} generated component "
                "evidence; that evidence does not transfer to another datasheet ID."
            )
            if component_row is not None
            else (
                "Source-reviewed exact faction variant is not selected into the generated "
                "catalog support evidence. Generic mechanics alone do not establish its "
                "catalog, geometry, source rules, or faction integration."
            )
        )
        rows.append(
            {
                "key": f"{review.faction_id}:{datasheet_id}",
                "faction_id": review.faction_id,
                "faction_name": review.faction_name,
                "datasheet_id": datasheet_id,
                "datasheet_name": review_row.datasheet_name,
                "source_treatment": review_row.treatment.value,
                "source_reference": review_row.pdf_page_reference,
                "identity_scope": (
                    "Faction-local catalog, profile, ability, RuleIR, geometry-binding, and "
                    "runtime-support identity."
                ),
                "reusable_generic_mechanic_ids": list(mechanic_ids),
                "component_support": component_support,
                "current_points": _current_points_payload(
                    faction_id=review.faction_id,
                    datasheet_id=datasheet_id,
                    datasheet_name=review_row.datasheet_name,
                ),
                "faction_local_rules": [
                    {
                        "rule_name": member.rule_name,
                        "execution_status": member.execution_status.value,
                        "support_transfer": member.support_transfer.value,
                        "runtime_consumer_ids": list(member.runtime_consumer_ids),
                        "source_row_ids": list(member.source_row_ids),
                    }
                    for member in semantic_members
                ],
                "support_conclusion": support_conclusion,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "family_id": FAMILY_ID,
        "family_name": "Maulerfiend",
        "identity_policy": (
            "The shared name and generic engine mechanics do not make these records one "
            "datasheet. Support is keyed by exact faction_id plus datasheet_id; profiles, "
            "source rules, geometry bindings, and faction integration remain faction-local."
        ),
        "generic_mechanics": [
            {
                "mechanic_id": mechanic.mechanic_id,
                "scope": mechanic.scope,
                "evidence": list(mechanic.evidence),
                "certification_limit": mechanic.certification_limit,
            }
            for mechanic in _GENERIC_MECHANICS
        ],
        "rows": rows,
        "absent_factions": [
            {
                "faction_id": death_guard_review.faction_id,
                "faction_name": death_guard_review.faction_name,
                "status": "not_present_in_current_source_review",
                "evidence": (
                    "The exhaustive current Death Guard Faction Pack review and MFM faction "
                    "inventory contain no Maulerfiend row; no synthetic support row is emitted."
                ),
            }
        ],
    }


def maulerfiend_cross_faction_support_markdown(
    payload: MaulerfiendCrossFactionSupportPayload,
    *,
    heading_level: int = 2,
) -> list[str]:
    if payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Unsupported Maulerfiend cross-faction support schema.")
    if type(heading_level) is not int or heading_level not in (2, 3):
        raise ValueError("Maulerfiend cross-faction heading_level must be 2 or 3.")
    section_heading = f"{'#' * heading_level} Maulerfiend Cross-faction Support"
    subsection_heading_prefix = "#" * (heading_level + 1)
    lines = [
        "",
        section_heading,
        "",
        payload["identity_policy"],
        "",
        (
            "The machine-readable report is "
            "`data/generated/ability_coverage/maulerfiend_cross_faction_support.json`."
        ),
        "",
        f"{subsection_heading_prefix} Reusable generic mechanics",
        "",
        "| Mechanic | Scope | Certification limit |",
        "| --- | --- | --- |",
    ]
    for mechanic in payload["generic_mechanics"]:
        lines.append(
            f"| `{mechanic['mechanic_id']}` | `{mechanic['scope']}` | "
            f"{mechanic['certification_limit']} |"
        )
    lines.extend(
        (
            "",
            f"{subsection_heading_prefix} Exact faction variants",
            "",
            (
                "| Faction / exact key | Source treatment | Current MFM points | "
                "Generated component evidence | Faction-local source rules | Conclusion |"
            ),
            "| --- | --- | --- | --- | --- | --- |",
        )
    )
    for row in payload["rows"]:
        component_support = row["component_support"]
        component_label = (
            "Not selected"
            if component_support is None
            else f"`{component_support['overall']}` for this exact ID"
        )
        rules_label = "<br>".join(
            f"{rule['rule_name']} (`{rule['execution_status']}`)"
            for rule in row["faction_local_rules"]
        )
        points_label = "<br>".join(
            _current_points_bracket_label(bracket) for bracket in row["current_points"]["brackets"]
        )
        lines.append(
            f"| {row['faction_name']} / `{row['key']}` | `{row['source_treatment']}` | "
            f"{points_label} | {component_label} | {rules_label} | "
            f"{row['support_conclusion']} |"
        )
    for absent in payload["absent_factions"]:
        lines.extend(("", f"**{absent['faction_name']}:** {absent['evidence']}"))
    return lines


def includes_maulerfiend_faction(
    payload: MaulerfiendCrossFactionSupportPayload, faction_id: str
) -> bool:
    return any(row["faction_id"] == faction_id for row in payload["rows"]) or any(
        row["faction_id"] == faction_id for row in payload["absent_factions"]
    )


def _current_points_payload(
    *,
    faction_id: str,
    datasheet_id: str,
    datasheet_name: str,
) -> CurrentPointsPayload:
    expected = _EXPECTED_CURRENT_POINTS.get((faction_id, datasheet_id))
    if expected is None:
        raise ValueError("Maulerfiend current-points exact identity is unreviewed.")
    faction = mfm_2026_07.faction_record(faction_id)
    matches = tuple(
        unit
        for unit in faction.units
        if unit.name.casefold() == datasheet_name.casefold() and unit.source_section_id == "units"
    )
    if len(matches) != 1:
        raise ValueError("Maulerfiend current MFM faction/name identity drifted.")
    unit = matches[0]
    brackets: list[CurrentPointsBracketPayload] = []
    actual: list[tuple[int, int | None, int, int]] = []
    for bracket in unit.cost_brackets:
        if len(bracket.rows) != 1:
            raise ValueError("Maulerfiend current MFM bracket must have one model-count row.")
        row = bracket.rows[0]
        if row.model_count is None:
            raise ValueError("Maulerfiend current MFM row must carry a model count.")
        actual.append(
            (
                bracket.unit_number_min,
                bracket.unit_number_max,
                row.model_count,
                row.points,
            )
        )
        brackets.append(
            {
                "unit_number_min": bracket.unit_number_min,
                "unit_number_max": bracket.unit_number_max,
                "model_count": row.model_count,
                "points": row.points,
                "source_ids": [bracket.source_id, row.source_id],
            }
        )
    if tuple(actual) != expected:
        raise ValueError("Maulerfiend current MFM points drifted from reviewed values.")
    return {
        "source_package_id": mfm_2026_07.SOURCE_PACKAGE_ID,
        "source_payload_checksum_sha256": (mfm_2026_07.SOURCE_PAYLOAD_CHECKSUM_SHA256),
        "faction_id": faction_id,
        "datasheet_id": datasheet_id,
        "mfm_unit_id": unit.unit_id,
        "brackets": brackets,
    }


def _current_points_bracket_label(bracket: CurrentPointsBracketPayload) -> str:
    maximum = bracket["unit_number_max"]
    if maximum is None:
        unit_range = (
            "all units"
            if bracket["unit_number_min"] == 1
            else f"unit {bracket['unit_number_min']}+"
        )
    elif maximum == bracket["unit_number_min"]:
        unit_range = f"unit {maximum}"
    else:
        unit_range = f"units {bracket['unit_number_min']}-{maximum}"
    return f"{unit_range}: **{bracket['points']} pts** ({bracket['model_count']} model)"
