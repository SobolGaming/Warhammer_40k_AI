from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.mission_scoring_policies import MissionScoringPolicies
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.objective_control import ObjectiveControlRecord
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_scoring_state_evidence import (
    PrimaryScoringStateEvidence,
)
from warhammer40k_core.engine.primary_victory_point_policy import (
    validate_victory_point_ledger_policy,
)
from warhammer40k_core.engine.scoring import (
    VictoryPointLedger,
    VictoryPointSourceKind,
    initial_victory_point_ledgers,
)


def validate_victory_point_ledgers(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> list[VictoryPointLedger]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState victory_point_ledgers must be a list.")
    if not values:
        return initial_victory_point_ledgers(player_ids)
    validated: list[VictoryPointLedger] = []
    seen: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not VictoryPointLedger:
            raise GameLifecycleError(
                "GameState victory_point_ledgers must contain VictoryPointLedger values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("VictoryPointLedger player_id is not in this game.")
        if value.player_id in seen:
            raise GameLifecycleError("GameState victory_point_ledgers must be unique.")
        seen.add(value.player_id)
        validated.append(value)
    if set(seen) != set(player_ids):
        raise GameLifecycleError("GameState victory_point_ledgers must include every player.")
    return sorted(validated, key=lambda ledger: ledger.player_id)


def validate_victory_point_ledger_policy_sources(
    ledgers: list[VictoryPointLedger],
    *,
    mission_setup: MissionSetup | None,
    objective_control_records: tuple[ObjectiveControlRecord, ...],
    primary_scoring_state_evidence_records: tuple[PrimaryScoringStateEvidence, ...],
    turn_order: tuple[str, ...],
    current_battle_round: int,
    policies: MissionScoringPolicies | None = None,
) -> None:
    if mission_setup is None:
        if any(
            transaction.source_kind is VictoryPointSourceKind.PRIMARY
            for ledger in ledgers
            for transaction in ledger.transactions
        ):
            raise GameLifecycleError(
                "Primary VP ledger source validation requires a mission setup."
            )
        return
    if policies is None:
        raise GameLifecycleError("Victory Point ledger source validation requires policies.")
    policies.validate_mission_setup(mission_setup)
    for ledger in ledgers:
        policy = policies.policy_for_player(ledger.player_id)
        if any(
            transaction.source_kind is VictoryPointSourceKind.PRIMARY
            and transaction.battle_round > current_battle_round
            for transaction in ledger.transactions
        ):
            raise GameLifecycleError(
                "Primary VP transaction battle_round is later than the game state."
            )
        validate_victory_point_ledger_policy(
            policy=policy,
            ledger=ledger,
            objective_control_records=objective_control_records,
            primary_scoring_state_evidence_records=primary_scoring_state_evidence_records,
            turn_order=turn_order,
        )
