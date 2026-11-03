"""Authenticated projection for current description deltas and historical controls."""

from __future__ import annotations

import json
from dataclasses import replace
from functools import cache
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from tools.core_deadly_demise_catalog_overlay import (
    CORE_DESCRIPTION_ARTIFACTS,
    CORE_DESCRIPTION_SOURCE_IDS,
)

from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRPayload
from warhammer40k_core.rules.source_catalog import SourceArtifactHash

# This is an authenticated successor projection for old description-only tests,
# not a runtime adapter or permission to erase arbitrary later source changes.
_MANDIBLASTERS_CURRENT_DESCRIPTOR = (
    "de7f25671f28ef4e1e172fa559a6965cd3090321d8d572ede41f7213a546f366"
)
_MANDIBLASTERS_PRIOR_DESCRIPTOR = "5703c37d361330d4eeae3d25d75d05bcd6fc394e24cb9338de96c7ea9ebde19a"
_MANDIBLASTERS_PRIOR_IR = "ab5ab419648b4f1d43fa1d5e993c6a7568e887c1de509579e958a61548945555"
_ABILITY_ARTIFACT_CURRENT = "9845d550d30aa6118d9adc2942ff21d0c03159fd9ab381f6742e7e08d35d26fd"
_ABILITY_ARTIFACT_PRIOR = "0311a59d21bbd08984f40ba3c0f9df1172be131d85777c0647b8cc50cbb186af"


def before_mandiblasters_correction(package: CanonicalCatalogPackage) -> CanonicalCatalogPackage:
    """Project only exact reviewed descriptor and compiled-artifact successors."""
    observed = tuple(
        (row, ability)
        for row in package.army_catalog.datasheets
        for ability in row.abilities
        if ability.ability_id == "000000595:mandiblasters"
    )
    artifacts = tuple(
        a for a in package.source_artifacts if a.artifact_name == "Datasheets_abilities.json"
    )
    if not observed:
        assert all(a.artifact_hash != _ABILITY_ARTIFACT_CURRENT for a in artifacts)
        return package
    assert len(observed) == 1
    owner, ability = observed[0]
    assert owner.datasheet_id == "000000595"
    assert len(artifacts) == 1
    assert artifacts[0].artifact_hash == _ABILITY_ARTIFACT_CURRENT
    assert (
        sha256(
            json.dumps(ability.to_payload(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        == _MANDIBLASTERS_CURRENT_DESCRIPTOR
    )
    assert ability.rule_ir_payload is not None
    rule = RuleIR.from_payload(cast(RuleIRPayload, ability.rule_ir_payload))
    clause = rule.clauses[0]
    effect = clause.effects[0]
    prior_rule = replace(
        rule,
        clauses=(
            replace(
                clause,
                effects=(
                    replace(
                        effect,
                        parameters=tuple(
                            p
                            for p in effect.parameters
                            if p.key not in {"weapon_scope", "requires_charge_move_this_turn"}
                        ),
                    ),
                ),
            ),
        ),
    )
    assert prior_rule.ir_hash() == _MANDIBLASTERS_PRIOR_IR
    prior = replace(ability, rule_ir_payload=cast(Any, prior_rule.to_payload()))
    assert (
        sha256(
            json.dumps(prior.to_payload(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        == _MANDIBLASTERS_PRIOR_DESCRIPTOR
    )
    return replace(
        package,
        army_catalog=replace(
            package.army_catalog,
            datasheets=tuple(
                replace(row, abilities=tuple(prior if a is ability else a for a in row.abilities))
                if row is owner
                else row
                for row in package.army_catalog.datasheets
            ),
        ),
        source_artifacts=tuple(
            replace(a, artifact_hash=_ABILITY_ARTIFACT_PRIOR) if a is artifacts[0] else a
            for a in package.source_artifacts
        ),
    )


@cache
def core_description_audit() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(
            Path(
                "data/source_audits/core_descriptions_2026_11/catalog-description-delta.json"
            ).read_bytes()
        ),
    )


def before_core_description_correction(package: CanonicalCatalogPackage) -> CanonicalCatalogPackage:
    """Authenticate complete current payload while projecting only the approved delta."""
    package = before_mandiblasters_correction(package)
    audit = core_description_audit()
    surface = next(
        row for row in audit["surfaces"] if row["catalog_id"] == package.army_catalog.catalog_id
    )
    if surface["surface"] == "daemons5":
        assert package.package_hash() == surface["package_hash"]
        return package
    occurrences = {(row["datasheet_id"], row["ability_id"]): row for row in surface["occurrences"]}
    wording = {row["ability_id"]: row["proposed_description"] for row in audit["wording"]}
    observed = [
        (row.datasheet_id, ability)
        for row in package.army_catalog.datasheets
        for ability in row.abilities
        if ability.ability_id in wording
    ]
    assert len(observed) == len(occurrences)
    for owner, ability in observed:
        assert ability.effect_description == wording[ability.ability_id]
        expected = {
            **occurrences[(owner, ability.ability_id)]["descriptor"],
            "effect_description": ability.effect_description,
        }
        assert ability.to_payload() == expected
    added_ids = {CORE_DESCRIPTION_SOURCE_IDS[ability.ability_id] for _, ability in observed}
    if "000008344" in {ability.ability_id for _, ability in observed}:
        added_ids.add("gw-11e-core-abilities:core:scout-move")
    assert package.army_catalog.source_ids == tuple(
        sorted(set(surface["catalog_source_ids"]) | added_ids)
    )
    prior_artifacts = tuple(SourceArtifactHash(**row) for row in surface["source_artifacts"])
    prefix = tuple(
        row for row in prior_artifacts if row.artifact_name != "core-stealth-2026-09.json"
    )
    assert package.source_artifacts == tuple(
        sorted((*prefix, *CORE_DESCRIPTION_ARTIFACTS), key=lambda artifact: artifact.artifact_name)
    )
    projected = replace(
        package,
        army_catalog=replace(
            package.army_catalog,
            source_ids=tuple(surface["catalog_source_ids"]),
            datasheets=tuple(
                replace(
                    row,
                    abilities=tuple(
                        replace(
                            ability,
                            effect_description=occurrences[(row.datasheet_id, ability.ability_id)][
                                "descriptor"
                            ]["effect_description"],
                        )
                        if (row.datasheet_id, ability.ability_id) in occurrences
                        else ability
                        for ability in row.abilities
                    ),
                )
                for row in package.army_catalog.datasheets
            ),
        ),
        source_artifacts=prior_artifacts,
    )
    assert projected.package_hash() == surface["package_hash"]
    return projected
