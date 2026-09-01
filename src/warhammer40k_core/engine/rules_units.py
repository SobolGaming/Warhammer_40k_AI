from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

RulesUnitComponentRole = Literal["bodyguard", "leader", "support", "unit"]


@dataclass(frozen=True, slots=True)
class RulesUnitComponent:
    unit: UnitInstance
    role: RulesUnitComponentRole

    def __post_init__(self) -> None:
        if type(self.unit) is not UnitInstance:
            raise GameLifecycleError("RulesUnitComponent unit must be a UnitInstance.")
        if self.role not in {"bodyguard", "leader", "support", "unit"}:
            raise GameLifecycleError("RulesUnitComponent has unsupported role.")


@dataclass(frozen=True, slots=True)
class RulesUnitView:
    unit_instance_id: str
    owner_player_id: str
    components: tuple[RulesUnitComponent, ...]
    attached_unit: AttachedUnitFormation | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("RulesUnitView unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "owner_player_id",
            _validate_identifier("RulesUnitView owner_player_id", self.owner_player_id),
        )
        if type(self.components) is not tuple:
            raise GameLifecycleError("RulesUnitView components must be a tuple.")
        if not self.components:
            raise GameLifecycleError("RulesUnitView requires at least one component.")
        for component in self.components:
            if type(component) is not RulesUnitComponent:
                raise GameLifecycleError(
                    "RulesUnitView components must contain RulesUnitComponent values."
                )
        if self.attached_unit is not None and type(self.attached_unit) is not (
            AttachedUnitFormation
        ):
            raise GameLifecycleError(
                "RulesUnitView attached_unit must be an AttachedUnitFormation."
            )
        if self.attached_unit is None and len(self.components) != 1:
            raise GameLifecycleError("Physical RulesUnitView requires exactly one component.")

    @property
    def component_unit_instance_ids(self) -> tuple[str, ...]:
        return tuple(component.unit.unit_instance_id for component in self.components)

    @property
    def own_models(self) -> tuple[ModelInstance, ...]:
        return tuple(model for component in self.components for model in component.unit.own_models)

    @property
    def keywords(self) -> tuple[str, ...]:
        keywords = {
            keyword
            for component in self.keyword_contributing_components
            for keyword in component.unit.keywords
        }
        return tuple(sorted(keywords))

    @property
    def faction_keywords(self) -> tuple[str, ...]:
        keywords = {
            keyword
            for component in self.keyword_contributing_components
            for keyword in component.unit.faction_keywords
        }
        return tuple(sorted(keywords))

    @property
    def keyword_contributing_components(self) -> tuple[RulesUnitComponent, ...]:
        return tuple(
            component
            for component in self.components
            if any(model.is_alive for model in component.unit.own_models)
        )

    @property
    def is_attached_rules_unit(self) -> bool:
        return self.attached_unit is not None

    def component_unit_id_for_model(self, model_instance_id: str) -> str:
        requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
        for component in self.components:
            if any(
                model.model_instance_id == requested_model_id for model in component.unit.own_models
            ):
                return component.unit.unit_instance_id
        raise GameLifecycleError("RulesUnitView model_instance_id is not in the rules unit.")

    def component_unit_for_model(self, model_instance_id: str) -> UnitInstance:
        requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
        for component in self.components:
            if any(
                model.model_instance_id == requested_model_id for model in component.unit.own_models
            ):
                return component.unit
        raise GameLifecycleError("RulesUnitView model_instance_id is not in the rules unit.")

    def component_role_for_model(self, model_instance_id: str) -> RulesUnitComponentRole:
        requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
        for component in self.components:
            if any(
                model.model_instance_id == requested_model_id for model in component.unit.own_models
            ):
                return component.role
        raise GameLifecycleError("RulesUnitView model_instance_id is not in the rules unit.")

    def alive_models(self) -> tuple[ModelInstance, ...]:
        return tuple(model for model in self.own_models if model.is_alive)

    def bodyguard_model_ids(self, models: Iterable[ModelInstance]) -> tuple[str, ...]:
        if self.attached_unit is None:
            return ()
        return tuple(
            sorted(
                model.model_instance_id
                for model in models
                if self.component_role_for_model(model.model_instance_id) == "bodyguard"
            )
        )

    def character_model_ids(self, models: Iterable[ModelInstance]) -> tuple[str, ...]:
        if self.attached_unit is None:
            return ()
        return tuple(
            sorted(
                model.model_instance_id
                for model in models
                if self.component_role_for_model(model.model_instance_id) in {"leader", "support"}
            )
        )


