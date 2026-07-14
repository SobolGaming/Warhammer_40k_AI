from __future__ import annotations

from warhammer40k_core.rules.wahapedia_bridge_patterns import UNIT_COMPOSITION_MAX_MODELS_RE
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow


def composition_max_unit_models(
    *,
    rows: tuple[NormalizedSourceRow, ...],
    error_type: type[ValueError],
) -> int | None:
    maxima: list[int] = []
    for row in rows:
        description = row.runtime_fields_payload().get("description")
        if description is None or not description.strip():
            raise error_type("Unit composition source row requires description.")
        match = UNIT_COMPOSITION_MAX_MODELS_RE.fullmatch(description.strip())
        if match is not None:
            maxima.append(int(match.group("maximum")))
    if len(maxima) > 1:
        raise error_type("Datasheet declares multiple unit-size maxima.")
    return None if not maxima else maxima[0]


def composition_count_range(count_text: str, *, error_type: type[ValueError]) -> tuple[int, int]:
    if "-" not in count_text:
        count = _positive_int(count_text, error_type=error_type)
        return count, count
    minimum_text, maximum_text = count_text.split("-", maxsplit=1)
    minimum = _non_negative_int(minimum_text, error_type=error_type)
    maximum = _positive_int(maximum_text, error_type=error_type)
    if maximum < minimum:
        raise error_type("Unit composition maximum must be at least its minimum.")
    return minimum, maximum


def optional_int_text(value: int | None) -> str:
    return "" if value is None else str(value)


def _positive_int(value: str, *, error_type: type[ValueError]) -> int:
    integer = _non_negative_int(value, error_type=error_type)
    if integer < 1:
        raise error_type("Unit composition count must be positive.")
    return integer


def _non_negative_int(value: str, *, error_type: type[ValueError]) -> int:
    try:
        integer = int(value)
    except ValueError as exc:
        raise error_type("Unit composition count must be an integer.") from exc
    if integer < 0:
        raise error_type("Unit composition count must not be negative.")
    return integer
