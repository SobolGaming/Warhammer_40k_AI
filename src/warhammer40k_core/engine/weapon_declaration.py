from __future__ import annotations

from dataclasses import dataclass
from typing import NotRequired, Self, TypedDict, cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import RandomCharacteristicTiming
from warhammer40k_core.core.weapon_profiles import WeaponProfile, WeaponProfilePayload
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.shooting_types import ShootingType, shooting_type_from_token
from warhammer40k_core.engine.transports import FiringDeckSelection, FiringDeckSelectionPayload

SHOOTING_DECLARATION_PROPOSAL_KIND = "shooting_declaration"


class WeaponDeclarationPayload(TypedDict):
    attacker_model_instance_id: str
    wargear_id: str
    weapon_profile_id: str
    target_unit_instance_id: str
    shooting_type: str
    selected_weapon_ability_ids: list[str]
    firing_deck_source_unit_instance_id: str | None
    firing_deck_source_model_instance_id: str | None


class ShootingDeclarationProposalPayload(TypedDict):
    proposal_request_id: str
    proposal_kind: str
    player_id: str
    battle_round: int
    unit_instance_id: str
    source_decision_request_id: str
    source_decision_result_id: str
    declarations: list[WeaponDeclarationPayload]
    firing_deck_selection: FiringDeckSelectionPayload | None
    visibility_cache_key: str


class RangedAttackPoolPayload(TypedDict):
    attacker_model_instance_id: str
    wargear_id: str
    weapon_profile_id: str
    weapon_profile: WeaponProfilePayload
    target_unit_instance_id: str
    shooting_type: str
    attacks: int
    target_visible_model_ids: list[str]
    target_in_range_model_ids: list[str]
    hit_roll_modifier: int
    targeting_rule_ids: list[str]
    selected_weapon_ability_ids: list[str]
    firing_deck_source_unit_instance_id: str | None
    firing_deck_source_model_instance_id: str | None


class ShootingProposalViolationPayload(TypedDict):
    violation_code: str
    message: str
    field: str | None


class ShootingProposalValidationResultPayload(TypedDict):
    proposal_request_id: str
    proposal_kind: str
    is_valid: bool
    status: str
    violations: list[ShootingProposalViolationPayload]


class AvailableWeaponPayload(TypedDict):
    model_instance_id: str
    wargear_id: str
    weapon_profile_id: str
    weapon_profile: WeaponProfilePayload
    firing_deck_source_unit_instance_id: NotRequired[str]
    firing_deck_source_model_instance_id: NotRequired[str]


