from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.mission_scoring_policies import MissionScoringPolicies
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.scoring import (
    VictoryPointLedger,
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
    policies: MissionScoringPolicies | None = None,
) -> None:
    if mission_setup is None:
        return
    if policies is None:
        raise GameLifecycleError("Victory Point ledger source validation requires policies.")
    policies.validate_mission_setup(mission_setup)
    for ledger in ledgers:
        policy = policies.policy_for_player(ledger.player_id)
        for transaction in ledger.transactions:
            policy.cap_bucket_for_victory_point_source(
                source_kind=transaction.source_kind,
                source_id=transaction.source_id,
            )
