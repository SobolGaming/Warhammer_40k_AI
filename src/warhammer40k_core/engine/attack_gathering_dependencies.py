"""Declared functional dependencies of source-owned future attack providers.

TARGET_ONLY providers depend on current target/beneficiary/resource state, not
the attacking physical model or profile. ATTACK_KIND_AND_TARGET additionally
depends on ranged/melee kind. UNKNOWN declares no equivalence proof and remains
an explicit unresolved native grouping boundary; it is never passing support.
"""

from enum import StrEnum

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.engine.phase import GameLifecycleError


class AttackGatheringDependency(StrEnum):
    UNKNOWN = "unknown"
    TARGET_ONLY = "target_only"
    ATTACK_KIND_AND_TARGET = "attack_kind_and_target"


def validate_gathering_dependency(value: AttackGatheringDependency) -> None:
    if type(value) is not AttackGatheringDependency:
        raise GameLifecycleError("Attack provider gathering dependency must be typed.")


def validate_save_gathering_characteristics(values: tuple[Characteristic, ...] | None) -> None:
    """None records an unproved output inventory; known slots remain typed."""
    if values is None:
        return
    if (
        type(values) is not tuple
        or not values
        or any(
            type(value) is not Characteristic
            or value
            not in {
                Characteristic.SAVE,
                Characteristic.INVULNERABLE_SAVE,
                Characteristic.ARMOR_PENETRATION,
            }
            for value in values
        )
        or len(set(values)) != len(values)
    ):
        raise GameLifecycleError(
            "Save provider gathering characteristics must be typed unique slots."
        )
