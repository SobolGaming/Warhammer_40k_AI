from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine import mortal_wound_application_authority as _mwaa
from warhammer40k_core.engine.battlefield_state import ModelPlacement, ModelPlacementPayload
from warhammer40k_core.engine.damage_allocation import (
    DamageApplication,
    DamageApplicationPayload,
    FeelNoPainResolution,
    FeelNoPainResolutionPayload,
    FeelNoPainSource,
    FeelNoPainSourcePayload,
    MortalWoundApplicationProgress,
    MortalWoundRoutingResult,
    alive_placed_models_for_rules_unit,
    build_feel_no_pain_request,
    model_by_id,
    resolve_feel_no_pain_rolls,
    resolve_mortal_wound_feel_no_pain_decision,
)
from warhammer40k_core.engine.damage_allocation_targets import allocatable_rules_unit
from warhammer40k_core.engine.damage_allocation_validation import (
    validate_unique_sorted_exact_type_tuple,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import (
    EventRecord,
    EventRecordPayload,
    JsonValue,
    validate_json_value,
)
from warhammer40k_core.engine.finite_decision_validation import (
    invalid_finite_decision_status as _invalid_finite_decision_status,
)
from warhammer40k_core.engine.mortal_wound_context import (
    parse_mortal_wound_feel_no_pain_context,
)
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    evidence_from_json,
    evidence_to_json,
    record_finalized_mortal_wound_progress_destructions,
    validate_mortal_wound_destruction_evidence_mode,
)
from warhammer40k_core.engine.mortal_wound_logical_death import (
    MortalWoundLogicalDeathCauseBinding,
    MortalWoundLogicalDeathRecorder,
)
from warhammer40k_core.engine.mutation_decision_authority import (
    validate_mutation_decision_closure,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rules_units import (
    current_placed_alive_rules_unit_view_for_identity,
    rules_unit_view_by_id,
)
from warhammer40k_core.engine.unit_keyword_queries import unit_has_keyword

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

SELECT_MORTAL_WOUND_MODEL_DECISION_TYPE = "select_mortal_wound_model"
MORTAL_WOUND_MODEL_ALLOCATED_EVENT_TYPE = "mortal_wound_model_allocated"

_validate_identifier = IdentifierValidator(GameLifecycleError)


class MortalWoundAllocationPriority(StrEnum):
    WOUNDED_NON_CHARACTER = "wounded_non_character"
    NON_CHARACTER = "non_character"
    WOUNDED_CHARACTER = "wounded_character"
    CHARACTER = "character"


class MortalWoundSelectionDisposition(StrEnum):
    SOLE_LEGAL_MODEL = "sole_legal_model"
    PLAYER_DECISION = "player_decision"


class MortalWoundAllocationOccurrencePayload(TypedDict):
    occurrence_id: str
    application_id: str
    wound_index: int
    target_unit_instance_id: str
    priority_tier: str
    legal_model_ids: list[str]
    selected_model_id: str
    selection_disposition: str
    parent_request_id: str | None
    parent_result_id: str | None
    feel_no_pain_sources: list[FeelNoPainSourcePayload]
    feel_no_pain_decline_allowed: bool


@dataclass(frozen=True, slots=True)
class MortalWoundAllocationOccurrence:
    occurrence_id: str
    application_id: str
    wound_index: int
    target_unit_instance_id: str
    priority_tier: MortalWoundAllocationPriority
    legal_model_ids: tuple[str, ...]
    selected_model_id: str
    selection_disposition: MortalWoundSelectionDisposition
    parent_request_id: str | None
    parent_result_id: str | None
    feel_no_pain_sources: tuple[FeelNoPainSource, ...]
    feel_no_pain_decline_allowed: bool

    def __post_init__(self) -> None:
        application_id = _validate_identifier(
            "MortalWoundAllocationOccurrence application_id",
            self.application_id,
        )
        object.__setattr__(self, "application_id", application_id)
        if type(self.wound_index) is not int or self.wound_index < 1:
            raise GameLifecycleError(
                "MortalWoundAllocationOccurrence wound_index must be positive."
            )
        expected_occurrence_id = _mortal_wound_allocation_occurrence_id(
            application_id=application_id,
            wound_index=self.wound_index,
        )
        if self.occurrence_id != expected_occurrence_id:
            raise GameLifecycleError("Mortal-wound allocation occurrence ID drift.")
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier(
                "MortalWoundAllocationOccurrence target_unit_instance_id",
                self.target_unit_instance_id,
            ),
        )
        if type(self.priority_tier) is not MortalWoundAllocationPriority:
            raise GameLifecycleError("Mortal-wound allocation occurrence tier is invalid.")
        legal_model_ids = _validate_ordered_identifier_tuple(
            "MortalWoundAllocationOccurrence legal_model_ids",
            self.legal_model_ids,
        )
        if not legal_model_ids:
            raise GameLifecycleError("Mortal-wound allocation occurrence requires legal models.")
        object.__setattr__(self, "legal_model_ids", legal_model_ids)
        selected_model_id = _validate_identifier(
            "MortalWoundAllocationOccurrence selected_model_id",
            self.selected_model_id,
        )
        if selected_model_id not in legal_model_ids:
            raise GameLifecycleError("Mortal-wound allocation selected model is not legal.")
        object.__setattr__(self, "selected_model_id", selected_model_id)
        if type(self.selection_disposition) is not MortalWoundSelectionDisposition:
            raise GameLifecycleError("Mortal-wound allocation occurrence disposition is invalid.")
        parent_request_id = _optional_identifier(
            "MortalWoundAllocationOccurrence parent_request_id",
            self.parent_request_id,
        )
        parent_result_id = _optional_identifier(
            "MortalWoundAllocationOccurrence parent_result_id",
            self.parent_result_id,
        )
        object.__setattr__(self, "parent_request_id", parent_request_id)
        object.__setattr__(self, "parent_result_id", parent_result_id)
        if self.selection_disposition is MortalWoundSelectionDisposition.SOLE_LEGAL_MODEL:
            if (
                len(legal_model_ids) != 1
                or parent_request_id is not None
                or parent_result_id is not None
            ):
                raise GameLifecycleError("Sole mortal-wound allocation disposition drift.")
        elif len(legal_model_ids) < 2 or parent_request_id is None or parent_result_id is None:
            raise GameLifecycleError("Player mortal-wound allocation disposition drift.")
        sources = validate_unique_sorted_exact_type_tuple(
            self.feel_no_pain_sources,
            item_type=FeelNoPainSource,
            collection_label="Mortal-wound allocation Feel No Pain sources",
            identity=lambda source: source.source_id,
            duplicate_message=(
                "Mortal-wound allocation Feel No Pain sources must not duplicate IDs."
            ),
        )
        object.__setattr__(self, "feel_no_pain_sources", sources)
        if type(self.feel_no_pain_decline_allowed) is not bool:
            raise GameLifecycleError(
                "Mortal-wound allocation Feel No Pain decline policy must be a bool."
            )
        if len(sources) < 2 and not self.feel_no_pain_decline_allowed:
            raise GameLifecycleError(
                "Mortal-wound allocation occurrence must authorize a Feel No Pain choice."
            )

    def to_payload(self) -> MortalWoundAllocationOccurrencePayload:
        return {
            "occurrence_id": self.occurrence_id,
            "application_id": self.application_id,
            "wound_index": self.wound_index,
            "target_unit_instance_id": self.target_unit_instance_id,
            "priority_tier": self.priority_tier.value,
            "legal_model_ids": list(self.legal_model_ids),
            "selected_model_id": self.selected_model_id,
            "selection_disposition": self.selection_disposition.value,
            "parent_request_id": self.parent_request_id,
            "parent_result_id": self.parent_result_id,
            "feel_no_pain_sources": [source.to_payload() for source in self.feel_no_pain_sources],
            "feel_no_pain_decline_allowed": self.feel_no_pain_decline_allowed,
        }

    @classmethod
    def from_payload(cls, payload: object) -> MortalWoundAllocationOccurrence:
        raw = _exact_payload_object(
            payload,
            expected_fields={
                "occurrence_id",
                "application_id",
                "wound_index",
                "target_unit_instance_id",
                "priority_tier",
                "legal_model_ids",
                "selected_model_id",
                "selection_disposition",
                "parent_request_id",
                "parent_result_id",
                "feel_no_pain_sources",
                "feel_no_pain_decline_allowed",
            },
        )
        wound_index = raw["wound_index"]
        decline_allowed = raw["feel_no_pain_decline_allowed"]
        source_payloads = raw["feel_no_pain_sources"]
        if type(wound_index) is not int or type(decline_allowed) is not bool:
            raise GameLifecycleError("Mortal-wound allocation occurrence scalars are invalid.")
        if not isinstance(source_payloads, list) or any(
            not isinstance(source, dict) for source in source_payloads
        ):
            raise GameLifecycleError(
                "Mortal-wound allocation occurrence sources must contain objects."
            )
        try:
            priority_tier = MortalWoundAllocationPriority(
                _payload_identifier(raw, key="priority_tier")
            )
            disposition = MortalWoundSelectionDisposition(
                _payload_identifier(raw, key="selection_disposition")
            )
        except (TypeError, ValueError) as exc:
            raise GameLifecycleError(
                "Mortal-wound allocation occurrence contains an unsupported token."
            ) from exc
        return cls(
            occurrence_id=_payload_identifier(raw, key="occurrence_id"),
            application_id=_payload_identifier(raw, key="application_id"),
            wound_index=wound_index,
            target_unit_instance_id=_payload_identifier(
                raw,
                key="target_unit_instance_id",
            ),
            priority_tier=priority_tier,
            legal_model_ids=_payload_identifier_list(raw, key="legal_model_ids"),
            selected_model_id=_payload_identifier(raw, key="selected_model_id"),
            selection_disposition=disposition,
            parent_request_id=_payload_optional_identifier(raw, key="parent_request_id"),
            parent_result_id=_payload_optional_identifier(raw, key="parent_result_id"),
            feel_no_pain_sources=tuple(
                FeelNoPainSource.from_payload(cast(FeelNoPainSourcePayload, source))
                for source in source_payloads
            ),
            feel_no_pain_decline_allowed=decline_allowed,
        )


