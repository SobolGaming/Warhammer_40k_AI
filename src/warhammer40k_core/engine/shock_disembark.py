from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.transport_disembark_permissions import (
    transport_disembark_permission_effect,
    transport_disembark_restriction_overrides,
)
from warhammer40k_core.engine.transport_disembark_state import (
    TransportRestrictionOverride,
    TransportRestrictionOverrideKind,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


SHOCK_DISEMBARK_PERMISSION_EFFECT_KIND = "shock_disembark_permission"


def shock_disembark_permission_effect(
    *,
    effect_id: str,
    source_rule_id: str,
    owner_player_id: str,
    transport_unit_instance_id: str,
    eligible_rules_unit_instance_ids: tuple[str, ...],
    started_battle_round: int,
    expiration: EffectExpiration,
    started_phase: BattlePhaseKind | None = None,
) -> PersistingEffect:
    return transport_disembark_permission_effect(
        effect_kind=SHOCK_DISEMBARK_PERMISSION_EFFECT_KIND,
        effect_id=effect_id,
        source_rule_id=source_rule_id,
        owner_player_id=owner_player_id,
        transport_unit_instance_id=transport_unit_instance_id,
        eligible_rules_unit_instance_ids=eligible_rules_unit_instance_ids,
        started_battle_round=started_battle_round,
        expiration=expiration,
        started_phase=started_phase,
    )


def shock_disembark_restriction_overrides(
    *,
    state: GameState,
    player_id: str,
    battle_round: int,
    rules_unit_instance_id: str,
    transport_unit_instance_id: str,
) -> tuple[TransportRestrictionOverride, ...]:
    return transport_disembark_restriction_overrides(
        state=state,
        effect_kind=SHOCK_DISEMBARK_PERMISSION_EFFECT_KIND,
        override_kind=TransportRestrictionOverrideKind.ALLOW_SHOCK_DISEMBARK_AFTER_ADVANCE,
        player_id=player_id,
        battle_round=battle_round,
        rules_unit_instance_id=rules_unit_instance_id,
        transport_unit_instance_id=transport_unit_instance_id,
        label="Shock Disembark",
    )


__all__ = (
    "SHOCK_DISEMBARK_PERMISSION_EFFECT_KIND",
    "shock_disembark_permission_effect",
    "shock_disembark_restriction_overrides",
)
