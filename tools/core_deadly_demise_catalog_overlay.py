"""Reconcile reviewed current Core catalog descriptions."""

from dataclasses import replace
from hashlib import sha256
from typing import Final

from warhammer40k_core.core.datasheet import CatalogAbilitySourceKind
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.source_catalog import SourceArtifactHash
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_abilities_2026_09,
    core_descriptions_2026_11,
    core_fights_first_2026_09,
    core_stealth_2026_09,
)

ABILITY_ID: Final = "000008339"
SOURCE_ID: Final = "gw-11e-core-abilities:core:deadly-demise"
SOURCE_ARTIFACT: Final = SourceArtifactHash(
    artifact_name="core-abilities-2026-09.json",
    artifact_hash="c45ac9d1ea006d32f8fc803940f51f971e934acbd6f09c51ef263c64b7f69c7b",
)
CURRENT_TEXT_SHA256: Final = "a5ca19362fe04090968372fe83f3398cfa1236d52d69a2a87ad6ca555f429ff4"
HISTORICAL_TEXT_SHA256: Final = "77abd1f1b24c3a5190d0232154a41a1f0116c355fc748714fbdc5ed94717e0d0"
REVIEWED_PARAMETERS: Final = {
    "000000599": "D3",
    "000000605": "1",
    "000000611": "D3",
    "000000613": "1",
    "000000968": "D3",
    "000000969": "D6",
    "000001029": "D3",
    "000001030": "D6",
    "000001120": "D6",
    "000001148": "D6",
    "000001149": "D3",
    "000001151": "D3",
    "000002582": "D6",
    "000002639": "D3",
    "000002758": "D3",
    "000004077": "D6",
    "000004086": "D3",
    "000004091": "D3",
    "000004195": "1",
    "000004207": "D6",
    "000004208": "D6",
    "000004209": "D6",
}
_BRIDGE_PREFIXES: Final = {
    "data-package:core-v2:chaos-daemons-bridge-catalog:phase17k-generated": (
        "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated:Datasheets_abilities:"
    ),
    "data-package:core-v2:chaos-daemons-roster:2026-07": (
        "data-package:core-v2:chaos-daemons-roster-bridge:2026-07:Datasheets_abilities:"
    ),
}


def with_current_deadly_demise(package: CanonicalCatalogPackage) -> CanonicalCatalogPackage:
    """Replace the entire stale paragraph/example, preserving structured occurrences."""
    catalog = package.army_catalog
    expected = {
        row.datasheet_id for row in catalog.datasheets if row.datasheet_id in REVIEWED_PARAMETERS
    }
    occurrences = tuple(
        (row.datasheet_id, ability)
        for row in catalog.datasheets
        for ability in row.abilities
        if ability.ability_id == ABILITY_ID
    )
    if not expected and not occurrences:
        return package
    if len(occurrences) != len(expected) or {owner for owner, _ in occurrences} != expected:
        raise ValueError("Deadly Demise reviewed occurrence closure drifted.")
    package_id = package.package_id.stable_identity()
    if package_id not in _BRIDGE_PREFIXES:
        raise ValueError("Deadly Demise current catalog owner is unreviewed.")
    prefix = _BRIDGE_PREFIXES[package_id]
    rule = core_abilities_2026_09.source_rule_record()
    if (
        SOURCE_ARTIFACT.artifact_hash != core_abilities_2026_09.EXPECTED_ARTIFACT_SHA256
        or rule.source_id != SOURCE_ID
        or sha256(rule.source_text.encode()).hexdigest() != CURRENT_TEXT_SHA256
    ):
        raise ValueError("Deadly Demise current Core source pin drifted.")
    if SOURCE_ID in catalog.source_ids or any(
        row.artifact_name == SOURCE_ARTIFACT.artifact_name for row in package.source_artifacts
    ):
        raise ValueError("Deadly Demise current description was already applied.")
    for owner, ability in occurrences:
        if (
            ability.source_id != f"{prefix}{owner}:1"
            or ability.source_kind is not CatalogAbilitySourceKind.CORE
            or ability.parameter_tokens != (REVIEWED_PARAMETERS[owner],)
            or sha256(ability.effect_description.encode()).hexdigest() != HISTORICAL_TEXT_SHA256
        ):
            raise ValueError("Deadly Demise reviewed descriptor input drifted.")
    return replace(
        package,
        army_catalog=replace(
            catalog,
            datasheets=tuple(
                replace(
                    row,
                    abilities=tuple(
                        replace(ability, effect_description=rule.source_text)
                        if ability.ability_id == ABILITY_ID
                        else ability
                        for ability in row.abilities
                    ),
                )
                for row in catalog.datasheets
            ),
            source_ids=tuple(sorted((*catalog.source_ids, SOURCE_ID))),
        ),
        source_artifacts=(*package.source_artifacts, SOURCE_ARTIFACT),
    )