class MortalWoundApplicationProgressPayload(TypedDict):
    application_id: str
    source_rule_id: str
    source_context: JsonValue
    target_unit_instance_id: str
    defender_player_id: str
    mortal_wounds: int
    remaining_mortal_wounds: int
    spill_over: bool
    destruction_evidence: JsonValue
    logical_death_events: list[JsonValue]
    logical_death_cause_binding: JsonValue
    applications: list[DamageApplicationPayload]
    feel_no_pain_resolutions: list[FeelNoPainResolutionPayload]
    ignored_mortal_wounds: int
    remaining_mortal_wounds_lost: int
    priority_model_ids: list[str]
    destroyed_model_placements: list[JsonValue]


class MortalWoundModelDecisionPayload(TypedDict):
    request_id: str
    result_id: str
    player_id: str
    selected_model_id: str
    legal_model_ids: list[str]
    priority_tier: str
    mortal_wound_progress: MortalWoundApplicationProgressPayload


@dataclass(frozen=True, slots=True)
class MortalWoundModelDecision:
    request_id: str
    result_id: str
    player_id: str
    selected_model_id: str
    legal_model_ids: tuple[str, ...]
    priority_tier: MortalWoundAllocationPriority
    progress: MortalWoundApplicationProgress

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("MortalWoundModelDecision request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("MortalWoundModelDecision result_id", self.result_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("MortalWoundModelDecision player_id", self.player_id),
        )
        selected_model_id = _validate_identifier(
            "MortalWoundModelDecision selected_model_id",
            self.selected_model_id,
        )
        object.__setattr__(self, "selected_model_id", selected_model_id)
        legal_model_ids = _validate_ordered_identifier_tuple(
            "MortalWoundModelDecision legal_model_ids",
            self.legal_model_ids,
        )
        object.__setattr__(self, "legal_model_ids", legal_model_ids)
        if len(legal_model_ids) < 2:
            raise GameLifecycleError("MortalWoundModelDecision requires a player choice.")
        if selected_model_id not in legal_model_ids:
            raise GameLifecycleError("MortalWoundModelDecision selected model must be legal.")
        if type(self.priority_tier) is not MortalWoundAllocationPriority:
            raise GameLifecycleError("MortalWoundModelDecision priority tier is invalid.")
        if type(self.progress) is not MortalWoundApplicationProgress:
            raise GameLifecycleError("MortalWoundModelDecision progress is invalid.")

    @classmethod
    def from_result(
        cls,
        *,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> MortalWoundModelDecision:
        if request.decision_type != SELECT_MORTAL_WOUND_MODEL_DECISION_TYPE:
            raise GameLifecycleError("Mortal wound model decision request type drifted.")
        result.validate_for_request(request)
        actor_id = result.actor_id
        if actor_id is None:
            raise GameLifecycleError("Mortal wound model decision requires a controlling player.")
        request_payload = _payload_object(request.payload)
        result_payload = _payload_object(result.payload)
        priority_token = _payload_string(request_payload, key="priority_tier")
        try:
            priority_tier = MortalWoundAllocationPriority(priority_token)
        except ValueError as exc:
            raise GameLifecycleError("Mortal wound model priority tier is invalid.") from exc
        progress_payload = request_payload.get("mortal_wound_progress")
        if not isinstance(progress_payload, dict):
            raise GameLifecycleError("Mortal wound model progress payload must be an object.")
        return cls(
            request_id=request.request_id,
            result_id=result.result_id,
            player_id=actor_id,
            selected_model_id=_payload_string(result_payload, key="selected_model_id"),
            legal_model_ids=_payload_string_tuple(request_payload, key="legal_model_ids"),
            priority_tier=priority_tier,
            progress=mortal_wound_progress_from_payload(
                cast(MortalWoundApplicationProgressPayload, progress_payload)
            ),
        )

    def to_payload(self) -> MortalWoundModelDecisionPayload:
        return {
            "request_id": self.request_id,
            "result_id": self.result_id,
            "player_id": self.player_id,
            "selected_model_id": self.selected_model_id,
            "legal_model_ids": list(self.legal_model_ids),
            "priority_tier": self.priority_tier.value,
            "mortal_wound_progress": mortal_wound_progress_to_payload(self.progress),
        }


def mortal_wound_progress_to_payload(
    progress: MortalWoundApplicationProgress,
) -> MortalWoundApplicationProgressPayload:
    if type(progress) is not MortalWoundApplicationProgress:
        raise GameLifecycleError("Mortal wound progress serialization requires typed progress.")
    return {
        "application_id": progress.application_id,
        "source_rule_id": progress.source_rule_id,
        "source_context": progress.source_context,
        "target_unit_instance_id": progress.target_unit_instance_id,
        "defender_player_id": progress.defender_player_id,
        "mortal_wounds": progress.mortal_wounds,
        "remaining_mortal_wounds": progress.remaining_mortal_wounds,
        "spill_over": progress.spill_over,
        "destruction_evidence": cast(
            JsonValue,
            evidence_to_json(progress.destruction_evidence),
        ),
        "logical_death_events": [
            cast(JsonValue, event.to_payload()) for event in progress.logical_death_events
        ],
        "logical_death_cause_binding": cast(
            JsonValue,
            (
                None
                if progress.logical_death_cause_binding is None
                else progress.logical_death_cause_binding.to_payload()
            ),
        ),
        "applications": [application.to_payload() for application in progress.applications],
        "feel_no_pain_resolutions": [
            resolution.to_payload() for resolution in progress.feel_no_pain_resolutions
        ],
        "ignored_mortal_wounds": progress.ignored_mortal_wounds,
        "remaining_mortal_wounds_lost": progress.remaining_mortal_wounds_lost,
        "priority_model_ids": list(progress.priority_model_ids),
        "destroyed_model_placements": [
            cast(JsonValue, placement.to_payload())
            for placement in progress.destroyed_model_placements
        ],
    }


def mortal_wound_progress_from_payload(
    payload: MortalWoundApplicationProgressPayload,
) -> MortalWoundApplicationProgress:
    binding_payload = payload["logical_death_cause_binding"]
    if binding_payload is not None and not isinstance(binding_payload, dict):
        raise GameLifecycleError(
            "MortalWoundApplicationProgress logical-death binding payload is invalid."
        )
    return MortalWoundApplicationProgress(
        application_id=payload["application_id"],
        source_rule_id=payload["source_rule_id"],
        source_context=payload["source_context"],
        target_unit_instance_id=payload["target_unit_instance_id"],
        defender_player_id=payload["defender_player_id"],
        mortal_wounds=payload["mortal_wounds"],
        remaining_mortal_wounds=payload["remaining_mortal_wounds"],
        spill_over=payload["spill_over"],
        destruction_evidence=evidence_from_json(payload["destruction_evidence"]),
        logical_death_events=tuple(
            EventRecord.from_payload(cast(EventRecordPayload, event))
            for event in payload["logical_death_events"]
        ),
        logical_death_cause_binding=(
            None
            if binding_payload is None
            else MortalWoundLogicalDeathCauseBinding.from_payload(binding_payload)
        ),
        applications=tuple(
            DamageApplication.from_payload(application) for application in payload["applications"]
        ),
        feel_no_pain_resolutions=tuple(
            FeelNoPainResolution.from_payload(resolution)
            for resolution in payload["feel_no_pain_resolutions"]
        ),
        ignored_mortal_wounds=payload["ignored_mortal_wounds"],
        remaining_mortal_wounds_lost=payload["remaining_mortal_wounds_lost"],
        priority_model_ids=tuple(payload["priority_model_ids"]),
        destroyed_model_placements=tuple(
            ModelPlacement.from_payload(cast(ModelPlacementPayload, placement))
            for placement in payload["destroyed_model_placements"]
        ),
    )


def mortal_wound_priority_model_ids(
    *,
    state: GameState,
    target_unit_instance_id: str,
    priority_model_ids: tuple[str, ...] = (),
) -> tuple[str, ...]:
    model_ids, _ = mortal_wound_priority_selection(
        state=state,
        target_unit_instance_id=target_unit_instance_id,
        priority_model_ids=priority_model_ids,
    )
    return model_ids


def mortal_wound_priority_selection(
    *,
    state: GameState,
    target_unit_instance_id: str,
    priority_model_ids: tuple[str, ...] = (),
) -> tuple[tuple[str, ...], MortalWoundAllocationPriority]:
    rules_unit = allocatable_rules_unit(state=state, unit_id=target_unit_instance_id)
    alive_models = alive_placed_models_for_rules_unit(state=state, rules_unit=rules_unit)
    requested_priority_ids = _validate_identifier_tuple(
        "mortal wound priority_model_ids",
        priority_model_ids,
    )
    alive_ids = {model.model_instance_id for model in alive_models}
    for model_id in requested_priority_ids:
        model_by_id(state=state, model_instance_id=model_id)
    alive_priority_ids = alive_ids & set(requested_priority_ids)
    allowed_ids = alive_priority_ids if alive_priority_ids else alive_ids

    character_ids = set(rules_unit.character_model_ids(alive_models))
    if rules_unit.is_attached_rules_unit:
        character_ids.update(
            model.model_instance_id
            for model in alive_models
            if unit_has_keyword(
                rules_unit.component_unit_for_model(model.model_instance_id),
                "CHARACTER",
            )
        )
    elif unit_has_keyword(rules_unit.components[0].unit, "CHARACTER"):
        character_ids.update(alive_ids)

    wounded_ids = {
        model.model_instance_id
        for model in alive_models
        if model.wounds_remaining < model.starting_wounds
    }
    tiers = (
        (
            MortalWoundAllocationPriority.WOUNDED_NON_CHARACTER,
            allowed_ids & wounded_ids - character_ids,
        ),
        (MortalWoundAllocationPriority.NON_CHARACTER, allowed_ids - character_ids),
        (
            MortalWoundAllocationPriority.WOUNDED_CHARACTER,
            allowed_ids & wounded_ids & character_ids,
        ),
        (MortalWoundAllocationPriority.CHARACTER, allowed_ids & character_ids),
    )
    for priority, model_ids in tiers:
        if model_ids:
            return tuple(sorted(model_ids)), priority
    raise GameLifecycleError("Mortal wound allocation has no legal model.")


def build_mortal_wound_model_request(
    *,
    request_id: str,
    progress: MortalWoundApplicationProgress,
    legal_model_ids: tuple[str, ...],
    priority_tier: MortalWoundAllocationPriority,
) -> DecisionRequest:
    if type(progress) is not MortalWoundApplicationProgress:
        raise GameLifecycleError("Mortal wound model request requires progress.")
    model_ids = _validate_ordered_identifier_tuple(
        "Mortal wound model legal_model_ids",
        legal_model_ids,
    )
    if len(model_ids) < 2:
        raise GameLifecycleError("Mortal wound model request requires a player choice.")
    if type(priority_tier) is not MortalWoundAllocationPriority:
        raise GameLifecycleError("Mortal wound model request priority tier is invalid.")
    return DecisionRequest(
        request_id=request_id,
        decision_type=SELECT_MORTAL_WOUND_MODEL_DECISION_TYPE,
        actor_id=progress.defender_player_id,
        payload=validate_json_value(
            {
                "target_unit_instance_id": progress.target_unit_instance_id,
                "source_rule_id": progress.source_rule_id,
                "remaining_mortal_wounds": progress.remaining_mortal_wounds,
                "legal_model_ids": list(model_ids),
                "priority_tier": priority_tier.value,
                "mortal_wound_progress": mortal_wound_progress_to_payload(progress),
                "selection_kind": "mortal_wound_model",
            }
        ),
        options=tuple(
            DecisionOption(
                option_id=model_id,
                label=model_id,
                payload={
                    "submission_kind": SELECT_MORTAL_WOUND_MODEL_DECISION_TYPE,
                    "selected_model_id": model_id,
                    "priority_tier": priority_tier.value,
                },
            )
            for model_id in model_ids
        ),
    )


def is_mortal_wound_model_request(request: object) -> bool:
    if type(request) is not DecisionRequest:
        return False
    if request.decision_type != SELECT_MORTAL_WOUND_MODEL_DECISION_TYPE:
        return False
    payload = request.payload
    return isinstance(payload, dict) and payload.get("selection_kind") == "mortal_wound_model"


def is_mortal_wound_resolution_request(request: object) -> bool:
    from warhammer40k_core.engine.damage_allocation import is_mortal_wound_feel_no_pain_request

    return is_mortal_wound_model_request(request) or (
        type(request) is DecisionRequest and is_mortal_wound_feel_no_pain_request(request)
    )


def mortal_wound_resolution_source_context(request: DecisionRequest) -> JsonValue:
    return mortal_wound_resolution_progress(request).source_context


def mortal_wound_resolution_progress(
    request: DecisionRequest,
) -> MortalWoundApplicationProgress:
    from warhammer40k_core.engine.damage_allocation import is_mortal_wound_feel_no_pain_request

    if is_mortal_wound_model_request(request):
        payload = _payload_object(request.payload)
        progress_payload = payload.get("mortal_wound_progress")
        if not isinstance(progress_payload, dict):
            raise GameLifecycleError("Mortal wound model request progress must be an object.")
        return mortal_wound_progress_from_payload(
            cast(MortalWoundApplicationProgressPayload, progress_payload)
        )
    if is_mortal_wound_feel_no_pain_request(request):
        request_payload = _payload_object(request.payload)
        return MortalWoundApplicationProgress.from_feel_no_pain_context(
            request_payload.get("lost_wound_context")
        )
    raise GameLifecycleError("Request is not a mortal wound resolution decision.")


def continue_mortal_wound_application(
    *,
    state: GameState,
    decisions: DecisionController,
    request_id: str,
    progress: MortalWoundApplicationProgress,
    dice_manager: DiceRollManager | None = None,
    remove_destroyed_models: bool = True,
    logical_death_recorder: MortalWoundLogicalDeathRecorder | None = None,
) -> MortalWoundRoutingResult:
    if type(remove_destroyed_models) is not bool:
        raise GameLifecycleError("remove_destroyed_models must be a bool.")
    validate_mortal_wound_destruction_evidence_mode(
        progress=progress,
        remove_destroyed_models=remove_destroyed_models,
    )
    if not remove_destroyed_models and (
        progress.logical_death_cause_binding is None or logical_death_recorder is None
    ):
        raise GameLifecycleError("Retained mortal wound routing requires logical-death authority.")
    _mwaa.ensure_started(state, decisions.event_log, progress)
    current = progress
    while current.remaining_mortal_wounds:
        rules_unit = current_placed_alive_rules_unit_view_for_identity(
            state=state,
            unit_instance_id=current.target_unit_instance_id,
        )
        if rules_unit is None:
            completed = current.with_remaining_lost()
            record_finalized_mortal_wound_progress_destructions(
                state=state,
                decisions=decisions,
                progress=completed,
                remove_destroyed_models=remove_destroyed_models,
            )
            return MortalWoundRoutingResult(
                progress=completed,
                application=completed.to_application(),
            )
        legal_model_ids, priority_tier = mortal_wound_priority_selection(
            state=state,
            target_unit_instance_id=rules_unit.unit_instance_id,
            priority_model_ids=current.priority_model_ids,
        )
        if len(legal_model_ids) > 1:
            return MortalWoundRoutingResult(
                progress=current,
                request=build_mortal_wound_model_request(
                    request_id=request_id,
                    progress=current,
                    legal_model_ids=legal_model_ids,
                    priority_tier=priority_tier,
                ),
            )
        model_instance_id = next(iter(legal_model_ids))
        return _continue_mortal_wound_application_for_model(
            state=state,
            decisions=decisions,
            request_id=request_id,
            progress=current,
            model_instance_id=model_instance_id,
            legal_model_ids=legal_model_ids,
            priority_tier=priority_tier,
            model_decision=None,
            dice_manager=dice_manager,
            remove_destroyed_models=remove_destroyed_models,
            logical_death_recorder=logical_death_recorder,
        )
    record_finalized_mortal_wound_progress_destructions(
        state=state,
        decisions=decisions,
        progress=current,
        remove_destroyed_models=remove_destroyed_models,
    )
    return MortalWoundRoutingResult(progress=current, application=current.to_application())


def _continue_mortal_wound_application_for_model(
    *,
    state: GameState,
    decisions: DecisionController,
    request_id: str,
    progress: MortalWoundApplicationProgress,
    model_instance_id: str,
    legal_model_ids: tuple[str, ...],
    priority_tier: MortalWoundAllocationPriority,
    model_decision: MortalWoundModelDecision | None,
    dice_manager: DiceRollManager | None,
    remove_destroyed_models: bool,
    logical_death_recorder: MortalWoundLogicalDeathRecorder | None,
) -> MortalWoundRoutingResult:
    sources = mortal_wound_feel_no_pain_sources(
        state=state,
        model_instance_id=model_instance_id,
    )
    decline_allowed = mortal_wound_feel_no_pain_decline_allowed(
        state=state,
        model_instance_id=model_instance_id,
    )
    if len(sources) > 1 or (sources and decline_allowed):
        occurrence = _record_mortal_wound_allocation_occurrence(
            decisions=decisions,
            progress=progress,
            legal_model_ids=legal_model_ids,
            priority_tier=priority_tier,
            selected_model_id=model_instance_id,
            model_decision=model_decision,
            sources=sources,
            decline_allowed=decline_allowed,
        )
        request = build_feel_no_pain_request(
            request_id=request_id,
            defender_player_id=progress.defender_player_id,
            lost_wound_context=validate_json_value(
                progress.to_feel_no_pain_context(
                    model_instance_id=model_instance_id,
                    allocation_occurrence=validate_json_value(occurrence.to_payload()),
                )
            ),
            sources=sources,
            decline_allowed=decline_allowed,
        )
        return MortalWoundRoutingResult(progress=progress, request=request)
    if sources:
        if dice_manager is None:
            raise GameLifecycleError("Mortal wound Feel No Pain resolution requires dice manager.")
        resolution = resolve_feel_no_pain_rolls(
            manager=dice_manager,
            source=sources[0],
            player_id=progress.defender_player_id,
            model_instance_id=model_instance_id,
            requested_wounds=1,
        )
    else:
        resolution = FeelNoPainResolution.declined(requested_wounds=1)
    updated = progress.after_wound_resolution(
        state=state,
        decisions=decisions,
        model_instance_id=model_instance_id,
        resolution=resolution,
        remove_destroyed_model=remove_destroyed_models,
        logical_death_recorder=logical_death_recorder,
    )
    return continue_mortal_wound_application(
        state=state,
        decisions=decisions,
        request_id=request_id,
        progress=updated,
        dice_manager=dice_manager,
        remove_destroyed_models=remove_destroyed_models,
        logical_death_recorder=logical_death_recorder,
    )


def _record_mortal_wound_allocation_occurrence(
    *,
    decisions: DecisionController,
    progress: MortalWoundApplicationProgress,
    legal_model_ids: tuple[str, ...],
    priority_tier: MortalWoundAllocationPriority,
    selected_model_id: str,
    model_decision: MortalWoundModelDecision | None,
    sources: tuple[FeelNoPainSource, ...],
    decline_allowed: bool,
) -> MortalWoundAllocationOccurrence:
    wound_index = progress.mortal_wounds - progress.remaining_mortal_wounds + 1
    occurrence = MortalWoundAllocationOccurrence(
        occurrence_id=_mortal_wound_allocation_occurrence_id(
            application_id=progress.application_id,
            wound_index=wound_index,
        ),
        application_id=progress.application_id,
        wound_index=wound_index,
        target_unit_instance_id=progress.target_unit_instance_id,
        priority_tier=priority_tier,
        legal_model_ids=legal_model_ids,
        selected_model_id=selected_model_id,
        selection_disposition=(
            MortalWoundSelectionDisposition.SOLE_LEGAL_MODEL
            if model_decision is None
            else MortalWoundSelectionDisposition.PLAYER_DECISION
        ),
        parent_request_id=None if model_decision is None else model_decision.request_id,
        parent_result_id=None if model_decision is None else model_decision.result_id,
        feel_no_pain_sources=sources,
        feel_no_pain_decline_allowed=decline_allowed,
    )
    existing = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == MORTAL_WOUND_MODEL_ALLOCATED_EVENT_TYPE
        and isinstance(event.payload, dict)
        and event.payload.get("occurrence_id") == occurrence.occurrence_id
    )
    if existing:
        raise GameLifecycleError("Mortal-wound allocation occurrence already exists.")
    decisions.event_log.append(
        MORTAL_WOUND_MODEL_ALLOCATED_EVENT_TYPE,
        occurrence.to_payload(),
    )
    return occurrence


