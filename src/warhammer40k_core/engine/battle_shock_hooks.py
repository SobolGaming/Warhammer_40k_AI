from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.dice import DiceExpression, RerollPermission
from warhammer40k_core.core.modifiers import RollModifier, RollModifierPayload
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockTestReason,
    BattleShockTestRequest,
    battle_shock_test_reason_from_token,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.lifecycle_hooks import LifecycleHookEvent, validate_hook_bindings
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.battle_shock_historical_authority import (
        HistoricalBattleShockAuthorityContext,
    )
    from warhammer40k_core.engine.game_state import GameState


type BattleShockModifierHandler = Callable[
    ["BattleShockModifierContext"],
    tuple[RollModifier, ...],
]
type BattleShockRerollPermissionHandler = Callable[
    ["BattleShockRerollPermissionContext"],
    RerollPermission | None,
]
type BattleShockDiceExpressionHandler = Callable[
    ["BattleShockDiceExpressionContext"],
    DiceExpression | None,
]
type BattleShockOutcomeHandler = Callable[["BattleShockOutcomeContext"], None]
type BattleShockPendingOutcomeAuthorityValidator = Callable[
    ["BattleShockPendingOutcomeAuthorityContext"],
    "BattleShockPendingOutcomeAuthority | None",
]
type BattleShockForcedTestHandler = Callable[
    ["BattleShockForcedTestContext"],
    tuple[str, ...],
]
type HistoricalBattleShockContributionHandler = Callable[
    ["HistoricalBattleShockAuthorityContext"],
    "HistoricalBattleShockContribution",
]


class BattleShockModifierApplicationPayload(TypedDict):
    hook_id: str
    source_id: str
    modifiers: list[RollModifierPayload]


class BattleShockForcedTestApplicationPayload(TypedDict):
    hook_id: str
    source_id: str
    unit_instance_ids: list[str]


@dataclass(frozen=True, slots=True)
class HistoricalBattleShockContribution:
    """One loaded provider's exact event-bound pre-result contribution."""

    dice_expression: DiceExpression | None = None
    modifiers: tuple[RollModifier, ...] = ()
    reroll_permission: RerollPermission | None = None

    def __post_init__(self) -> None:
        if self.dice_expression is not None:
            if type(self.dice_expression) is not DiceExpression:
                raise GameLifecycleError("Historical Battle-shock dice expression must be typed.")
            _validate_battle_shock_dice_expression(self.dice_expression)
        modifiers = _validate_roll_modifier_tuple(self.modifiers)
        _validate_unique_modifier_ids(modifiers)
        object.__setattr__(
            self,
            "modifiers",
            tuple(sorted(modifiers, key=lambda value: value.modifier_id)),
        )
        if self.reroll_permission is not None and type(self.reroll_permission) is not (
            RerollPermission
        ):
            raise GameLifecycleError("Historical Battle-shock reroll permission must be typed.")


@dataclass(frozen=True, slots=True)
class BattleShockForcedTestApplication:
    hook_id: str
    source_id: str
    unit_instance_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        unit_ids = _validate_identifier_tuple("unit_instance_ids", self.unit_instance_ids)
        if not unit_ids:
            raise GameLifecycleError("Battle-shock forced-test application requires unit IDs.")
        object.__setattr__(self, "unit_instance_ids", tuple(sorted(unit_ids)))

    def to_payload(self) -> BattleShockForcedTestApplicationPayload:
        return {
            "hook_id": self.hook_id,
            "source_id": self.source_id,
            "unit_instance_ids": list(self.unit_instance_ids),
        }

    @classmethod
    def from_payload(cls, payload: BattleShockForcedTestApplicationPayload) -> Self:
        application = cls(
            hook_id=payload["hook_id"],
            source_id=payload["source_id"],
            unit_instance_ids=tuple(payload["unit_instance_ids"]),
        )
        if payload != application.to_payload():
            raise GameLifecycleError("Battle-shock forced-test application payload drifted.")
        return application