@dataclass(frozen=True, slots=True)
class WeaponDeclaration:
    attacker_model_instance_id: str
    wargear_id: str
    weapon_profile_id: str
    target_unit_instance_id: str
    shooting_type: ShootingType
    selected_weapon_ability_ids: tuple[str, ...] = ()
    firing_deck_source_unit_instance_id: str | None = None
    firing_deck_source_model_instance_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "attacker_model_instance_id",
            _validate_identifier(
                "WeaponDeclaration attacker_model_instance_id",
                self.attacker_model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "wargear_id",
            _validate_identifier("WeaponDeclaration wargear_id", self.wargear_id),
        )
        object.__setattr__(
            self,
            "weapon_profile_id",
            _validate_identifier(
                "WeaponDeclaration weapon_profile_id",
                self.weapon_profile_id,
            ),
        )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier(
                "WeaponDeclaration target_unit_instance_id",
                self.target_unit_instance_id,
            ),
        )
        object.__setattr__(self, "shooting_type", shooting_type_from_token(self.shooting_type))
        object.__setattr__(
            self,
            "selected_weapon_ability_ids",
            _validate_identifier_tuple(
                "WeaponDeclaration selected_weapon_ability_ids",
                self.selected_weapon_ability_ids,
            ),
        )
        object.__setattr__(
            self,
            "firing_deck_source_unit_instance_id",
            _validate_optional_identifier(
                "WeaponDeclaration firing_deck_source_unit_instance_id",
                self.firing_deck_source_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "firing_deck_source_model_instance_id",
            _validate_optional_identifier(
                "WeaponDeclaration firing_deck_source_model_instance_id",
                self.firing_deck_source_model_instance_id,
            ),
        )
        if (self.firing_deck_source_unit_instance_id is None) != (
            self.firing_deck_source_model_instance_id is None
        ):
            raise GameLifecycleError(
                "WeaponDeclaration Firing Deck source unit and model must be supplied together."
            )

    @property
    def uses_firing_deck(self) -> bool:
        return self.firing_deck_source_unit_instance_id is not None

    def to_payload(self) -> WeaponDeclarationPayload:
        return {
            "attacker_model_instance_id": self.attacker_model_instance_id,
            "wargear_id": self.wargear_id,
            "weapon_profile_id": self.weapon_profile_id,
            "target_unit_instance_id": self.target_unit_instance_id,
            "shooting_type": self.shooting_type.value,
            "selected_weapon_ability_ids": list(self.selected_weapon_ability_ids),
            "firing_deck_source_unit_instance_id": self.firing_deck_source_unit_instance_id,
            "firing_deck_source_model_instance_id": self.firing_deck_source_model_instance_id,
        }

    @classmethod
    def from_payload(cls, payload: WeaponDeclarationPayload) -> Self:
        missing = _weapon_declaration_missing_field(payload)
        if missing is not None:
            raise GameLifecycleError(f"WeaponDeclaration payload missing {missing}.")
        return cls(
            attacker_model_instance_id=payload["attacker_model_instance_id"],
            wargear_id=payload["wargear_id"],
            weapon_profile_id=payload["weapon_profile_id"],
            target_unit_instance_id=payload["target_unit_instance_id"],
            shooting_type=shooting_type_from_token(payload["shooting_type"]),
            selected_weapon_ability_ids=tuple(payload["selected_weapon_ability_ids"]),
            firing_deck_source_unit_instance_id=payload["firing_deck_source_unit_instance_id"],
            firing_deck_source_model_instance_id=payload["firing_deck_source_model_instance_id"],
        )


@dataclass(frozen=True, slots=True)
class ShootingDeclarationProposal:
    proposal_request_id: str
    proposal_kind: str
    player_id: str
    battle_round: int
    unit_instance_id: str
    source_decision_request_id: str
    source_decision_result_id: str
    declarations: tuple[WeaponDeclaration, ...]
    firing_deck_selection: FiringDeckSelection | None = None
    visibility_cache_key: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "proposal_request_id",
            _validate_identifier(
                "ShootingDeclarationProposal proposal_request_id",
                self.proposal_request_id,
            ),
        )
        object.__setattr__(
            self,
            "proposal_kind",
            _validate_identifier(
                "ShootingDeclarationProposal proposal_kind",
                self.proposal_kind,
            ),
        )
        if self.proposal_kind != SHOOTING_DECLARATION_PROPOSAL_KIND:
            raise GameLifecycleError("ShootingDeclarationProposal has unsupported proposal_kind.")
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("ShootingDeclarationProposal player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int(
                "ShootingDeclarationProposal battle_round",
                self.battle_round,
            ),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "ShootingDeclarationProposal unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "source_decision_request_id",
            _validate_identifier(
                "ShootingDeclarationProposal source_decision_request_id",
                self.source_decision_request_id,
            ),
        )
        object.__setattr__(
            self,
            "source_decision_result_id",
            _validate_identifier(
                "ShootingDeclarationProposal source_decision_result_id",
                self.source_decision_result_id,
            ),
        )
        object.__setattr__(
            self,
            "declarations",
            _validate_weapon_declarations(self.declarations),
        )
        if self.firing_deck_selection is not None and type(self.firing_deck_selection) is not (
            FiringDeckSelection
        ):
            raise GameLifecycleError(
                "ShootingDeclarationProposal firing_deck_selection must be FiringDeckSelection."
            )
        object.__setattr__(
            self,
            "visibility_cache_key",
            _validate_identifier(
                "ShootingDeclarationProposal visibility_cache_key",
                self.visibility_cache_key,
            ),
        )

    def validation_result_for_request(
        self,
        request: ShootingDeclarationProposalRequest,
    ) -> ShootingProposalValidationResult:
        if type(request) is not ShootingDeclarationProposalRequest:
            raise GameLifecycleError("Shooting proposal validation requires a proposal request.")
        if self.proposal_request_id != request.request_id:
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                violation_code="stale_proposal_request",
                message="Shooting declaration proposal_request_id does not match request.",
                field="proposal_request_id",
                status="stale",
            )
        if self.proposal_kind != request.proposal_kind:
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                violation_code="proposal_kind_drift",
                message="Shooting declaration proposal_kind does not match request.",
                field="proposal_kind",
            )
        if self.player_id != request.active_player_id:
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                violation_code="proposal_player_drift",
                message="Shooting declaration player_id does not match request.",
                field="player_id",
            )
        if self.battle_round != request.battle_round:
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                violation_code="proposal_battle_round_drift",
                message="Shooting declaration battle_round does not match request.",
                field="battle_round",
            )
        if self.unit_instance_id != request.unit_instance_id:
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                violation_code="proposal_unit_drift",
                message="Shooting declaration unit_instance_id does not match request.",
                field="unit_instance_id",
            )
        if self.source_decision_request_id != request.source_decision_request_id:
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                violation_code="source_decision_request_drift",
                message="Shooting declaration source_decision_request_id does not match request.",
                field="source_decision_request_id",
            )
        if self.source_decision_result_id != request.source_decision_result_id:
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                violation_code="source_decision_result_drift",
                message="Shooting declaration source_decision_result_id does not match request.",
                field="source_decision_result_id",
            )
        if self.visibility_cache_key != request.visibility_cache_key:
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                violation_code="visibility_cache_key_drift",
                message="Shooting declaration visibility_cache_key does not match request.",
                field="visibility_cache_key",
            )
        return ShootingProposalValidationResult.valid(proposal_request_id=request.request_id)

    def to_payload(self) -> ShootingDeclarationProposalPayload:
        return {
            "proposal_request_id": self.proposal_request_id,
            "proposal_kind": self.proposal_kind,
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "source_decision_request_id": self.source_decision_request_id,
            "source_decision_result_id": self.source_decision_result_id,
            "declarations": [declaration.to_payload() for declaration in self.declarations],
            "firing_deck_selection": (
                None
                if self.firing_deck_selection is None
                else self.firing_deck_selection.to_payload()
            ),
            "visibility_cache_key": self.visibility_cache_key,
        }

    @classmethod
    def from_payload(cls, payload: ShootingDeclarationProposalPayload) -> Self:
        firing_deck_payload = payload["firing_deck_selection"]
        return cls(
            proposal_request_id=payload["proposal_request_id"],
            proposal_kind=payload["proposal_kind"],
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            source_decision_request_id=payload["source_decision_request_id"],
            source_decision_result_id=payload["source_decision_result_id"],
            declarations=tuple(
                WeaponDeclaration.from_payload(declaration)
                for declaration in payload["declarations"]
            ),
            firing_deck_selection=(
                None
                if firing_deck_payload is None
                else FiringDeckSelection.from_payload(firing_deck_payload)
            ),
            visibility_cache_key=payload["visibility_cache_key"],
        )