def resolve_mortal_wound_model_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
    next_request_id: str,
    dice_manager: DiceRollManager | None = None,
    remove_destroyed_models: bool = True,
    logical_death_recorder: MortalWoundLogicalDeathRecorder | None = None,
) -> MortalWoundRoutingResult:
    if type(remove_destroyed_models) is not bool:
        raise GameLifecycleError("remove_destroyed_models must be a bool.")
    decision = MortalWoundModelDecision.from_result(request=request, result=result)
    progress = decision.progress
    if decision.player_id != progress.defender_player_id:
        raise GameLifecycleError("Mortal wound model controlling player drift.")
    legal_model_ids, priority_tier = mortal_wound_priority_selection(
        state=state,
        target_unit_instance_id=progress.target_unit_instance_id,
        priority_model_ids=progress.priority_model_ids,
    )
    if legal_model_ids != decision.legal_model_ids or priority_tier is not decision.priority_tier:
        raise GameLifecycleError("Mortal wound model priority context drifted.")
    return _continue_mortal_wound_application_for_model(
        state=state,
        decisions=decisions,
        request_id=next_request_id,
        progress=progress,
        model_instance_id=decision.selected_model_id,
        legal_model_ids=legal_model_ids,
        priority_tier=priority_tier,
        model_decision=decision,
        dice_manager=dice_manager,
        remove_destroyed_models=remove_destroyed_models,
        logical_death_recorder=logical_death_recorder,
    )