@dataclass(frozen=True, slots=True)
class BattleShockModifierApplication:
    hook_id: str
    source_id: str
    modifiers: tuple[RollModifier, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        modifiers = _validate_roll_modifier_tuple(self.modifiers)
        if not modifiers:
            raise GameLifecycleError("Battle-shock modifier application requires modifiers.")
        _validate_unique_modifier_ids(modifiers)
        if any(modifier.source_id != self.source_id for modifier in modifiers):
            raise GameLifecycleError("Battle-shock modifier application source drifted.")
        object.__setattr__(
            self,
            "modifiers",
            tuple(sorted(modifiers, key=lambda modifier: modifier.modifier_id)),
        )

    def to_payload(self) -> BattleShockModifierApplicationPayload:
        return {
            "hook_id": self.hook_id,
            "source_id": self.source_id,
            "modifiers": [modifier.to_payload() for modifier in self.modifiers],
        }

    @classmethod
    def from_payload(cls, payload: BattleShockModifierApplicationPayload) -> Self:
        application = cls(
            hook_id=payload["hook_id"],
            source_id=payload["source_id"],
            modifiers=tuple(
                RollModifier.from_payload(modifier) for modifier in payload["modifiers"]
            ),
        )
        if payload != application.to_payload():
            raise GameLifecycleError("Battle-shock modifier application payload drifted.")
        return application


@dataclass(frozen=True, slots=True)
class BattleShockModifierApplicationAuthorityContext:
    state: GameState
    request: BattleShockTestRequest
    application: BattleShockModifierApplication
    active_player_id: str
    phase: BattlePhase
    phase_start_battle_shocked_unit_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError(
                "Battle-shock modifier application authority requires GameState."
            )
        if type(self.request) is not BattleShockTestRequest:
            raise GameLifecycleError(
                "Battle-shock modifier application authority requires a request."
            )
        if type(self.application) is not BattleShockModifierApplication:
            raise GameLifecycleError(
                "Battle-shock modifier application authority requires an application."
            )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("active_player_id", self.active_player_id),
        )
        object.__setattr__(self, "phase", _battle_phase_from_token(self.phase))
        object.__setattr__(
            self,
            "phase_start_battle_shocked_unit_ids",
            _validate_identifier_tuple(
                "phase_start_battle_shocked_unit_ids",
                self.phase_start_battle_shocked_unit_ids,
            ),
        )


type BattleShockModifierApplicationValidator = Callable[
    [BattleShockModifierApplicationAuthorityContext],
    None,
]


def battle_shock_modifier_applications_from_modifiers(
    *, provider_id: str, modifiers: tuple[RollModifier, ...]
) -> tuple[BattleShockModifierApplication, ...]:
    """Group a precomputed producer's modifiers into deterministic source rows."""
    provider = _validate_identifier("provider_id", provider_id)
    validated = _validate_roll_modifier_tuple(modifiers)
    _validate_unique_modifier_ids(validated)
    by_source_id: dict[str, list[RollModifier]] = {}
    for modifier in validated:
        if modifier.source_id is None:
            raise GameLifecycleError("Battle-shock modifier applications require source IDs.")
        by_source_id.setdefault(modifier.source_id, []).append(modifier)
    return tuple(
        BattleShockModifierApplication(
            hook_id=provider,
            source_id=source_id,
            modifiers=tuple(source_modifiers),
        )
        for source_id, source_modifiers in sorted(by_source_id.items())
    )


@dataclass(frozen=True, slots=True)
class BattleShockForcedTestContext:
    state: GameState
    active_player_id: str
    phase: BattlePhase
    phase_start_battle_shocked_unit_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("BattleShockForcedTestContext state must be a GameState.")
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("active_player_id", self.active_player_id),
        )
        object.__setattr__(self, "phase", _battle_phase_from_token(self.phase))
        object.__setattr__(
            self,
            "phase_start_battle_shocked_unit_ids",
            _validate_identifier_tuple(
                "phase_start_battle_shocked_unit_ids",
                self.phase_start_battle_shocked_unit_ids,
            ),
        )


@dataclass(frozen=True, slots=True)
class BattleShockModifierContext:
    state: GameState
    request: BattleShockTestRequest
    active_player_id: str
    phase: BattlePhase
    phase_start_battle_shocked_unit_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("BattleShockModifierContext state must be a GameState.")
        if type(self.request) is not BattleShockTestRequest:
            raise GameLifecycleError(
                "BattleShockModifierContext request must be a BattleShockTestRequest."
            )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("active_player_id", self.active_player_id),
        )
        object.__setattr__(self, "phase", _battle_phase_from_token(self.phase))
        object.__setattr__(
            self,
            "phase_start_battle_shocked_unit_ids",
            _validate_identifier_tuple(
                "phase_start_battle_shocked_unit_ids",
                self.phase_start_battle_shocked_unit_ids,
            ),
        )