@dataclass(frozen=True, slots=True)
class RangedAttackPool:
    attacker_model_instance_id: str
    wargear_id: str
    weapon_profile_id: str
    weapon_profile: WeaponProfile
    target_unit_instance_id: str
    shooting_type: ShootingType
    attacks: int
    target_visible_model_ids: tuple[str, ...]
    target_in_range_model_ids: tuple[str, ...]
    hit_roll_modifier: int = 0
    targeting_rule_ids: tuple[str, ...] = ()
    selected_weapon_ability_ids: tuple[str, ...] = ()
    firing_deck_source_unit_instance_id: str | None = None
    firing_deck_source_model_instance_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "attacker_model_instance_id",
            _validate_identifier(
                "RangedAttackPool attacker_model_instance_id",
                self.attacker_model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "wargear_id",
            _validate_identifier("RangedAttackPool wargear_id", self.wargear_id),
        )
        object.__setattr__(
            self,
            "weapon_profile_id",
            _validate_identifier(
                "RangedAttackPool weapon_profile_id",
                self.weapon_profile_id,
            ),
        )
        if type(self.weapon_profile) is not WeaponProfile:
            raise GameLifecycleError("RangedAttackPool weapon_profile must be a WeaponProfile.")
        if self.weapon_profile.profile_id != self.weapon_profile_id:
            raise GameLifecycleError("RangedAttackPool weapon_profile_id drift.")
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier(
                "RangedAttackPool target_unit_instance_id",
                self.target_unit_instance_id,
            ),
        )
        object.__setattr__(self, "shooting_type", shooting_type_from_token(self.shooting_type))
        object.__setattr__(
            self,
            "attacks",
            _validate_positive_int("RangedAttackPool attacks", self.attacks),
        )
        object.__setattr__(
            self,
            "target_visible_model_ids",
            _validate_identifier_tuple(
                "RangedAttackPool target_visible_model_ids",
                self.target_visible_model_ids,
            ),
        )
        object.__setattr__(
            self,
            "target_in_range_model_ids",
            _validate_identifier_tuple(
                "RangedAttackPool target_in_range_model_ids",
                self.target_in_range_model_ids,
            ),
        )
        if type(self.hit_roll_modifier) is not int:
            raise GameLifecycleError("RangedAttackPool hit_roll_modifier must be an int.")
        object.__setattr__(
            self,
            "targeting_rule_ids",
            _validate_identifier_tuple(
                "RangedAttackPool targeting_rule_ids",
                self.targeting_rule_ids,
            ),
        )
        object.__setattr__(
            self,
            "selected_weapon_ability_ids",
            _validate_identifier_tuple(
                "RangedAttackPool selected_weapon_ability_ids",
                self.selected_weapon_ability_ids,
            ),
        )
        object.__setattr__(
            self,
            "firing_deck_source_unit_instance_id",
            _validate_optional_identifier(
                "RangedAttackPool firing_deck_source_unit_instance_id",
                self.firing_deck_source_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "firing_deck_source_model_instance_id",
            _validate_optional_identifier(
                "RangedAttackPool firing_deck_source_model_instance_id",
                self.firing_deck_source_model_instance_id,
            ),
        )
        if (self.firing_deck_source_unit_instance_id is None) != (
            self.firing_deck_source_model_instance_id is None
        ):
            raise GameLifecycleError(
                "RangedAttackPool Firing Deck source unit and model must be supplied together."
            )

    @classmethod
    def from_declaration(
        cls,
        *,
        declaration: WeaponDeclaration,
        weapon_profile: WeaponProfile,
        attacks: int,
        target_visible_model_ids: tuple[str, ...],
        target_in_range_model_ids: tuple[str, ...],
        hit_roll_modifier: int,
        targeting_rule_ids: tuple[str, ...],
    ) -> Self:
        if type(declaration) is not WeaponDeclaration:
            raise GameLifecycleError("RangedAttackPool requires a WeaponDeclaration.")
        return cls(
            attacker_model_instance_id=declaration.attacker_model_instance_id,
            wargear_id=declaration.wargear_id,
            weapon_profile_id=declaration.weapon_profile_id,
            weapon_profile=weapon_profile,
            target_unit_instance_id=declaration.target_unit_instance_id,
            shooting_type=declaration.shooting_type,
            attacks=attacks,
            target_visible_model_ids=target_visible_model_ids,
            target_in_range_model_ids=target_in_range_model_ids,
            hit_roll_modifier=hit_roll_modifier,
            targeting_rule_ids=targeting_rule_ids,
            selected_weapon_ability_ids=declaration.selected_weapon_ability_ids,
            firing_deck_source_unit_instance_id=declaration.firing_deck_source_unit_instance_id,
            firing_deck_source_model_instance_id=declaration.firing_deck_source_model_instance_id,
        )

    def to_payload(self) -> RangedAttackPoolPayload:
        return {
            "attacker_model_instance_id": self.attacker_model_instance_id,
            "wargear_id": self.wargear_id,
            "weapon_profile_id": self.weapon_profile_id,
            "weapon_profile": self.weapon_profile.to_payload(),
            "target_unit_instance_id": self.target_unit_instance_id,
            "shooting_type": self.shooting_type.value,
            "attacks": self.attacks,
            "target_visible_model_ids": list(self.target_visible_model_ids),
            "target_in_range_model_ids": list(self.target_in_range_model_ids),
            "hit_roll_modifier": self.hit_roll_modifier,
            "targeting_rule_ids": list(self.targeting_rule_ids),
            "selected_weapon_ability_ids": list(self.selected_weapon_ability_ids),
            "firing_deck_source_unit_instance_id": self.firing_deck_source_unit_instance_id,
            "firing_deck_source_model_instance_id": self.firing_deck_source_model_instance_id,
        }

    @classmethod
    def from_payload(cls, payload: RangedAttackPoolPayload) -> Self:
        return cls(
            attacker_model_instance_id=payload["attacker_model_instance_id"],
            wargear_id=payload["wargear_id"],
            weapon_profile_id=payload["weapon_profile_id"],
            weapon_profile=WeaponProfile.from_payload(payload["weapon_profile"]),
            target_unit_instance_id=payload["target_unit_instance_id"],
            shooting_type=shooting_type_from_token(payload["shooting_type"]),
            attacks=payload["attacks"],
            target_visible_model_ids=tuple(payload["target_visible_model_ids"]),
            target_in_range_model_ids=tuple(payload["target_in_range_model_ids"]),
            hit_roll_modifier=payload["hit_roll_modifier"],
            targeting_rule_ids=tuple(payload["targeting_rule_ids"]),
            selected_weapon_ability_ids=tuple(payload["selected_weapon_ability_ids"]),
            firing_deck_source_unit_instance_id=payload["firing_deck_source_unit_instance_id"],
            firing_deck_source_model_instance_id=payload["firing_deck_source_model_instance_id"],
        )


@dataclass(frozen=True, slots=True)
class ShootingProposalViolation:
    violation_code: str
    message: str
    field: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "violation_code",
            _validate_identifier("ShootingProposalViolation violation_code", self.violation_code),
        )
        object.__setattr__(
            self,
            "message",
            _validate_non_empty_string("ShootingProposalViolation message", self.message),
        )
        object.__setattr__(
            self,
            "field",
            _validate_optional_identifier("ShootingProposalViolation field", self.field),
        )

    def to_payload(self) -> ShootingProposalViolationPayload:
        return {
            "violation_code": self.violation_code,
            "message": self.message,
            "field": self.field,
        }