@dataclass(frozen=True, slots=True)
class RulesUnitIdentityReconciliation:
    historical_unit_instance_id: str
    current_unit_instance_ids: tuple[str, ...]
    surviving_unit_instance_ids: tuple[str, ...]
    placed_surviving_unit_instance_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        historical_id = _validate_identifier(
            "historical_unit_instance_id",
            self.historical_unit_instance_id,
        )
        current_ids = _validated_sorted_identity_ids(
            "current_unit_instance_ids",
            self.current_unit_instance_ids,
        )
        surviving_ids = _validated_sorted_identity_ids(
            "surviving_unit_instance_ids",
            self.surviving_unit_instance_ids,
        )
        placed_ids = _validated_sorted_identity_ids(
            "placed_surviving_unit_instance_ids",
            self.placed_surviving_unit_instance_ids,
        )
        if not current_ids:
            raise GameLifecycleError("Rules-unit reconciliation requires current identities.")
        if not set(surviving_ids).issubset(current_ids):
            raise GameLifecycleError("Rules-unit surviving identities must be current.")
        if not set(placed_ids).issubset(surviving_ids):
            raise GameLifecycleError("Rules-unit placed identities must be surviving.")
        object.__setattr__(self, "historical_unit_instance_id", historical_id)
        object.__setattr__(self, "current_unit_instance_ids", current_ids)
        object.__setattr__(self, "surviving_unit_instance_ids", surviving_ids)
        object.__setattr__(self, "placed_surviving_unit_instance_ids", placed_ids)

    @property
    def is_split(self) -> bool:
        return self.current_unit_instance_ids != (self.historical_unit_instance_id,)

    @property
    def is_destroyed(self) -> bool:
        return not self.surviving_unit_instance_ids

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            validate_json_value(
                {
                    "historical_unit_instance_id": self.historical_unit_instance_id,
                    "current_unit_instance_ids": list(self.current_unit_instance_ids),
                    "surviving_unit_instance_ids": list(self.surviving_unit_instance_ids),
                    "placed_surviving_unit_instance_ids": list(
                        self.placed_surviving_unit_instance_ids
                    ),
                    "is_split": self.is_split,
                    "is_destroyed": self.is_destroyed,
                }
            ),
        )


def rules_unit_display_name(rules_unit: RulesUnitView) -> str:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Rules-unit display name requires RulesUnitView.")
    return " + ".join(component.unit.name for component in rules_unit.components)


def rules_unit_view_by_id(*, state: GameState, unit_instance_id: str) -> RulesUnitView:
    return rules_unit_view_from_armies(
        armies=tuple(state.army_definitions),
        unit_instance_id=unit_instance_id,
    )


def rules_unit_view_from_armies(
    *,
    armies: tuple[ArmyDefinition, ...],
    unit_instance_id: str,
) -> RulesUnitView:
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in armies:
        attached_unit = _attached_unit_for_id(army=army, unit_instance_id=requested_id)
        if attached_unit is not None:
            return _attached_rules_unit_view(army=army, attached_unit=attached_unit)
    for army in armies:
        for unit in army.units:
            if unit.unit_instance_id == requested_id:
                return RulesUnitView(
                    unit_instance_id=unit.unit_instance_id,
                    owner_player_id=army.player_id,
                    components=(RulesUnitComponent(unit=unit, role="unit"),),
                    attached_unit=None,
                )
    raise GameLifecycleError("Rules unit_instance_id is unknown.")


