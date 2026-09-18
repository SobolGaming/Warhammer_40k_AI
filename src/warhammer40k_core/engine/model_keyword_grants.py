"""Apply source-authorized roster keyword changes to their physical model owners."""

from dataclasses import replace

from warhammer40k_core.engine.core_ability_state import core_keyword_sources_after_grant
from warhammer40k_core.engine.unit_factory import UnitInstance


def grant_unit_keywords(
    unit: UnitInstance,
    *,
    keywords: tuple[str, ...],
    source_id: str,
    source_instance_id: str | None = None,
) -> UnitInstance:
    return replace(
        unit,
        core_keyword_sources=core_keyword_sources_after_grant(
            unit,
            keywords=keywords,
            source_id=source_id,
            source_instance_id=source_id if source_instance_id is None else source_instance_id,
        ),
        own_models=tuple(
            replace(
                model,
                keyword_assignment=replace(
                    model.keyword_assignment,
                    keywords=tuple(sorted({*model.keywords, *keywords})),
                    source_ids=tuple(sorted({*model.keyword_assignment.source_ids, source_id})),
                ),
            )
            for model in unit.own_models
        ),
    )


def replace_unit_faction_keywords(
    unit: UnitInstance, *, keywords: tuple[str, ...], source_id: str
) -> UnitInstance:
    return replace(
        unit,
        own_models=tuple(
            replace(
                model,
                keyword_assignment=replace(
                    model.keyword_assignment,
                    faction_keywords=keywords,
                    source_ids=tuple(sorted({*model.keyword_assignment.source_ids, source_id})),
                ),
            )
            for model in unit.own_models
        ),
    )


def unit_with_attached_role_evidence(
    unit: UnitInstance,
    *,
    role: str | None,
) -> UnitInstance:
    if role is None:
        return unit
    evidence = {f"runtime-attached-unit:{role}"}
    if role in {"leader", "support"}:
        evidence.add(f"attached-role:{role}")
    return replace(
        unit,
        own_models=tuple(
            replace(
                model,
                source_ids=tuple(sorted({*model.source_ids, *evidence})),
                keyword_assignment=replace(
                    model.keyword_assignment,
                    keywords=tuple(sorted({*model.keywords, "ATTACHED_UNIT"})),
                    source_ids=tuple(sorted({*model.keyword_assignment.source_ids, *evidence})),
                ),
            )
            for model in unit.own_models
        ),
    )
