from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, Self, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.reserves import ReserveOrigin
from warhammer40k_core.engine.turn_end_hooks import (
    SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.stratagems_model import StratagemUseRecord


PRIMARY_RESERVE_ENTRY_PROVIDER_RESOLVED_EVENT = "primary_reserve_entry_provider_resolved"
GENERIC_RULE_IR_RESERVE_REMOVAL_PROVIDER_ID = "generic:rule-ir:reserve-removal"
GENERIC_STRATAGEM_RESERVE_REMOVAL_RESOLVED_EVENT = "generic_stratagem_reserve_removal_resolved"

_PROVIDER_PAYLOAD_KEYS = frozenset(
    (
        "provider_kind",
        "provider_id",
        "player_id",
        "source_rule_id",
        "target_rules_unit_instance_id",
        "decision_record_id",
        "decision_request_id",
        "decision_result_id",
        "stratagem_use_id",
        "source_terminal_event_type",
    )
)


class PrimaryReserveEntryProviderKind(StrEnum):
    TURN_END_ABILITY = "turn_end_ability"
    GENERIC_RULE_IR_STRATAGEM = "generic_rule_ir_stratagem"


class PrimaryReserveEntryAbilityAuthorityKind(StrEnum):
    CATALOG_RULE_IR = "catalog_rule_ir"
    DATASHEET_ABILITY = "datasheet_ability"
    ENHANCEMENT_ASSIGNMENT = "enhancement_assignment"


class PrimaryReserveEntryComponentMatchPolicy(StrEnum):
    ANY_COMPONENT = "any_component"
    ALL_COMPONENTS = "all_components"


@dataclass(frozen=True, slots=True)
class PrimaryReserveEntryAbilityProviderDefinition:
    provider_id: str
    source_terminal_event_type: str
    authority_kind: PrimaryReserveEntryAbilityAuthorityKind
    source_rule_id: str | None = None
    content_id: str | None = None
    component_match_policy: PrimaryReserveEntryComponentMatchPolicy = (
        PrimaryReserveEntryComponentMatchPolicy.ANY_COMPONENT
    )
    terminal_static_identity: tuple[tuple[str, JsonValue], ...] = ()
    terminal_request_identity_keys: tuple[str, ...] = ()
    terminal_result_identity_keys: tuple[str, ...] = ()
    required_arrival_timing: str | None = None
    required_arrival_phase: str | None = None
    required_arrival_source_rule_id: str | None = None
    required_arrival_placement_kind: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_id",
            _validate_identifier("ability provider definition ID", self.provider_id),
        )
        object.__setattr__(
            self,
            "source_terminal_event_type",
            _validate_identifier(
                "ability provider terminal event type",
                self.source_terminal_event_type,
            ),
        )
        for field_name in (
            "required_arrival_timing",
            "required_arrival_phase",
            "required_arrival_source_rule_id",
            "required_arrival_placement_kind",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_optional_identifier(field_name, getattr(self, field_name)),
            )
        arrival_values = (
            self.required_arrival_timing,
            self.required_arrival_phase,
            self.required_arrival_source_rule_id,
        )
        if any(value is not None for value in arrival_values) and any(
            value is None for value in arrival_values
        ):
            raise GameLifecycleError("Ability provider required arrival is incomplete.")
        if type(self.authority_kind) is not PrimaryReserveEntryAbilityAuthorityKind:
            raise GameLifecycleError("Ability provider authority kind is invalid.")
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_optional_identifier("ability provider source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "content_id",
            _validate_optional_identifier("ability provider content_id", self.content_id),
        )
        if type(self.component_match_policy) is not PrimaryReserveEntryComponentMatchPolicy:
            raise GameLifecycleError("Ability provider component match policy is invalid.")
        if self.authority_kind is PrimaryReserveEntryAbilityAuthorityKind.CATALOG_RULE_IR:
            if self.source_rule_id is not None or self.content_id is not None:
                raise GameLifecycleError("Catalog ability provider definition is malformed.")
        elif self.source_rule_id is None or self.content_id is None:
            raise GameLifecycleError("Source-specific ability provider definition is incomplete.")
        if (
            self.authority_kind is not PrimaryReserveEntryAbilityAuthorityKind.DATASHEET_ABILITY
            and self.component_match_policy
            is not PrimaryReserveEntryComponentMatchPolicy.ANY_COMPONENT
        ):
            raise GameLifecycleError("Only Datasheet ability providers can require all components.")
        object.__setattr__(
            self,
            "terminal_static_identity",
            _validate_terminal_static_identity(self.terminal_static_identity),
        )
        object.__setattr__(
            self,
            "terminal_request_identity_keys",
            _validate_identifier_tuple(
                "terminal request identity keys", self.terminal_request_identity_keys
            ),
        )
        object.__setattr__(
            self,
            "terminal_result_identity_keys",
            _validate_identifier_tuple(
                "terminal result identity keys", self.terminal_result_identity_keys
            ),
        )


@dataclass(frozen=True, slots=True)
class PrimaryReserveEntryRequirements:
    required_arrival_battle_round: int | None = None
    required_arrival_phase: str | None = None
    required_arrival_source_rule_id: str | None = None
    required_arrival_placement_kind: str | None = None


@dataclass(frozen=True, slots=True)
class PrimaryReserveEntryLifecycleOccurrence:
    event_order: int
    historical_unit_instance_id: str
    reserve_entry_state: dict[str, JsonValue]


class PrimaryReserveEntryOccurrenceValidator(Protocol):
    def __call__(
        self,
        *,
        state: object,
        event_records: tuple[EventRecord, ...],
        decision_records: tuple[DecisionRecord, ...],
        event_index_by_id: dict[str, int],
    ) -> tuple[PrimaryReserveEntryLifecycleOccurrence, ...]: ...


