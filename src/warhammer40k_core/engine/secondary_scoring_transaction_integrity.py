from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
    VictoryPointAward,
    VictoryPointSourceKind,
    VictoryPointTransaction,
)
from warhammer40k_core.engine.secondary_deployment_zone_evidence import (
    bind_state_backed_secondary_scoring_commit,
    enemy_unit_ids_in_player_deployment_zone_for_secondary_boundary,
    require_state_backed_secondary_scoring_commit,
)
from warhammer40k_core.engine.secondary_scoring_provider import (
    SecondaryScoringProviderKind,
    is_registered_phase11f_cap_probe,
    secondary_scoring_provider_kind_from_metadata,
    validate_generic_rule_ir_secondary_award,
    validate_legacy_phase11f_secondary_award,
)
from warhammer40k_core.engine.secondary_victory_point_policy import (
    state_backed_secondary_binding_identity,
    validate_state_backed_secondary_award_binding,
    validate_state_backed_secondary_ledger_binding,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.objective_control import ObjectiveControlRecord

_SECONDARY_SOURCE_KINDS = frozenset(
    {
        VictoryPointSourceKind.FIXED_SECONDARY,
        VictoryPointSourceKind.TACTICAL_SECONDARY,
    }
)


def validate_secondary_award_semantics(
    *,
    state: GameState,
    award: VictoryPointAward,
) -> None:
    """Require a live Secondary award to equal the state-backed policy result."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Secondary VP semantic validation requires GameState.")
    if type(award) is not VictoryPointAward:
        raise GameLifecycleError("Secondary VP semantic validation requires an award.")
    if award.source_kind not in _SECONDARY_SOURCE_KINDS:
        raise GameLifecycleError("Secondary VP semantic validation requires a Secondary award.")
    provider = secondary_scoring_provider_kind_from_metadata(award.metadata)
    if provider is SecondaryScoringProviderKind.LEGACY_PHASE11F:
        scoring_rule_id = _legacy_scoring_rule_id(award.metadata)
        validate_legacy_phase11f_secondary_award(
            award=award,
            expected=_legacy_score_secondary_mission_award(state=state, award=award),
        )
        if is_registered_phase11f_cap_probe(
            source_id=award.source_id,
            scoring_rule_id=scoring_rule_id,
        ):
            _reject_duplicate_phase11f_probe(
                state=state,
                player_id=award.player_id,
                source_id=award.source_id,
                scoring_rule_id=scoring_rule_id,
            )
            return
        card = _card_for_secondary_source(
            state=state,
            player_id=award.player_id,
            source_id=award.source_id,
            source_kind=award.source_kind,
            battle_round=award.battle_round,
            require_scored_transaction_id=None,
        )
        if card.status is not SecondaryMissionCardStatus.ACTIVE:
            raise GameLifecycleError("Legacy Phase 11F Secondary VP requires an active card.")
        return
    if provider is SecondaryScoringProviderKind.GENERIC_RULE_IR:
        validate_generic_rule_ir_secondary_award(award=award)
        return
    binding = validate_state_backed_secondary_award_binding(
        award=award,
        objective_control_records=tuple(state.objective_control_records),
    )
    _reject_duplicate_secondary_binding(state=state, binding=binding)
    if award.source_kind is VictoryPointSourceKind.TACTICAL_SECONDARY:
        _reject_duplicate_tactical_source(
            state=state,
            player_id=award.player_id,
            source_id=award.source_id,
        )
    _card_for_secondary_source(
        state=state,
        player_id=award.player_id,
        source_id=award.source_id,
        source_kind=award.source_kind,
        battle_round=award.battle_round,
        require_scored_transaction_id=None,
    )
    record = _record_for_binding(state=state, binding=binding)
    require_state_backed_secondary_scoring_commit(
        metadata=award.metadata,
        state=state,
        record=record,
    )
    expected = _expected_state_backed_secondary_award(
        state=state,
        player_id=award.player_id,
        source_id=award.source_id,
        source_kind=award.source_kind,
        hidden=award.hidden,
        record=record,
    )
    if expected is None or award != expected:
        raise GameLifecycleError(
            "Secondary VP award drifted from authoritative scoring-state semantics."
        )


def validate_secondary_transaction_semantics(*, state: GameState) -> None:
    """Recompute every state-backed Secondary row and rebind scored Tactical cards."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Secondary VP transaction validation requires GameState.")
    transactions = tuple(
        transaction
        for ledger in state.victory_point_ledgers
        for transaction in ledger.transactions
        if transaction.source_kind in _SECONDARY_SOURCE_KINDS
    )
    seen_bindings: set[tuple[str, VictoryPointSourceKind, str, str]] = set()
    seen_tactical_sources: set[tuple[str, str]] = set()
    seen_probe_keys: set[tuple[str, str, str]] = set()
    for transaction in transactions:
        provider = secondary_scoring_provider_kind_from_metadata(transaction.metadata)
        if provider is SecondaryScoringProviderKind.LEGACY_PHASE11F:
            actual = _uncapped_award_from_transaction(transaction)
            validate_legacy_phase11f_secondary_award(
                award=actual,
                expected=_legacy_score_secondary_mission_award(state=state, award=actual),
            )
            scoring_rule_id = _legacy_scoring_rule_id(actual.metadata)
            if is_registered_phase11f_cap_probe(
                source_id=actual.source_id,
                scoring_rule_id=scoring_rule_id,
            ):
                probe_key = (actual.player_id, actual.source_id, scoring_rule_id)
                if probe_key in seen_probe_keys:
                    raise GameLifecycleError(
                        "Registered Phase 11F Secondary VP probe must not repeat."
                    )
                seen_probe_keys.add(probe_key)
            else:
                _card_for_secondary_source(
                    state=state,
                    player_id=actual.player_id,
                    source_id=actual.source_id,
                    source_kind=actual.source_kind,
                    battle_round=actual.battle_round,
                    require_scored_transaction_id=(
                        transaction.transaction_id
                        if actual.source_kind is VictoryPointSourceKind.TACTICAL_SECONDARY
                        else None
                    ),
                )
            continue
        if provider is SecondaryScoringProviderKind.GENERIC_RULE_IR:
            validate_generic_rule_ir_secondary_award(
                award=_uncapped_award_from_transaction(transaction),
            )
            continue
        if state.mission_setup is None:
            raise GameLifecycleError("Secondary VP semantic validation requires MissionSetup.")
        binding = validate_state_backed_secondary_ledger_binding(
            transaction=transaction,
            objective_control_records=tuple(state.objective_control_records),
        )
        if binding in seen_bindings:
            raise GameLifecycleError(
                "Secondary VP ledger must not repeat a source at one boundary."
            )
        seen_bindings.add(binding)
        if transaction.source_kind is VictoryPointSourceKind.TACTICAL_SECONDARY:
            tactical_key = (transaction.player_id, transaction.source_id)
            if tactical_key in seen_tactical_sources:
                raise GameLifecycleError(
                    "Tactical Secondary VP ledger must not repeat a source across boundaries."
                )
            seen_tactical_sources.add(tactical_key)
        _card_for_secondary_source(
            state=state,
            player_id=transaction.player_id,
            source_id=transaction.source_id,
            source_kind=transaction.source_kind,
            battle_round=transaction.battle_round,
            require_scored_transaction_id=(
                transaction.transaction_id
                if transaction.source_kind is VictoryPointSourceKind.TACTICAL_SECONDARY
                else None
            ),
        )
        record = _record_for_binding(state=state, binding=binding)
        require_state_backed_secondary_scoring_commit(
            metadata=transaction.metadata,
            state=state,
            record=record,
        )
        expected = _expected_state_backed_secondary_award(
            state=state,
            player_id=transaction.player_id,
            source_id=transaction.source_id,
            source_kind=transaction.source_kind,
            hidden=transaction.hidden,
            record=record,
        )
        actual = _uncapped_award_from_transaction(transaction)
        if expected is None or actual != expected:
            raise GameLifecycleError(
                "Secondary VP transactions drifted from authoritative scoring-state semantics."
            )
    _validate_scored_tactical_card_bindings(state=state, transactions=transactions)