@dataclass(frozen=True, slots=True)
class BattleShockRerollPermissionContext:
    state: GameState
    request: BattleShockTestRequest
    active_player_id: str
    phase: BattlePhase
    phase_start_battle_shocked_unit_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError(
                "BattleShockRerollPermissionContext state must be a GameState."
            )
        if type(self.request) is not BattleShockTestRequest:
            raise GameLifecycleError(
                "BattleShockRerollPermissionContext request must be a BattleShockTestRequest."
            )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("active_player_id", self.active_player_id),
        )
        object.__setattr__(self, "phase", _battle_phase_from_token(self.phase))
        object.__setattr__(
            self,
            "phase_start_battle_shocked_unit_ids",
            _validate_identifier_tuple(
                "phase_start_battle_shocked_unit_ids",
                self.phase_start_battle_shocked_unit_ids,
            ),
        )


@dataclass(frozen=True, slots=True)
class BattleShockDiceExpressionContext:
    state: GameState
    player_id: str
    unit_instance_id: str
    reason: BattleShockTestReason
    active_player_id: str
    phase: BattlePhase
    default_expression: DiceExpression
    phase_start_battle_shocked_unit_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("BattleShockDiceExpressionContext state must be a GameState.")
        object.__setattr__(self, "player_id", _validate_identifier("player_id", self.player_id))
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "reason",
            battle_shock_test_reason_from_token(self.reason),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("active_player_id", self.active_player_id),
        )
        object.__setattr__(self, "phase", _battle_phase_from_token(self.phase))
        if type(self.default_expression) is not DiceExpression:
            raise GameLifecycleError(
                "BattleShockDiceExpressionContext default_expression must be a DiceExpression."
            )
        _validate_battle_shock_dice_expression(self.default_expression)
        object.__setattr__(
            self,
            "phase_start_battle_shocked_unit_ids",
            _validate_identifier_tuple(
                "phase_start_battle_shocked_unit_ids",
                self.phase_start_battle_shocked_unit_ids,
            ),
        )


@dataclass(frozen=True, slots=True)
class BattleShockOutcomeContext:
    state: GameState
    decisions: DecisionController
    dice_manager: DiceRollManager
    result: BattleShockResult
    active_player_id: str
    phase: BattlePhase
    auto_passed: bool
    phase_start_battle_shocked_unit_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("BattleShockOutcomeContext state must be a GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError(
                "BattleShockOutcomeContext decisions must be a DecisionController."
            )
        if type(self.dice_manager) is not DiceRollManager:
            raise GameLifecycleError(
                "BattleShockOutcomeContext dice_manager must be a DiceRollManager."
            )
        if type(self.result) is not BattleShockResult:
            raise GameLifecycleError(
                "BattleShockOutcomeContext result must be a BattleShockResult."
            )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("active_player_id", self.active_player_id),
        )
        object.__setattr__(self, "phase", _battle_phase_from_token(self.phase))
        if type(self.auto_passed) is not bool:
            raise GameLifecycleError("BattleShockOutcomeContext auto_passed must be a bool.")
        object.__setattr__(
            self,
            "phase_start_battle_shocked_unit_ids",
            _validate_identifier_tuple(
                "phase_start_battle_shocked_unit_ids",
                self.phase_start_battle_shocked_unit_ids,
            ),
        )


@dataclass(frozen=True, slots=True)
class BattleShockPendingOutcomeAuthorityContext:
    """Internal loaded-provider context for one outcome-enqueued decision."""

    state: GameState
    decisions: DecisionController
    request: DecisionRequest

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("Pending Battle-shock outcome authority requires GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError(
                "Pending Battle-shock outcome authority requires DecisionController."
            )
        if type(self.request) is not DecisionRequest:
            raise GameLifecycleError(
                "Pending Battle-shock outcome authority requires DecisionRequest."
            )


@dataclass(frozen=True, slots=True)
class BattleShockPendingOutcomeAuthority:
    """Exact Battle-shock result occurrence claimed by a loaded outcome provider."""

    result: BattleShockResult
    resolved_event_index: int

    def __post_init__(self) -> None:
        if type(self.result) is not BattleShockResult:
            raise GameLifecycleError("Pending Battle-shock outcome result must be typed.")
        if type(self.resolved_event_index) is not int or self.resolved_event_index < 0:
            raise GameLifecycleError(
                "Pending Battle-shock outcome resolved-event index is invalid."
            )


