from __future__ import annotations

from dataclasses import dataclass, replace
from typing import cast

from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldScenario,
    PlacementError,
    UnitPlacement,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.phases.movement_rules_unit_disembark import (
    RulesUnitDisembarkResolution,
    RulesUnitDisembarkSelection,
    apply_rules_unit_disembark_to_battlefield,
    resolve_rules_unit_disembark,
)
from warhammer40k_core.engine.rules_unit_placement import (
    RulesUnitPlacement,
    RulesUnitPlacementPayload,
)
from warhammer40k_core.engine.rules_units import (
    RulesUnitComponent,
    RulesUnitView,
    rules_unit_contains_component_lineage,
)
from warhammer40k_core.engine.transports import (
    EMERGENCY_DISEMBARK_MOVE_SOURCE_ID,
    EMERGENCY_DISEMBARK_RULE_ID,
    DestroyedTransportDisembark,
    DestroyedTransportDisembarkPayload,
    DestroyedTransportHazardRolls,
    DestroyedTransportHazardRollsPayload,
    DisembarkModeKind,
    TransportCargoState,
    TransportMovementStatus,
    TransportRestrictionOverride,
)
from warhammer40k_core.geometry.pose import GeometryError

DESTROYED_TRANSPORT_RULES_UNIT_DISEMBARK_EVENT_FIELD = "destroyed_transport_rules_unit_disembark"