@dataclass(frozen=True, slots=True)
class PrimaryReserveEntryProvider:
    """Typed authority for one during-battle Strategic Reserves mutation."""

    provider_kind: PrimaryReserveEntryProviderKind
    provider_id: str
    player_id: str
    source_rule_id: str
    target_rules_unit_instance_id: str
    decision_record_id: str
    decision_request_id: str
    decision_result_id: str
    stratagem_use_id: str | None
    source_terminal_event_type: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_kind",
            primary_reserve_entry_provider_kind_from_token(self.provider_kind),
        )
        for field_name in (
            "provider_id",
            "player_id",
            "source_rule_id",
            "target_rules_unit_instance_id",
            "decision_record_id",
            "decision_request_id",
            "decision_result_id",
            "source_terminal_event_type",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_identifier(field_name, getattr(self, field_name)),
            )
        object.__setattr__(
            self,
            "stratagem_use_id",
            _validate_optional_identifier("stratagem_use_id", self.stratagem_use_id),
        )
        if self.provider_kind is PrimaryReserveEntryProviderKind.TURN_END_ABILITY:
            if self.stratagem_use_id is not None:
                raise GameLifecycleError(
                    "Turn-end ability reserve provider cannot name a Stratagem use."
                )
        elif self.stratagem_use_id is None:
            raise GameLifecycleError(
                "Generic RuleIR Stratagem reserve provider requires a Stratagem use."
            )
        if self.provider_kind is PrimaryReserveEntryProviderKind.GENERIC_RULE_IR_STRATAGEM and (
            self.provider_id != GENERIC_RULE_IR_RESERVE_REMOVAL_PROVIDER_ID
            or self.source_terminal_event_type != GENERIC_STRATAGEM_RESERVE_REMOVAL_RESOLVED_EVENT
        ):
            raise GameLifecycleError("Generic RuleIR Stratagem reserve provider identity drift.")

    @property
    def reserve_origin(self) -> ReserveOrigin:
        if self.provider_kind is PrimaryReserveEntryProviderKind.TURN_END_ABILITY:
            return ReserveOrigin.DURING_BATTLE_ABILITY
        return ReserveOrigin.DURING_BATTLE_STRATAGEM

    @property
    def occurrence_id(self) -> str:
        source_occurrence_id = (
            self.decision_result_id if self.stratagem_use_id is None else self.stratagem_use_id
        )
        return f"{source_occurrence_id}:reserve-entry:{self.target_rules_unit_instance_id}"

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "provider_kind": self.provider_kind.value,
            "provider_id": self.provider_id,
            "player_id": self.player_id,
            "source_rule_id": self.source_rule_id,
            "target_rules_unit_instance_id": self.target_rules_unit_instance_id,
            "decision_record_id": self.decision_record_id,
            "decision_request_id": self.decision_request_id,
            "decision_result_id": self.decision_result_id,
            "stratagem_use_id": self.stratagem_use_id,
            "source_terminal_event_type": self.source_terminal_event_type,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if not isinstance(payload, dict):
            raise GameLifecycleError("Primary reserve-entry provider payload is malformed.")
        value = cast(dict[str, object], payload)
        if set(value) != set(_PROVIDER_PAYLOAD_KEYS):
            raise GameLifecycleError("Primary reserve-entry provider payload is malformed.")
        return cls(
            provider_kind=primary_reserve_entry_provider_kind_from_token(value["provider_kind"]),
            provider_id=_validate_identifier("provider_id", value["provider_id"]),
            player_id=_validate_identifier("player_id", value["player_id"]),
            source_rule_id=_validate_identifier("source_rule_id", value["source_rule_id"]),
            target_rules_unit_instance_id=_validate_identifier(
                "target_rules_unit_instance_id",
                value["target_rules_unit_instance_id"],
            ),
            decision_record_id=_validate_identifier(
                "decision_record_id", value["decision_record_id"]
            ),
            decision_request_id=_validate_identifier(
                "decision_request_id", value["decision_request_id"]
            ),
            decision_result_id=_validate_identifier(
                "decision_result_id", value["decision_result_id"]
            ),
            stratagem_use_id=_validate_optional_identifier(
                "stratagem_use_id", value["stratagem_use_id"]
            ),
            source_terminal_event_type=_validate_identifier(
                "source_terminal_event_type", value["source_terminal_event_type"]
            ),
        )