def _legacy_scoring_rule_id(metadata: JsonValue) -> str:
    raw = metadata
    if not isinstance(raw, dict):
        raise GameLifecycleError("Secondary VP metadata must be an object.")
    scoring_rule_id = raw.get("scoring_rule_id")
    if type(scoring_rule_id) is not str or not scoring_rule_id:
        raise GameLifecycleError("Legacy Phase 11F Secondary VP requires scoring_rule_id.")
    return scoring_rule_id


def _legacy_score_secondary_mission_award(
    *,
    state: GameState,
    award: VictoryPointAward,
) -> VictoryPointAward | None:
    metadata = award.metadata
    if not isinstance(metadata, dict):
        raise GameLifecycleError("Secondary VP metadata must be an object.")
    scoring_rule_id = metadata.get("scoring_rule_id")
    if type(scoring_rule_id) is not str or not scoring_rule_id:
        raise GameLifecycleError("Legacy Phase 11F Secondary VP requires scoring_rule_id.")
    if is_registered_phase11f_cap_probe(
        source_id=award.source_id,
        scoring_rule_id=scoring_rule_id,
    ):
        return None
    if state.mission_setup is None:
        raise GameLifecycleError("Secondary VP semantic validation requires MissionSetup.")
    policies = mission_scoring_policies_from_setup(state.mission_setup)
    return policies.secondary_award(
        player_id=award.player_id,
        battle_round=award.battle_round,
        phase=award.phase,
        secondary_mission_id=award.source_id,
        source_kind=award.source_kind,
        hidden=award.hidden,
    )


