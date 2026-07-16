from __future__ import annotations

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError


def metadata_with_vp_cap_audit(
    metadata: JsonValue,
    *,
    requested_amount: int,
    applied_amount: int,
    source_cap: int,
    source_points_before: int,
    source_points_after: int,
    total_cap: int,
    total_points_before: int,
    total_points_after: int,
    capped_reasons: tuple[str, ...],
    fixed_secondary_mission_cap: int | None = None,
    fixed_secondary_mission_points_before: int = 0,
    fixed_secondary_mission_points_after: int = 0,
    primary_battle_round_cap: int | None = None,
    primary_battle_round_points_before: int = 0,
    primary_battle_round_points_after: int = 0,
) -> JsonValue:
    audit = {
        "requested_amount": _positive_int("requested_amount", requested_amount),
        "applied_amount": _non_negative_int("applied_amount", applied_amount),
        "source_cap": _non_negative_int("source_cap", source_cap),
        "source_points_before": _non_negative_int("source_points_before", source_points_before),
        "source_points_after": _non_negative_int("source_points_after", source_points_after),
        "total_cap": _positive_int("total_cap", total_cap),
        "total_points_before": _non_negative_int("total_points_before", total_points_before),
        "total_points_after": _non_negative_int("total_points_after", total_points_after),
        "capped_reasons": list(_ordered_identifiers("capped_reasons", capped_reasons)),
    }
    if fixed_secondary_mission_cap is not None:
        audit["fixed_secondary_mission_cap"] = _positive_int(
            "fixed_secondary_mission_cap",
            fixed_secondary_mission_cap,
        )
        audit["fixed_secondary_mission_points_before"] = _non_negative_int(
            "fixed_secondary_mission_points_before",
            fixed_secondary_mission_points_before,
        )
        audit["fixed_secondary_mission_points_after"] = _non_negative_int(
            "fixed_secondary_mission_points_after",
            fixed_secondary_mission_points_after,
        )
    if primary_battle_round_cap is not None:
        audit["primary_battle_round_cap"] = _positive_int(
            "primary_battle_round_cap",
            primary_battle_round_cap,
        )
        audit["primary_battle_round_points_before"] = _non_negative_int(
            "primary_battle_round_points_before",
            primary_battle_round_points_before,
        )
        audit["primary_battle_round_points_after"] = _non_negative_int(
            "primary_battle_round_points_after",
            primary_battle_round_points_after,
        )
    validated_metadata = validate_json_value(metadata)
    if validated_metadata is None:
        return {"vp_cap_audit": validate_json_value(audit)}
    if isinstance(validated_metadata, dict):
        if "vp_cap_audit" in validated_metadata:
            raise GameLifecycleError("Victory point metadata already contains vp_cap_audit.")
        updated = dict(validated_metadata)
        updated["vp_cap_audit"] = validate_json_value(audit)
        return updated
    return {
        "original_metadata": validated_metadata,
        "vp_cap_audit": validate_json_value(audit),
    }


def _positive_int(field_name: str, value: object) -> int:
    if type(value) is not int or value <= 0:
        raise GameLifecycleError(f"{field_name} must be a positive integer.")
    return value


def _non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int or value < 0:
        raise GameLifecycleError(f"{field_name} must be a non-negative integer.")
    return value


def _ordered_identifiers(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple or not values:
        raise GameLifecycleError(f"{field_name} must be a non-empty tuple.")
    validated = tuple(
        _validate_identifier(f"{field_name}[{index}]", value) for index, value in enumerate(values)
    )
    if len(set(validated)) != len(validated):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return validated


_validate_identifier = IdentifierValidator(GameLifecycleError)
