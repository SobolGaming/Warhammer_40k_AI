from __future__ import annotations

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusteringError,
    ArmyMusterRequest,
    muster_army,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage, SetupStep
from warhammer40k_core.engine.unit_resource_state import (
    unit_resource_initializations_for_army,
)
from warhammer40k_core.engine.unit_resources import UnitResourceTransactionKind


def validate_mustered_army_consistency(
    *,
    state: GameState,
    catalog: ArmyCatalog,
    muster_requests: tuple[ArmyMusterRequest, ...],
) -> None:
    if not state.army_definitions and not _state_requires_mustered_armies(state):
        return
    try:
        expected_armies = tuple(
            sorted(
                (muster_army(catalog=catalog, request=request) for request in muster_requests),
                key=lambda army: army.player_id,
            )
        )
    except ArmyMusteringError as exc:
        raise GameLifecycleError("Lifecycle config army muster requests are invalid.") from exc
    expected_payloads = [army.to_payload() for army in expected_armies]
    state_payloads = [army.to_payload() for army in state.army_definitions]
    if _state_requires_mustered_armies(state) and not state_payloads:
        raise GameLifecycleError("Lifecycle state is missing mustered army definitions.")
    if state_payloads and state_payloads != expected_payloads:
        raise GameLifecycleError("Lifecycle state army definitions do not match config.")
    if state_payloads:
        _validate_unit_resource_initialization_consistency(
            state=state,
            expected_armies=expected_armies,
        )


def _validate_unit_resource_initialization_consistency(
    *,
    state: GameState,
    expected_armies: tuple[ArmyDefinition, ...],
) -> None:
    expected: dict[tuple[str, str, str], tuple[int, str]] = {}
    for army in expected_armies:
        for initialization in unit_resource_initializations_for_army(army):
            key = (
                army.player_id,
                initialization.unit_instance_id,
                initialization.resource_kind,
            )
            if key in expected:
                raise GameLifecycleError("Mustered unit resource initialization is duplicated.")
            expected[key] = (initialization.amount, initialization.source_rule_id)
    actual: dict[tuple[str, str, str], tuple[int, str]] = {}
    for ledger in state.unit_resource_ledgers:
        for transaction in ledger.transactions:
            if transaction.transaction_kind is not UnitResourceTransactionKind.INITIALIZE:
                continue
            key = (ledger.player_id, ledger.unit_instance_id, transaction.resource_kind)
            if key in actual:
                raise GameLifecycleError("Unit resource ledger initialization is duplicated.")
            actual[key] = (transaction.amount, transaction.source_rule_id)
    if actual != expected:
        raise GameLifecycleError(
            "Lifecycle unit resource initializations do not match source-backed roster choices."
        )


def _state_requires_mustered_armies(state: GameState) -> bool:
    if state.stage is not GameLifecycleStage.SETUP:
        return True
    if state.setup_step_index is None:
        return True
    muster_step_index = _setup_step_index_or_none(state, SetupStep.MUSTER_ARMIES)
    if muster_step_index is None:
        raise GameLifecycleError("Lifecycle state setup sequence must include MUSTER_ARMIES.")
    return state.setup_step_index > muster_step_index


def _setup_step_index_or_none(state: GameState, step: SetupStep) -> int | None:
    for index, candidate in enumerate(state.setup_sequence):
        if candidate is step:
            return index
    return None