@dataclass(frozen=True, slots=True)
class BattleShockHookBinding:
    hook_id: str
    source_id: str
    forced_test_handler: BattleShockForcedTestHandler | None = None
    dice_expression_handler: BattleShockDiceExpressionHandler | None = None
    modifier_handler: BattleShockModifierHandler | None = None
    modifier_application_validator: BattleShockModifierApplicationValidator | None = None
    modifier_source_effect_evidence: bool = False
    reroll_permission_handler: BattleShockRerollPermissionHandler | None = None
    outcome_handler: BattleShockOutcomeHandler | None = None
    pending_outcome_authority_validator: BattleShockPendingOutcomeAuthorityValidator | None = None
    historical_contribution_handler: HistoricalBattleShockContributionHandler | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if (
            self.forced_test_handler is None
            and self.dice_expression_handler is None
            and self.modifier_handler is None
            and self.reroll_permission_handler is None
            and self.outcome_handler is None
        ):
            raise GameLifecycleError("BattleShockHookBinding requires at least one handler.")
        if self.forced_test_handler is not None and not callable(self.forced_test_handler):
            raise GameLifecycleError("BattleShockHookBinding forced_test_handler must be callable.")
        if self.dice_expression_handler is not None and not callable(self.dice_expression_handler):
            raise GameLifecycleError(
                "BattleShockHookBinding dice_expression_handler must be callable."
            )
        if self.modifier_handler is not None and not callable(self.modifier_handler):
            raise GameLifecycleError("BattleShockHookBinding modifier_handler must be callable.")
        if self.modifier_application_validator is not None and not callable(
            self.modifier_application_validator
        ):
            raise GameLifecycleError(
                "BattleShockHookBinding modifier_application_validator must be callable."
            )
        if type(self.modifier_source_effect_evidence) is not bool:
            raise GameLifecycleError(
                "BattleShockHookBinding modifier_source_effect_evidence must be a bool."
            )
        if (
            self.modifier_application_validator is not None or self.modifier_source_effect_evidence
        ) and self.modifier_handler is None:
            raise GameLifecycleError(
                "BattleShockHookBinding modifier authority requires a modifier handler."
            )
        if self.modifier_application_validator is not None and self.modifier_source_effect_evidence:
            raise GameLifecycleError(
                "BattleShockHookBinding modifier authority path must be unambiguous."
            )
        if self.reroll_permission_handler is not None and not callable(
            self.reroll_permission_handler
        ):
            raise GameLifecycleError(
                "BattleShockHookBinding reroll_permission_handler must be callable."
            )
        if self.outcome_handler is not None and not callable(self.outcome_handler):
            raise GameLifecycleError("BattleShockHookBinding outcome_handler must be callable.")
        if self.pending_outcome_authority_validator is not None and not callable(
            self.pending_outcome_authority_validator
        ):
            raise GameLifecycleError(
                "BattleShockHookBinding pending outcome authority validator must be callable."
            )
        if self.pending_outcome_authority_validator is not None and self.outcome_handler is None:
            raise GameLifecycleError(
                "BattleShockHookBinding pending outcome authority requires an outcome handler."
            )
        if self.historical_contribution_handler is not None and not callable(
            self.historical_contribution_handler
        ):
            raise GameLifecycleError(
                "BattleShockHookBinding historical contribution handler must be callable."
            )