def primary_reserve_entry_provider_from_accepted_ability_decision(
    *,
    state: object,
    decisions: DecisionController,
    result: DecisionResult,
    provider_id: str,
    source_rule_id: str,
    target_rules_unit_instance_id: str,
    source_terminal_event_type: str,
) -> PrimaryReserveEntryProvider:
    """Build an ability provider only from the controller's accepted result."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Ability reserve provider requires GameState.")
    if type(decisions) is not DecisionController or type(result) is not DecisionResult:
        raise GameLifecycleError("Ability reserve provider requires accepted decision context.")
    record = _accepted_decision_record(decisions=decisions, result=result)
    requested_provider_id = _validate_identifier("provider_id", provider_id)
    requested_source_rule_id = _validate_identifier("source_rule_id", source_rule_id)
    requested_target_id = _validate_identifier(
        "target_rules_unit_instance_id", target_rules_unit_instance_id
    )
    if (
        record.request.decision_type != SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE
        or record.result.decision_type != SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE
        or record.result.actor_id is None
    ):
        raise GameLifecycleError("Ability reserve provider requires a turn-end decision.")
    request_payload = _payload_object(record.request.payload, field_name="ability request")
    result_payload = _payload_object(record.result.payload, field_name="ability result")
    selected_target_id = _ability_result_target_id(result_payload)
    if (
        request_payload.get("source_rule_id") != requested_source_rule_id
        or request_payload.get("hook_id") != requested_provider_id
        or result_payload.get("source_rule_id") != requested_source_rule_id
        or result_payload.get("hook_id") != requested_provider_id
        or result_payload.get("player_id") != record.result.actor_id
        or result_payload.get("use_ability") is not True
        or not _rules_unit_identity_matches(
            state=state,
            first_unit_instance_id=selected_target_id,
            second_unit_instance_id=requested_target_id,
        )
    ):
        raise GameLifecycleError("Ability reserve provider decision context drift.")
    provider = PrimaryReserveEntryProvider(
        provider_kind=PrimaryReserveEntryProviderKind.TURN_END_ABILITY,
        provider_id=requested_provider_id,
        player_id=record.result.actor_id,
        source_rule_id=requested_source_rule_id,
        target_rules_unit_instance_id=requested_target_id,
        decision_record_id=record.record_id,
        decision_request_id=record.request.request_id,
        decision_result_id=record.result.result_id,
        stratagem_use_id=None,
        source_terminal_event_type=source_terminal_event_type,
    )
    validate_primary_reserve_entry_provider_registration(state=state, provider=provider)
    return provider


def primary_reserve_entry_provider_from_accepted_stratagem_use(
    *,
    state: object,
    decisions: DecisionController,
    use_record: StratagemUseRecord,
    source_rule_id: str,
    target_rules_unit_instance_id: str,
    executed_effect_payload: JsonValue,
) -> PrimaryReserveEntryProvider:
    """Build a generic RuleIR Stratagem provider from its accepted use record."""
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagems_model import (
        GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
        STRATAGEM_DECISION_TYPE,
        STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
        StratagemUseRecord,
    )

    if (
        type(state) is not GameState
        or type(decisions) is not DecisionController
        or type(use_record) is not StratagemUseRecord
    ):
        raise GameLifecycleError("Stratagem reserve provider requires accepted use context.")
    result = _decision_result_for_use(decisions=decisions, use_record=use_record)
    record = _accepted_decision_record(decisions=decisions, result=result)
    requested_source_rule_id = _validate_identifier("source_rule_id", source_rule_id)
    requested_target_id = _validate_identifier(
        "target_rules_unit_instance_id", target_rules_unit_instance_id
    )
    use_target_ids = set(use_record.targeted_unit_instance_ids) | set(
        use_record.affected_unit_instance_ids
    )
    if (
        record.request.decision_type
        not in {STRATAGEM_DECISION_TYPE, STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE}
        or record.result.decision_type != record.request.decision_type
        or record.result.actor_id != use_record.player_id
        or record.request.request_id != use_record.request_id
        or record.result.result_id != use_record.result_id
        or record.result.selected_option_id != use_record.selected_option_id
        or use_record.handler_id != GENERIC_RULE_IR_STRATAGEM_HANDLER_ID
        or not use_record.effects_resolved
        or not _rules_unit_identity_matches_any(
            state=state,
            unit_instance_id=requested_target_id,
            candidate_unit_instance_ids=use_target_ids,
        )
    ):
        raise GameLifecycleError("Generic RuleIR Stratagem reserve provider context drift.")
    provider = PrimaryReserveEntryProvider(
        provider_kind=PrimaryReserveEntryProviderKind.GENERIC_RULE_IR_STRATAGEM,
        provider_id=GENERIC_RULE_IR_RESERVE_REMOVAL_PROVIDER_ID,
        player_id=use_record.player_id,
        source_rule_id=requested_source_rule_id,
        target_rules_unit_instance_id=requested_target_id,
        decision_record_id=record.record_id,
        decision_request_id=record.request.request_id,
        decision_result_id=record.result.result_id,
        stratagem_use_id=use_record.use_id,
        source_terminal_event_type=GENERIC_STRATAGEM_RESERVE_REMOVAL_RESOLVED_EVENT,
    )
    _validate_stratagem_provider_authority(
        state=state,
        decisions=decisions,
        provider=provider,
        record=record,
        use_record=use_record,
        executed_effect_payload=executed_effect_payload,
    )
    return provider


def validate_accepted_primary_reserve_entry_provider(
    *,
    state: object,
    decisions: DecisionController,
    provider: PrimaryReserveEntryProvider,
) -> None:
    """Re-authenticate a provider immediately before its engine mutation."""
    from warhammer40k_core.engine.game_state import GameState

    if (
        type(state) is not GameState
        or type(decisions) is not DecisionController
        or type(provider) is not PrimaryReserveEntryProvider
    ):
        raise GameLifecycleError("Reserve-entry mutation requires typed provider authority.")
    record = _accepted_decision_record_for_provider(decisions=decisions, provider=provider)
    validate_primary_reserve_entry_provider_registration(state=state, provider=provider)
    if provider.provider_kind is PrimaryReserveEntryProviderKind.TURN_END_ABILITY:
        request_payload = _payload_object(record.request.payload, field_name="ability request")
        result_payload = _payload_object(record.result.payload, field_name="ability result")
        selected_target_id = _ability_result_target_id(result_payload)
        if (
            record.request.decision_type != SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE
            or record.result.decision_type != SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE
            or record.result.actor_id != provider.player_id
            or request_payload.get("source_rule_id") != provider.source_rule_id
            or request_payload.get("hook_id") != provider.provider_id
            or result_payload.get("source_rule_id") != provider.source_rule_id
            or result_payload.get("hook_id") != provider.provider_id
            or result_payload.get("player_id") != provider.player_id
            or result_payload.get("use_ability") is not True
            or not _rules_unit_identity_matches(
                state=state,
                first_unit_instance_id=selected_target_id,
                second_unit_instance_id=provider.target_rules_unit_instance_id,
            )
        ):
            raise GameLifecycleError("Ability reserve provider accepted context drift.")
        return
    if provider.stratagem_use_id is None:
        raise GameLifecycleError("Stratagem reserve provider use identity is missing.")
    uses = tuple(
        use for use in state.stratagem_use_records if use.use_id == provider.stratagem_use_id
    )
    if len(uses) != 1:
        raise GameLifecycleError("Stratagem reserve provider use identity is missing.")
    executed_effect_event = _executed_reserve_effect_event(
        state=state,
        decisions=decisions,
        provider=provider,
        use_record=uses[0],
    )
    _validate_stratagem_provider_authority(
        state=state,
        decisions=decisions,
        provider=provider,
        record=record,
        use_record=uses[0],
        executed_effect_payload=executed_effect_event.payload,
    )


def primary_reserve_entry_requirements(
    *,
    state: object,
    decisions: DecisionController,
    provider: PrimaryReserveEntryProvider,
) -> PrimaryReserveEntryRequirements:
    """Derive exact arrival constraints from the authenticated source provider."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState or type(decisions) is not DecisionController:
        raise GameLifecycleError("Reserve-entry requirements require typed authority.")
    if provider.provider_kind is PrimaryReserveEntryProviderKind.TURN_END_ABILITY:
        return primary_reserve_entry_requirements_from_evidence(
            state=state,
            provider=provider,
            executed_effect_payload=None,
            entry_battle_round=state.battle_round,
            entry_active_player_id=state.active_player_id,
        )
    if provider.stratagem_use_id is None:
        raise GameLifecycleError("Stratagem reserve-entry requirements lack use identity.")
    uses = tuple(
        use for use in state.stratagem_use_records if use.use_id == provider.stratagem_use_id
    )
    if len(uses) != 1:
        raise GameLifecycleError("Stratagem reserve-entry requirements lack exact use.")
    effect_event = _executed_reserve_effect_event(
        state=state,
        decisions=decisions,
        provider=provider,
        use_record=uses[0],
    )
    return primary_reserve_entry_requirements_from_evidence(
        state=state,
        provider=provider,
        executed_effect_payload=effect_event.payload,
        entry_battle_round=state.battle_round,
        entry_active_player_id=state.active_player_id,
    )


