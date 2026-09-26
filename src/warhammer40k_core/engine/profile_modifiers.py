"""Apply source-linked numeric operations to fixed or unresolved profile values."""

from warhammer40k_core.core.attributes import CharacteristicBoundPolicy, CharacteristicValue
from warhammer40k_core.core.random_profile_values import (
    ProfileCharacteristicValue,
    RandomProfileValue,
    with_random_profile_delta,
)
from warhammer40k_core.core.weapon_profiles import RangeProfile, RangeProfileKind
from warhammer40k_core.engine.phase import GameLifecycleError


def profile_with_delta(
    value: ProfileCharacteristicValue,
    delta: int,
    *,
    source_id: str,
    modifier_id: str | None = None,
    bound_numeric: bool = False,
) -> ProfileCharacteristicValue:
    if type(delta) is not int:
        raise GameLifecycleError("Profile modifier delta must be an integer.")
    if isinstance(value, RandomProfileValue):
        return with_random_profile_delta(
            value,
            delta=delta,
            source_id=source_id,
            modifier_id=modifier_id
            if modifier_id is not None
            else f"{source_id}:{value.characteristic.value}",
        )
    if type(value) is not CharacteristicValue or not value.is_numeric:
        raise GameLifecycleError(
            "Profile modifier requires CharacteristicValue and cannot modify dash characteristics."
        )
    final = value.final + delta
    if bound_numeric:
        final = CharacteristicBoundPolicy.for_characteristic(value.characteristic).apply(final)
    return CharacteristicValue.from_raw(value.characteristic, final)


def range_with_delta(
    profile: RangeProfile,
    delta: int,
    *,
    source_id: str,
    target_id: str,
) -> RangeProfile:
    """Apply Range modifiers to the selected roll without consuming fresh dice."""
    if profile.kind is not RangeProfileKind.DISTANCE:
        raise GameLifecycleError("Range modifier requires a ranged weapon.")
    value = profile.random_value
    if value is None:
        if profile.distance_inches is None:
            raise GameLifecycleError("Fixed weapon Range is missing.")
        return RangeProfile.distance(profile.distance_inches + delta)
    modified = with_random_profile_delta(
        value, delta=delta, source_id=source_id, modifier_id=f"{source_id}:range"
    )
    if value.evaluation_id is not None:
        modified = modified.evaluate(
            raw=value.raw, evaluation_id=value.evaluation_id, target_id=target_id
        )
    return RangeProfile.random(modified)