@dataclass(frozen=True, slots=True)
class BattleShockHookRegistry:
    bindings: tuple[BattleShockHookBinding, ...]

    def __post_init__(self) -> None:
        bindings = _validate_hook_bindings(self.bindings)
        object.__setattr__(self, "bindings", bindings)

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(cls, bindings: tuple[BattleShockHookBinding, ...]) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[BattleShockHookBinding, ...]:
        return self.bindings

    def modifiers_for(
        self,
        context: BattleShockModifierContext,
    ) -> tuple[RollModifier, ...]:
        applications = self.modifier_applications_for(context)
        return tuple(
            sorted(
                (modifier for application in applications for modifier in application.modifiers),
                key=lambda modifier: modifier.modifier_id,
            )
        )

    def modifier_applications_for(
        self,
        context: BattleShockModifierContext,
    ) -> tuple[BattleShockModifierApplication, ...]:
        if type(context) is not BattleShockModifierContext:
            raise GameLifecycleError("Battle-shock modifier hooks require a context.")
        applications: list[BattleShockModifierApplication] = []
        for binding in self.bindings:
            if binding.modifier_handler is None:
                continue
            handler_modifiers = binding.modifier_handler(context)
            modifiers = _validate_roll_modifier_tuple(handler_modifiers)
            if not modifiers:
                continue
            by_source_id: dict[str, list[RollModifier]] = {}
            for modifier in modifiers:
                if modifier.source_id is None:
                    raise GameLifecycleError(
                        "Battle-shock modifier applications require source IDs."
                    )
                by_source_id.setdefault(modifier.source_id, []).append(modifier)
            binding_applications = tuple(
                BattleShockModifierApplication(
                    hook_id=binding.hook_id,
                    source_id=source_id,
                    modifiers=tuple(source_modifiers),
                )
                for source_id, source_modifiers in sorted(by_source_id.items())
            )
            if binding.modifier_application_validator is not None:
                for application in binding_applications:
                    binding.modifier_application_validator(
                        BattleShockModifierApplicationAuthorityContext(
                            state=context.state,
                            request=context.request,
                            application=application,
                            active_player_id=context.active_player_id,
                            phase=context.phase,
                            phase_start_battle_shocked_unit_ids=(
                                context.phase_start_battle_shocked_unit_ids
                            ),
                        )
                    )
            applications.extend(binding_applications)
        flattened = tuple(
            modifier for application in applications for modifier in application.modifiers
        )
        _validate_unique_modifier_ids(flattened)
        return tuple(
            sorted(
                applications,
                key=lambda application: (application.hook_id, application.source_id),
            )
        )

    def reroll_permission_for(
        self,
        context: BattleShockRerollPermissionContext,
    ) -> RerollPermission | None:
        if type(context) is not BattleShockRerollPermissionContext:
            raise GameLifecycleError("Battle-shock reroll hooks require a context.")
        permissions: list[RerollPermission] = []
        for binding in self.bindings:
            if binding.reroll_permission_handler is None:
                continue
            permission = binding.reroll_permission_handler(context)
            if permission is None:
                continue
            if type(permission) is not RerollPermission:
                raise GameLifecycleError(
                    "Battle-shock reroll handlers must return RerollPermission or None."
                )
            permissions.append(permission)
        if len(permissions) > 1:
            raise GameLifecycleError("Multiple Battle-shock reroll permissions are available.")
        return permissions[0] if permissions else None

    def dice_expression_for(
        self,
        context: BattleShockDiceExpressionContext,
    ) -> DiceExpression:
        if type(context) is not BattleShockDiceExpressionContext:
            raise GameLifecycleError("Battle-shock dice-expression hooks require a context.")
        expression = context.default_expression
        override_source_ids: list[str] = []
        for binding in self.bindings:
            if binding.dice_expression_handler is None:
                continue
            candidate = binding.dice_expression_handler(context)
            if candidate is None:
                continue
            if type(candidate) is not DiceExpression:
                raise GameLifecycleError(
                    "Battle-shock dice-expression handlers must return DiceExpression or None."
                )
            _validate_battle_shock_dice_expression(candidate)
            if override_source_ids and candidate != expression:
                raise GameLifecycleError(
                    "Battle-shock dice-expression hooks produced conflicting overrides."
                )
            expression = candidate
            override_source_ids.append(binding.source_id)
        return expression

    def forced_below_starting_strength_unit_ids(
        self,
        context: BattleShockForcedTestContext,
    ) -> tuple[str, ...]:
        applications = self.forced_test_applications_for(context)
        return tuple(
            sorted(
                {
                    unit_id
                    for application in applications
                    for unit_id in application.unit_instance_ids
                }
            )
        )

    def forced_test_applications_for(
        self,
        context: BattleShockForcedTestContext,
    ) -> tuple[BattleShockForcedTestApplication, ...]:
        if type(context) is not BattleShockForcedTestContext:
            raise GameLifecycleError("Battle-shock forced-test hooks require a context.")
        applications: list[BattleShockForcedTestApplication] = []
        for binding in self.bindings:
            if binding.forced_test_handler is None:
                continue
            handler_ids = binding.forced_test_handler(context)
            forced_ids = _validate_identifier_tuple(
                "forced_below_starting_strength_unit_ids",
                handler_ids,
            )
            if forced_ids:
                applications.append(
                    BattleShockForcedTestApplication(
                        hook_id=binding.hook_id,
                        source_id=binding.source_id,
                        unit_instance_ids=forced_ids,
                    )
                )
        return tuple(
            sorted(
                applications,
                key=lambda application: (application.hook_id, application.source_id),
            )
        )

    def resolve_outcomes(self, context: BattleShockOutcomeContext) -> None:
        if type(context) is not BattleShockOutcomeContext:
            raise GameLifecycleError("Battle-shock outcome hooks require a context.")
        for binding in self.bindings:
            if binding.outcome_handler is None:
                continue
            binding.outcome_handler(context)

    def pending_outcome_authority_for(
        self,
        context: BattleShockPendingOutcomeAuthorityContext,
    ) -> BattleShockPendingOutcomeAuthority | None:
        """Return the sole loaded provider claim for an outcome-enqueued request."""

        if type(context) is not BattleShockPendingOutcomeAuthorityContext:
            raise GameLifecycleError("Pending Battle-shock outcome hooks require context.")
        claims: list[BattleShockPendingOutcomeAuthority] = []
        for binding in self.bindings:
            validator = binding.pending_outcome_authority_validator
            if validator is None:
                continue
            before_state = context.state.to_payload()
            before_queue = context.decisions.queue.pending_requests
            before_record_count = len(context.decisions.records)
            before_events = context.decisions.event_log.records
            claim = validator(context)
            if claim is not None and type(claim) is not BattleShockPendingOutcomeAuthority:
                raise GameLifecycleError(
                    "Pending Battle-shock outcome validators must return typed authority or None."
                )
            if (
                context.state.to_payload() != before_state
                or context.decisions.queue.pending_requests != before_queue
                or len(context.decisions.records) != before_record_count
                or context.decisions.event_log.records != before_events
            ):
                raise GameLifecycleError(
                    "Pending Battle-shock outcome authority validation mutated runtime state."
                )
            if claim is not None:
                if claim.resolved_event_index >= len(before_events):
                    raise GameLifecycleError(
                        "Pending Battle-shock outcome resolved-event index is out of bounds."
                    )
                claims.append(claim)
        if len(claims) > 1:
            raise GameLifecycleError(
                "Pending Battle-shock outcome request has multiple loaded authorities."
            )
        return None if not claims else claims[0]


