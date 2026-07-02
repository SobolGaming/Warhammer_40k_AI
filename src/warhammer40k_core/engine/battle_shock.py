from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
    DiceRollSpecPayload,
    DiceRollState,
    DiceRollStatePayload,
    ModifiedRollResult,
    ModifiedRollResultPayload,
    UnmodifiedRollResult,
)
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import BattlefieldRuntimeState
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_leadership_characteristic_for_unit,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    UnitCharacteristicModifierContext,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.unit_state import (
    BelowHalfStrengthContext,
    BelowHalfStrengthContextPayload,
    StartingStrengthRecord,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

BATTLE_SHOCK_ROLL_TYPE = "battle_shock_roll"


class BattleShockTestReason(StrEnum):
    BELOW_HALF_STRENGTH = "below_half_strength"
    BELOW_STARTING_STRENGTH_FORCED = "below_starting_strength_forced"
    FORCED_BY_STRATAGEM = "forced_by_stratagem"
    FORCED_BY_ARMY_RULE = "forced_by_army_rule"


class StratagemTargetPermissionStatus(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"


class BattleShockTestRequestPayload(TypedDict):
    request_id: str
    game_id: str
    battle_round: int
    player_id: str
    unit_instance_id: str
    reason: str
    leadership_target: int
    below_half_strength_context: BelowHalfStrengthContextPayload
    spec: DiceRollSpecPayload


class BattleShockResultPayload(TypedDict):
    result_id: str
    request: BattleShockTestRequestPayload
    roll_state: DiceRollStatePayload
    modified_roll: ModifiedRollResultPayload
    total: int
    leadership_target: int
    passed: bool


class BattleShockedUnitStatePayload(TypedDict):
    player_id: str
    unit_instance_id: str
    model_instance_ids: list[str]
    source_result_id: str
    battle_round_started: int
    expires_at_player_command_phase_start: str
    expires_at_battle_round: int


class StratagemTargetPermissionPayload(TypedDict):
    player_id: str
    target_player_id: str
    target_unit_instance_id: str
    status: str
    allow_battle_shocked: bool
    denial_reason: str | None


@dataclass(frozen=True, slots=True)
class BattleShockTestRequest:
    request_id: str
    game_id: str
    battle_round: int
    player_id: str
    unit_instance_id: str
    reason: BattleShockTestReason
    leadership_target: int
    below_half_strength_context: BelowHalfStrengthContext
    spec: DiceRollSpec

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("BattleShockTestRequest request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("BattleShockTestRequest game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("BattleShockTestRequest battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("BattleShockTestRequest player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("BattleShockTestRequest unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(self, "reason", battle_shock_test_reason_from_token(self.reason))
        object.__setattr__(
            self,
            "leadership_target",
            _validate_positive_int(
                "BattleShockTestRequest leadership_target",
                self.leadership_target,
            ),
        )
        if type(self.below_half_strength_context) is not BelowHalfStrengthContext:
            raise GameLifecycleError(
                "BattleShockTestRequest below_half_strength_context must be a "
                "BelowHalfStrengthContext."
            )
        if self.below_half_strength_context.player_id != self.player_id:
            raise GameLifecycleError("BattleShockTestRequest context player drift.")
        if self.below_half_strength_context.unit_instance_id != self.unit_instance_id:
            raise GameLifecycleError("BattleShockTestRequest context unit drift.")
        if type(self.spec) is not DiceRollSpec:
            raise GameLifecycleError("BattleShockTestRequest spec must be a DiceRollSpec.")
        _validate_battle_shock_spec(self.spec, unit_instance_id=self.unit_instance_id)

    @classmethod
    def for_unit(
        cls,
        *,
        request_id: str,
        game_id: str,
        battle_round: int,
        player_id: str,
        unit_instance_id: str,
        reason: BattleShockTestReason,
        leadership_target: int,
        below_half_strength_context: BelowHalfStrengthContext,
        dice_expression: DiceExpression | None = None,
    ) -> Self:
        expression = _battle_shock_dice_expression(dice_expression)
        return cls(
            request_id=request_id,
            game_id=game_id,
            battle_round=battle_round,
            player_id=player_id,
            unit_instance_id=unit_instance_id,
            reason=reason,
            leadership_target=leadership_target,
            below_half_strength_context=below_half_strength_context,
            spec=DiceRollSpec(
                expression=expression,
                reason=f"Battle-shock test for {unit_instance_id}",
                roll_type=BATTLE_SHOCK_ROLL_TYPE,
                actor_id=unit_instance_id,
            ),
        )

    def to_payload(self) -> BattleShockTestRequestPayload:
        return {
            "request_id": self.request_id,
            "game_id": self.game_id,
            "battle_round": self.battle_round,
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "reason": self.reason.value,
            "leadership_target": self.leadership_target,
            "below_half_strength_context": self.below_half_strength_context.to_payload(),
            "spec": self.spec.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: BattleShockTestRequestPayload) -> Self:
        return cls(
            request_id=payload["request_id"],
            game_id=payload["game_id"],
            battle_round=payload["battle_round"],
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            reason=battle_shock_test_reason_from_token(payload["reason"]),
            leadership_target=payload["leadership_target"],
            below_half_strength_context=BelowHalfStrengthContext.from_payload(
                payload["below_half_strength_context"]
            ),
            spec=DiceRollSpec.from_payload(payload["spec"]),
        )


@dataclass(frozen=True, slots=True)
class BattleShockResult:
    result_id: str
    request: BattleShockTestRequest
    roll_state: DiceRollState
    modified_roll: ModifiedRollResult
    total: int
    leadership_target: int
    passed: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("BattleShockResult result_id", self.result_id),
        )
        if type(self.request) is not BattleShockTestRequest:
            raise GameLifecycleError("BattleShockResult request must be a BattleShockTestRequest.")
        if type(self.roll_state) is not DiceRollState:
            raise GameLifecycleError("BattleShockResult roll_state must be a DiceRollState.")
        if self.roll_state.original_result.spec != self.request.spec:
            raise GameLifecycleError("BattleShockResult roll_state spec drift.")
        if type(self.modified_roll) is not ModifiedRollResult:
            raise GameLifecycleError(
                "BattleShockResult modified_roll must be a ModifiedRollResult."
            )
        expected_unmodified = UnmodifiedRollResult.from_state(self.roll_state)
        if self.modified_roll.unmodified != expected_unmodified:
            raise GameLifecycleError("BattleShockResult modified roll drift.")
        object.__setattr__(
            self,
            "total",
            _validate_positive_int("BattleShockResult total", self.total),
        )
        if self.total != self.modified_roll.final_value:
            raise GameLifecycleError("BattleShockResult total drift.")
        object.__setattr__(
            self,
            "leadership_target",
            _validate_positive_int("BattleShockResult leadership_target", self.leadership_target),
        )
        if self.leadership_target != self.request.leadership_target:
            raise GameLifecycleError("BattleShockResult leadership target drift.")
        if type(self.passed) is not bool:
            raise GameLifecycleError("BattleShockResult passed must be a bool.")
        if self.passed != (self.total >= self.leadership_target):
            raise GameLifecycleError("BattleShockResult pass/fail drift.")

    @classmethod
    def from_roll_state(
        cls,
        *,
        result_id: str,
        request: BattleShockTestRequest,
        roll_state: DiceRollState,
        modifiers: tuple[RollModifier, ...] = (),
    ) -> Self:
        modified_roll = ModifiedRollResult.from_unmodified(
            UnmodifiedRollResult.from_state(roll_state),
            modifiers=modifiers,
        )
        return cls(
            result_id=result_id,
            request=request,
            roll_state=roll_state,
            modified_roll=modified_roll,
            total=modified_roll.final_value,
            leadership_target=request.leadership_target,
            passed=modified_roll.final_value >= request.leadership_target,
        )

    def to_payload(self) -> BattleShockResultPayload:
        return {
            "result_id": self.result_id,
            "request": self.request.to_payload(),
            "roll_state": self.roll_state.to_payload(),
            "modified_roll": self.modified_roll.to_payload(),
            "total": self.total,
            "leadership_target": self.leadership_target,
            "passed": self.passed,
        }

    @classmethod
    def from_payload(cls, payload: BattleShockResultPayload) -> Self:
        return cls(
            result_id=payload["result_id"],
            request=BattleShockTestRequest.from_payload(payload["request"]),
            roll_state=DiceRollState.from_payload(payload["roll_state"]),
            modified_roll=ModifiedRollResult.from_payload(payload["modified_roll"]),
            total=payload["total"],
            leadership_target=payload["leadership_target"],
            passed=payload["passed"],
        )


@dataclass(frozen=True, slots=True)
class BattleShockedUnitState:
    player_id: str
    unit_instance_id: str
    model_instance_ids: tuple[str, ...]
    source_result_id: str
    battle_round_started: int
    expires_at_player_command_phase_start: str
    expires_at_battle_round: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("BattleShockedUnitState player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("BattleShockedUnitState unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "model_instance_ids",
            _validate_identifier_tuple(
                "BattleShockedUnitState model_instance_ids",
                self.model_instance_ids,
                min_length=1,
            ),
        )
        object.__setattr__(
            self,
            "source_result_id",
            _validate_identifier("BattleShockedUnitState source_result_id", self.source_result_id),
        )
        object.__setattr__(
            self,
            "battle_round_started",
            _validate_positive_int(
                "BattleShockedUnitState battle_round_started",
                self.battle_round_started,
            ),
        )
        object.__setattr__(
            self,
            "expires_at_player_command_phase_start",
            _validate_identifier(
                "BattleShockedUnitState expires_at_player_command_phase_start",
                self.expires_at_player_command_phase_start,
            ),
        )
        object.__setattr__(
            self,
            "expires_at_battle_round",
            _validate_positive_int(
                "BattleShockedUnitState expires_at_battle_round",
                self.expires_at_battle_round,
            ),
        )
        if self.expires_at_battle_round <= self.battle_round_started:
            raise GameLifecycleError("BattleShockedUnitState expiry must be a future round.")

    @classmethod
    def from_result(
        cls,
        *,
        result: BattleShockResult,
        unit: UnitInstance,
    ) -> Self:
        if type(result) is not BattleShockResult:
            raise GameLifecycleError("BattleShockedUnitState requires a BattleShockResult.")
        if result.passed:
            raise GameLifecycleError("Passed Battle-shock results do not create shocked state.")
        if type(unit) is not UnitInstance:
            raise GameLifecycleError("BattleShockedUnitState requires a UnitInstance.")
        if unit.unit_instance_id != result.request.unit_instance_id:
            raise GameLifecycleError("BattleShockedUnitState unit drift.")
        return cls(
            player_id=result.request.player_id,
            unit_instance_id=result.request.unit_instance_id,
            model_instance_ids=tuple(model.model_instance_id for model in unit.own_models),
            source_result_id=result.result_id,
            battle_round_started=result.request.battle_round,
            expires_at_player_command_phase_start=result.request.player_id,
            expires_at_battle_round=result.request.battle_round + 1,
        )

    def to_payload(self) -> BattleShockedUnitStatePayload:
        return {
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "model_instance_ids": list(self.model_instance_ids),
            "source_result_id": self.source_result_id,
            "battle_round_started": self.battle_round_started,
            "expires_at_player_command_phase_start": self.expires_at_player_command_phase_start,
            "expires_at_battle_round": self.expires_at_battle_round,
        }

    @classmethod
    def from_payload(cls, payload: BattleShockedUnitStatePayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            model_instance_ids=tuple(payload["model_instance_ids"]),
            source_result_id=payload["source_result_id"],
            battle_round_started=payload["battle_round_started"],
            expires_at_player_command_phase_start=payload["expires_at_player_command_phase_start"],
            expires_at_battle_round=payload["expires_at_battle_round"],
        )


@dataclass(frozen=True, slots=True)
class StratagemTargetPermission:
    player_id: str
    target_player_id: str
    target_unit_instance_id: str
    status: StratagemTargetPermissionStatus
    allow_battle_shocked: bool = False
    denial_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("StratagemTargetPermission player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "target_player_id",
            _validate_identifier(
                "StratagemTargetPermission target_player_id",
                self.target_player_id,
            ),
        )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier(
                "StratagemTargetPermission target_unit_instance_id",
                self.target_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "status",
            stratagem_target_permission_status_from_token(self.status),
        )
        if type(self.allow_battle_shocked) is not bool:
            raise GameLifecycleError("StratagemTargetPermission allow_battle_shocked must be bool.")
        object.__setattr__(
            self,
            "denial_reason",
            _validate_optional_identifier(
                "StratagemTargetPermission denial_reason",
                self.denial_reason,
            ),
        )
        if (
            self.status is StratagemTargetPermissionStatus.ALLOWED
            and self.denial_reason is not None
        ):
            raise GameLifecycleError("Allowed StratagemTargetPermission cannot have denial_reason.")
        if self.status is StratagemTargetPermissionStatus.DENIED and self.denial_reason is None:
            raise GameLifecycleError("Denied StratagemTargetPermission requires denial_reason.")

    @property
    def is_allowed(self) -> bool:
        return self.status is StratagemTargetPermissionStatus.ALLOWED

    def to_payload(self) -> StratagemTargetPermissionPayload:
        return {
            "player_id": self.player_id,
            "target_player_id": self.target_player_id,
            "target_unit_instance_id": self.target_unit_instance_id,
            "status": self.status.value,
            "allow_battle_shocked": self.allow_battle_shocked,
            "denial_reason": self.denial_reason,
        }

    @classmethod
    def from_payload(cls, payload: StratagemTargetPermissionPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            target_player_id=payload["target_player_id"],
            target_unit_instance_id=payload["target_unit_instance_id"],
            status=stratagem_target_permission_status_from_token(payload["status"]),
            allow_battle_shocked=payload["allow_battle_shocked"],
            denial_reason=payload["denial_reason"],
        )


def collect_battle_shock_test_requests(
    *,
    game_id: str,
    battle_round: int,
    player_id: str,
    army: ArmyDefinition,
    battlefield_state: BattlefieldRuntimeState,
    starting_strength_records: tuple[StartingStrengthRecord, ...],
    state: GameState | None = None,
    forced_below_starting_strength_unit_ids: tuple[str, ...] = (),
    allow_duplicate_below_half_tests: bool = False,
    ability_index: AbilityCatalogIndex | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
    battle_shock_dice_expressions_by_unit_id: Mapping[str, DiceExpression] | None = None,
) -> tuple[BattleShockTestRequest, ...]:
    requested_game_id = _validate_identifier("game_id", game_id)
    requested_round = _validate_positive_int("battle_round", battle_round)
    requested_player_id = _validate_identifier("player_id", player_id)
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Battle-shock requests require an ArmyDefinition.")
    if army.player_id != requested_player_id:
        raise GameLifecycleError("Battle-shock request army player drift.")
    if type(battlefield_state) is not BattlefieldRuntimeState:
        raise GameLifecycleError("Battle-shock requests require BattlefieldRuntimeState.")
    catalog_ability_index = _battle_shock_ability_index(ability_index)
    records = _starting_strength_by_unit(
        starting_strength_records,
        player_id=requested_player_id,
    )
    forced_ids = set(
        _validate_identifier_tuple(
            "forced_below_starting_strength_unit_ids",
            forced_below_starting_strength_unit_ids,
            min_length=0,
        )
    )
    if type(allow_duplicate_below_half_tests) is not bool:
        raise GameLifecycleError("allow_duplicate_below_half_tests must be a bool.")
    runtime_modifiers = _runtime_modifier_registry(runtime_modifier_registry)
    dice_expressions_by_unit = _battle_shock_dice_expression_mapping(
        battle_shock_dice_expressions_by_unit_id
    )

    requests: list[BattleShockTestRequest] = []
    for unit in army.units:
        current_model_ids = _current_battlefield_model_ids(
            unit=unit,
            battlefield_state=battlefield_state,
        )
        if not current_model_ids:
            continue
        record = records.get(unit.unit_instance_id)
        if record is None:
            raise GameLifecycleError("Battle-shock request missing StartingStrengthRecord.")
        context = BelowHalfStrengthContext.from_unit(
            player_id=requested_player_id,
            unit=unit,
            starting_strength=record,
            current_model_ids=current_model_ids,
        )
        forced_test_added = False
        if unit.unit_instance_id in forced_ids and context.is_below_starting_strength:
            requests.append(
                _battle_shock_request_for_context(
                    game_id=requested_game_id,
                    battle_round=requested_round,
                    player_id=requested_player_id,
                    unit=unit,
                    context=context,
                    current_model_ids=current_model_ids,
                    reason=BattleShockTestReason.BELOW_STARTING_STRENGTH_FORCED,
                    ability_index=catalog_ability_index,
                    state=state,
                    runtime_modifier_registry=runtime_modifiers,
                    dice_expression=dice_expressions_by_unit.get(unit.unit_instance_id),
                )
            )
            forced_test_added = True
        if context.is_below_half_strength and (
            allow_duplicate_below_half_tests or not forced_test_added
        ):
            requests.append(
                _battle_shock_request_for_context(
                    game_id=requested_game_id,
                    battle_round=requested_round,
                    player_id=requested_player_id,
                    unit=unit,
                    context=context,
                    current_model_ids=current_model_ids,
                    reason=BattleShockTestReason.BELOW_HALF_STRENGTH,
                    ability_index=catalog_ability_index,
                    state=state,
                    runtime_modifier_registry=runtime_modifiers,
                    dice_expression=dice_expressions_by_unit.get(unit.unit_instance_id),
                )
            )
    return tuple(
        sorted(
            requests,
            key=lambda request: (request.unit_instance_id, request.reason.value),
        )
    )


def friendly_stratagem_target_permission(
    *,
    player_id: str,
    target_player_id: str,
    target_unit_instance_id: str,
    battle_shocked_unit_ids: tuple[str, ...],
    allow_battle_shocked: bool = False,
) -> StratagemTargetPermission:
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_target_player_id = _validate_identifier("target_player_id", target_player_id)
    requested_target_unit_id = _validate_identifier(
        "target_unit_instance_id",
        target_unit_instance_id,
    )
    shocked_ids = set(
        _validate_identifier_tuple("battle_shocked_unit_ids", battle_shocked_unit_ids)
    )
    if type(allow_battle_shocked) is not bool:
        raise GameLifecycleError("allow_battle_shocked must be a bool.")
    if (
        requested_player_id == requested_target_player_id
        and requested_target_unit_id in shocked_ids
        and not allow_battle_shocked
    ):
        return StratagemTargetPermission(
            player_id=requested_player_id,
            target_player_id=requested_target_player_id,
            target_unit_instance_id=requested_target_unit_id,
            status=StratagemTargetPermissionStatus.DENIED,
            allow_battle_shocked=allow_battle_shocked,
            denial_reason="friendly_battle_shocked_unit",
        )
    return StratagemTargetPermission(
        player_id=requested_player_id,
        target_player_id=requested_target_player_id,
        target_unit_instance_id=requested_target_unit_id,
        status=StratagemTargetPermissionStatus.ALLOWED,
        allow_battle_shocked=allow_battle_shocked,
    )


def battle_shock_test_reason_from_token(token: object) -> BattleShockTestReason:
    if type(token) is BattleShockTestReason:
        return token
    if type(token) is not str:
        raise GameLifecycleError("BattleShockTestReason token must be a string.")
    try:
        return BattleShockTestReason(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported BattleShockTestReason token: {token}.") from exc


def battle_shock_leadership_target_for_unit(
    unit: UnitInstance,
    *,
    current_model_ids: tuple[str, ...],
    ability_index: AbilityCatalogIndex,
    state: GameState | None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> int:
    return _best_leadership(
        unit,
        current_model_ids=current_model_ids,
        ability_index=ability_index,
        state=state,
        runtime_modifier_registry=runtime_modifier_registry,
    )


def stratagem_target_permission_status_from_token(
    token: object,
) -> StratagemTargetPermissionStatus:
    if type(token) is StratagemTargetPermissionStatus:
        return token
    if type(token) is not str:
        raise GameLifecycleError("StratagemTargetPermissionStatus token must be a string.")
    try:
        return StratagemTargetPermissionStatus(token)
    except ValueError as exc:
        raise GameLifecycleError(
            f"Unsupported StratagemTargetPermissionStatus token: {token}."
        ) from exc


def _battle_shock_request_for_context(
    *,
    game_id: str,
    battle_round: int,
    player_id: str,
    unit: UnitInstance,
    context: BelowHalfStrengthContext,
    current_model_ids: tuple[str, ...],
    reason: BattleShockTestReason,
    ability_index: AbilityCatalogIndex,
    state: GameState | None,
    runtime_modifier_registry: RuntimeModifierRegistry,
    dice_expression: DiceExpression | None,
) -> BattleShockTestRequest:
    return BattleShockTestRequest.for_unit(
        request_id=(
            f"battle-shock:{battle_round:02d}:{player_id}:{unit.unit_instance_id}:{reason.value}"
        ),
        game_id=game_id,
        battle_round=battle_round,
        player_id=player_id,
        unit_instance_id=unit.unit_instance_id,
        reason=reason,
        leadership_target=_best_leadership(
            unit,
            current_model_ids=current_model_ids,
            ability_index=ability_index,
            state=state,
            runtime_modifier_registry=runtime_modifier_registry,
        ),
        below_half_strength_context=context,
        dice_expression=dice_expression,
    )


def _best_leadership(
    unit: UnitInstance,
    *,
    current_model_ids: tuple[str, ...],
    ability_index: AbilityCatalogIndex,
    state: GameState | None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> int:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Leadership lookup requires a UnitInstance.")
    if type(ability_index) is not AbilityCatalogIndex:
        raise GameLifecycleError("Leadership lookup requires an AbilityCatalogIndex.")
    model_ids = set(_validate_identifier_tuple("current_model_ids", current_model_ids))
    if not model_ids:
        raise GameLifecycleError("Battle-shock Leadership lookup requires current models.")
    catalog_value = catalog_leadership_characteristic_for_unit(
        ability_index=ability_index,
        unit=unit,
        current_model_instance_ids=current_model_ids,
    )
    if catalog_value is not None:
        base_leadership = catalog_value
        return _modified_leadership_target(
            state=state,
            runtime_modifier_registry=runtime_modifier_registry,
            unit_instance_id=unit.unit_instance_id,
            base_leadership=base_leadership,
        )
    leadership_values = tuple(
        _model_leadership(model)
        for model in unit.own_models
        if model.model_instance_id in model_ids
    )
    if not leadership_values:
        raise GameLifecycleError("Battle-shock Leadership lookup found no models.")
    base_leadership = min(leadership_values)
    return _modified_leadership_target(
        state=state,
        runtime_modifier_registry=runtime_modifier_registry,
        unit_instance_id=unit.unit_instance_id,
        base_leadership=base_leadership,
    )


def _modified_leadership_target(
    *,
    state: GameState | None,
    runtime_modifier_registry: RuntimeModifierRegistry | None,
    unit_instance_id: str,
    base_leadership: int,
) -> int:
    if state is None:
        return base_leadership
    runtime_modifiers = _runtime_modifier_registry(runtime_modifier_registry)
    return runtime_modifiers.modified_unit_characteristic(
        UnitCharacteristicModifierContext(
            state=state,
            unit_instance_id=unit_instance_id,
            characteristic=Characteristic.LEADERSHIP,
            base_value=base_leadership,
            current_value=base_leadership,
        )
    )


def _runtime_modifier_registry(
    registry: RuntimeModifierRegistry | None,
) -> RuntimeModifierRegistry:
    if registry is None:
        return RuntimeModifierRegistry.empty()
    if type(registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError("Battle-shock runtime modifier registry is invalid.")
    return registry


def _battle_shock_ability_index(
    ability_index: AbilityCatalogIndex | None,
) -> AbilityCatalogIndex:
    if ability_index is None:
        return AbilityCatalogIndex.from_records(())
    if type(ability_index) is not AbilityCatalogIndex:
        raise GameLifecycleError("Battle-shock ability_index must be an AbilityCatalogIndex.")
    return ability_index


def _battle_shock_dice_expression(
    expression: DiceExpression | None,
) -> DiceExpression:
    if expression is None:
        return DiceExpression(quantity=2, sides=6)
    if type(expression) is not DiceExpression:
        raise GameLifecycleError("Battle-shock dice expression must be a DiceExpression.")
    if expression not in {
        DiceExpression(quantity=2, sides=6),
        DiceExpression(quantity=3, sides=6),
    }:
        raise GameLifecycleError("Battle-shock dice expression must be 2D6 or 3D6.")
    return expression


def _battle_shock_dice_expression_mapping(
    mapping: object,
) -> Mapping[str, DiceExpression]:
    if mapping is None:
        return {}
    if not isinstance(mapping, Mapping):
        raise GameLifecycleError("battle_shock_dice_expressions_by_unit_id must be a mapping.")
    validated: dict[str, DiceExpression] = {}
    for raw_unit_id, raw_expression in cast(Mapping[object, object], mapping).items():
        unit_id = _validate_identifier("battle_shock_dice_expressions_by_unit_id key", raw_unit_id)
        if unit_id in validated:
            raise GameLifecycleError(
                "battle_shock_dice_expressions_by_unit_id contains duplicate unit IDs."
            )
        validated[unit_id] = _battle_shock_dice_expression(cast(DiceExpression, raw_expression))
    return validated


def _model_leadership(model: ModelInstance) -> int:
    if type(model) is not ModelInstance:
        raise GameLifecycleError("Leadership lookup requires a ModelInstance.")
    for characteristic in model.characteristics:
        if characteristic.characteristic is Characteristic.LEADERSHIP:
            return characteristic.final
    raise GameLifecycleError("ModelInstance is missing Leadership.")


def _current_battlefield_model_ids(
    *,
    unit: UnitInstance,
    battlefield_state: BattlefieldRuntimeState,
) -> tuple[str, ...]:
    placement = battlefield_state.unit_placement_or_none(unit.unit_instance_id)
    if placement is None:
        return ()
    unit_model_by_id = {model.model_instance_id: model for model in unit.own_models}
    current_ids: list[str] = []
    for model_placement in placement.model_placements:
        model = unit_model_by_id.get(model_placement.model_instance_id)
        if model is None:
            raise GameLifecycleError("Battlefield unit placement contains unknown model.")
        if model.is_alive:
            current_ids.append(model.model_instance_id)
    return tuple(sorted(current_ids))


def _starting_strength_by_unit(
    records: object,
    *,
    player_id: str,
) -> dict[str, StartingStrengthRecord]:
    if type(records) is not tuple:
        raise GameLifecycleError("starting_strength_records must be a tuple.")
    mapped: dict[str, StartingStrengthRecord] = {}
    for record in cast(tuple[object, ...], records):
        if type(record) is not StartingStrengthRecord:
            raise GameLifecycleError(
                "starting_strength_records must contain StartingStrengthRecord values."
            )
        if record.player_id != player_id:
            continue
        if record.unit_instance_id in mapped:
            raise GameLifecycleError("starting_strength_records contains duplicate units.")
        mapped[record.unit_instance_id] = record
    return mapped


def _validate_battle_shock_spec(spec: DiceRollSpec, *, unit_instance_id: str) -> None:
    _battle_shock_dice_expression(spec.expression)
    if spec.roll_type != BATTLE_SHOCK_ROLL_TYPE:
        raise GameLifecycleError("BattleShockTestRequest spec roll_type drift.")
    if spec.actor_id != unit_instance_id:
        raise GameLifecycleError("BattleShockTestRequest spec actor drift.")


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int = 0,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    if len(validated) < min_length:
        raise GameLifecycleError(f"{field_name} must contain at least {min_length} values.")
    return tuple(sorted(validated))


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value
