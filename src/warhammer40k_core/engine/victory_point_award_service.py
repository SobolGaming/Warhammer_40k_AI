from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine import (
    primary_scoring_transaction_integrity as _primary_vp_integrity,
)
from warhammer40k_core.engine import (
    secondary_scoring_transaction_integrity as _secondary_vp_integrity,
)
from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.scoring import (
    VictoryPointAward,
    VictoryPointLedger,
    VictoryPointSourceKind,
    VictoryPointTransaction,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def resolve_victory_point_award_for_game_state(
    *,
    state: GameState,
    award: VictoryPointAward,
) -> tuple[list[VictoryPointLedger], VictoryPointTransaction]:
    """Validate and resolve one award without mutating authoritative state."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Victory Point award resolution requires GameState.")
    if type(award) is not VictoryPointAward:
        raise GameLifecycleError("GameState award must be a VictoryPointAward.")
    ledger = state.victory_point_ledger_for_player(award.player_id)
    if award.source_kind is VictoryPointSourceKind.PRIMARY:
        if state.mission_setup is None:
            raise GameLifecycleError("Primary VP awards require a mission setup.")
        if state.stage is not GameLifecycleStage.BATTLE:
            raise GameLifecycleError("Primary VP awards may be recorded only during battle.")
        if award.battle_round != state.battle_round:
            raise GameLifecycleError("Primary VP award battle_round drift.")
        if state.current_battle_phase is None or award.phase != state.current_battle_phase.value:
            raise GameLifecycleError("Primary VP award phase drift.")
        if state.active_player_id is None:
            raise GameLifecycleError("Primary VP award requires an active player.")
    applied_amount = award.amount
    transaction_metadata = award.metadata
    if state.mission_setup is not None:
        policy = mission_scoring_policies_from_setup(state.mission_setup)
        applied_amount, transaction_metadata = policy.capped_award_for_ledger(
            ledger=ledger,
            award=award,
            objective_control_records=tuple(state.objective_control_records),
            primary_scoring_state_evidence_records=tuple(
                state.primary_scoring_state_evidence_records
            ),
            turn_order=state.turn_order,
            current_active_player_id=state.active_player_id,
        )
    if award.source_kind is VictoryPointSourceKind.PRIMARY:
        _primary_vp_integrity.validate_primary_award_semantics(state=state, award=award)
    elif award.source_kind in {
        VictoryPointSourceKind.FIXED_SECONDARY,
        VictoryPointSourceKind.TACTICAL_SECONDARY,
    }:
        _secondary_vp_integrity.validate_secondary_award_semantics(state=state, award=award)
    updated, transaction = ledger.award(
        award,
        applied_amount=applied_amount,
        metadata=transaction_metadata,
    )
    ledgers = [
        updated if stored.player_id == ledger.player_id else stored
        for stored in state.victory_point_ledgers
    ]
    return sorted(ledgers, key=lambda stored: stored.player_id), transaction


def validate_secondary_transaction_semantics(*, state: GameState) -> None:
    """Restore-time Secondary VP semantic authentication."""
    _secondary_vp_integrity.validate_secondary_transaction_semantics(state=state)


__all__ = (
    "resolve_victory_point_award_for_game_state",
    "validate_secondary_transaction_semantics",
)