def _validate_hook_bindings(value: object) -> tuple[BattleShockHookBinding, ...]:
    return validate_hook_bindings(
        value,
        lifecycle_event=LifecycleHookEvent.BATTLE_SHOCK,
        binding_type=BattleShockHookBinding,
        registry_name="BattleShockHookRegistry",
        invalid_binding_message=(
            "BattleShockHookRegistry bindings must contain BattleShockHookBinding values."
        ),
    )


def _validate_roll_modifier_tuple(value: object) -> tuple[RollModifier, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("Battle-shock modifier handlers must return a tuple.")
    modifiers: list[RollModifier] = []
    for modifier in cast(tuple[object, ...], value):
        if type(modifier) is not RollModifier:
            raise GameLifecycleError(
                "Battle-shock modifier handlers must return RollModifier values."
            )
        modifiers.append(modifier)
    return tuple(modifiers)


def _validate_unique_modifier_ids(modifiers: tuple[RollModifier, ...]) -> None:
    seen: set[str] = set()
    for modifier in modifiers:
        if modifier.modifier_id in seen:
            raise GameLifecycleError("Battle-shock modifier IDs must be unique.")
        seen.add(modifier.modifier_id)


def _validate_battle_shock_dice_expression(expression: DiceExpression) -> None:
    if expression not in {
        DiceExpression(quantity=2, sides=6),
        DiceExpression(quantity=3, sides=6),
    }:
        raise GameLifecycleError("Battle-shock dice expression must be 2D6 or 3D6.")


def _validate_identifier_tuple(field_name: str, value: object) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"Battle-shock hook {field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for item in cast(tuple[object, ...], value):
        identifier = _validate_identifier(f"{field_name} value", item)
        if identifier in seen:
            raise GameLifecycleError(f"Battle-shock hook {field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(identifiers)


def _battle_phase_from_token(token: object) -> BattlePhase:
    if type(token) is BattlePhase:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Battle-shock hook phase must be a BattlePhase.")
    try:
        return BattlePhase(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported Battle-shock hook phase: {token}.") from exc


_validate_identifier = IdentifierValidator(GameLifecycleError)
