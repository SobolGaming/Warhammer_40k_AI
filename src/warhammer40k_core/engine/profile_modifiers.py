"""Apply source-linked numeric operations to fixed or unresolved profile values."""

from dataclasses import replace

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.modifiers import ModifierOperation, ModifierTerm
from warhammer40k_core.core.profile_modifier_trace import CharacteristicModifierTrace
from warhammer40k_core.core.random_profile_values import (
    ProfileCharacteristicValue,
    RandomProfileValue,
    with_random_profile_delta,
)
from warhammer40k_core.core.weapon_profiles import RangeProfile, RangeProfileKind
from warhammer40k_core.engine.phase import GameLifecycleError


def resolved_profile_with_modifier_trace(value: ProfileCharacteristicValue) -> CharacteristicValue:
    """Keep random source operations when crossing into a numeric owner boundary."""
    if not isinstance(value, RandomProfileValue):
        return value
    resolved = value.resolved_value()
    trace = CharacteristicModifierTrace(
        characteristic=value.characteristic,
        source_value=value.raw,
        modifiers=value.modifiers,
        ignored_modifier_ids=value.ignored_modifier_ids,
    )
    traced = trace.value()
    if replace(traced, modifier_trace=None) != resolved:
        raise GameLifecycleError("Random profile modifier source arithmetic drifted.")
    return traced


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
    previous = value.modifier_trace
    if previous is None and value.applied_modifier_ids:
        raise GameLifecycleError("Profile modifier source operations are missing.")
    if previous is not None and previous.bounded != bound_numeric:
        raise GameLifecycleError("Profile modifier bound policy drifted.")
    modifier = ModifierTerm(ModifierOperation.ADD, delta).bind(
        modifier_id=modifier_id
        if modifier_id is not None
        else f"{source_id}:{value.characteristic.value}",
        source_id=source_id,
        characteristic=value.characteristic,
    )
    return CharacteristicModifierTrace(
        characteristic=value.characteristic,
        source_value=value.raw if previous is None else previous.source_value,
        modifiers=(*(previous.modifiers if previous is not None else ()), modifier),
        bounded=bound_numeric,
        ignored_modifier_ids=() if previous is None else previous.ignored_modifier_ids,
    ).value()


def range_with_delta(
    profile: RangeProfile,
    delta: int,
    *,
    source_id: str,
    target_id: str,
    modifier_id: str | None = None,
) -> RangeProfile:
    """Apply Range modifiers to the selected roll without consuming fresh dice."""
    if profile.kind is not RangeProfileKind.DISTANCE:
        raise GameLifecycleError("Range modifier requires a ranged weapon.")
    value = profile.random_value
    if value is None:
        if profile.distance_inches is None:
            raise GameLifecycleError("Fixed weapon Range is missing.")
        previous = profile.modifier_trace
        modifier = ModifierTerm(ModifierOperation.ADD, delta).bind(
            modifier_id=f"{source_id}:range" if modifier_id is None else modifier_id,
            source_id=source_id,
            characteristic=Characteristic.RANGE,
        )
        trace = CharacteristicModifierTrace(
            Characteristic.RANGE,
            profile.distance_inches if previous is None else previous.source_value,
            (*(previous.modifiers if previous is not None else ()), modifier),
            ignored_modifier_ids=() if previous is None else previous.ignored_modifier_ids,
        )
        return RangeProfile(
            kind=profile.kind,
            distance_inches=trace.resolve().final,
            modifier_trace=trace,
        )
    modified = with_random_profile_delta(
        value,
        delta=delta,
        source_id=source_id,
        modifier_id=f"{source_id}:range" if modifier_id is None else modifier_id,
    )
    if value.evaluation_id is not None:
        modified = modified.evaluate(
            raw=value.raw, evaluation_id=value.evaluation_id, target_id=target_id
        )
    return RangeProfile.random(modified)