@dataclass(frozen=True, slots=True)
class DestroyedTransportRulesUnitDisembark:
    """One canonical attached-rules-unit Emergency Disembark resolution."""

    placement: RulesUnitDisembarkResolution
    hazard_rolls: DestroyedTransportHazardRolls
    destroyed_model_instance_ids: tuple[str, ...]
    hazard_destroyed_model_instance_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.placement) is not RulesUnitDisembarkResolution:
            raise GameLifecycleError(
                "Destroyed Transport rules-unit disembark requires grouped placement."
            )
        if type(self.hazard_rolls) is not DestroyedTransportHazardRolls:
            raise GameLifecycleError(
                "Destroyed Transport rules-unit disembark requires hazard rolls."
            )
        destroyed_ids = _validate_identifier_tuple(
            "Destroyed Transport rules-unit omitted model ids",
            self.destroyed_model_instance_ids,
        )
        hazard_destroyed_ids = _validate_identifier_tuple(
            "Destroyed Transport rules-unit hazard casualty ids",
            self.hazard_destroyed_model_instance_ids,
        )
        object.__setattr__(self, "destroyed_model_instance_ids", destroyed_ids)
        object.__setattr__(
            self,
            "hazard_destroyed_model_instance_ids",
            hazard_destroyed_ids,
        )
        selection = self.placement.selection
        if (
            selection.disembark_mode is not DisembarkModeKind.EMERGENCY_DISEMBARK
            or selection.transport_movement_status is not TransportMovementStatus.NOT_MOVED
            or selection.unit_instance_id != self.hazard_rolls.unit_instance_id
            or selection.player_id != self.hazard_rolls.player_id
            or selection.battle_round != self.hazard_rolls.battle_round
            or selection.transport_unit_instance_id != self.hazard_rolls.transport_unit_instance_id
        ):
            raise GameLifecycleError(
                "Destroyed Transport rules-unit disembark hazard context drift."
            )
        placed_ids = {
            placement.model_instance_id
            for placement in selection.attempted_placement.model_placements
        }
        omitted_ids = set(destroyed_ids)
        hazard_casualty_ids = set(hazard_destroyed_ids)
        if (
            placed_ids & omitted_ids
            or placed_ids & hazard_casualty_ids
            or omitted_ids & hazard_casualty_ids
            or placed_ids | omitted_ids | hazard_casualty_ids
            != set(self.hazard_rolls.model_instance_ids)
        ):
            raise GameLifecycleError(
                "Destroyed Transport rules-unit disembark model inventory drift."
            )
        if self.placement.is_valid:
            cargo = self.placement.updated_cargo_state
            disembarked_state = self.placement.disembarked_unit_state
            if cargo is None or disembarked_state is None:
                raise GameLifecycleError(
                    "Valid destroyed Transport rules-unit disembark lacks mutation state."
                )
            if any(
                cargo.contains_unit(component_id)
                for component_id in self.hazard_rolls.component_unit_instance_ids
            ):
                raise GameLifecycleError(
                    "Destroyed Transport rules-unit cargo mutation retained a component."
                )
            if (
                disembarked_state.unit_instance_id != self.hazard_rolls.unit_instance_id
                or disembarked_state.source_rule_id != EMERGENCY_DISEMBARK_RULE_ID
            ):
                raise GameLifecycleError(
                    "Destroyed Transport rules-unit disembarked state identity drift."
                )

    @property
    def is_valid(self) -> bool:
        return self.placement.is_valid

    def event_evidence(self) -> DestroyedTransportRulesUnitDisembarkEvidence:
        if not self.is_valid:
            raise GameLifecycleError(
                "Invalid destroyed Transport rules-unit disembark has no event evidence."
            )
        return DestroyedTransportRulesUnitDisembarkEvidence(
            player_id=self.hazard_rolls.player_id,
            battle_round=self.hazard_rolls.battle_round,
            rules_unit_instance_id=self.hazard_rolls.unit_instance_id,
            component_unit_instance_ids=self.hazard_rolls.component_unit_instance_ids,
            transport_unit_instance_id=self.hazard_rolls.transport_unit_instance_id,
            disembark_mode=DisembarkModeKind.EMERGENCY_DISEMBARK,
            attempted_placement=self.placement.selection.attempted_placement,
            hazard_rolls=self.hazard_rolls,
            destroyed_model_instance_ids=self.destroyed_model_instance_ids,
            hazard_destroyed_model_instance_ids=(self.hazard_destroyed_model_instance_ids),
        )

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            validate_json_value(
                {
                    "placement": self.placement.to_payload(),
                    "hazard_rolls": self.hazard_rolls.to_payload(),
                    "destroyed_model_instance_ids": list(self.destroyed_model_instance_ids),
                    "hazard_destroyed_model_instance_ids": list(
                        self.hazard_destroyed_model_instance_ids
                    ),
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class DestroyedTransportRulesUnitDisembarkEvidence:
    player_id: str
    battle_round: int
    rules_unit_instance_id: str
    component_unit_instance_ids: tuple[str, ...]
    transport_unit_instance_id: str
    disembark_mode: DisembarkModeKind
    attempted_placement: RulesUnitPlacement
    hazard_rolls: DestroyedTransportHazardRolls
    destroyed_model_instance_ids: tuple[str, ...]
    hazard_destroyed_model_instance_ids: tuple[str, ...]
    source_rule_id: str = EMERGENCY_DISEMBARK_MOVE_SOURCE_ID

    def __post_init__(self) -> None:
        player_id = _validate_identifier("Emergency Disembark evidence player_id", self.player_id)
        rules_unit_id = _validate_identifier(
            "Emergency Disembark evidence rules_unit_instance_id",
            self.rules_unit_instance_id,
        )
        component_ids = _validate_identifier_tuple(
            "Emergency Disembark evidence component ids",
            self.component_unit_instance_ids,
        )
        transport_id = _validate_identifier(
            "Emergency Disembark evidence transport_unit_instance_id",
            self.transport_unit_instance_id,
        )
        omitted_ids = _validate_identifier_tuple(
            "Emergency Disembark evidence omitted model ids",
            self.destroyed_model_instance_ids,
        )
        hazard_casualty_ids = _validate_identifier_tuple(
            "Emergency Disembark evidence hazard casualty ids",
            self.hazard_destroyed_model_instance_ids,
        )
        object.__setattr__(self, "player_id", player_id)
        object.__setattr__(self, "rules_unit_instance_id", rules_unit_id)
        object.__setattr__(self, "component_unit_instance_ids", component_ids)
        object.__setattr__(self, "transport_unit_instance_id", transport_id)
        object.__setattr__(self, "destroyed_model_instance_ids", omitted_ids)
        object.__setattr__(
            self,
            "hazard_destroyed_model_instance_ids",
            hazard_casualty_ids,
        )
        if type(self.battle_round) is not int or self.battle_round < 1:
            raise GameLifecycleError("Emergency Disembark evidence battle_round must be positive.")
        if self.disembark_mode is not DisembarkModeKind.EMERGENCY_DISEMBARK:
            raise GameLifecycleError("Emergency Disembark evidence mode drift.")
        if self.source_rule_id != EMERGENCY_DISEMBARK_MOVE_SOURCE_ID:
            raise GameLifecycleError("Emergency Disembark evidence source rule drift.")
        if rules_unit_id in component_ids:
            raise GameLifecycleError(
                "Emergency Disembark grouped evidence requires canonical attached identity."
            )
        if type(self.attempted_placement) is not RulesUnitPlacement:
            raise GameLifecycleError("Emergency Disembark evidence placement is invalid.")
        if type(self.hazard_rolls) is not DestroyedTransportHazardRolls:
            raise GameLifecycleError("Emergency Disembark evidence hazard rolls are invalid.")
        if (
            self.hazard_rolls.player_id != player_id
            or self.hazard_rolls.battle_round != self.battle_round
            or self.hazard_rolls.unit_instance_id != rules_unit_id
            or self.hazard_rolls.component_unit_instance_ids != component_ids
            or self.hazard_rolls.transport_unit_instance_id != transport_id
            or self.hazard_rolls.disembark_mode is not self.disembark_mode
            or self.attempted_placement.rules_unit_instance_id != rules_unit_id
            or not set(self.attempted_placement.component_unit_instance_ids).issubset(component_ids)
        ):
            raise GameLifecycleError("Emergency Disembark evidence context drift.")
        placed_ids = {
            placement.model_instance_id for placement in self.attempted_placement.model_placements
        }
        omitted_id_set = set(omitted_ids)
        hazard_casualty_id_set = set(hazard_casualty_ids)
        if (
            placed_ids & omitted_id_set
            or placed_ids & hazard_casualty_id_set
            or omitted_id_set & hazard_casualty_id_set
            or placed_ids | omitted_id_set | hazard_casualty_id_set
            != set(self.hazard_rolls.model_instance_ids)
        ):
            raise GameLifecycleError("Emergency Disembark evidence model inventory drift.")

    @property
    def placed_model_instance_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                placement.model_instance_id
                for placement in self.attempted_placement.model_placements
            )
        )

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            validate_json_value(
                {
                    "source_rule_id": self.source_rule_id,
                    "player_id": self.player_id,
                    "battle_round": self.battle_round,
                    "rules_unit_instance_id": self.rules_unit_instance_id,
                    "component_unit_instance_ids": list(self.component_unit_instance_ids),
                    "transport_unit_instance_id": self.transport_unit_instance_id,
                    "disembark_mode": self.disembark_mode.value,
                    "attempted_rules_unit_placement": self.attempted_placement.to_payload(),
                    "hazard_rolls": self.hazard_rolls.to_payload(),
                    "destroyed_model_instance_ids": list(self.destroyed_model_instance_ids),
                    "hazard_destroyed_model_instance_ids": list(
                        self.hazard_destroyed_model_instance_ids
                    ),
                }
            ),
        )

    @classmethod
    def from_payload(cls, payload: object) -> DestroyedTransportRulesUnitDisembarkEvidence:
        validated_payload = validate_json_value(payload)
        if not isinstance(validated_payload, dict):
            raise GameLifecycleError("Emergency Disembark evidence payload must be an object.")
        payload = validated_payload
        try:
            return cls(
                source_rule_id=cast(str, payload["source_rule_id"]),
                player_id=cast(str, payload["player_id"]),
                battle_round=cast(int, payload["battle_round"]),
                rules_unit_instance_id=cast(str, payload["rules_unit_instance_id"]),
                component_unit_instance_ids=_payload_identifier_tuple(
                    "Emergency Disembark evidence component ids",
                    payload["component_unit_instance_ids"],
                ),
                transport_unit_instance_id=cast(str, payload["transport_unit_instance_id"]),
                disembark_mode=DisembarkModeKind(cast(str, payload["disembark_mode"])),
                attempted_placement=RulesUnitPlacement.from_payload(
                    cast(
                        RulesUnitPlacementPayload,
                        payload["attempted_rules_unit_placement"],
                    )
                ),
                hazard_rolls=DestroyedTransportHazardRolls.from_payload(
                    cast(DestroyedTransportHazardRollsPayload, payload["hazard_rolls"])
                ),
                destroyed_model_instance_ids=_payload_identifier_tuple(
                    "Emergency Disembark evidence omitted model ids",
                    payload["destroyed_model_instance_ids"],
                ),
                hazard_destroyed_model_instance_ids=_payload_identifier_tuple(
                    "Emergency Disembark evidence hazard casualty ids",
                    payload["hazard_destroyed_model_instance_ids"],
                ),
            )
        except GameLifecycleError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise GameLifecycleError("Emergency Disembark evidence payload is invalid.") from exc


