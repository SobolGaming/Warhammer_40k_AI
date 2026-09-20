"""Firing Deck resolution snapshots all cargo independently of weapon contributors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, cast

from warhammer40k_core.core.weapon_profiles import RangeProfileKind, WeaponKeyword, WeaponProfile
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.weapon_instances import equipped_weapon_instance_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.transports import (
        FiringDeckResolutionPayload,
        FiringDeckSelection,
        TransportCargoState,
        TransportOperationViolation,
    )

# pyright: reportPrivateUsage=false


@dataclass(frozen=True, slots=True)
class FiringDeckResolution:
    selection: FiringDeckSelection
    violations: tuple[TransportOperationViolation, ...]
    temporary_weapon_profiles: tuple[WeaponProfile, ...]
    ineligible_unit_instance_ids: tuple[str, ...]
    embarked_unit_instance_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.transports import (
            FiringDeckSelection,
            _validate_identifier_tuple,
            _validate_transport_violation_tuple,
        )

        object.__setattr__(
            self,
            "embarked_unit_instance_ids",
            _validate_identifier_tuple(
                "FiringDeckResolution embarked_unit_instance_ids", self.embarked_unit_instance_ids
            ),
        )
        if type(self.selection) is not FiringDeckSelection:
            raise GameLifecycleError("FiringDeckResolution selection must be FiringDeckSelection.")
        object.__setattr__(
            self,
            "violations",
            _validate_transport_violation_tuple(
                "FiringDeckResolution violations",
                self.violations,
            ),
        )
        profiles = tuple(self.temporary_weapon_profiles)
        for profile in profiles:
            if type(profile) is not WeaponProfile:
                raise GameLifecycleError("Firing Deck profiles must contain WeaponProfile.")
        object.__setattr__(self, "temporary_weapon_profiles", profiles)
        object.__setattr__(
            self,
            "ineligible_unit_instance_ids",
            _validate_identifier_tuple(
                "FiringDeckResolution ineligible_unit_instance_ids",
                self.ineligible_unit_instance_ids,
            ),
        )
        if self.violations and (
            self.temporary_weapon_profiles or self.ineligible_unit_instance_ids
        ):
            raise GameLifecycleError("Invalid FiringDeckResolution cannot mark shooting state.")
        if not self.violations and len(self.temporary_weapon_profiles) != len(
            self.selection.weapon_selections
        ):
            raise GameLifecycleError("Valid FiringDeckResolution weapon count drift.")
        if not self.violations:
            expected_profiles = tuple(
                selection.weapon_profile for selection in self.selection.weapon_selections
            )
            if self.temporary_weapon_profiles != expected_profiles:
                raise GameLifecycleError("Valid FiringDeckResolution weapon profile drift.")
            selected_ids = {
                row.embarked_unit_instance_id for row in self.selection.weapon_selections
            }
            if not selected_ids <= set(self.embarked_unit_instance_ids):
                raise GameLifecycleError("Firing Deck selection is outside the cargo snapshot.")
            if self.ineligible_unit_instance_ids != self.embarked_unit_instance_ids:
                raise GameLifecycleError("Valid FiringDeckResolution ineligible unit drift.")

    @property
    def is_valid(self) -> bool:
        return not self.violations

    def to_payload(self) -> FiringDeckResolutionPayload:
        return {
            "embarked_unit_instance_ids": list(self.embarked_unit_instance_ids),
            "selection": self.selection.to_payload(),
            "is_valid": self.is_valid,
            "violations": [violation.to_payload() for violation in self.violations],
            "temporary_weapon_profiles": [
                profile.to_payload() for profile in self.temporary_weapon_profiles
            ],
            "ineligible_unit_instance_ids": list(self.ineligible_unit_instance_ids),
        }

    @classmethod
    def from_payload(cls, payload: FiringDeckResolutionPayload) -> Self:
        from warhammer40k_core.engine.transports import (
            FiringDeckSelection,
            TransportOperationViolation,
        )

        resolution = cls(
            embarked_unit_instance_ids=tuple(payload["embarked_unit_instance_ids"]),
            selection=FiringDeckSelection.from_payload(payload["selection"]),
            violations=tuple(
                TransportOperationViolation.from_payload(violation)
                for violation in payload["violations"]
            ),
            temporary_weapon_profiles=tuple(
                WeaponProfile.from_payload(profile)
                for profile in payload["temporary_weapon_profiles"]
            ),
            ineligible_unit_instance_ids=tuple(payload["ineligible_unit_instance_ids"]),
        )
        if resolution.is_valid != payload["is_valid"]:
            raise GameLifecycleError("FiringDeckResolution payload validity drift.")
        return resolution


def resolve_firing_deck_selection(
    *,
    cargo_state: TransportCargoState,
    selection: FiringDeckSelection,
    embarked_units: tuple[UnitInstance, ...],
) -> FiringDeckResolution:
    from warhammer40k_core.engine.transports import (
        FiringDeckSelection,
        TransportCargoState,
        TransportOperationViolation,
        TransportOperationViolationCode,
    )

    if type(cargo_state) is not TransportCargoState:
        raise GameLifecycleError("resolve_firing_deck_selection requires TransportCargoState.")
    if type(selection) is not FiringDeckSelection:
        raise GameLifecycleError("resolve_firing_deck_selection requires FiringDeckSelection.")
    units = _unit_by_id(embarked_units)
    violations: list[TransportOperationViolation] = []
    if selection.transport_unit_instance_id != cargo_state.transport_unit_instance_id:
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.FRIENDLY_TRANSPORT_REQUIRED,
                message="Firing Deck selection transport drift.",
                unit_instance_id=selection.transport_unit_instance_id,
            )
        )
    if len(selection.weapon_selections) > selection.firing_deck_value:
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.FIRING_DECK_CAPACITY_EXCEEDED,
                message="Firing Deck selection exceeds the ability value.",
                unit_instance_id=selection.transport_unit_instance_id,
            )
        )
    selected_model_keys: set[tuple[str, str]] = set()
    for weapon_selection in selection.weapon_selections:
        selected_model_key = (
            weapon_selection.embarked_unit_instance_id,
            weapon_selection.model_instance_id,
        )
        if selected_model_key in selected_model_keys:
            violations.append(
                TransportOperationViolation(
                    violation_code=(
                        TransportOperationViolationCode.FIRING_DECK_DUPLICATE_MODEL_SELECTION
                    ),
                    message="Firing Deck can select at most one weapon per embarked model.",
                    unit_instance_id=weapon_selection.embarked_unit_instance_id,
                    model_instance_id=weapon_selection.model_instance_id,
                )
            )
        selected_model_keys.add(selected_model_key)
        unit = units.get(weapon_selection.embarked_unit_instance_id)
        if unit is None or not cargo_state.contains_unit(
            weapon_selection.embarked_unit_instance_id
        ):
            violations.append(
                TransportOperationViolation(
                    violation_code=TransportOperationViolationCode.FIRING_DECK_UNIT_NOT_EMBARKED,
                    message="Firing Deck selected unit is not embarked in this Transport.",
                    unit_instance_id=weapon_selection.embarked_unit_instance_id,
                )
            )
            continue
        if weapon_selection.embarked_unit_instance_id in selection.already_shot_unit_instance_ids:
            violations.append(
                TransportOperationViolation(
                    violation_code=TransportOperationViolationCode.FIRING_DECK_UNIT_ALREADY_SHOT,
                    message="Firing Deck cannot select a unit that has already shot.",
                    unit_instance_id=weapon_selection.embarked_unit_instance_id,
                )
            )
        model = next(
            (
                model
                for model in unit.own_models
                if model.model_instance_id == weapon_selection.model_instance_id
            ),
            None,
        )
        if model is None:
            violations.append(
                TransportOperationViolation(
                    violation_code=TransportOperationViolationCode.FIRING_DECK_MODEL_DRIFT,
                    message="Firing Deck selected model is not in the embarked unit.",
                    unit_instance_id=weapon_selection.embarked_unit_instance_id,
                    model_instance_id=weapon_selection.model_instance_id,
                )
            )
        else:
            weapon_instance = equipped_weapon_instance_by_id(
                model=model,
                weapon_instance_id=weapon_selection.weapon_instance_id,
            )
            if weapon_instance is None or weapon_instance.wargear_id != weapon_selection.wargear_id:
                violations.append(
                    TransportOperationViolation(
                        violation_code=(
                            TransportOperationViolationCode.FIRING_DECK_WEAPON_INSTANCE_DRIFT
                        ),
                        message="Firing Deck weapon instance is not equipped by this model.",
                        unit_instance_id=weapon_selection.embarked_unit_instance_id,
                        model_instance_id=weapon_selection.model_instance_id,
                    )
                )
        if weapon_selection.weapon_profile.range_profile.kind is RangeProfileKind.MELEE:
            violations.append(
                TransportOperationViolation(
                    violation_code=TransportOperationViolationCode.FIRING_DECK_MELEE_WEAPON,
                    message="Firing Deck requires a ranged weapon.",
                    unit_instance_id=weapon_selection.embarked_unit_instance_id,
                    model_instance_id=weapon_selection.model_instance_id,
                )
            )
        if WeaponKeyword.ONE_SHOT in weapon_selection.weapon_profile.keywords:
            violations.append(
                TransportOperationViolation(
                    violation_code=TransportOperationViolationCode.FIRING_DECK_ONE_SHOT_WEAPON,
                    message="Firing Deck cannot select One Shot weapons.",
                    unit_instance_id=weapon_selection.embarked_unit_instance_id,
                    model_instance_id=weapon_selection.model_instance_id,
                )
            )
    if violations:
        return FiringDeckResolution(
            embarked_unit_instance_ids=cargo_state.embarked_unit_instance_ids,
            selection=selection,
            violations=tuple(violations),
            temporary_weapon_profiles=(),
            ineligible_unit_instance_ids=(),
        )
    return FiringDeckResolution(
        selection=selection,
        violations=(),
        temporary_weapon_profiles=tuple(row.weapon_profile for row in selection.weapon_selections),
        ineligible_unit_instance_ids=cargo_state.embarked_unit_instance_ids,
        embarked_unit_instance_ids=cargo_state.embarked_unit_instance_ids,
    )


def _unit_by_id(units: tuple[UnitInstance, ...]) -> dict[str, UnitInstance]:
    validated = _validate_unit_tuple("embarked_units", units)
    return {unit.unit_instance_id: unit for unit in validated}


def _validate_unit_tuple(field_name: str, values: object) -> tuple[UnitInstance, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    units: list[UnitInstance] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not UnitInstance:
            raise GameLifecycleError(f"{field_name} must contain UnitInstance values.")
        if value.unit_instance_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate unit IDs.")
        seen.add(value.unit_instance_id)
        units.append(value)
    return tuple(sorted(units, key=lambda unit: unit.unit_instance_id))