def rules_unit_views_from_armies(
    *,
    armies: tuple[ArmyDefinition, ...],
) -> tuple[RulesUnitView, ...]:
    if type(armies) is not tuple:
        raise GameLifecycleError("Rules-unit enumeration armies must be a tuple.")
    views: list[RulesUnitView] = []
    for army in armies:
        if type(army) is not ArmyDefinition:
            raise GameLifecycleError(
                "Rules-unit enumeration armies must contain ArmyDefinition values."
            )
        attached_component_ids = {
            component_id
            for attached_unit in army.attached_units
            for component_id in attached_unit.component_unit_instance_ids
        }
        views.extend(
            _attached_rules_unit_view(army=army, attached_unit=attached_unit)
            for attached_unit in army.attached_units
        )
        views.extend(
            RulesUnitView(
                unit_instance_id=unit.unit_instance_id,
                owner_player_id=army.player_id,
                components=(RulesUnitComponent(unit=unit, role="unit"),),
                attached_unit=None,
            )
            for unit in army.units
            if unit.unit_instance_id not in attached_component_ids
        )
    view_ids = [view.unit_instance_id for view in views]
    if len(view_ids) != len(set(view_ids)):
        raise GameLifecycleError("Rules-unit enumeration identities must be unique.")
    return tuple(sorted(views, key=lambda view: view.unit_instance_id))


def placed_alive_rules_unit_views(*, state: GameState) -> tuple[RulesUnitView, ...]:
    """Enumerate current rules units that are physically present on the battlefield."""
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Placed rules-unit enumeration requires battlefield_state.")
    placed_model_ids = frozenset(battlefield.placed_model_ids())
    unavailable_unit_ids = {
        unit_id
        for cargo_state in state.transport_cargo_states
        for unit_id in cargo_state.embarked_unit_instance_ids
    }
    for reserve_state in state.reserve_states:
        if not reserve_state.is_unarrived:
            continue
        unavailable_unit_ids.add(reserve_state.unit_instance_id)
        unavailable_unit_ids.update(reserve_state.embarked_unit_instance_ids)

    present: list[RulesUnitView] = []
    for view in rules_unit_views_from_armies(armies=tuple(state.army_definitions)):
        identity_ids = {view.unit_instance_id, *view.component_unit_instance_ids}
        if identity_ids.intersection(unavailable_unit_ids):
            continue
        if any(
            model.is_alive and model.model_instance_id in placed_model_ids
            for model in view.own_models
        ):
            present.append(view)
    return tuple(present)


