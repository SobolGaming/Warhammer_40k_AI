"""Permanent rule provenance uses physical source inventory, not live membership."""

from warhammer40k_core.engine.unit_factory import UnitInstance


def static_rule_source_keywords(unit: UnitInstance) -> tuple[str, ...]:
    """Keep the same source evidence when casualties trigger content refresh.

    Runtime unit keyword queries deliberately exclude destroyed models. They
    must not rewrite an already-created permanent rule's provenance. Consumers
    continue to use current presence, keywords and conditions for applicability.
    """
    return tuple(
        sorted(
            {
                keyword
                for model in unit.own_models
                for keyword in (*model.keywords, *model.faction_keywords)
            }
        )
    )