@dataclass(frozen=True, slots=True)
class EmergencyDisembarkOmittedModelEvidence:
    player_id: str
    rules_unit_instance_id: str
    component_unit_instance_ids: tuple[str, ...]
    placed_model_instance_ids: tuple[str, ...]
    destroyed_model_instance_ids: tuple[str, ...]


def resolve_destroyed_transport_rules_unit_disembark(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    cargo_state: TransportCargoState,
    rules_unit: RulesUnitView,
    attempted_placement: RulesUnitPlacement,
    transport_placement: UnitPlacement,
    hazard_rolls: DestroyedTransportHazardRolls,
    objective_markers: tuple[ObjectiveMarker, ...] = (),
    restriction_overrides: tuple[TransportRestrictionOverride, ...] = (),
) -> DestroyedTransportRulesUnitDisembark:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError(
            "Destroyed Transport rules-unit disembark requires BattlefieldScenario."
        )
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError(
            "Destroyed Transport rules-unit disembark requires RulesetDescriptor."
        )
    if not rules_unit.is_attached_rules_unit:
        raise GameLifecycleError(
            "Destroyed Transport grouped disembark requires attached rules-unit identity."
        )
    if (
        rules_unit.unit_instance_id != hazard_rolls.unit_instance_id
        or cargo_state.transport_unit_instance_id != hazard_rolls.transport_unit_instance_id
        or attempted_placement.rules_unit_instance_id != rules_unit.unit_instance_id
    ):
        raise GameLifecycleError("Destroyed Transport rules-unit disembark context drift.")
    if not rules_unit_contains_component_lineage(
        rules_unit=rules_unit,
        component_unit_instance_ids=hazard_rolls.component_unit_instance_ids,
    ):
        raise GameLifecycleError("Destroyed Transport rules-unit disembark component drift.")
    survivor_ids = tuple(
        sorted(
            model.model_instance_id
            for model in rules_unit.alive_models()
            if model.model_instance_id in set(hazard_rolls.model_instance_ids)
        )
    )
    placed_ids = tuple(
        sorted(placement.model_instance_id for placement in attempted_placement.model_placements)
    )
    if not placed_ids or not set(placed_ids).issubset(survivor_ids):
        raise GameLifecycleError(
            "Destroyed Transport rules-unit placement must contain living hazard survivors."
        )
    filtered_view = _placed_survivor_rules_unit(
        rules_unit=rules_unit,
        placed_model_instance_ids=placed_ids,
    )
    placement = resolve_rules_unit_disembark(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        cargo_state=cargo_state,
        selection=RulesUnitDisembarkSelection(
            player_id=hazard_rolls.player_id,
            battle_round=hazard_rolls.battle_round,
            unit_instance_id=hazard_rolls.unit_instance_id,
            transport_unit_instance_id=hazard_rolls.transport_unit_instance_id,
            attempted_placement=attempted_placement,
            disembark_mode=DisembarkModeKind.EMERGENCY_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
            restriction_overrides=restriction_overrides,
        ),
        rules_unit=filtered_view,
        transport_placement=transport_placement,
        objective_markers=objective_markers,
    )
    if placement.is_valid:
        updated_cargo = cargo_state.for_movement_phase(battle_round=hazard_rolls.battle_round)
        for component_id in hazard_rolls.component_unit_instance_ids:
            if updated_cargo.contains_unit(component_id):
                updated_cargo = updated_cargo.with_disembarked_unit(component_id)
        placement = replace(placement, updated_cargo_state=updated_cargo)
    survivor_id_set = set(survivor_ids)
    return DestroyedTransportRulesUnitDisembark(
        placement=placement,
        hazard_rolls=hazard_rolls,
        destroyed_model_instance_ids=tuple(sorted(survivor_id_set - set(placed_ids))),
        hazard_destroyed_model_instance_ids=tuple(
            sorted(set(hazard_rolls.model_instance_ids) - survivor_id_set)
        ),
    )