def _reject_duplicate_secondary_binding(
    *,
    state: GameState,
    binding: tuple[str, VictoryPointSourceKind, str, str],
) -> None:
    for ledger in state.victory_point_ledgers:
        for transaction in ledger.transactions:
            existing = state_backed_secondary_binding_identity(
                player_id=transaction.player_id,
                source_kind=transaction.source_kind,
                source_id=transaction.source_id,
                metadata=transaction.metadata,
            )
            if existing == binding:
                raise GameLifecycleError(
                    "Secondary VP ledger must not repeat a source at one boundary."
                )


def _reject_duplicate_phase11f_probe(
    *,
    state: GameState,
    player_id: str,
    source_id: str,
    scoring_rule_id: str,
) -> None:
    for ledger in state.victory_point_ledgers:
        for transaction in ledger.transactions:
            if transaction.player_id != player_id or transaction.source_id != source_id:
                continue
            if (
                secondary_scoring_provider_kind_from_metadata(transaction.metadata)
                is not SecondaryScoringProviderKind.LEGACY_PHASE11F
            ):
                continue
            if _legacy_scoring_rule_id(transaction.metadata) == scoring_rule_id:
                raise GameLifecycleError("Registered Phase 11F Secondary VP probe must not repeat.")


def _reject_duplicate_tactical_source(
    *,
    state: GameState,
    player_id: str,
    source_id: str,
) -> None:
    for ledger in state.victory_point_ledgers:
        for transaction in ledger.transactions:
            if transaction.source_kind is not VictoryPointSourceKind.TACTICAL_SECONDARY:
                continue
            if (
                secondary_scoring_provider_kind_from_metadata(transaction.metadata)
                is not SecondaryScoringProviderKind.STATE_BACKED_OBJECTIVE_CONTROL
            ):
                continue
            if transaction.player_id == player_id and transaction.source_id == source_id:
                raise GameLifecycleError(
                    "Tactical Secondary VP ledger must not repeat a source across boundaries."
                )


def _card_for_secondary_source(
    *,
    state: GameState,
    player_id: str,
    source_id: str,
    source_kind: VictoryPointSourceKind,
    battle_round: int,
    require_scored_transaction_id: str | None,
) -> SecondaryMissionCardState:
    mode = (
        SecondaryMissionCardMode.FIXED
        if source_kind is VictoryPointSourceKind.FIXED_SECONDARY
        else SecondaryMissionCardMode.TACTICAL
    )
    matches = tuple(
        card
        for card in state.secondary_mission_card_states
        if card.player_id == player_id
        and card.secondary_mission_id == source_id
        and card.mode is mode
        and card.status in {SecondaryMissionCardStatus.ACTIVE, SecondaryMissionCardStatus.SCORED}
        and (
            source_kind is VictoryPointSourceKind.FIXED_SECONDARY
            or card.battle_round == battle_round
        )
    )
    if len(matches) != 1:
        raise GameLifecycleError("Secondary VP source does not identify an active or scored card.")
    card = matches[0]
    if require_scored_transaction_id is None:
        return card
    if (
        card.status is not SecondaryMissionCardStatus.SCORED
        or card.scored_transaction_id != require_scored_transaction_id
    ):
        raise GameLifecycleError(
            "Scored tactical secondary card does not identify its ledger transaction."
        )
    return card