def primary_reserve_entry_requirements_from_evidence(
    *,
    state: object,
    provider: PrimaryReserveEntryProvider,
    executed_effect_payload: JsonValue,
    entry_battle_round: int,
    entry_active_player_id: str | None,
) -> PrimaryReserveEntryRequirements:
    """Derive arrival constraints from replay-authenticated provider evidence."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState or type(provider) is not PrimaryReserveEntryProvider:
        raise GameLifecycleError("Reserve-entry evidence requirements require typed authority.")
    if provider.provider_kind is PrimaryReserveEntryProviderKind.TURN_END_ABILITY:
        if executed_effect_payload is not None:
            raise GameLifecycleError("Ability reserve-entry requirements cannot name RuleIR.")
        from warhammer40k_core.engine.primary_reserve_entry_provider_defaults import (
            default_primary_reserve_entry_ability_provider_definitions,
        )

        definitions = tuple(
            definition
            for definition in default_primary_reserve_entry_ability_provider_definitions()
            if definition.provider_id == provider.provider_id
            and definition.source_terminal_event_type == provider.source_terminal_event_type
        )
        if len(definitions) != 1:
            raise GameLifecycleError("Ability reserve-entry requirements are not registered.")
        definition = definitions[0]
        return PrimaryReserveEntryRequirements(
            required_arrival_battle_round=_required_arrival_round(
                state=state,
                player_id=provider.player_id,
                timing=definition.required_arrival_timing,
                round_offset=None,
                battle_round=entry_battle_round,
                active_player_id=entry_active_player_id,
            ),
            required_arrival_phase=definition.required_arrival_phase,
            required_arrival_source_rule_id=definition.required_arrival_source_rule_id,
            required_arrival_placement_kind=definition.required_arrival_placement_kind,
        )
    if executed_effect_payload is None:
        raise GameLifecycleError("Stratagem reserve-entry requirements require RuleIR evidence.")
    effect_payload = _payload_object(
        executed_effect_payload,
        field_name="reserve-entry requirements effect",
    )
    effect = _payload_object(
        effect_payload.get("effect"),
        field_name="reserve-entry requirements descriptor",
    )
    parameters = _rule_effect_parameters(effect)
    round_offset = _optional_int_parameter(parameters, "required_arrival_battle_round_offset")
    timing = _optional_string_parameter(parameters, "required_arrival_timing")
    if round_offset is not None and timing is not None:
        raise GameLifecycleError("Reserve-entry requirements use two arrival timings.")
    required_round = _required_arrival_round(
        state=state,
        player_id=provider.player_id,
        timing=timing,
        round_offset=round_offset,
        battle_round=entry_battle_round,
        active_player_id=entry_active_player_id,
    )
    required_phase = _optional_string_parameter(parameters, "required_arrival_phase")
    required_source = _optional_string_parameter(parameters, "required_arrival_source_rule_id")
    required_placement = _optional_string_parameter(parameters, "required_arrival_placement_kind")
    required_fields = (required_round, required_phase, required_source)
    if any(value is not None for value in required_fields) and any(
        value is None for value in required_fields
    ):
        raise GameLifecycleError("Reserve-entry requirements are incomplete.")
    return PrimaryReserveEntryRequirements(
        required_arrival_battle_round=required_round,
        required_arrival_phase=required_phase,
        required_arrival_source_rule_id=required_source,
        required_arrival_placement_kind=required_placement,
    )


def validate_primary_reserve_entry_provider_registration(
    *,
    state: object,
    provider: PrimaryReserveEntryProvider,
) -> None:
    """Require a source-backed runtime route for an ability provider envelope."""
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.primary_reserve_entry_provider_defaults import (
        default_primary_reserve_entry_ability_provider_definitions,
    )
    from warhammer40k_core.engine.rules_units import current_rules_unit_views_for_identity

    if type(state) is not GameState or type(provider) is not PrimaryReserveEntryProvider:
        raise GameLifecycleError("Reserve-entry provider registration requires typed state.")
    if provider.provider_kind is not PrimaryReserveEntryProviderKind.TURN_END_ABILITY:
        return
    definitions = tuple(
        definition
        for definition in default_primary_reserve_entry_ability_provider_definitions()
        if definition.provider_id == provider.provider_id
        and definition.source_terminal_event_type == provider.source_terminal_event_type
    )
    if len(definitions) != 1:
        raise GameLifecycleError("Turn-end ability reserve provider is not registered.")
    definition = definitions[0]
    if definition.source_rule_id is not None and (
        definition.source_rule_id != provider.source_rule_id
    ):
        raise GameLifecycleError("Turn-end ability reserve provider source drift.")
    rules_unit_views = current_rules_unit_views_for_identity(
        state=state,
        unit_instance_id=provider.target_rules_unit_instance_id,
    )
    if {view.owner_player_id for view in rules_unit_views} != {provider.player_id}:
        raise GameLifecycleError("Turn-end ability reserve provider target drift.")
    if definition.authority_kind is PrimaryReserveEntryAbilityAuthorityKind.CATALOG_RULE_IR:
        _validate_catalog_rule_ir_authority(
            provider=provider,
            rules_unit_views=rules_unit_views,
        )
        return
    if definition.authority_kind is PrimaryReserveEntryAbilityAuthorityKind.DATASHEET_ABILITY:
        component_matches = tuple(
            any(
                ability.ability_id == definition.content_id
                and ability.source_id == provider.source_rule_id
                for ability in component.unit.datasheet_abilities
            )
            for rules_unit_view in rules_unit_views
            for component in rules_unit_view.living_components
        )
        authority_matches = (
            bool(component_matches) and all(component_matches)
            if definition.component_match_policy
            is PrimaryReserveEntryComponentMatchPolicy.ALL_COMPONENTS
            else any(component_matches)
        )
        if not authority_matches:
            raise GameLifecycleError(
                "Turn-end reserve provider lacks its Datasheet ability authority."
            )
        return
    army = next(
        (
            candidate
            for candidate in state.army_definitions
            if candidate.player_id == provider.player_id
        ),
        None,
    )
    if army is None:
        raise GameLifecycleError("Turn-end reserve provider player army is missing.")
    component_unit_ids = {
        component.unit.unit_instance_id
        for rules_unit_view in rules_unit_views
        for component in rules_unit_view.living_components
    }
    if not any(
        assignment.enhancement_id == definition.content_id
        and f"{army.army_id}:{assignment.target_unit_selection_id}" in component_unit_ids
        for assignment in army.enhancement_assignments
    ):
        raise GameLifecycleError(
            "Turn-end reserve provider lacks its Enhancement assignment authority."
        )


def validate_primary_reserve_entry_source_terminal_identity(
    *,
    state: object,
    provider: PrimaryReserveEntryProvider,
    decision: DecisionRecord,
    terminal_payload: dict[str, JsonValue],
    reserve_entry: dict[str, JsonValue],
) -> None:
    """Apply the registered source owner's immutable terminal contract."""
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.primary_reserve_entry_provider_defaults import (
        default_primary_reserve_entry_ability_provider_definitions,
    )
    from warhammer40k_core.engine.rules_units import current_rules_unit_views_for_identity

    if (
        type(state) is not GameState
        or type(provider) is not PrimaryReserveEntryProvider
        or type(decision) is not DecisionRecord
        or provider.provider_kind is not PrimaryReserveEntryProviderKind.TURN_END_ABILITY
    ):
        raise GameLifecycleError("Ability reserve terminal identity requires typed authority.")
    definitions = tuple(
        definition
        for definition in default_primary_reserve_entry_ability_provider_definitions()
        if definition.provider_id == provider.provider_id
        and definition.source_terminal_event_type == provider.source_terminal_event_type
    )
    if len(definitions) != 1:
        raise GameLifecycleError("Ability reserve terminal provider is not registered.")
    definition = definitions[0]
    request_payload = _payload_object(
        decision.request.payload,
        field_name="ability terminal request",
    )
    result_payload = _payload_object(
        decision.result.payload,
        field_name="ability terminal result",
    )
    for key, value in definition.terminal_static_identity:
        if terminal_payload.get(key) != value:
            raise GameLifecycleError("Ability reserve source terminal static identity drift.")
    for key in definition.terminal_request_identity_keys:
        if key not in request_payload or terminal_payload.get(key) != request_payload[key]:
            raise GameLifecycleError("Ability reserve source terminal request identity drift.")
    for key in definition.terminal_result_identity_keys:
        if key not in result_payload or terminal_payload.get(key) != result_payload[key]:
            raise GameLifecycleError("Ability reserve source terminal result identity drift.")
    if definition.authority_kind is PrimaryReserveEntryAbilityAuthorityKind.CATALOG_RULE_IR:
        rules_units = current_rules_unit_views_for_identity(
            state=state,
            unit_instance_id=provider.target_rules_unit_instance_id,
        )
        abilities = tuple(
            ability
            for rules_unit in rules_units
            for component in rules_unit.living_components
            for ability in component.unit.datasheet_abilities
            if ability.source_id == provider.source_rule_id
        )
        identities = {(ability.ability_id, ability.name) for ability in abilities}
        if (
            len(identities) != 1
            or (terminal_payload.get("ability_id"), terminal_payload.get("ability_name"))
            not in identities
        ):
            raise GameLifecycleError("Catalog reserve source terminal ability identity drift.")
    if "required_arrival_battle_round" in terminal_payload and terminal_payload.get(
        "required_arrival_battle_round"
    ) != reserve_entry.get("required_arrival_battle_round"):
        raise GameLifecycleError("Ability reserve source terminal arrival round drift.")
    if "required_arrival_phase" in terminal_payload and terminal_payload.get(
        "required_arrival_phase"
    ) != reserve_entry.get("required_arrival_phase"):
        raise GameLifecycleError("Ability reserve source terminal arrival phase drift.")