@dataclass(frozen=True, slots=True)
class ShootingProposalValidationResult:
    proposal_request_id: str
    proposal_kind: str
    is_valid: bool
    status: str
    violations: tuple[ShootingProposalViolation, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "proposal_request_id",
            _validate_identifier(
                "ShootingProposalValidationResult proposal_request_id",
                self.proposal_request_id,
            ),
        )
        object.__setattr__(
            self,
            "proposal_kind",
            _validate_identifier(
                "ShootingProposalValidationResult proposal_kind",
                self.proposal_kind,
            ),
        )
        if self.proposal_kind != SHOOTING_DECLARATION_PROPOSAL_KIND:
            raise GameLifecycleError("ShootingProposalValidationResult proposal_kind drift.")
        if type(self.is_valid) is not bool:
            raise GameLifecycleError("ShootingProposalValidationResult is_valid must be a bool.")
        object.__setattr__(
            self,
            "status",
            _validate_identifier("ShootingProposalValidationResult status", self.status),
        )
        object.__setattr__(
            self,
            "violations",
            _validate_shooting_proposal_violations(self.violations),
        )
        if self.is_valid and self.violations:
            raise GameLifecycleError(
                "Valid ShootingProposalValidationResult must not include violations."
            )
        if not self.is_valid and not self.violations:
            raise GameLifecycleError(
                "Invalid ShootingProposalValidationResult requires violations."
            )

    @classmethod
    def valid(cls, *, proposal_request_id: str) -> Self:
        return cls(
            proposal_request_id=proposal_request_id,
            proposal_kind=SHOOTING_DECLARATION_PROPOSAL_KIND,
            is_valid=True,
            status="valid",
        )

    @classmethod
    def invalid(
        cls,
        *,
        proposal_request_id: str,
        violation_code: str,
        message: str,
        field: str | None = None,
        status: str = "invalid",
    ) -> Self:
        return cls(
            proposal_request_id=proposal_request_id,
            proposal_kind=SHOOTING_DECLARATION_PROPOSAL_KIND,
            is_valid=False,
            status=status,
            violations=(
                ShootingProposalViolation(
                    violation_code=violation_code,
                    message=message,
                    field=field,
                ),
            ),
        )

    def to_payload(self) -> ShootingProposalValidationResultPayload:
        return {
            "proposal_request_id": self.proposal_request_id,
            "proposal_kind": self.proposal_kind,
            "is_valid": self.is_valid,
            "status": self.status,
            "violations": [violation.to_payload() for violation in self.violations],
        }


