"""Explicit keyword ownership for canonical runtime fixtures."""

from dataclasses import replace

from warhammer40k_core.core.validation import canonical_keyword_token
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance


def with_model_keywords(model: ModelInstance, *, keywords: tuple[str, ...]) -> ModelInstance:
    requested = {canonical_keyword_token(k) for k in keywords}
    name = model.keyword_assignment.name_keyword
    return replace(
        model,
        keyword_assignment=replace(
            model.keyword_assignment,
            keywords=tuple(sorted(requested | ({name} if name is not None else set()))),
            name_is_ordinary_keyword=(
                model.keyword_assignment.name_is_ordinary_keyword
                if name is None
                else name in requested
            ),
        ),
    )


def with_unit_keywords(
    unit: UnitInstance,
    *,
    keywords: tuple[str, ...] | None = None,
    faction_keywords: tuple[str, ...] | None = None,
) -> UnitInstance:
    current = {k for model in unit.own_models for k in model.keywords}
    factions = {k for model in unit.own_models for k in model.faction_keywords}
    requested = current if keywords is None else {canonical_keyword_token(k) for k in keywords}
    requested_factions = (
        factions
        if faction_keywords is None
        else {canonical_keyword_token(k) for k in faction_keywords}
    )
    return replace(
        unit,
        own_models=tuple(
            replace(
                model,
                keyword_assignment=replace(
                    model.keyword_assignment,
                    keywords=tuple(
                        sorted(
                            (set(model.keywords) - (current - requested))
                            | (requested - current)
                            | (
                                {model.keyword_assignment.name_keyword}
                                if model.keyword_assignment.name_keyword is not None
                                else set()
                            )
                        )
                    ),
                    faction_keywords=tuple(
                        sorted(
                            (set(model.faction_keywords) - (factions - requested_factions))
                            | (requested_factions - factions)
                        )
                    ),
                    name_is_ordinary_keyword=(
                        model.keyword_assignment.name_is_ordinary_keyword
                        if keywords is None or model.keyword_assignment.name_keyword is None
                        else model.keyword_assignment.name_keyword in requested
                    ),
                ),
            )
            for model in unit.own_models
        ),
    )
