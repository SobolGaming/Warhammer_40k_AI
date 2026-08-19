from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_battlefield_departure import (
    PrimaryBattlefieldDepartureState,
)
from warhammer40k_core.engine.primary_scoring_position_witness import (
    PrimaryScoringRulesUnitPositionWitness,
    validate_primary_scoring_position_witnesses,
)

_validate_identifier = IdentifierValidator(GameLifecycleError)


@dataclass(frozen=True, slots=True)
class PrimaryScoringPersistedRulesUnitLineage:
    """Current scoring-position descendants of one historical rules-unit identity."""

    historical_unit_instance_id: str
    owner_player_id: str | None
    frozen_component_unit_instance_ids: tuple[str, ...]
    current_witnesses: tuple[PrimaryScoringRulesUnitPositionWitness, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "historical_unit_instance_id",
            _validate_identifier(
                "Primary scoring persisted lineage historical_unit_instance_id",
                self.historical_unit_instance_id,
            ),
        )
        if self.owner_player_id is not None:
            object.__setattr__(
                self,
                "owner_player_id",
                _validate_identifier(
                    "Primary scoring persisted lineage owner_player_id",
                    self.owner_player_id,
                ),
            )
        frozen_ids = _validated_sorted_ids(
            "Primary scoring persisted lineage frozen_component_unit_instance_ids",
            self.frozen_component_unit_instance_ids,
        )
        witnesses = tuple(
            sorted(self.current_witnesses, key=lambda witness: witness.rules_unit_instance_id)
        )
        if self.current_witnesses != witnesses:
            raise GameLifecycleError(
                "Primary scoring persisted lineage current witnesses must be sorted."
            )
        owner_ids = {witness.owner_player_id for witness in witnesses}
        if self.owner_player_id is None:
            if witnesses or frozen_ids:
                raise GameLifecycleError(
                    "Primary scoring persisted lineage without an owner cannot keep descendants."
                )
        elif owner_ids and owner_ids != {self.owner_player_id}:
            raise GameLifecycleError("Primary scoring persisted rules-unit lineage owner drifted.")
        object.__setattr__(self, "frozen_component_unit_instance_ids", frozen_ids)
        object.__setattr__(self, "current_witnesses", witnesses)

    @property
    def current_witness_unit_instance_ids(self) -> tuple[str, ...]:
        return tuple(witness.rules_unit_instance_id for witness in self.current_witnesses)