CORE_DESCRIPTION_SOURCE_IDS: Final = {
    "000008336": "gw-11e-core-abilities:core:lone-operative",
    "000008337": "gw-11e-core-stealth:stealth",
    "000008340": "gw-11e-core-fights-first:fights-first",
    "000008344": "gw-11e-core-abilities:core:scouts",
    "000008345": "gw-11e-core-abilities:core:infiltrators",
}
CORE_DESCRIPTION_TEXT_HASHES: Final = {
    "000008336": (
        "58d9823ec43a78082d08752d1ac20aab60cb09094261430d2b6bb2bcbd2247d9",
        "1932185d8939b87c944cf0325c76fde4b6cebe63643b53589764189a6f00078e",
    ),
    "000008337": (
        "e7ddf8793630406990dab49943167e1388e8a06c0025cd8e8275fec372b0bf58",
        "f10c66ca0215b0893d5385bd13b4064640f23182cdaef342715a87e68c8d4f85",
    ),
    "000008340": (
        "97e80636cba0aadc16602107adcd88df5e758e5d94f01ae9d465d9c2cb3f3fbc",
        "35e5bd3db977c70e49dc2ae64913ce55fbd487a8df0333e85636d5e8ff4fb227",
    ),
    "000008344": (
        "b8f6cdaeff891e3219197d8faa8619929416e7c524ed267374d711393b1750f1",
        "e031b0603c0345803a0fbe63f36f5994bd00c62706c45d8e491d1a1e4484fa87",
    ),
    "000008345": (
        "4d9bd8cdaca5d05bc39b437d70f7cb5559e3eaa802cd8a43bb1488ee20009137",
        "a38c1fea40ae417ef57a6a04a9440b0b745c13061ca58409fe4c0bb90f648258",
    ),
}
CORE_DESCRIPTION_OCCURRENCES: Final = {
    ("000000572", "000008340"): (
        "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated:Datasheets_abilities:000000572:1",
        (),
    ),
    ("000000588", "000008337"): (
        "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated:Datasheets_abilities:000000588:1",
        (),
    ),
    ("000000592", "000008337"): (
        "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated:Datasheets_abilities:000000592:2",
        (),
    ),
    ("000000592", "000008345"): (
        "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated:Datasheets_abilities:000000592:1",
        (),
    ),
    ("000000594", "000008340"): (
        "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated:Datasheets_abilities:000000594:1",
        (),
    ),
    ("000000595", "000008337"): (
        "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated:Datasheets_abilities:000000595:3",
        (),
    ),
    ("000000595", "000008344"): (
        "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated:Datasheets_abilities:000000595:2",
        ("7",),
    ),
    ("000000595", "000008345"): (
        "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated:Datasheets_abilities:000000595:1",
        (),
    ),
    ("000000612", "000008344"): (
        "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated:Datasheets_abilities:000000612:1",
        ("9",),
    ),
    ("000001148", "000008337"): (
        "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated:Datasheets_abilities:000001148:3",
        (),
    ),
    ("000002531", "000008344"): (
        "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated:Datasheets_abilities:000002531:1",
        ("7",),
    ),
    ("000002532", "000008344"): (
        "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated:Datasheets_abilities:000002532:1",
        ("7",),
    ),
    ("000002533", "000008337"): (
        "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated:Datasheets_abilities:000002533:2",
        (),
    ),
    ("000002533", "000008344"): (
        "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated:Datasheets_abilities:000002533:1",
        ("9",),
    ),
    ("000002538", "000008336"): (
        "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated:Datasheets_abilities:000002538:2",
        (),
    ),
    ("000002538", "000008337"): (
        "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated:Datasheets_abilities:000002538:3",
        (),
    ),
    ("000002538", "000008340"): (
        "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated:Datasheets_abilities:000002538:1",
        (),
    ),
    ("000004079", "000008345"): (
        "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated:Datasheets_abilities:000004079:1",
        (),
    ),
    ("000004080", "000008344"): (
        "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated:Datasheets_abilities:000004080:1",
        ("6",),
    ),
    ("000004083", "000008336"): (
        "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated:Datasheets_abilities:000004083:3",
        (),
    ),
    ("000004193", "000008344"): (
        "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated:Datasheets_abilities:000004193:2",
        ("7",),
    ),
    ("000004194", "000008344"): (
        "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated:Datasheets_abilities:000004194:2",
        ("7",),
    ),
    ("000004195", "000008344"): (
        "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated:Datasheets_abilities:000004195:2",
        ("7",),
    ),
    ("000004196", "000008344"): (
        "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated:Datasheets_abilities:000004196:2",
        ("7",),
    ),
}