def current_rules_unit_views_for_identity(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[RulesUnitView, ...]:
    """Resolve one current rules-unit identity, including a component alias."""
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    current_views = rules_unit_views_from_armies(armies=tuple(state.army_definitions))
    direct_matches = tuple(
        view
        for view in current_views
        if requested_id == view.unit_instance_id or requested_id in view.component_unit_instance_ids
    )
    if not direct_matches:
        raise GameLifecycleError("Rules unit_instance_id is unknown.")
    if len(direct_matches) != 1:
        raise GameLifecycleError("Current rules-unit identity is ambiguous.")
    return direct_matches


def current_rules_unit_views_for_canonical_identity(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[RulesUnitView, ...]:
    """Resolve one canonical current rules-unit identity."""
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    current_views = current_rules_unit_views_for_identity(
        state=state,
        unit_instance_id=requested_id,
    )
    if any(view.unit_instance_id == requested_id for view in current_views):
        return current_views
    if any(
        record.attached_unit_instance_id == requested_id
        for record in state.starting_attached_unit_records
    ):
        return current_views
    raise GameLifecycleError(
        "Rules-unit identity must be canonical; canonical rules-unit identity required."
    )


def rules_unit_identities_share_lineage(
    *,
    state: GameState,
    first_unit_instance_id: str,
    second_unit_instance_id: str,
) -> bool:
    """Return whether two identities resolve to one overlapping current rules unit."""
    first_views = current_rules_unit_views_for_identity(
        state=state,
        unit_instance_id=first_unit_instance_id,
    )
    second_views = current_rules_unit_views_for_identity(
        state=state,
        unit_instance_id=second_unit_instance_id,
    )
    first_owners = {view.owner_player_id for view in first_views}
    second_owners = {view.owner_player_id for view in second_views}
    if len(first_owners) != 1 or first_owners != second_owners:
        return False
    first_component_ids = {
        component_id for view in first_views for component_id in view.component_unit_instance_ids
    }
    second_component_ids = {
        component_id for view in second_views for component_id in view.component_unit_instance_ids
    }
    return bool(first_component_ids.intersection(second_component_ids))


def rules_unit_identity_history_contains(
    *,
    state: GameState,
    identity_ids: tuple[str, ...],
    unit_instance_id: str,
) -> bool:
    """Return whether current or historical rules-unit identity history contains a unit."""
    if type(identity_ids) is not tuple:
        raise GameLifecycleError("Rules-unit identity history must be a tuple.")
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    historical_ids = tuple(
        _validate_identifier("identity_id", identity_id) for identity_id in identity_ids
    )
    return any(
        historical_id == requested_id
        or rules_unit_identities_share_lineage(
            state=state,
            first_unit_instance_id=historical_id,
            second_unit_instance_id=requested_id,
        )
        for historical_id in historical_ids
    )


def reconcile_rules_unit_identity(
    *,
    state: GameState,
    unit_instance_id: str,
) -> RulesUnitIdentityReconciliation:
    """Resolve identity into its deterministic current, living, and placed view."""
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    current_views = current_rules_unit_views_for_identity(
        state=state,
        unit_instance_id=requested_id,
    )
    battlefield = state.battlefield_state
    placed_model_ids: frozenset[str] = (
        frozenset() if battlefield is None else frozenset(battlefield.placed_model_ids())
    )
    surviving_views = tuple(
        view for view in current_views if any(model.is_alive for model in view.own_models)
    )
    placed_views = tuple(
        view
        for view in surviving_views
        if any(
            model.is_alive and model.model_instance_id in placed_model_ids
            for model in view.own_models
        )
    )
    return RulesUnitIdentityReconciliation(
        historical_unit_instance_id=requested_id,
        current_unit_instance_ids=tuple(view.unit_instance_id for view in current_views),
        surviving_unit_instance_ids=tuple(view.unit_instance_id for view in surviving_views),
        placed_surviving_unit_instance_ids=tuple(view.unit_instance_id for view in placed_views),
    )


def current_placed_alive_rules_unit_view_for_identity(
    *,
    state: GameState,
    unit_instance_id: str,
) -> RulesUnitView | None:
    """Return the one current placed survivor represented by a rules-unit identity."""
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Rules-unit survivor resolution requires battlefield_state.")
    placed_model_ids = set(battlefield.placed_model_ids())
    surviving_views = tuple(
        view
        for view in current_rules_unit_views_for_identity(
            state=state,
            unit_instance_id=unit_instance_id,
        )
        if any(
            model.is_alive and model.model_instance_id in placed_model_ids
            for model in view.own_models
        )
    )
    if not surviving_views:
        return None
    if len(surviving_views) != 1:
        raise GameLifecycleError(
            "Historical rules-unit identity resolves to multiple placed survivors."
        )
    return surviving_views[0]


def rules_unit_id_for_unit_id(
    *,
    armies: tuple[ArmyDefinition, ...],
    unit_instance_id: str,
) -> str:
    return rules_unit_view_from_armies(
        armies=armies,
        unit_instance_id=unit_instance_id,
    ).unit_instance_id


def canonical_rules_unit_view_from_armies(
    *,
    armies: tuple[ArmyDefinition, ...],
    unit_instance_id: str,
    owner_player_id: str,
) -> RulesUnitView:
    view = rules_unit_view_from_armies(
        armies=armies,
        unit_instance_id=unit_instance_id,
    )
    if view.unit_instance_id != unit_instance_id:
        raise GameLifecycleError("Rules-unit identity must be canonical.")
    if view.owner_player_id != owner_player_id:
        raise GameLifecycleError("Rules-unit owner drift.")
    return view


def rules_unit_owner_player_id(*, state: GameState, unit_instance_id: str) -> str:
    return rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id).owner_player_id


def rules_unit_identity_ids(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[str, ...]:
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for rules_unit in rules_unit_views_from_armies(armies=tuple(state.army_definitions)):
        if requested_id == rules_unit.unit_instance_id or (
            requested_id in rules_unit.component_unit_instance_ids
        ):
            return tuple(
                dict.fromkeys(
                    (
                        rules_unit.unit_instance_id,
                        *rules_unit.component_unit_instance_ids,
                    )
                )
            )
    for starting_attached_unit in state.starting_attached_unit_records:
        if starting_attached_unit.attached_unit_instance_id == requested_id:
            return tuple(
                dict.fromkeys(
                    (
                        starting_attached_unit.attached_unit_instance_id,
                        *starting_attached_unit.component_unit_instance_ids,
                    )
                )
            )
    raise GameLifecycleError("Rules unit_instance_id is unknown.")


def rules_unit_is_battle_shocked(
    *,
    state: GameState,
    unit_instance_id: str,
) -> bool:
    identity_ids = rules_unit_identity_ids(
        state=state,
        unit_instance_id=unit_instance_id,
    )
    return any(unit_id in state.battle_shocked_unit_ids for unit_id in identity_ids)


def placed_alive_models_for_component_unit(
    *, state: GameState, unit_instance_id: str
) -> tuple[ModelInstance, ...]:
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    if state.battlefield_state is None:
        return ()
    placed_model_ids = frozenset(state.battlefield_state.placed_model_ids())
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=requested_id)
    component = next(
        (
            candidate
            for candidate in rules_unit.components
            if candidate.unit.unit_instance_id == requested_id
        ),
        None,
    )
    if component is None:
        raise GameLifecycleError("Rules unit does not contain the requested component unit.")
    return tuple(
        sorted(
            (
                model
                for model in component.unit.own_models
                if model.is_alive and model.model_instance_id in placed_model_ids
            ),
            key=lambda model: model.model_instance_id,
        )
    )


def _attached_unit_for_id(
    *,
    army: ArmyDefinition,
    unit_instance_id: str,
) -> AttachedUnitFormation | None:
    for attached_unit in army.attached_units:
        if attached_unit.attached_unit_instance_id == unit_instance_id:
            return attached_unit
        if unit_instance_id in attached_unit.component_unit_instance_ids:
            return attached_unit
    return None


def _attached_rules_unit_view(
    *,
    army: ArmyDefinition,
    attached_unit: AttachedUnitFormation,
) -> RulesUnitView:
    unit_by_id = {unit.unit_instance_id: unit for unit in army.units}
    components: list[RulesUnitComponent] = []
    for unit_id in attached_unit.component_unit_instance_ids:
        unit = unit_by_id.get(unit_id)
        if unit is None:
            raise GameLifecycleError("Attached rules-unit component is unknown.")
        if unit_id == attached_unit.bodyguard_unit_instance_id:
            role: RulesUnitComponentRole = "bodyguard"
        elif unit_id in attached_unit.leader_unit_instance_ids:
            role = "leader"
        elif unit_id in attached_unit.support_unit_instance_ids:
            role = "support"
        else:
            raise GameLifecycleError("Attached rules-unit component role is unknown.")
        components.append(RulesUnitComponent(unit=unit, role=role))
    return RulesUnitView(
        unit_instance_id=attached_unit.attached_unit_instance_id,
        owner_player_id=army.player_id,
        components=tuple(components),
        attached_unit=attached_unit,
    )


def _validated_sorted_identity_ids(
    field_name: str,
    values: tuple[str, ...],
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated = tuple(_validate_identifier(field_name, value) for value in values)
    if len(set(validated)) != len(validated):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    if validated != tuple(sorted(validated)):
        raise GameLifecycleError(f"{field_name} must be sorted.")
    return validated


_validate_identifier = IdentifierValidator(GameLifecycleError)
