from __future__ import annotations

from warhammer40k_core.engine import catalog_poisoned_status_support as _poisoned
from warhammer40k_core.engine import catalog_selectable_ability_mode_support as _ability_modes
from warhammer40k_core.rules.rule_ir import RuleClause


def registered_consumer_ids() -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                *_ability_modes.registered_consumer_ids(),
                *_poisoned.registered_consumer_ids(),
            }
        )
    )


def consumer_ids_for_clause(clause: RuleClause) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                *_ability_modes.consumer_ids_for_clause(clause),
                *_poisoned.consumer_ids_for_clause(clause),
            }
        )
    )