def _validate_scored_tactical_card_bindings(
    *,
    state: GameState,
    transactions: tuple[VictoryPointTransaction, ...],
) -> None:
    transactions_by_id = {transaction.transaction_id: transaction for transaction in transactions}
    for card in state.secondary_mission_card_states:
        if card.status is not SecondaryMissionCardStatus.SCORED:
            continue
        if card.mode is not SecondaryMissionCardMode.TACTICAL:
            continue
        if card.scored_transaction_id is None:
            raise GameLifecycleError("Scored secondary card requires scored_transaction_id.")
        transaction = transactions_by_id.get(card.scored_transaction_id)
        if transaction is None:
            raise GameLifecycleError(
                "Scored tactical secondary card does not identify its ledger transaction."
            )
        if (
            transaction.player_id != card.player_id
            or transaction.source_kind is not VictoryPointSourceKind.TACTICAL_SECONDARY
            or transaction.source_id != card.secondary_mission_id
        ):
            raise GameLifecycleError(
                "Scored tactical secondary card does not identify its ledger transaction."
            )
        provider = secondary_scoring_provider_kind_from_metadata(transaction.metadata)
        if provider is SecondaryScoringProviderKind.GENERIC_RULE_IR:
            raise GameLifecycleError(
                "Scored tactical secondary card cannot bind a generic RuleIR transaction."
            )
        if provider is SecondaryScoringProviderKind.STATE_BACKED_OBJECTIVE_CONTROL:
            validate_state_backed_secondary_ledger_binding(
                transaction=transaction,
                objective_control_records=tuple(state.objective_control_records),
            )


def _expected_state_backed_secondary_award(
    *,
    state: GameState,
    player_id: str,
    source_id: str,
    source_kind: VictoryPointSourceKind,
    hidden: bool,
    record: ObjectiveControlRecord,
) -> VictoryPointAward | None:
    if state.mission_setup is None:
        raise GameLifecycleError("Secondary VP semantic validation requires MissionSetup.")
    policies = mission_scoring_policies_from_setup(state.mission_setup)
    award = policies.secondary_award_from_mission_state(
        player_id=player_id,
        battle_round=record.battle_round,
        phase=record.phase,
        secondary_mission_id=source_id,
        source_kind=source_kind,
        hidden=hidden,
        record=record,
        mission_setup=state.mission_setup,
        unit_destruction_states=tuple(state.secondary_unit_destruction_states),
        objective_cleanse_states=tuple(state.secondary_objective_cleanse_states),
        terrain_plunder_states=tuple(state.secondary_terrain_plunder_states),
        enemy_unit_ids_in_player_deployment_zone=(
            enemy_unit_ids_in_player_deployment_zone_for_secondary_boundary(
                state=state,
                record=record,
                player_id=player_id,
            )
        ),
        starting_strength_records=tuple(state.starting_strength_records),
    )
    if award is None:
        return None
    return bind_state_backed_secondary_scoring_commit(award, state=state, record=record)


def _record_for_binding(
    *,
    state: GameState,
    binding: tuple[str, VictoryPointSourceKind, str, str],
) -> ObjectiveControlRecord:
    matches = tuple(
        record for record in state.objective_control_records if record.record_id == binding[3]
    )
    if len(matches) != 1:
        raise GameLifecycleError(
            "Secondary VP semantic validation requires one objective-control boundary."
        )
    return matches[0]


def _uncapped_award_from_transaction(
    transaction: VictoryPointTransaction,
) -> VictoryPointAward:
    metadata: JsonValue = transaction.metadata
    requested_amount = transaction.amount
    if isinstance(metadata, dict) and "vp_cap_audit" in metadata:
        cap_audit = metadata["vp_cap_audit"]
        if not isinstance(cap_audit, dict):
            raise GameLifecycleError("Secondary VP transaction cap audit must be an object.")
        requested_amount_value = cap_audit.get("requested_amount")
        applied_amount = cap_audit.get("applied_amount")
        if type(requested_amount_value) is not int or requested_amount_value <= 0:
            raise GameLifecycleError(
                "Secondary VP transaction cap audit requires positive requested_amount."
            )
        if type(applied_amount) is not int or applied_amount != transaction.amount:
            raise GameLifecycleError("Secondary VP transaction cap audit applied_amount drifted.")
        if applied_amount > requested_amount_value:
            raise GameLifecycleError(
                "Secondary VP transaction cap audit applied_amount exceeds requested_amount."
            )
        requested_amount = requested_amount_value
        restored_metadata = dict(metadata)
        restored_metadata.pop("vp_cap_audit")
        metadata = restored_metadata
    return VictoryPointAward(
        player_id=transaction.player_id,
        battle_round=transaction.battle_round,
        phase=transaction.phase,
        amount=requested_amount,
        source_kind=transaction.source_kind,
        source_id=transaction.source_id,
        scoring_timing=transaction.scoring_timing,
        hidden=transaction.hidden,
        metadata=metadata,
    )


__all__ = (
    "validate_secondary_award_semantics",
    "validate_secondary_transaction_semantics",
)