@dataclass(frozen=True, slots=True)
class ShootingDeclarationProposalRequest:
    request_id: str
    active_player_id: str
    battle_round: int
    unit_instance_id: str
    source_decision_request_id: str
    source_decision_result_id: str
    visibility_cache_key: str
    proposal_kind: str = SHOOTING_DECLARATION_PROPOSAL_KIND

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("ShootingDeclarationProposalRequest request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier(
                "ShootingDeclarationProposalRequest active_player_id",
                self.active_player_id,
            ),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int(
                "ShootingDeclarationProposalRequest battle_round",
                self.battle_round,
            ),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "ShootingDeclarationProposalRequest unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "source_decision_request_id",
            _validate_identifier(
                "ShootingDeclarationProposalRequest source_decision_request_id",
                self.source_decision_request_id,
            ),
        )
        object.__setattr__(
            self,
            "source_decision_result_id",
            _validate_identifier(
                "ShootingDeclarationProposalRequest source_decision_result_id",
                self.source_decision_result_id,
            ),
        )
        object.__setattr__(
            self,
            "visibility_cache_key",
            _validate_identifier(
                "ShootingDeclarationProposalRequest visibility_cache_key",
                self.visibility_cache_key,
            ),
        )
        object.__setattr__(
            self,
            "proposal_kind",
            _validate_identifier(
                "ShootingDeclarationProposalRequest proposal_kind",
                self.proposal_kind,
            ),
        )
        if self.proposal_kind != SHOOTING_DECLARATION_PROPOSAL_KIND:
            raise GameLifecycleError("ShootingDeclarationProposalRequest proposal_kind drift.")