def invalid_mortal_wound_model_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    invalid_reason = "invalid_mortal_wound_model_result"
    invalid_status = _invalid_finite_decision_status(
        state=state,
        request=request,
        result=result,
        invalid_reason=invalid_reason,
    )
    if invalid_status is not None:
        return invalid_status
    try:
        decision = MortalWoundModelDecision.from_result(request=request, result=result)
        progress = mortal_wound_resolution_progress(request)
        legal_model_ids, priority_tier = mortal_wound_priority_selection(
            state=state,
            target_unit_instance_id=progress.target_unit_instance_id,
            priority_model_ids=progress.priority_model_ids,
        )
    except GameLifecycleError as exc:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message=str(exc),
            payload={"invalid_reason": invalid_reason, "field": "mortal_wound_context"},
        )
    if decision.player_id != progress.defender_player_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Mortal wound model controlling player no longer matches state.",
            payload={"invalid_reason": invalid_reason, "field": "actor_id"},
        )
    if decision.legal_model_ids != legal_model_ids:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Mortal wound model options no longer match the legal priority tier.",
            payload={"invalid_reason": invalid_reason, "field": "legal_model_ids"},
        )
    if decision.priority_tier is not priority_tier:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Mortal wound model priority tier no longer matches state.",
            payload={"invalid_reason": invalid_reason, "field": "priority_tier"},
        )
    return None


