from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import (
    RulesetDescriptor,
)
from warhammer40k_core.core.weapon_profiles import RangeProfileKind
from warhammer40k_core.engine.ability_instance_selection import (
    WeaponInstanceSelectionError,
)
from warhammer40k_core.engine.attack_sequence import AttackSequence
from warhammer40k_core.engine.attack_weapon_inventory import melee_weapon_selection_context
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.interaction_metadata import (
    interaction_annotated_decision_request_payload,
)
from warhammer40k_core.engine.movement_proposals import (
    ProposalKind,
    ProposalValidationResult,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.weapon_declaration import (
    RangedAttackPool,
    WeaponDeclaration,
    attacks_for_profile,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


if TYPE_CHECKING:
    from warhammer40k_core.engine.fight_resolution import (
        MeleeDeclarationProposal,
        MeleeDeclarationProposalRequest,
        MeleeTargetAllocationPayload,
        MeleeWeaponDeclarationPayload,
    )


@dataclass(frozen=True, slots=True)
class MeleeTargetAllocation:
    target_unit_instance_id: str
    attacks: int | None = None

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.fight_resolution import (
            _validate_identifier,
            _validate_positive_int,
        )

        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier(
                "MeleeTargetAllocation target_unit_instance_id",
                self.target_unit_instance_id,
            ),
        )
        if self.attacks is not None:
            object.__setattr__(
                self,
                "attacks",
                _validate_positive_int("MeleeTargetAllocation attacks", self.attacks),
            )

    def to_payload(self) -> MeleeTargetAllocationPayload:

        payload: MeleeTargetAllocationPayload = {
            "target_unit_instance_id": self.target_unit_instance_id
        }
        if self.attacks is not None:
            payload["attacks"] = self.attacks
        return payload

    @classmethod
    def from_payload(cls, payload: MeleeTargetAllocationPayload) -> Self:
        return cls(
            target_unit_instance_id=payload["target_unit_instance_id"],
            attacks=payload.get("attacks"),
        )


@dataclass(frozen=True, slots=True)
class MeleeWeaponDeclaration:
    attacker_model_instance_id: str
    wargear_id: str
    weapon_profile_id: str
    target_allocations: tuple[MeleeTargetAllocation, ...]
    selected_weapon_ability_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.fight_resolution import (
            _validate_identifier,
            _validate_identifier_tuple,
            _validate_melee_target_allocations,
        )

        object.__setattr__(
            self,
            "attacker_model_instance_id",
            _validate_identifier(
                "MeleeWeaponDeclaration attacker_model_instance_id",
                self.attacker_model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "wargear_id",
            _validate_identifier("MeleeWeaponDeclaration wargear_id", self.wargear_id),
        )
        object.__setattr__(
            self,
            "weapon_profile_id",
            _validate_identifier(
                "MeleeWeaponDeclaration weapon_profile_id",
                self.weapon_profile_id,
            ),
        )
        object.__setattr__(
            self,
            "target_allocations",
            _validate_melee_target_allocations(self.target_allocations),
        )
        object.__setattr__(
            self,
            "selected_weapon_ability_ids",
            _validate_identifier_tuple(
                "MeleeWeaponDeclaration selected_weapon_ability_ids",
                self.selected_weapon_ability_ids,
            ),
        )

    @property
    def weapon_key(self) -> tuple[str, str, str]:
        return (
            self.attacker_model_instance_id,
            self.wargear_id,
            self.weapon_profile_id,
        )

    @property
    def target_unit_instance_ids(self) -> tuple[str, ...]:
        return tuple(allocation.target_unit_instance_id for allocation in self.target_allocations)

    def to_payload(self) -> MeleeWeaponDeclarationPayload:
        return {
            "attacker_model_instance_id": self.attacker_model_instance_id,
            "wargear_id": self.wargear_id,
            "weapon_profile_id": self.weapon_profile_id,
            "selected_weapon_ability_ids": list(self.selected_weapon_ability_ids),
            "target_allocations": [
                allocation.to_payload() for allocation in self.target_allocations
            ],
        }

    @classmethod
    def from_payload(cls, payload: MeleeWeaponDeclarationPayload) -> Self:
        return cls(
            attacker_model_instance_id=payload["attacker_model_instance_id"],
            wargear_id=payload["wargear_id"],
            weapon_profile_id=payload["weapon_profile_id"],
            selected_weapon_ability_ids=tuple(payload.get("selected_weapon_ability_ids", [])),
            target_allocations=tuple(
                MeleeTargetAllocation.from_payload(allocation)
                for allocation in payload["target_allocations"]
            ),
        )


def available_melee_weapons_payloads(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit: UnitInstance,
    army_catalog: ArmyCatalog,
    state: GameState | None = None,
    source_decision_result_id: str | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> tuple[JsonValue, ...]:
    from warhammer40k_core.engine.fight_resolution import (
        _available_melee_weapons_for_unit,
        _is_extra_attacks_weapon,
        _maximum_attacks_for_profile,
        _melee_target_unit_ids_for_model,
        _runtime_modifier_registry,
    )

    rows: list[JsonValue] = []
    for weapon in _available_melee_weapons_for_unit(
        unit=unit,
        army_catalog=army_catalog,
        state=state,
        source_decision_result_id=source_decision_result_id,
    ):
        target_ids = _melee_target_unit_ids_for_model(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_instance_id=unit.unit_instance_id,
            model_instance_id=weapon["model_instance_id"],
            state=state,
            source_decision_result_id=source_decision_result_id,
        )
        # A pure availability preview has no committed attack occasion. Lifecycle
        # requests always provide the activation result and carry its full inventory.
        context = None
        if target_ids and source_decision_result_id is not None:
            context = melee_weapon_selection_context(
                state=state,
                runtime_modifier_registry=_runtime_modifier_registry(runtime_modifier_registry),
                attacking_unit_instance_id=unit.unit_instance_id,
                attacker_model_instance_id=weapon["model_instance_id"],
                weapon_instance_id=weapon["weapon_instance_id"],
                source_request_id=source_decision_result_id,
                target_unit_instance_ids=target_ids,
                profile=weapon["weapon_profile"],
            )
        row = validate_json_value(
            {
                "model_instance_id": weapon["model_instance_id"],
                "wargear_id": weapon["wargear_id"],
                "weapon_profile_id": weapon["weapon_profile"].profile_id,
                "weapon_profile": weapon["weapon_profile"].to_payload(),
                "weapon_ability_selection_context": None
                if context is None
                else context.to_payload(),
                "required_weapon_ability_selections": []
                if context is None
                else [
                    interaction_annotated_decision_request_payload(request)
                    for request in context.selection_requests(
                        actor_id=scenario.battlefield_state.unit_placement_by_id(
                            unit.unit_instance_id
                        ).player_id
                    )
                ],
                "is_extra_attacks": _is_extra_attacks_weapon(weapon["weapon_profile"]),
                "maximum_declared_targets": _maximum_attacks_for_profile(weapon["weapon_profile"]),
                "fixed_attacks": weapon["weapon_profile"].attack_profile.fixed_attacks,
                "engaged_target_unit_instance_ids": list(target_ids),
            }
        )
        rows.append(row)
    return tuple(rows)


def validate_melee_declaration_rules(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    request: MeleeDeclarationProposalRequest,
    proposal: MeleeDeclarationProposal,
    army_catalog: ArmyCatalog,
    state: GameState | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> ProposalValidationResult:
    from warhammer40k_core.engine.fight_resolution import (
        _available_melee_weapons_by_key,
        _invalid_melee_validation,
        _is_extra_attacks_weapon,
        _melee_target_unit_ids_for_model,
        _required_primary_melee_model_ids,
        _runtime_modifier_registry,
        _unit_by_id,
        _validate_melee_target_allocation_counts,
        _validate_melee_target_count_limit,
    )

    if ruleset_descriptor.descriptor_hash != request.ruleset_descriptor_hash:
        return _invalid_melee_validation(
            request=request,
            violation_code="ruleset_descriptor_hash_drift",
            message="Melee declaration request ruleset descriptor hash drifted.",
            field="ruleset_descriptor_hash",
            status="stale",
        )
    if proposal.proposal_kind != request.proposal_kind:
        return _invalid_melee_validation(
            request=request,
            violation_code="proposal_kind_drift",
            message="Melee declaration proposal_kind does not match the pending request.",
            field="proposal_kind",
        )
    if not proposal.declarations:
        return _invalid_melee_validation(
            request=request,
            violation_code="melee_declaration_required",
            message="A fighting unit must declare melee attacks when it has legal attacks.",
            field="declarations",
        )
    unit = _unit_by_id(scenario=scenario, unit_instance_id=proposal.unit_instance_id)
    available = _available_melee_weapons_by_key(
        unit=unit,
        army_catalog=army_catalog,
        state=state,
        source_decision_result_id=request.source_decision_result_id,
    )
    required_primary_model_ids = _required_primary_melee_model_ids(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit=unit,
        available=available,
        state=state,
        source_decision_result_id=request.source_decision_result_id,
    )
    declared_primary_model_ids: set[str] = set()
    declared_weapon_keys: set[tuple[str, str, str]] = set()
    for declaration in proposal.declarations:
        key = declaration.weapon_key
        if key in declared_weapon_keys:
            return _invalid_melee_validation(
                request=request,
                violation_code="duplicate_melee_weapon_declaration",
                message="Each model/wargear/profile melee declaration may be used once.",
                field="declarations",
            )
        declared_weapon_keys.add(key)
        available_weapon = available.get(key)
        if available_weapon is None:
            return _invalid_melee_validation(
                request=request,
                violation_code="melee_weapon_not_available",
                message="Melee declaration selected a weapon that is not available.",
                field="declarations",
            )
        profile = available_weapon["weapon_profile"]
        if profile.range_profile.kind is not RangeProfileKind.MELEE:
            return _invalid_melee_validation(
                request=request,
                violation_code="melee_weapon_not_melee",
                message="Melee declaration selected a non-melee weapon profile.",
                field="weapon_profile_id",
            )
        engaged_target_ids = _melee_target_unit_ids_for_model(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_instance_id=proposal.unit_instance_id,
            model_instance_id=declaration.attacker_model_instance_id,
            state=state,
            source_decision_result_id=request.source_decision_result_id,
        )
        if not engaged_target_ids:
            return _invalid_melee_validation(
                request=request,
                violation_code="melee_model_not_engaged",
                message="Declared melee model is not engaged with any enemy unit.",
                field="attacker_model_instance_id",
            )
        target_count_validation = _validate_melee_target_count_limit(
            request=request,
            declaration=declaration,
            profile=profile,
        )
        if target_count_validation is not None:
            return target_count_validation
        for allocation in declaration.target_allocations:
            if allocation.target_unit_instance_id not in engaged_target_ids:
                return _invalid_melee_validation(
                    request=request,
                    violation_code="melee_target_not_engaged_with_model",
                    message="Melee declaration target is not engaged with the attacking model.",
                    field="target_allocations",
                )
        context = melee_weapon_selection_context(
            state=state,
            runtime_modifier_registry=_runtime_modifier_registry(runtime_modifier_registry),
            attacking_unit_instance_id=unit.unit_instance_id,
            attacker_model_instance_id=declaration.attacker_model_instance_id,
            weapon_instance_id=available_weapon["weapon_instance_id"],
            source_request_id=request.source_decision_result_id,
            target_unit_instance_ids=engaged_target_ids,
            profile=profile,
        )
        # Every committed attack authenticates its inventory before selection.
        matching_rows = tuple(
            row
            for row in request.available_weapons
            if isinstance(row, dict)
            and row.get("model_instance_id") == declaration.attacker_model_instance_id
            and row.get("wargear_id") == declaration.wargear_id
            and row.get("weapon_profile_id") == declaration.weapon_profile_id
        )
        if len(matching_rows) != 1 or matching_rows[0].get(
            "weapon_ability_selection_context"
        ) != validate_json_value(context.to_payload()):
            return _invalid_melee_validation(
                request=request,
                violation_code="weapon_ability_inventory_drift",
                message="Melee source inventory differs from the pending request.",
                field="declarations",
            )
        try:
            profiles = tuple(
                context.selected_profile(target, declaration.selected_weapon_ability_ids)
                for target in declaration.target_unit_instance_ids
            )
        except WeaponInstanceSelectionError as exc:
            return _invalid_melee_validation(
                request=request,
                violation_code="weapon_ability_selection_invalid",
                message=str(exc),
                field="declarations",
            )
        profile = profiles[0]
        attack_allocation_validation = _validate_melee_target_allocation_counts(
            request=request,
            declaration=declaration,
            profile=profile,
            scenario=scenario,
            state=state,
        )
        if attack_allocation_validation is not None:
            return attack_allocation_validation
        if _is_extra_attacks_weapon(profile):
            continue
        if declaration.attacker_model_instance_id in declared_primary_model_ids:
            return _invalid_melee_validation(
                request=request,
                violation_code="melee_model_declared_multiple_weapons",
                message="A melee model cannot declare more than one non-extra-attack weapon.",
                field="attacker_model_instance_id",
            )
        declared_primary_model_ids.add(declaration.attacker_model_instance_id)
    missing_primary = required_primary_model_ids - declared_primary_model_ids
    if missing_primary:
        return _invalid_melee_validation(
            request=request,
            violation_code="melee_primary_weapon_required",
            message="Each fighting model must select one non-extra melee weapon.",
            field="declarations",
        )
    return ProposalValidationResult.valid(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.MELEE_DECLARATION,
    )


def melee_attack_sequence_from_proposal(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    proposal: MeleeDeclarationProposal,
    army_catalog: ArmyCatalog,
    dice_manager: DiceRollManager,
    sequence_id: str,
    state: GameState | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> AttackSequence:
    from warhammer40k_core.engine.fight_resolution import (
        _available_melee_weapons_by_key,
        _cleave_attack_bonus_for_target,
        _melee_target_unit_ids_for_model,
        _melee_targeting_rule_ids,
        _require_declared_melee_attacks,
        _runtime_modifier_registry,
        _unit_by_id,
        _unit_made_charge_move,
        melee_targeting_permission_sources_for_model_target,
        target_model_ids_for_melee_attack,
    )

    unit = _unit_by_id(scenario=scenario, unit_instance_id=proposal.unit_instance_id)
    available = _available_melee_weapons_by_key(
        unit=unit,
        army_catalog=army_catalog,
        state=state,
        source_decision_result_id=proposal.source_decision_result_id,
    )
    runtime_modifiers = _runtime_modifier_registry(runtime_modifier_registry)
    pools: list[RangedAttackPool] = []
    for declaration_index, declaration in enumerate(proposal.declarations):
        available_weapon = available[declaration.weapon_key]
        profile = available_weapon["weapon_profile"]
        target_ids = _melee_target_unit_ids_for_model(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_instance_id=proposal.unit_instance_id,
            model_instance_id=declaration.attacker_model_instance_id,
            state=state,
            source_decision_result_id=proposal.source_decision_result_id,
        )
        if not set(declaration.target_unit_instance_ids) <= set(target_ids):
            raise GameLifecycleError("Melee target engagement drifted after validation.")
        context = melee_weapon_selection_context(
            state=state,
            runtime_modifier_registry=runtime_modifiers,
            attacking_unit_instance_id=unit.unit_instance_id,
            attacker_model_instance_id=declaration.attacker_model_instance_id,
            weapon_instance_id=available_weapon["weapon_instance_id"],
            source_request_id=proposal.source_decision_result_id,
            target_unit_instance_ids=target_ids,
            profile=profile,
        )
        profile = context.selected_profile(
            declaration.target_unit_instance_ids[0], declaration.selected_weapon_ability_ids
        )
        resolved_attacks = attacks_for_profile(
            profile,
            manager=dice_manager,
            scope_id=(
                f"{sequence_id}:declaration-{declaration_index:03d}:"
                f"{declaration.attacker_model_instance_id}:{declaration.wargear_id}:"
                f"{declaration.weapon_profile_id}:attacks"
            ),
            actor_id=proposal.player_id,
        )
        single_target = len(declaration.target_allocations) == 1
        if not single_target:
            declared_total = sum(
                _require_declared_melee_attacks(allocation)
                for allocation in declaration.target_allocations
            )
            if declared_total != resolved_attacks:
                raise GameLifecycleError("Melee split attack total drifted after validation.")
        for allocation in declaration.target_allocations:
            pool_profile = context.selected_profile(
                allocation.target_unit_instance_id, declaration.selected_weapon_ability_ids
            )
            cleave_bonus = _cleave_attack_bonus_for_target(
                scenario=scenario,
                profile=pool_profile,
                single_target=single_target,
                target_unit_instance_id=allocation.target_unit_instance_id,
                state=state,
            )
            attacks = (
                resolved_attacks + cleave_bonus
                if single_target
                else _require_declared_melee_attacks(allocation)
            )
            targeting_rule_ids = _melee_targeting_rule_ids(
                profile=pool_profile,
                cleave_bonus=cleave_bonus,
                unit_made_charge_move=_unit_made_charge_move(
                    state=state,
                    unit_instance_id=proposal.unit_instance_id,
                ),
                extra_rule_ids=melee_targeting_permission_sources_for_model_target(
                    scenario=scenario,
                    target_unit_instance_id=allocation.target_unit_instance_id,
                    attacker_model_instance_id=declaration.attacker_model_instance_id,
                    state=state,
                    source_decision_result_id=proposal.source_decision_result_id,
                ),
            )
            target_model_ids = target_model_ids_for_melee_attack(
                scenario=scenario,
                ruleset_descriptor=ruleset_descriptor,
                unit_instance_id=proposal.unit_instance_id,
                model_instance_id=declaration.attacker_model_instance_id,
                target_unit_instance_id=allocation.target_unit_instance_id,
                state=state,
                source_decision_result_id=proposal.source_decision_result_id,
            )
            pools.append(
                RangedAttackPool.from_declaration(
                    weapon_selection_context=context
                    if declaration.selected_weapon_ability_ids
                    else None,
                    declaration=WeaponDeclaration(
                        weapon_instance_id=available_weapon["weapon_instance_id"],
                        attacker_model_instance_id=declaration.attacker_model_instance_id,
                        wargear_id=declaration.wargear_id,
                        weapon_profile_id=declaration.weapon_profile_id,
                        target_unit_instance_id=allocation.target_unit_instance_id,
                        shooting_type=ShootingType.NORMAL,
                        selected_weapon_ability_ids=declaration.selected_weapon_ability_ids,
                    ),
                    weapon_profile=pool_profile,
                    attacks=attacks,
                    target_visible_model_ids=target_model_ids,
                    target_in_range_model_ids=target_model_ids,
                    hit_roll_modifier=0,
                    targeting_rule_ids=targeting_rule_ids,
                )
            )
    return AttackSequence(
        sequence_id=sequence_id,
        source_phase=BattlePhase.FIGHT,
        attacker_player_id=proposal.player_id,
        attacking_unit_instance_id=proposal.unit_instance_id,
        attack_pools=tuple(pools),
    )


def build_melee_declaration_request(
    *,
    request_id: str,
    game_id: str,
    battle_round: int,
    active_player_id: str,
    actor_id: str,
    unit_instance_id: str,
    source_decision_request_id: str,
    source_decision_result_id: str,
    ruleset_descriptor: RulesetDescriptor,
    available_weapons: tuple[JsonValue, ...],
    target_unit_instance_ids: tuple[str, ...],
) -> DecisionRequest:
    from warhammer40k_core.engine.decision_request import (
        DecisionRequest,
        parameterized_decision_option,
    )
    from warhammer40k_core.engine.fight_resolution import (
        SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
        MeleeDeclarationProposalRequest,
    )
    from warhammer40k_core.engine.interaction_metadata import NESTED_INTERACTION_REQUESTS_KEY

    nested: list[JsonValue] = []
    for row in available_weapons:
        if not isinstance(row, dict):
            raise GameLifecycleError("Melee availability row must be an object.")
        requests = row.get("required_weapon_ability_selections", [])
        if not isinstance(requests, list):
            raise GameLifecycleError("Melee availability requires finite instance requests.")
        nested.extend(requests)
    proposal_request = MeleeDeclarationProposalRequest(
        request_id=request_id,
        actor_id=actor_id,
        game_id=game_id,
        battle_round=battle_round,
        active_player_id=active_player_id,
        unit_instance_id=unit_instance_id,
        source_decision_request_id=source_decision_request_id,
        source_decision_result_id=source_decision_result_id,
        ruleset_descriptor_hash=ruleset_descriptor.descriptor_hash,
        available_weapons=available_weapons,
        target_unit_instance_ids=target_unit_instance_ids,
    )
    return DecisionRequest(
        request_id=request_id,
        decision_type=SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
        actor_id=actor_id,
        payload=validate_json_value(
            {
                "proposal_request": proposal_request.to_payload(),
                NESTED_INTERACTION_REQUESTS_KEY: nested,
            }
        ),
        options=(parameterized_decision_option(),),
    )