def apply_destroyed_transport_rules_unit_disembark_to_battlefield(
    *,
    battlefield_state: BattlefieldRuntimeState,
    disembark: DestroyedTransportRulesUnitDisembark,
) -> BattlefieldRuntimeState:
    if type(disembark) is not DestroyedTransportRulesUnitDisembark:
        raise GameLifecycleError(
            "Destroyed Transport battlefield mutation requires grouped disembark."
        )
    updated = apply_rules_unit_disembark_to_battlefield(
        battlefield_state=battlefield_state,
        disembark=disembark.placement,
    )
    return updated.with_unplaced_models_marked_removed(disembark.destroyed_model_instance_ids)


def emergency_disembark_omitted_model_evidence_from_event_payload(
    payload: object,
) -> EmergencyDisembarkOmittedModelEvidence | None:
    validated_payload = validate_json_value(payload)
    if not isinstance(validated_payload, dict):
        raise GameLifecycleError("Destroyed Transport disembark event payload is invalid.")
    grouped = validated_payload.get(DESTROYED_TRANSPORT_RULES_UNIT_DISEMBARK_EVENT_FIELD)
    physical = validated_payload.get("destroyed_transport_disembark")
    if grouped is not None and physical is not None:
        raise GameLifecycleError("Destroyed Transport disembark evidence is ambiguous.")
    if grouped is not None:
        evidence = DestroyedTransportRulesUnitDisembarkEvidence.from_payload(grouped)
        if (
            validated_payload.get("active_player_id") != evidence.player_id
            or validated_payload.get("battle_round") != evidence.battle_round
            or validated_payload.get("unit_instance_id") != evidence.rules_unit_instance_id
            or validated_payload.get("component_unit_instance_ids")
            != list(evidence.component_unit_instance_ids)
            or validated_payload.get("transport_unit_instance_id")
            != evidence.transport_unit_instance_id
            or validated_payload.get("disembark_mode") != evidence.disembark_mode.value
        ):
            raise GameLifecycleError(
                "Destroyed Transport rules-unit disembark event context drift."
            )
        return EmergencyDisembarkOmittedModelEvidence(
            player_id=evidence.player_id,
            rules_unit_instance_id=evidence.rules_unit_instance_id,
            component_unit_instance_ids=evidence.component_unit_instance_ids,
            placed_model_instance_ids=evidence.placed_model_instance_ids,
            destroyed_model_instance_ids=evidence.destroyed_model_instance_ids,
        )
    if physical is None:
        return None
    try:
        disembark = DestroyedTransportDisembark.from_payload(
            cast(DestroyedTransportDisembarkPayload, physical)
        )
    except (GeometryError, KeyError, PlacementError, TypeError, ValueError) as exc:
        raise GameLifecycleError("Destroyed Transport disembark authority is invalid.") from exc
    if disembark.disembark_mode is not DisembarkModeKind.EMERGENCY_DISEMBARK:
        raise GameLifecycleError("Destroyed Transport omitted-model authority mode drift.")
    return EmergencyDisembarkOmittedModelEvidence(
        player_id=disembark.player_id,
        rules_unit_instance_id=disembark.unit_instance_id,
        component_unit_instance_ids=(disembark.unit_instance_id,),
        placed_model_instance_ids=tuple(
            sorted(
                placement.model_instance_id
                for placement in disembark.placement.selection.attempted_placement.model_placements
            )
        ),
        destroyed_model_instance_ids=disembark.destroyed_model_instance_ids,
    )


