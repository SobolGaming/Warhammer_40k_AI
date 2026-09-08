"""Shared datasheet keyword inventory before model-scope assignment."""

from collections.abc import Callable

from warhammer40k_core.rules.wahapedia_bridge_defaults import PdfDatasheetCorrection
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow


def datasheet_keyword_inventory(
    *,
    keyword_rows: tuple[NormalizedSourceRow, ...],
    correction: PdfDatasheetCorrection | None,
    raw_field: Callable[[NormalizedSourceRow, str], str],
    correction_source_row: Callable[[PdfDatasheetCorrection], NormalizedSourceRow],
    error_type: type[ValueError],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[NormalizedSourceRow, ...]]:
    if not keyword_rows:
        raise error_type("Datasheet has no keyword rows.")
    removed = set(correction.removed_keywords if correction is not None else ())
    keywords: list[str] = list(
        correction.replacement_keywords
        if correction is not None and correction.replacement_keywords is not None
        else ()
    )
    replaces_keywords = correction is not None and correction.replacement_keywords is not None
    faction_keywords: list[str] = []
    source_rows: list[NormalizedSourceRow] = []
    for row in keyword_rows:
        keyword = raw_field(row, "keyword").strip()
        if not keyword:
            if row.runtime_fields_payload()["is_faction_keyword"] != "true":
                raise error_type(
                    "Empty datasheet keyword rows must be faction-keyword placeholders."
                )
            source_rows.append(row)
            continue
        if keyword in removed:
            if correction is not None:
                source_rows.append(row)
            continue
        if row.runtime_fields_payload()["is_faction_keyword"] == "true":
            faction_keywords.append(keyword)
        elif not replaces_keywords:
            keywords.append(keyword)
        source_rows.append(row)
    if correction is not None:
        source_rows.append(correction_source_row(correction))
    return (
        tuple(sorted(dict.fromkeys(keywords))),
        tuple(sorted(dict.fromkeys(faction_keywords))),
        tuple(source_rows),
    )
