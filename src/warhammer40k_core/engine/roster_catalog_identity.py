"""Validate the source identity of a roster against its typed catalog."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.army_catalog import ArmyCatalog

if TYPE_CHECKING:
    from warhammer40k_core.engine.army_mustering import ArmyMusterRequest


def validate_request_matches_catalog(
    *,
    catalog: ArmyCatalog,
    request: ArmyMusterRequest,
) -> None:
    from warhammer40k_core.engine.army_mustering import ArmyMusteringError

    if request.catalog_id != catalog.catalog_id:
        raise ArmyMusteringError("ArmyMusterRequest catalog_id does not match catalog.")
    if request.source_package_id != catalog.source_package_id:
        raise ArmyMusteringError("ArmyMusterRequest source_package_id does not match catalog.")
    if request.ruleset_id != catalog.ruleset_id:
        raise ArmyMusteringError("ArmyMusterRequest ruleset_id does not match catalog.")