def validate_mortal_wound_feel_no_pain_request_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    request: DecisionRequest,
    request_event: EventRecord | None = None,
) -> MortalWoundAllocationOccurrence:
    from warhammer40k_core.engine.damage_allocation import (
        is_mortal_wound_feel_no_pain_request,
    )

    if not is_mortal_wound_feel_no_pain_request(request):
        raise GameLifecycleError(
            "Mortal-wound allocation authority requires a Feel No Pain request."
        )
    if type(event_records) is not tuple or any(
        type(event) is not EventRecord for event in event_records
    ):
        raise GameLifecycleError("Mortal-wound allocation event history is invalid.")
    if type(decision_records) is not tuple or any(
        type(record) is not DecisionRecord for record in decision_records
    ):
        raise GameLifecycleError("Mortal-wound allocation decision history is invalid.")
    request_payload = _payload_object(request.payload)
    context = parse_mortal_wound_feel_no_pain_context(request_payload.get("lost_wound_context"))
    progress = MortalWoundApplicationProgress.from_feel_no_pain_context(
        validate_json_value(context)
    )
    occurrence = MortalWoundAllocationOccurrence.from_payload(context["allocation_occurrence"])
    expected_wound_index = progress.mortal_wounds - progress.remaining_mortal_wounds + 1
    if (
        occurrence.application_id != progress.application_id
        or occurrence.wound_index != expected_wound_index
        or occurrence.target_unit_instance_id != progress.target_unit_instance_id
        or occurrence.selected_model_id != context["model_instance_id"]
    ):
        raise GameLifecycleError("Mortal-wound allocation occurrence context drift.")

    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=progress.target_unit_instance_id,
    )
    if rules_unit.unit_instance_id != occurrence.target_unit_instance_id:
        raise GameLifecycleError("Mortal-wound allocation target rules-unit drift.")
    rules_unit.component_unit_for_model(occurrence.selected_model_id)
    legal_model_ids, priority_tier = mortal_wound_priority_selection(
        state=state,
        target_unit_instance_id=progress.target_unit_instance_id,
        priority_model_ids=progress.priority_model_ids,
    )
    if (
        legal_model_ids != occurrence.legal_model_ids
        or priority_tier is not occurrence.priority_tier
    ):
        raise GameLifecycleError("Mortal-wound allocation priority boundary drift.")

    loaded_sources = mortal_wound_feel_no_pain_sources(
        state=state,
        model_instance_id=occurrence.selected_model_id,
    )
    loaded_decline_allowed = mortal_wound_feel_no_pain_decline_allowed(
        state=state,
        model_instance_id=occurrence.selected_model_id,
    )
    if (
        loaded_sources != occurrence.feel_no_pain_sources
        or loaded_decline_allowed != occurrence.feel_no_pain_decline_allowed
    ):
        raise GameLifecycleError("Mortal-wound allocation Feel No Pain inventory drift.")
    expected_request = build_feel_no_pain_request(
        request_id=request.request_id,
        defender_player_id=progress.defender_player_id,
        lost_wound_context=validate_json_value(
            progress.to_feel_no_pain_context(
                model_instance_id=occurrence.selected_model_id,
                allocation_occurrence=validate_json_value(occurrence.to_payload()),
            )
        ),
        sources=loaded_sources,
        decline_allowed=loaded_decline_allowed,
    )
    if request != expected_request:
        raise GameLifecycleError("Mortal-wound Feel No Pain request authority drift.")

    parsed_occurrences = tuple(
        (
            event,
            MortalWoundAllocationOccurrence.from_payload(event.payload),
        )
        for event in event_records
        if event.event_type == MORTAL_WOUND_MODEL_ALLOCATED_EVENT_TYPE
    )
    matching_occurrences = tuple(
        (event, candidate)
        for event, candidate in parsed_occurrences
        if candidate.application_id == occurrence.application_id
        and candidate.wound_index == occurrence.wound_index
    )
    if len(matching_occurrences) != 1 or matching_occurrences[0][1] != occurrence:
        raise GameLifecycleError(
            "Pending mortal-wound Feel No Pain lacks one exact allocation occurrence."
        )
    occurrence_event = matching_occurrences[0][0]
    event_indexes = {event.event_id: index for index, event in enumerate(event_records)}
    if len(event_indexes) != len(event_records):
        raise GameLifecycleError("Mortal-wound allocation event history is duplicated.")
    occurrence_index = event_indexes[occurrence_event.event_id]

    request_events = tuple(
        event
        for event in event_records
        if event.event_type == "decision_requested" and event.payload == request.to_payload()
    )
    if len(request_events) != 1:
        raise GameLifecycleError("Pending mortal-wound Feel No Pain lacks one exact request event.")
    exact_request_event = request_events[0]
    if request_event is not None and request_event != exact_request_event:
        raise GameLifecycleError("Pending mortal-wound Feel No Pain request event drift.")
    if occurrence_index >= event_indexes[exact_request_event.event_id]:
        raise GameLifecycleError(
            "Mortal-wound allocation occurrence must precede its Feel No Pain request."
        )
    application_authorities = _mwaa.mortal_wound_application_authority_inventory(
        event_records=event_records,
        game_id=state.game_id,
    )
    _mwaa.validate_pending_mortal_wound_application_authority(
        state=state,
        event_records=event_records,
        progress=progress,
        request_event=exact_request_event,
        inventory=application_authorities,
    )

    if occurrence.selection_disposition is MortalWoundSelectionDisposition.PLAYER_DECISION:
        parent_request_id = cast(str, occurrence.parent_request_id)
        parent_result_id = cast(str, occurrence.parent_result_id)
        parent_record = validate_mutation_decision_closure(
            event_records=event_records,
            decision_records=decision_records,
            mutation_index=occurrence_index,
            request_id=parent_request_id,
            result_id=parent_result_id,
        )
        parent_decision = MortalWoundModelDecision.from_result(
            request=parent_record.request,
            result=parent_record.result,
        )
        if (
            parent_decision.progress != progress
            or parent_decision.player_id != progress.defender_player_id
            or parent_decision.legal_model_ids != occurrence.legal_model_ids
            or parent_decision.priority_tier is not occurrence.priority_tier
            or parent_decision.selected_model_id != occurrence.selected_model_id
        ):
            raise GameLifecycleError("Mortal-wound allocation parent decision drift.")
    elif legal_model_ids != (occurrence.selected_model_id,):
        raise GameLifecycleError("Automatic mortal-wound allocation is no longer sole.")
    return occurrence