def _placed_survivor_rules_unit(
    *,
    rules_unit: RulesUnitView,
    placed_model_instance_ids: tuple[str, ...],
) -> RulesUnitView:
    placed_ids = set(placed_model_instance_ids)
    components = tuple(
        RulesUnitComponent(
            unit=replace(
                component.unit,
                own_models=tuple(
                    model
                    for model in component.unit.own_models
                    if model.model_instance_id in placed_ids
                ),
            ),
            role=component.role,
        )
        for component in rules_unit.components
        if any(model.model_instance_id in placed_ids for model in component.unit.own_models)
    )
    if not components:
        raise GameLifecycleError(
            "Destroyed Transport rules-unit placement contains no authoritative models."
        )
    view = RulesUnitView(
        unit_instance_id=rules_unit.unit_instance_id,
        owner_player_id=rules_unit.owner_player_id,
        components=components,
        attached_unit=rules_unit.attached_unit,
    )
    if tuple(sorted(model.model_instance_id for model in view.alive_models())) != (
        placed_model_instance_ids
    ):
        raise GameLifecycleError("Destroyed Transport rules-unit placement model lineage drift.")
    return view


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated = tuple(
        _validate_identifier(field_name, value) for value in cast(tuple[object, ...], values)
    )
    if validated != tuple(sorted(set(validated))):
        raise GameLifecycleError(f"{field_name} must be unique and sorted.")
    return validated


def _payload_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not list:
        raise GameLifecycleError(f"{field_name} payload must be a list.")
    return _validate_identifier_tuple(field_name, tuple(cast(list[object], values)))


_validate_identifier = IdentifierValidator(GameLifecycleError)