CORE_DESCRIPTION_ARTIFACTS: Final = (
    SourceArtifactHash(
        "core-stealth-2026-09.json",
        "50d05f2f15af7a173b74cbd2e4c601a9ee00f4260bccdb4248aed584c9f9eadb",
    ),
    SourceArtifactHash(
        "core-fights-first-2026-09.json",
        "501db53231ec964f4c60af8dca80b726bca7902ba3618023e7a04919d712593d",
    ),
    SourceArtifactHash(
        "core-descriptions-2026-11.json",
        "8a82ba2800f48d34993ed332cc1a4d11e7eda895ee61bd2af36a51a98a51649e",
    ),
)


def with_current_core_descriptions(package: CanonicalCatalogPackage) -> CanonicalCatalogPackage:
    """Reconcile five reviewed families once, preserving structured runtime fields."""
    catalog = package.army_catalog
    owners = {row.datasheet_id for row in catalog.datasheets}
    expected = {key for key in CORE_DESCRIPTION_OCCURRENCES if key[0] in owners}
    occurrences = tuple(
        (row.datasheet_id, ability)
        for row in catalog.datasheets
        for ability in row.abilities
        if ability.ability_id in CORE_DESCRIPTION_SOURCE_IDS
    )
    if not expected and not occurrences:
        return package
    if (
        len(occurrences) != len(expected)
        or {(owner, ability.ability_id) for owner, ability in occurrences} != expected
    ):
        raise ValueError("Core description reviewed occurrence closure drifted.")
    if package.package_id.stable_identity() != (
        "data-package:core-v2:chaos-daemons-bridge-catalog:phase17k-generated"
    ):
        raise ValueError("Core description catalog owner is unreviewed.")
    rules = {
        **{rule.source_id: rule.source_text for rule in core_stealth_2026_09.source_rules()},
        **{rule.source_id: rule.source_text for rule in core_fights_first_2026_09.source_rules()},
        **{rule.source_id: rule.source_text for rule in core_descriptions_2026_11.source_rules()},
    }
    if tuple(row.artifact_hash for row in CORE_DESCRIPTION_ARTIFACTS) != (
        core_stealth_2026_09.EXPECTED_ARTIFACT_SHA256,
        core_fights_first_2026_09.EXPECTED_ARTIFACT_SHA256,
        core_descriptions_2026_11.EXPECTED_ARTIFACT_SHA256,
    ) or any(
        source not in rules
        or sha256(rules[source].encode()).hexdigest() != CORE_DESCRIPTION_TEXT_HASHES[ability][1]
        for ability, source in CORE_DESCRIPTION_SOURCE_IDS.items()
    ):
        raise ValueError("Core description current source pin drifted.")
    present = {ability.ability_id for _, ability in occurrences}
    sources = {CORE_DESCRIPTION_SOURCE_IDS[ability] for ability in present}
    if "000008344" in present:
        sources.add(core_descriptions_2026_11.SCOUT_MOVE_SOURCE_ID)
    artifacts = tuple(
        row
        for index, row in enumerate(CORE_DESCRIPTION_ARTIFACTS)
        if (index == 0 and "000008337" in present)
        or (index == 1 and "000008340" in present)
        or (index == 2 and bool(present & {"000008336", "000008344", "000008345"}))
    )
    if sources.intersection(catalog.source_ids) or any(
        row.artifact_name in {source.artifact_name for source in artifacts}
        for row in package.source_artifacts
    ):
        raise ValueError("Core description correction was already applied.")
    for owner, ability in occurrences:
        source_id, parameters = CORE_DESCRIPTION_OCCURRENCES[(owner, ability.ability_id)]
        if (
            ability.source_id != source_id
            or ability.source_kind is not CatalogAbilitySourceKind.CORE
            or ability.parameter_tokens != parameters
            or sha256(ability.effect_description.encode()).hexdigest()
            != CORE_DESCRIPTION_TEXT_HASHES[ability.ability_id][0]
        ):
            raise ValueError("Core description reviewed descriptor input drifted.")
    return replace(
        package,
        army_catalog=replace(
            catalog,
            datasheets=tuple(
                replace(
                    row,
                    abilities=tuple(
                        replace(
                            ability,
                            effect_description=rules[
                                CORE_DESCRIPTION_SOURCE_IDS[ability.ability_id]
                            ],
                        )
                        if ability.ability_id in present
                        else ability
                        for ability in row.abilities
                    ),
                )
                for row in catalog.datasheets
            ),
            source_ids=tuple(sorted((*catalog.source_ids, *sources))),
        ),
        source_artifacts=(*package.source_artifacts, *artifacts),
    )