def invalid_mortal_wound_feel_no_pain_status(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    invalid_reason = "invalid_mortal_wound_feel_no_pain_result"
    invalid_status = _invalid_finite_decision_status(
        state=state,
        request=request,
        result=result,
        invalid_reason=invalid_reason,
    )
    if invalid_status is not None:
        return invalid_status
    try:
        validate_mortal_wound_feel_no_pain_request_authority(
            state=state,
            event_records=decisions.event_log.records,
            decision_records=decisions.records,
            request=request,
        )
    except GameLifecycleError as exc:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message=str(exc),
            payload={
                "invalid_reason": invalid_reason,
                "field": "allocation_occurrence",
            },
        )
    return None


def resolve_mortal_wound_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
    next_request_id: str,
    dice_manager: DiceRollManager | None = None,
    remove_destroyed_models: bool = True,
    logical_death_recorder: MortalWoundLogicalDeathRecorder | None = None,
) -> MortalWoundRoutingResult:
    from warhammer40k_core.engine.damage_allocation import is_mortal_wound_feel_no_pain_request

    if is_mortal_wound_model_request(request):
        return resolve_mortal_wound_model_decision(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
            next_request_id=next_request_id,
            dice_manager=dice_manager,
            remove_destroyed_models=remove_destroyed_models,
            logical_death_recorder=logical_death_recorder,
        )
    if is_mortal_wound_feel_no_pain_request(request):
        return resolve_mortal_wound_feel_no_pain_decision(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
            next_request_id=next_request_id,
            dice_manager=dice_manager,
            remove_destroyed_models=remove_destroyed_models,
            logical_death_recorder=logical_death_recorder,
        )
    raise GameLifecycleError("Request is not a mortal wound resolution decision.")