def _validate_catalog_rule_ir_authority(
    *, provider: PrimaryReserveEntryProvider, rules_unit_views: object
) -> None:
    from warhammer40k_core.core.datasheet import CatalogAbilitySupport
    from warhammer40k_core.engine.catalog_rule_consumption import (
        CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
        catalog_rule_ir_consumers_for_rule,
    )
    from warhammer40k_core.engine.rules_units import RulesUnitView
    from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRPayload

    if type(rules_unit_views) is not tuple:
        raise GameLifecycleError("Catalog reserve provider requires rules-unit views.")
    raw_views = cast(tuple[object, ...], rules_unit_views)
    if any(type(rules_unit_view) is not RulesUnitView for rules_unit_view in raw_views):
        raise GameLifecycleError("Catalog reserve provider requires rules-unit views.")
    typed_views = cast(tuple[RulesUnitView, ...], raw_views)
    matching_abilities = tuple(
        ability
        for rules_unit_view in typed_views
        for component in rules_unit_view.living_components
        for ability in component.unit.datasheet_abilities
        if ability.source_id == provider.source_rule_id
        and ability.support is CatalogAbilitySupport.GENERIC_RULE_IR
        and ability.rule_ir_payload is not None
    )
    if len(matching_abilities) != 1:
        raise GameLifecycleError("Catalog reserve provider source ability is ambiguous.")
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, matching_abilities[0].rule_ir_payload))
    if (
        provider.provider_id != CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID
        or provider.provider_id not in catalog_rule_ir_consumers_for_rule(rule_ir)
    ):
        raise GameLifecycleError("Catalog reserve provider RuleIR authority drift.")


