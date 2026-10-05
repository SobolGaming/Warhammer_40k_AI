"""Keep catalog name identity separate from conventional keyword selectors."""

from collections.abc import Callable, Iterable

from warhammer40k_core.core.model_keywords import ModelKeywordAssignment
from warhammer40k_core.core.validation import canonical_keyword_token


def keyword_inventory_contains(
    *,
    keywords: Iterable[str],
    keyword: str,
    name_keywords: Iterable[str],
    normalizer: Callable[[str], str],
    ordinary_keywords: Iterable[str] = (),
) -> bool:
    normalized_query = normalizer(keyword)
    inventory = frozenset(keywords)
    names = frozenset(name_keywords).difference(ordinary_keywords)
    native = canonical_keyword_token(keyword.strip())
    if native in inventory.intersection(names):
        return True
    conventional = {normalizer(stored) for stored in inventory.difference(names)}
    return normalized_query in conventional


def exclusive_name_keywords(assignments: Iterable[ModelKeywordAssignment]) -> tuple[str, ...]:
    names: set[str] = set()
    ordinary: set[str] = set()
    for assignment in assignments:
        if assignment.name_keyword is not None:
            names.add(assignment.name_keyword)
        ordinary.update(
            keyword
            for keyword in assignment.keywords
            if keyword != assignment.name_keyword
            or assignment.name_is_ordinary_keyword
            or (
                keyword == "ATTACHED_UNIT"
                and any(
                    source_id.startswith("runtime-attached-unit:")
                    for source_id in assignment.source_ids
                )
            )
        )
    return tuple(sorted(names.difference(ordinary)))