def mortal_wound_feel_no_pain_sources(
    *,
    state: GameState,
    model_instance_id: str,
) -> tuple[FeelNoPainSource, ...]:
    sources = state.feel_no_pain_sources_for_model(model_instance_id=model_instance_id)
    typed_sources = validate_unique_sorted_exact_type_tuple(
        sources,
        item_type=FeelNoPainSource,
        collection_label="Feel No Pain sources",
        identity=lambda source: source.source_id,
        duplicate_message="Feel No Pain sources must not duplicate source IDs.",
    )
    return tuple(
        source
        for source in typed_sources
        if source.attack_condition is None or source.mortal_wounds
    )


def mortal_wound_feel_no_pain_decline_allowed(
    *,
    state: GameState,
    model_instance_id: str,
) -> bool:
    value = state.feel_no_pain_decline_allowed_for_model(model_instance_id=model_instance_id)
    if type(value) is not bool:
        raise GameLifecycleError("Feel No Pain decline state must be a bool.")
    return value


def _payload_object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Decision payload must be an object.")
    return value


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Decision payload {key} must be a string.")
    return _validate_identifier(key, value)


def _payload_string_tuple(
    payload: dict[str, JsonValue],
    *,
    key: str,
) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise GameLifecycleError(f"Decision payload {key} must be a list.")
    if any(type(item) is not str for item in value):
        raise GameLifecycleError(f"Decision payload {key} must contain strings.")
    return _validate_ordered_identifier_tuple(key, cast(tuple[str, ...], tuple(value)))