def primary_reserve_entry_provider_kind_from_token(
    value: object,
) -> PrimaryReserveEntryProviderKind:
    if type(value) is PrimaryReserveEntryProviderKind:
        return value
    if type(value) is not str:
        raise GameLifecycleError("Primary reserve-entry provider kind must be a string.")
    try:
        return PrimaryReserveEntryProviderKind(value)
    except ValueError as exc:
        raise GameLifecycleError("Primary reserve-entry provider kind is unsupported.") from exc


def _accepted_decision_record(
    *, decisions: DecisionController, result: DecisionResult
) -> DecisionRecord:
    try:
        record = decisions.record_for_result(result)
    except DecisionError as exc:
        raise GameLifecycleError("Reserve provider result was not accepted.") from exc
    requested_events = tuple(
        (index, event)
        for index, event in enumerate(decisions.event_log.records)
        if event.event_type == "decision_requested" and event.payload == record.request.to_payload()
    )
    recorded_events = tuple(
        (index, event)
        for index, event in enumerate(decisions.event_log.records)
        if event.event_type == "decision_recorded" and event.payload == record.to_payload()
    )
    if len(requested_events) != 1 or len(recorded_events) != 1:
        raise GameLifecycleError(
            "Reserve provider requires exact requested and recorded decision events."
        )
    if requested_events[0][0] >= recorded_events[0][0]:
        raise GameLifecycleError("Reserve provider decision event ordering drift.")
    return record


