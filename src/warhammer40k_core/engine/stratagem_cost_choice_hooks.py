from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult, DecisionResultPayload
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.lifecycle_hooks import LifecycleHookEvent, validate_hook_bindings
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_DECISION_TYPE,
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagems import (
        StratagemCatalogRecord,
        StratagemDefinition,
        StratagemEligibilityContext,
        StratagemTargetBinding,
    )


SELECT_STRATAGEM_COST_MODIFIER_OPTION_DECISION_TYPE = "select_stratagem_cost_modifier_option"

type StratagemCostChoiceRequestHandler = Callable[
    ["StratagemCostChoiceRequestContext"],
    DecisionRequest | None,
]
type StratagemCostChoiceResultHandler = Callable[["StratagemCostChoiceResultContext"], bool]


@dataclass(frozen=True, slots=True)
class StratagemCostChoiceRequestContext:
    state: GameState
    decisions: DecisionController
    source_request: DecisionRequest
    source_result: DecisionResult
    definition: StratagemDefinition
    eligibility_context: StratagemEligibilityContext
    target_binding: StratagemTargetBinding
    effect_selection: JsonValue

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState
        from warhammer40k_core.engine.stratagems import (
            StratagemDefinition,
            StratagemEligibilityContext,
            StratagemTargetBinding,
        )

        if type(self.state) is not GameState:
            raise GameLifecycleError("Stratagem cost choice context requires GameState.")
        if self.state.stage is not GameLifecycleStage.BATTLE:
            raise GameLifecycleError("Stratagem cost choices require battle stage.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError("Stratagem cost choice context requires DecisionController.")
        if type(self.source_request) is not DecisionRequest:
            raise GameLifecycleError(
                "Stratagem cost choice source_request must be DecisionRequest."
            )
        if self.source_request.decision_type not in {
            STRATAGEM_DECISION_TYPE,
            STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
        }:
            raise GameLifecycleError("Stratagem cost choice source_request decision_type drift.")
        if type(self.source_result) is not DecisionResult:
            raise GameLifecycleError("Stratagem cost choice source_result must be DecisionResult.")
        if self.source_result.request_id != self.source_request.request_id:
            raise GameLifecycleError("Stratagem cost choice source result request drift.")
        if type(self.definition) is not StratagemDefinition:
            raise GameLifecycleError("Stratagem cost choice requires StratagemDefinition.")
        if type(self.eligibility_context) is not StratagemEligibilityContext:
            raise GameLifecycleError("Stratagem cost choice requires eligibility context.")
        if type(self.target_binding) is not StratagemTargetBinding:
            raise GameLifecycleError("Stratagem cost choice requires target binding.")
        object.__setattr__(self, "effect_selection", validate_json_value(self.effect_selection))


@dataclass(frozen=True, slots=True)
class StratagemCostChoiceResultContext:
    state: GameState
    decisions: DecisionController
    request: DecisionRequest
    result: DecisionResult
    source_request: DecisionRequest
    source_result: DecisionResult
    definition: StratagemDefinition
    eligibility_context: StratagemEligibilityContext
    target_binding: StratagemTargetBinding
    effect_selection: JsonValue

    def __post_init__(self) -> None:
        if type(self.request) is not DecisionRequest:
            raise GameLifecycleError("Stratagem cost choice result requires DecisionRequest.")
        if self.request.decision_type != SELECT_STRATAGEM_COST_MODIFIER_OPTION_DECISION_TYPE:
            raise GameLifecycleError("Stratagem cost choice request decision_type drift.")
        if type(self.result) is not DecisionResult:
            raise GameLifecycleError("Stratagem cost choice result requires DecisionResult.")
        if self.result.request_id != self.request.request_id:
            raise GameLifecycleError("Stratagem cost choice result request drift.")
        StratagemCostChoiceRequestContext(
            state=self.state,
            decisions=self.decisions,
            source_request=self.source_request,
            source_result=self.source_result,
            definition=self.definition,
            eligibility_context=self.eligibility_context,
            target_binding=self.target_binding,
            effect_selection=self.effect_selection,
        )


@dataclass(frozen=True, slots=True)
class StratagemCostChoiceHookBinding:
    hook_id: str
    source_id: str
    request_handler: StratagemCostChoiceRequestHandler | None = None
    result_handler: StratagemCostChoiceResultHandler | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if self.request_handler is None and self.result_handler is None:
            raise GameLifecycleError("StratagemCostChoiceHookBinding requires a handler.")
        if self.request_handler is not None and not callable(self.request_handler):
            raise GameLifecycleError("Stratagem cost choice request_handler must be callable.")
        if self.result_handler is not None and not callable(self.result_handler):
            raise GameLifecycleError("Stratagem cost choice result_handler must be callable.")


@dataclass(frozen=True, slots=True)
class StratagemCostChoiceHookRegistry:
    bindings: tuple[StratagemCostChoiceHookBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_hook_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(cls, bindings: tuple[StratagemCostChoiceHookBinding, ...]) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[StratagemCostChoiceHookBinding, ...]:
        return self.bindings

    def next_request_for(
        self,
        context: StratagemCostChoiceRequestContext,
    ) -> DecisionRequest | None:
        if type(context) is not StratagemCostChoiceRequestContext:
            raise GameLifecycleError("Stratagem cost choice request hooks require a context.")
        for binding in self.bindings:
            if binding.request_handler is None:
                continue
            request = binding.request_handler(context)
            if request is None:
                continue
            if type(request) is not DecisionRequest:
                raise GameLifecycleError(
                    "Stratagem cost choice handlers must return DecisionRequest or None."
                )
            return request
        return None

    def apply_result(self, context: StratagemCostChoiceResultContext) -> bool:
        if type(context) is not StratagemCostChoiceResultContext:
            raise GameLifecycleError("Stratagem cost choice result hooks require a context.")
        handled_ids: list[str] = []
        for binding in self.bindings:
            if binding.result_handler is None:
                continue
            handled = binding.result_handler(context)
            if type(handled) is not bool:
                raise GameLifecycleError("Stratagem cost choice result handlers must return bool.")
            if handled:
                handled_ids.append(binding.hook_id)
        if len(handled_ids) > 1:
            raise GameLifecycleError("Stratagem cost choice result handled by multiple hooks.")
        return bool(handled_ids)


def stratagem_cost_choice_source_result(request: DecisionRequest) -> DecisionResult:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Stratagem cost choice source lookup requires DecisionRequest.")
    if request.decision_type != SELECT_STRATAGEM_COST_MODIFIER_OPTION_DECISION_TYPE:
        raise GameLifecycleError("DecisionRequest is not a stratagem cost choice request.")
    if not isinstance(request.payload, dict):
        raise GameLifecycleError("Stratagem cost choice request payload must be an object.")
    result_payload = request.payload.get("source_decision_result")
    if not isinstance(result_payload, dict):
        raise GameLifecycleError("Stratagem cost choice request is missing source result.")
    try:
        return DecisionResult.from_payload(cast(DecisionResultPayload, result_payload))
    except KeyError as exc:
        raise GameLifecycleError("Stratagem cost choice source result is malformed.") from exc


def source_selection_for_cost_choice(
    source_request: DecisionRequest,
    source_result: DecisionResult,
) -> tuple[
    StratagemEligibilityContext,
    StratagemCatalogRecord,
    StratagemTargetBinding,
    JsonValue,
]:
    from warhammer40k_core.engine.stratagems import (
        stratagem_selection_from_decision_result,
        stratagem_selection_from_target_proposal_result,
    )

    if source_request.decision_type == STRATAGEM_DECISION_TYPE:
        selection = stratagem_selection_from_decision_result(source_result)
    elif source_request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
        selection = stratagem_selection_from_target_proposal_result(source_result)
    else:
        raise GameLifecycleError("Stratagem cost choice source decision_type drift.")
    if selection is None:
        raise GameLifecycleError("Stratagem cost choice source selection is malformed.")
    return selection


def source_result_payload_for_cost_choice(source_result: DecisionResult) -> JsonValue:
    if type(source_result) is not DecisionResult:
        raise GameLifecycleError("Stratagem cost choice source result must be DecisionResult.")
    return validate_json_value(source_result.to_payload())


def _validate_hook_bindings(
    value: object,
) -> tuple[StratagemCostChoiceHookBinding, ...]:
    return validate_hook_bindings(
        value,
        lifecycle_event=LifecycleHookEvent.STRATAGEM_COST_CHOICE,
        binding_type=StratagemCostChoiceHookBinding,
        registry_name="StratagemCostChoiceHookRegistry",
        invalid_binding_message="StratagemCostChoiceHookRegistry requires hook bindings.",
        duplicate_hook_id_message="Stratagem cost choice hook IDs must be unique.",
    )


_validate_identifier = IdentifierValidator(GameLifecycleError)