def _exact_payload_object(
    value: object,
    *,
    expected_fields: set[str],
) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Mortal-wound allocation occurrence fields are invalid.")
    raw = cast(dict[str, object], value)
    if set(raw) != expected_fields:
        raise GameLifecycleError("Mortal-wound allocation occurrence fields are invalid.")
    return cast(dict[str, JsonValue], raw)


def _payload_identifier(payload: dict[str, JsonValue], *, key: str) -> str:
    return _validate_identifier(key, payload.get(key))


def _payload_optional_identifier(
    payload: dict[str, JsonValue],
    *,
    key: str,
) -> str | None:
    return _optional_identifier(key, payload.get(key))


def _payload_identifier_list(
    payload: dict[str, JsonValue],
    *,
    key: str,
) -> tuple[str, ...]:
    values = payload.get(key)
    if not isinstance(values, list) or any(type(value) is not str for value in values):
        raise GameLifecycleError(f"{key} must contain strings.")
    return tuple(cast(list[str], values))


def _optional_identifier(label: str, value: object) -> str | None:
    if value is None:
        return None
    return _validate_identifier(label, value)


def _mortal_wound_allocation_occurrence_id(
    *,
    application_id: str,
    wound_index: int,
) -> str:
    requested_application_id = _validate_identifier("application_id", application_id)
    if type(wound_index) is not int or wound_index < 1:
        raise GameLifecycleError("Mortal-wound allocation wound index must be positive.")
    return f"{requested_application_id}:allocation:{wound_index:06d}"


def _validate_identifier_tuple(label: str, value: object) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"{label} must be a tuple.")
    tuple_value = cast(tuple[object, ...], value)
    if any(type(item) is not str for item in tuple_value):
        raise GameLifecycleError(f"{label} must be a tuple.")
    return tuple(_validate_identifier(label, item) for item in cast(tuple[str, ...], tuple_value))


def _validate_ordered_identifier_tuple(label: str, value: object) -> tuple[str, ...]:
    identifiers = _validate_identifier_tuple(label, value)
    if tuple(sorted(set(identifiers))) != identifiers:
        raise GameLifecycleError(f"{label} must be unique and sorted.")
    return identifiers