def _accepted_decision_record_for_provider(
    *,
    decisions: DecisionController,
    provider: PrimaryReserveEntryProvider,
) -> DecisionRecord:
    matches = tuple(
        record
        for record in decisions.records
        if record.record_id == provider.decision_record_id
        and record.request.request_id == provider.decision_request_id
        and record.result.result_id == provider.decision_result_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Reserve-entry provider accepted decision is missing.")
    return _accepted_decision_record(decisions=decisions, result=matches[0].result)


def _validate_stratagem_provider_authority(
    *,
    state: object,
    decisions: DecisionController,
    provider: PrimaryReserveEntryProvider,
    record: DecisionRecord,
    use_record: StratagemUseRecord,
    executed_effect_payload: JsonValue,
) -> None:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.primary_reserve_rule_ir_integrity import (
        validate_exact_primary_reserve_rule_ir_placement_effect,
    )
    from warhammer40k_core.engine.rule_execution import scoped_rule_ir_from_execution_payload
    from warhammer40k_core.engine.stratagems_eligibility import derive_stratagem_use_unit_ids
    from warhammer40k_core.engine.stratagems_model import (
        GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
        STRATAGEM_DECISION_TYPE,
        STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
        StratagemUseRecord,
    )
    from warhammer40k_core.engine.stratagems_selection import (
        stratagem_selection_from_decision_result,
        stratagem_selection_from_target_proposal_result,
    )

    if type(state) is not GameState or type(use_record) is not StratagemUseRecord:
        raise GameLifecycleError("Stratagem reserve provider authority requires typed state.")
    if record.request.decision_type == STRATAGEM_DECISION_TYPE:
        selection = stratagem_selection_from_decision_result(record.result)
    elif record.request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
        selection = stratagem_selection_from_target_proposal_result(record.result)
    else:
        raise GameLifecycleError("Stratagem reserve provider decision type drift.")
    if selection is None:
        raise GameLifecycleError("Stratagem reserve provider decision selection is malformed.")
    context, catalog_record, target_binding, effect_selection = selection
    if record.request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
        _validate_target_proposal_request_binding(
            record=record,
            context=context,
            catalog_record=catalog_record,
        )
    definition = catalog_record.definition
    expected_targeted_unit_ids, expected_affected_unit_ids = derive_stratagem_use_unit_ids(
        state=state,
        definition=definition,
        context=context,
        target_binding=target_binding,
        effect_selection=effect_selection,
    )
    from warhammer40k_core.engine.stratagems_generic_metadata import (
        generic_rule_ir_execution_target_unit_ids,
    )

    expected_execution_target_ids = set(
        generic_rule_ir_execution_target_unit_ids(state=state, use_record=use_record)
    )
    recorded_target_ids = set(use_record.targeted_unit_instance_ids) | set(
        use_record.affected_unit_instance_ids
    )
    if (
        record.result.decision_type != record.request.decision_type
        or record.result.actor_id != provider.player_id
        or use_record.request_id != provider.decision_request_id
        or use_record.result_id != provider.decision_result_id
        or use_record.selected_option_id != record.result.selected_option_id
        or use_record.player_id != provider.player_id
        or context.game_id != state.game_id
        or context.player_id != use_record.player_id
        or context.battle_round != use_record.battle_round
        or context.phase is not use_record.phase
        or context.active_player_id != use_record.active_player_id
        or context.timing_window_id != use_record.timing_window_id
        or catalog_record.definition.stratagem_id != use_record.stratagem_id
        or definition.source_id != use_record.source_id
        or definition.handler_id != GENERIC_RULE_IR_STRATAGEM_HANDLER_ID
        or use_record.handler_id != GENERIC_RULE_IR_STRATAGEM_HANDLER_ID
        or definition.effect_payload != use_record.effect_payload
        or target_binding != use_record.target_binding
        or effect_selection != use_record.effect_selection
        or use_record.targeted_unit_instance_ids != expected_targeted_unit_ids
        or use_record.affected_unit_instance_ids != expected_affected_unit_ids
        or not use_record.effects_resolved
        or not _rules_unit_identity_matches_any(
            state=state,
            unit_instance_id=provider.target_rules_unit_instance_id,
            candidate_unit_instance_ids=recorded_target_ids,
        )
    ):
        raise GameLifecycleError("Generic RuleIR Stratagem accepted authority drift.")
    rule_ir = scoped_rule_ir_from_execution_payload(definition.effect_payload)
    if rule_ir.source_id != provider.source_rule_id:
        raise GameLifecycleError("Generic RuleIR Stratagem reserve source drift.")
    validated_effect = validate_exact_primary_reserve_rule_ir_placement_effect(
        rule_ir=rule_ir,
        executed_effect_payload=executed_effect_payload,
    )
    effect_payload = _payload_object(
        executed_effect_payload,
        field_name="executed Stratagem reserve effect",
    )
    parameters = validated_effect.parameters
    if (
        parameters.get("placement_kind") != "strategic_reserves"
        or parameters.get("operation") != "remove_to_reserves"
        or parameters.get("reserve_origin") != ReserveOrigin.DURING_BATTLE_STRATAGEM.value
    ):
        raise GameLifecycleError("Executed Stratagem reserve effect descriptor drift.")
    executed_target_ids = set(validated_effect.target_unit_instance_ids)
    if executed_target_ids != expected_execution_target_ids or not _rules_unit_identity_matches_any(
        state=state,
        unit_instance_id=provider.target_rules_unit_instance_id,
        candidate_unit_instance_ids=executed_target_ids,
    ):
        raise GameLifecycleError("Executed Stratagem reserve effect target drift.")
    _require_exact_stratagem_used_event(decisions=decisions, use_record=use_record)
    executed_events = tuple(
        (index, event)
        for index, event in enumerate(decisions.event_log.records)
        if event.event_type == "rule_execution_effect_applied" and event.payload == effect_payload
    )
    used_events = tuple(
        (index, event)
        for index, event in enumerate(decisions.event_log.records)
        if event.event_type == "stratagem_used" and event.payload == use_record.to_payload()
    )
    if (
        len(executed_events) != 1
        or len(used_events) != 1
        or used_events[0][0] >= executed_events[0][0]
    ):
        raise GameLifecycleError("Executed Stratagem reserve effect event ordering drift.")


def _validate_target_proposal_request_binding(
    *,
    record: DecisionRecord,
    context: object,
    catalog_record: object,
) -> None:
    from warhammer40k_core.engine.stratagems_model import (
        StratagemTargetProposal,
        StratagemTargetProposalPayload,
    )

    request_payload = _payload_object(
        record.request.payload,
        field_name="Stratagem target proposal request",
    )
    raw_proposal = request_payload.get("proposal_request")
    if not isinstance(raw_proposal, dict):
        raise GameLifecycleError("Stratagem reserve target proposal request is malformed.")
    try:
        request_proposal = StratagemTargetProposal.from_payload(
            cast(StratagemTargetProposalPayload, raw_proposal)
        )
    except (KeyError, GameLifecycleError) as exc:
        raise GameLifecycleError("Stratagem reserve target proposal request is malformed.") from exc
    if (
        request_proposal.target_binding is not None
        or request_proposal.context != context
        or request_proposal.catalog_record != catalog_record
    ):
        raise GameLifecycleError("Stratagem reserve target proposal context drift.")


def _executed_reserve_effect_event(
    *,
    state: object,
    decisions: DecisionController,
    provider: PrimaryReserveEntryProvider,
    use_record: StratagemUseRecord,
) -> EventRecord:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Stratagem reserve execution lookup requires GameState.")
    candidates: list[EventRecord] = []
    for event in decisions.event_log.records:
        if event.event_type != "rule_execution_effect_applied" or not isinstance(
            event.payload, dict
        ):
            continue
        context = event.payload.get("context")
        trigger_payload = context.get("trigger_payload") if isinstance(context, dict) else None
        target_ids = event.payload.get("target_unit_instance_ids")
        executed_target_ids: set[str] = set()
        if isinstance(target_ids, list):
            executed_target_ids = {
                target_id for target_id in cast(list[object], target_ids) if type(target_id) is str
            }
        if (
            event.payload.get("source_id") == provider.source_rule_id
            and isinstance(trigger_payload, dict)
            and trigger_payload.get("stratagem_use_id") == use_record.use_id
            and _rules_unit_identity_matches_any(
                state=state,
                unit_instance_id=provider.target_rules_unit_instance_id,
                candidate_unit_instance_ids=executed_target_ids,
            )
        ):
            candidates.append(event)
    if len(candidates) != 1:
        raise GameLifecycleError("Stratagem reserve provider executed effect is not unique.")
    return candidates[0]


def _rule_effect_parameters(effect: dict[str, JsonValue]) -> dict[str, JsonValue]:
    raw_parameters = effect.get("parameters")
    if not isinstance(raw_parameters, list):
        raise GameLifecycleError("Reserve-entry effect parameters are malformed.")
    parameters: dict[str, JsonValue] = {}
    for raw_parameter in raw_parameters:
        if not isinstance(raw_parameter, dict):
            raise GameLifecycleError("Reserve-entry effect parameter is malformed.")
        key = raw_parameter.get("key")
        if type(key) is not str or key in parameters:
            raise GameLifecycleError("Reserve-entry effect parameter identity is malformed.")
        parameters[key] = raw_parameter.get("value")
    return parameters


def _optional_string_parameter(parameters: dict[str, JsonValue], key: str) -> str | None:
    value = parameters.get(key)
    if value is None:
        return None
    return _validate_identifier(key, value)


def _optional_int_parameter(parameters: dict[str, JsonValue], key: str) -> int | None:
    value = parameters.get(key)
    if value is None:
        return None
    if type(value) is not int or value <= 0:
        raise GameLifecycleError(f"Reserve-entry {key} must be a positive integer.")
    return value


def _required_arrival_round(
    *,
    state: object,
    player_id: str,
    timing: str | None,
    round_offset: int | None,
    battle_round: int,
    active_player_id: str | None,
) -> int | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Reserve-entry arrival timing requires GameState.")
    if type(battle_round) is not int or battle_round <= 0:
        raise GameLifecycleError("Reserve-entry arrival battle round is invalid.")
    if round_offset is not None:
        return battle_round + round_offset
    if timing is None:
        return None
    if timing != "next_owner_movement_phase" or active_player_id is None:
        raise GameLifecycleError("Reserve-entry arrival timing is unsupported.")
    if active_player_id not in state.turn_order or player_id not in state.turn_order:
        raise GameLifecycleError("Reserve-entry arrival timing player identity drift.")
    active_index = state.turn_order.index(active_player_id)
    owner_index = state.turn_order.index(player_id)
    return battle_round if owner_index > active_index else battle_round + 1


def _decision_result_for_use(
    *, decisions: DecisionController, use_record: StratagemUseRecord
) -> DecisionResult:
    matches = tuple(
        record.result
        for record in decisions.records
        if record.result.result_id == use_record.result_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Stratagem reserve provider requires one accepted result.")
    return matches[0]


def _require_exact_stratagem_used_event(
    *, decisions: DecisionController, use_record: StratagemUseRecord
) -> None:
    matching_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == "stratagem_used" and event.payload == use_record.to_payload()
    )
    if len(matching_events) != 1:
        raise GameLifecycleError("Stratagem reserve provider requires one exact use event.")


def _ability_result_target_id(payload: dict[str, JsonValue]) -> str:
    candidates = tuple(
        value
        for key in ("target_unit_instance_id", "target_rules_unit_instance_id")
        if type(value := payload.get(key)) is str
    )
    if len(candidates) != 1:
        raise GameLifecycleError("Ability reserve provider target identity is ambiguous.")
    return _validate_identifier("ability reserve target", candidates[0])


def _rules_unit_identity_matches(
    *,
    state: object,
    first_unit_instance_id: str,
    second_unit_instance_id: str,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.rules_units import rules_unit_identities_share_lineage

    if type(state) is not GameState:
        raise GameLifecycleError("Reserve provider identity matching requires GameState.")
    return rules_unit_identities_share_lineage(
        state=state,
        first_unit_instance_id=first_unit_instance_id,
        second_unit_instance_id=second_unit_instance_id,
    )


def _rules_unit_identity_matches_any(
    *,
    state: object,
    unit_instance_id: str,
    candidate_unit_instance_ids: set[str],
) -> bool:
    return any(
        _rules_unit_identity_matches(
            state=state,
            first_unit_instance_id=unit_instance_id,
            second_unit_instance_id=candidate_id,
        )
        for candidate_id in candidate_unit_instance_ids
    )


def _payload_object(value: object, *, field_name: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Primary reserve-entry {field_name} must be an object.")
    return cast(dict[str, JsonValue], value)


def _validate_optional_identifier(field_name: str, value: object) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"Primary reserve-entry {field_name} must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    validated = tuple(_validate_identifier(field_name, value) for value in raw_values)
    if len(set(validated)) != len(validated):
        raise GameLifecycleError(f"Primary reserve-entry {field_name} must be unique.")
    return validated


def _validate_terminal_static_identity(
    values: object,
) -> tuple[tuple[str, JsonValue], ...]:
    from warhammer40k_core.engine.event_log import validate_json_value

    if type(values) is not tuple:
        raise GameLifecycleError("Primary reserve-entry terminal identity must be a tuple.")
    validated: list[tuple[str, JsonValue]] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not tuple:
            raise GameLifecycleError("Primary reserve-entry terminal identity row is malformed.")
        row = cast(tuple[object, ...], value)
        if len(row) != 2:
            raise GameLifecycleError("Primary reserve-entry terminal identity row is malformed.")
        key, raw = row
        validated.append(
            (
                _validate_identifier("terminal identity key", key),
                validate_json_value(raw),
            )
        )
    if len({key for key, _value in validated}) != len(validated):
        raise GameLifecycleError("Primary reserve-entry terminal identity keys must be unique.")
    return tuple(validated)


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "GENERIC_RULE_IR_RESERVE_REMOVAL_PROVIDER_ID",
    "GENERIC_STRATAGEM_RESERVE_REMOVAL_RESOLVED_EVENT",
    "PRIMARY_RESERVE_ENTRY_PROVIDER_RESOLVED_EVENT",
    "PrimaryReserveEntryAbilityAuthorityKind",
    "PrimaryReserveEntryAbilityProviderDefinition",
    "PrimaryReserveEntryComponentMatchPolicy",
    "PrimaryReserveEntryLifecycleOccurrence",
    "PrimaryReserveEntryOccurrenceValidator",
    "PrimaryReserveEntryProvider",
    "PrimaryReserveEntryProviderKind",
    "PrimaryReserveEntryRequirements",
    "primary_reserve_entry_provider_from_accepted_ability_decision",
    "primary_reserve_entry_provider_from_accepted_stratagem_use",
    "primary_reserve_entry_provider_kind_from_token",
    "primary_reserve_entry_requirements",
    "primary_reserve_entry_requirements_from_evidence",
    "validate_accepted_primary_reserve_entry_provider",
    "validate_primary_reserve_entry_provider_registration",
    "validate_primary_reserve_entry_source_terminal_identity",
)