def validate_primary_scoring_persisted_departures(
    values: object,
) -> tuple[PrimaryBattlefieldDepartureState, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(
            "Primary scoring persisted lineage requires PrimaryBattlefieldDepartureState tuples."
        )
    seen_ids: set[str] = set()
    validated: list[PrimaryBattlefieldDepartureState] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not PrimaryBattlefieldDepartureState:
            raise GameLifecycleError(
                "Primary scoring persisted lineage departures must be typed "
                "PrimaryBattlefieldDepartureState."
            )
        if value.departure_id in seen_ids:
            raise GameLifecycleError(
                "Primary scoring persisted lineage departures must not duplicate departure_id."
            )
        seen_ids.add(value.departure_id)
        validated.append(value)
    return tuple(validated)


def frozen_component_lineage_from_departures(
    *,
    historical_unit_instance_id: str,
    departures: tuple[PrimaryBattlefieldDepartureState, ...],
) -> tuple[str, frozenset[str]] | None:
    """Return owner and frozen components for a historical rules-unit identity."""

    requested_id = _validate_identifier(
        "Primary scoring persisted lineage historical_unit_instance_id",
        historical_unit_instance_id,
    )
    validated = validate_primary_scoring_persisted_departures(departures)
    direct_matches = tuple(
        departure for departure in validated if departure.rules_unit_instance_id == requested_id
    )
    if not direct_matches:
        return None
    owners = {departure.owner_player_id for departure in direct_matches}
    if len(owners) != 1:
        raise GameLifecycleError("Primary scoring persisted rules-unit lineage owner drifted.")
    component_lineages = {
        frozenset(departure.component_unit_instance_ids) for departure in direct_matches
    }
    if len(component_lineages) != 1:
        raise GameLifecycleError(
            "Primary scoring persisted rules-unit lineage component identity drifted."
        )
    historical_components = next(iter(component_lineages))
    if not historical_components:
        raise GameLifecycleError(
            "Primary scoring persisted rules-unit lineage component identity drifted."
        )
    return next(iter(owners)), historical_components


def related_departures_for_frozen_components(
    *,
    historical_unit_instance_id: str,
    frozen_components: frozenset[str],
    departures: tuple[PrimaryBattlefieldDepartureState, ...],
) -> tuple[PrimaryBattlefieldDepartureState, ...]:
    """Collect historical and descendant departure rows for one frozen component set."""

    requested_id = _validate_identifier(
        "Primary scoring persisted lineage historical_unit_instance_id",
        historical_unit_instance_id,
    )
    if type(frozen_components) is not frozenset or not frozen_components:
        raise GameLifecycleError(
            "Primary scoring persisted rules-unit lineage component identity drifted."
        )
    if any(type(component_id) is not str or not component_id for component_id in frozen_components):
        raise GameLifecycleError(
            "Primary scoring persisted rules-unit lineage component identity drifted."
        )
    validated = validate_primary_scoring_persisted_departures(departures)
    related: list[PrimaryBattlefieldDepartureState] = []
    for departure in validated:
        if departure.rules_unit_instance_id == requested_id:
            if frozenset(departure.component_unit_instance_ids) != frozen_components:
                raise GameLifecycleError(
                    "Primary scoring persisted rules-unit lineage component identity drifted."
                )
            related.append(departure)
            continue
        current_identities = frozenset(
            (departure.rules_unit_instance_id, *departure.component_unit_instance_ids)
        )
        departed_identities = frozenset(departure.departed_component_unit_instance_ids)
        if (
            not current_identities
            or not current_identities <= frozen_components
            or not departed_identities
            or not departed_identities <= frozen_components
        ):
            continue
        related.append(departure)
    return tuple(related)


def resolve_persisted_rules_unit_position_witnesses(
    *,
    historical_unit_instance_id: str,
    position_witnesses: tuple[PrimaryScoringRulesUnitPositionWitness, ...],
    departures: tuple[PrimaryBattlefieldDepartureState, ...],
) -> PrimaryScoringPersistedRulesUnitLineage:
    """Resolve a historical rules-unit identity onto current scoring position witnesses."""

    requested_id = _validate_identifier(
        "Primary scoring persisted lineage historical_unit_instance_id",
        historical_unit_instance_id,
    )
    witnesses = validate_primary_scoring_position_witnesses(position_witnesses)
    validated_departures = validate_primary_scoring_persisted_departures(departures)
    exact_matches = tuple(
        witness
        for witness in witnesses
        if _witness_covers_historical_identity(witness, historical_unit_instance_id=requested_id)
    )
    if len(exact_matches) > 1:
        raise GameLifecycleError(
            "Primary scoring persisted lineage matched multiple position witnesses."
        )
    departure_lineage = frozen_component_lineage_from_departures(
        historical_unit_instance_id=requested_id,
        departures=validated_departures,
    )
    if exact_matches:
        return _lineage_from_exact_match(
            historical_unit_instance_id=requested_id,
            witness=exact_matches[0],
            departure_lineage=departure_lineage,
        )
    if departure_lineage is None:
        return PrimaryScoringPersistedRulesUnitLineage(
            historical_unit_instance_id=requested_id,
            owner_player_id=None,
            frozen_component_unit_instance_ids=(),
            current_witnesses=(),
        )
    owner_player_id, frozen_components = departure_lineage
    descendants: list[PrimaryScoringRulesUnitPositionWitness] = []
    for witness in witnesses:
        components = frozenset(witness.rules_unit_membership.component_unit_instance_ids)
        if not components:
            raise GameLifecycleError(
                "Primary scoring persisted rules-unit lineage component identity drifted."
            )
        if components <= frozen_components:
            if witness.owner_player_id != owner_player_id:
                raise GameLifecycleError(
                    "Primary scoring persisted rules-unit lineage owner drifted."
                )
            if not witness.rules_unit_membership.evaluated_model_instance_ids:
                continue
            descendants.append(witness)
            continue
        if components & frozen_components:
            raise GameLifecycleError(
                "Primary scoring persisted rules-unit lineage component identity drifted."
            )
    return PrimaryScoringPersistedRulesUnitLineage(
        historical_unit_instance_id=requested_id,
        owner_player_id=owner_player_id,
        frozen_component_unit_instance_ids=tuple(sorted(frozen_components)),
        current_witnesses=tuple(
            sorted(descendants, key=lambda witness: witness.rules_unit_instance_id)
        ),
    )


def _lineage_from_exact_match(
    *,
    historical_unit_instance_id: str,
    witness: PrimaryScoringRulesUnitPositionWitness,
    departure_lineage: tuple[str, frozenset[str]] | None,
) -> PrimaryScoringPersistedRulesUnitLineage:
    current_components = frozenset(witness.rules_unit_membership.component_unit_instance_ids)
    if not current_components:
        raise GameLifecycleError(
            "Primary scoring persisted rules-unit lineage component identity drifted."
        )
    frozen_components = current_components
    if departure_lineage is not None:
        owner_player_id, departure_components = departure_lineage
        if owner_player_id != witness.owner_player_id:
            raise GameLifecycleError("Primary scoring persisted rules-unit lineage owner drifted.")
        if not current_components <= departure_components:
            raise GameLifecycleError(
                "Primary scoring persisted rules-unit lineage component identity drifted."
            )
        frozen_components = departure_components
    return PrimaryScoringPersistedRulesUnitLineage(
        historical_unit_instance_id=historical_unit_instance_id,
        owner_player_id=witness.owner_player_id,
        frozen_component_unit_instance_ids=tuple(sorted(frozen_components)),
        current_witnesses=(witness,),
    )


def _witness_covers_historical_identity(
    witness: PrimaryScoringRulesUnitPositionWitness,
    *,
    historical_unit_instance_id: str,
) -> bool:
    membership = witness.rules_unit_membership
    return (
        membership.rules_unit_instance_id == historical_unit_instance_id
        or historical_unit_instance_id in membership.component_unit_instance_ids
    )


def _validated_sorted_ids(label: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{label} must be a tuple.")
    validated = tuple(_validate_identifier(label, value) for value in values)
    expected = tuple(sorted(validated))
    if validated != expected:
        raise GameLifecycleError(f"{label} must be sorted.")
    if len(set(validated)) != len(validated):
        raise GameLifecycleError(f"{label} must be unique.")
    return expected


__all__ = (
    "PrimaryScoringPersistedRulesUnitLineage",
    "frozen_component_lineage_from_departures",
    "related_departures_for_frozen_components",
    "resolve_persisted_rules_unit_position_witnesses",
    "validate_primary_scoring_persisted_departures",
)