def shooting_declaration_missing_field(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return "payload"
    raw_payload = cast(dict[str, object], payload)
    required_fields = (
        "proposal_request_id",
        "proposal_kind",
        "player_id",
        "battle_round",
        "unit_instance_id",
        "source_decision_request_id",
        "source_decision_result_id",
        "declarations",
        "firing_deck_selection",
        "visibility_cache_key",
    )
    for field in required_fields:
        if field not in raw_payload:
            return field
    return None


def _weapon_declaration_missing_field(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return "declaration"
    raw_payload = cast(dict[str, object], payload)
    required_fields = (
        "attacker_model_instance_id",
        "wargear_id",
        "weapon_profile_id",
        "target_unit_instance_id",
        "shooting_type",
        "selected_weapon_ability_ids",
        "firing_deck_source_unit_instance_id",
        "firing_deck_source_model_instance_id",
    )
    for field in required_fields:
        if field not in raw_payload:
            return field
    return None


def shooting_declaration_proposal_from_json(payload: object) -> ShootingDeclarationProposal:
    missing = shooting_declaration_missing_field(payload)
    if missing is not None:
        raise GameLifecycleError(f"Shooting declaration proposal missing {missing}.")
    raw_payload = cast(ShootingDeclarationProposalPayload, payload)
    declarations = raw_payload["declarations"]
    if type(declarations) is not list:
        raise GameLifecycleError("Shooting declaration declarations must be a list.")
    return ShootingDeclarationProposal.from_payload(raw_payload)


def fixed_attacks_for_profile(weapon_profile: WeaponProfile) -> int:
    if type(weapon_profile) is not WeaponProfile:
        raise GameLifecycleError("fixed_attacks_for_profile requires a WeaponProfile.")
    fixed_attacks = weapon_profile.attack_profile.fixed_attacks
    if fixed_attacks is None:
        raise GameLifecycleError(
            "Phase 13B requires fixed attack counts; random attacks are resolved in Phase 13C."
        )
    return fixed_attacks


def attacks_for_profile(
    weapon_profile: WeaponProfile,
    *,
    manager: DiceRollManager,
    scope_id: str,
    actor_id: str,
) -> int:
    if type(weapon_profile) is not WeaponProfile:
        raise GameLifecycleError("attacks_for_profile requires a WeaponProfile.")
    if type(manager) is not DiceRollManager:
        raise GameLifecycleError("attacks_for_profile requires a DiceRollManager.")
    fixed_attacks = weapon_profile.attack_profile.fixed_attacks
    if fixed_attacks is not None:
        return fixed_attacks
    expression = weapon_profile.attack_profile.dice_expression
    if expression is None:
        raise GameLifecycleError("AttackProfile requires fixed attacks or a dice expression.")
    roll = manager.roll_random_characteristic(
        characteristic=Characteristic.ATTACKS,
        timing=RandomCharacteristicTiming.PER_WEAPON,
        scope_id=scope_id,
        expression=expression,
        reason=f"Phase 13C random Attacks roll for {weapon_profile.profile_id}",
        actor_id=actor_id,
    )
    return roll.value


def unresolved_attacks_for_validation(weapon_profile: WeaponProfile) -> int:
    if type(weapon_profile) is not WeaponProfile:
        raise GameLifecycleError("unresolved_attacks_for_validation requires a WeaponProfile.")
    fixed_attacks = weapon_profile.attack_profile.fixed_attacks
    if fixed_attacks is not None:
        return fixed_attacks
    if weapon_profile.attack_profile.dice_expression is None:
        raise GameLifecycleError("AttackProfile requires fixed attacks or a dice expression.")
    return 1


def _validate_weapon_declarations(values: object) -> tuple[WeaponDeclaration, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("ShootingDeclarationProposal declarations must be a tuple.")
    if not values:
        raise GameLifecycleError("ShootingDeclarationProposal requires declarations.")
    declarations = cast(tuple[object, ...], values)
    validated: list[WeaponDeclaration] = []
    for value in declarations:
        if type(value) is not WeaponDeclaration:
            raise GameLifecycleError(
                "ShootingDeclarationProposal declarations must contain WeaponDeclaration values."
            )
        validated.append(value)
    return tuple(validated)


def _validate_shooting_proposal_violations(
    values: object,
) -> tuple[ShootingProposalViolation, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("ShootingProposalValidationResult violations must be a tuple.")
    violations = cast(tuple[object, ...], values)
    validated: list[ShootingProposalViolation] = []
    for value in violations:
        if type(value) is not ShootingProposalViolation:
            raise GameLifecycleError(
                "ShootingProposalValidationResult violations must contain "
                "ShootingProposalViolation values."
            )
        validated.append(value)
    return tuple(validated)


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


def _validate_non_empty_string(field_name: str, value: object) -> str:
    return _validate_identifier(field_name, value)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an int.")
    if value <= 0:
        raise GameLifecycleError(f"{field_name} must be greater than zero.")
    return value


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    validated = tuple(_validate_identifier(field_name, value) for value in raw_values)
    if len(set(validated)) != len(validated):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return validated
