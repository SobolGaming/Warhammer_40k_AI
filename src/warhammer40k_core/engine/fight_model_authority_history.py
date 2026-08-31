from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
    ModelPlacement,
    ModelPlacementPayload,
    PlacementError,
    UnitPlacement,
    UnitPlacementPayload,
)
from warhammer40k_core.engine.battlefield_transition_history import (
    authoritative_battlefield_transition_batch_or_none,
    prior_fall_back_applied_transition_or_none,
)
from warhammer40k_core.engine.catalog_model_materialization_runtime import (
    CATALOG_MODELS_MATERIALIZED_EVENT,
    CATALOG_UNIT_DATASHEET_REPLACED_EVENT,
)
from warhammer40k_core.engine.event_log import EventLog, JsonValue
from warhammer40k_core.engine.healing import HealingStep, HealingStepKind, HealingStepPayload
from warhammer40k_core.engine.model_destruction_cause_authority import (
    consumed_model_destruction_cause_authority_for_event,
)
from warhammer40k_core.engine.model_logical_death import (
    MODEL_LOGICAL_DEATH_RECORDED_EVENT,
    model_logical_death_record_from_event,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_battlefield_departure import (
    PrimaryBattlefieldDepartureState,
)
from warhammer40k_core.engine.primary_historical_events import (
    PRIMARY_BATTLEFIELD_DEPARTURE_RECORDED_EVENT,
    PRIMARY_RESERVE_ENTRY_MUTATION_EVENT,
)
from warhammer40k_core.engine.primary_reserve_entry_provider import (
    PrimaryReserveEntryProvider,
)
from warhammer40k_core.engine.return_on_death import (
    RETURN_ON_DEATH_SET_BACK_UP_COMPLETED_EVENT_TYPE,
)
from warhammer40k_core.engine.rules_units import (
    current_rules_unit_views_for_canonical_identity,
    rules_unit_identities_share_lineage,
)
from warhammer40k_core.engine.transports import (
    DestroyedTransportDisembark,
    DestroyedTransportDisembarkPayload,
    DisembarkModeKind,
)
from warhammer40k_core.engine.unit_destroyed_hooks import (
    model_restoration_events_for_event_log_interval,
)
from warhammer40k_core.engine.unit_factory import (
    ModelInstance,
    ModelInstancePayload,
    UnitFactoryError,
)
from warhammer40k_core.geometry.pose import GeometryError

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.event_log import EventRecord
    from warhammer40k_core.engine.game_state import GameState


_FIGHT_ON_DEATH_AWAITING_EVENT = "fight_on_death_model_awaiting_attack"
_FIGHT_ON_DEATH_REMOVED_EVENT = "fight_on_death_models_removed"
_MODEL_DESTROYED_EVENT = "model_destroyed"
_HEALING_STEP_EVENT = "healing_step_resolved"
_CATALOG_PLACEMENT_MIRROR_EVENT = "battlefield_models_placed"


@dataclass(frozen=True, slots=True)
class _ModelAuthority:
    exists: bool
    living: bool
    placed: bool

    def __post_init__(self) -> None:
        if not self.exists and (self.living or self.placed):
            raise GameLifecycleError("Missing model authority cannot be living or placed.")


_MISSING_AUTHORITY = _ModelAuthority(exists=False, living=False, placed=False)


@dataclass(frozen=True, slots=True)
class _AuthorityMutation:
    model_instance_id: str
    after_exists: bool | None
    after_living: bool | None
    after_placed: bool | None
    before_exists: bool | None
    before_living: bool | None
    before_placed: bool | None
    source: str

    def reverse(self, authority: _ModelAuthority) -> _ModelAuthority:
        expected = (
            self.after_exists,
            self.after_living,
            self.after_placed,
        )
        actual = (authority.exists, authority.living, authority.placed)
        if any(
            required is not None and required is not observed
            for required, observed in zip(expected, actual, strict=True)
        ):
            raise GameLifecycleError(
                f"Fight model authority history is discontinuous at {self.source}."
            )
        return _ModelAuthority(
            exists=authority.exists if self.before_exists is None else self.before_exists,
            living=authority.living if self.before_living is None else self.before_living,
            placed=authority.placed if self.before_placed is None else self.before_placed,
        )


@dataclass(frozen=True, slots=True)
class _AuthorityBoundary:
    event_index: int
    authority_before: _ModelAuthority


@dataclass(frozen=True, slots=True)
class ModelAuthorityTimeline:
    """Sparse reverse reconstruction of model state at event boundaries."""

    event_count: int
    current_authority_by_model_id: dict[str, _ModelAuthority]
    boundaries_by_model_id: dict[str, tuple[_AuthorityBoundary, ...]]

    def has_placed_living_model_before_event(
        self,
        *,
        model_instance_id: str,
        event_index: int,
    ) -> bool:
        requested_model_id = _identifier(
            model_instance_id,
            field_name="Fight model authority model_instance_id",
        )
        if type(event_index) is not int or event_index < 0 or event_index >= self.event_count:
            raise GameLifecycleError("Fight model authority event index is invalid.")
        current = self.current_authority_by_model_id.get(requested_model_id)
        if current is None:
            return False
        boundaries = self.boundaries_by_model_id.get(requested_model_id, ())
        indexes = tuple(boundary.event_index for boundary in boundaries)
        position = bisect_left(indexes, event_index)
        authority = (
            current if position == len(boundaries) else boundaries[position].authority_before
        )
        return authority.exists and authority.living and authority.placed


@dataclass(frozen=True, slots=True)
class _CatalogMaterialization:
    event_index: int
    source_unit_instance_id: str
    models: tuple[ModelInstance, ...]
    transition_batch: BattlefieldTransitionBatch
    mirror_event_index: int


@dataclass(frozen=True, slots=True)
class _CatalogReplacement:
    event_index: int
    unit_instance_id: str
    retained_model_instance_ids: tuple[str, ...]
    pruned_model_instance_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _CatalogHistory:
    materializations: tuple[_CatalogMaterialization, ...]
    replacements: tuple[_CatalogReplacement, ...]
    mirror_event_indexes: frozenset[int]


def build_model_authority_timeline(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> ModelAuthorityTimeline:
    """Build a fail-closed logical and physical model history from current state."""

    _validate_typed_inputs(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
    )
    catalog_history = _catalog_history(state=state, event_records=event_records)
    model_unit_by_id, catalog_model_ids, initial_model_ids = _historical_model_inventory(
        state=state,
        catalog_history=catalog_history,
    )
    current = _current_authority_by_model_id(
        state=state,
        known_model_ids=frozenset(model_unit_by_id),
    )
    restoration_model_ids_by_index = _authenticated_restoration_model_ids_by_index(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
    )
    cleanup_model_ids_by_index = _end_turn_cleanup_model_ids_by_event_index(
        state=state,
        event_records=event_records,
        known_model_ids=frozenset(model_unit_by_id),
    )
    mutations_by_index = _authority_mutations_by_event_index(
        state=state,
        event_records=event_records,
        catalog_history=catalog_history,
        model_unit_by_id=model_unit_by_id,
        restoration_model_ids_by_index=restoration_model_ids_by_index,
        cleanup_model_ids_by_index=cleanup_model_ids_by_index,
    )

    authority = dict(current)
    reversed_boundaries: dict[str, list[_AuthorityBoundary]] = {}
    for event_index in reversed(range(len(event_records))):
        mutations = mutations_by_index.get(event_index, ())
        seen_model_ids: set[str] = set()
        for mutation in mutations:
            model_id = mutation.model_instance_id
            if model_id in seen_model_ids:
                raise GameLifecycleError(
                    "Fight model authority event mutates one model more than once."
                )
            seen_model_ids.add(model_id)
            after = authority.get(model_id)
            if after is None:
                raise GameLifecycleError("Fight model authority references an unknown model.")
            before = mutation.reverse(after)
            authority[model_id] = before
            reversed_boundaries.setdefault(model_id, []).append(
                _AuthorityBoundary(
                    event_index=event_index,
                    authority_before=before,
                )
            )

    if any(
        not authority[model_id].exists or not authority[model_id].living
        for model_id in initial_model_ids
    ):
        raise GameLifecycleError(
            "Fight model authority initial model history is not living and present."
        )
    if any(authority[model_id].exists for model_id in catalog_model_ids):
        raise GameLifecycleError(
            "Fight model authority materialized model exists before its creation event."
        )
    return ModelAuthorityTimeline(
        event_count=len(event_records),
        current_authority_by_model_id=current,
        boundaries_by_model_id={
            model_id: tuple(reversed(boundaries))
            for model_id, boundaries in reversed_boundaries.items()
        },
    )


def historical_rules_unit_model_ids(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    unit_instance_id: str,
) -> frozenset[str]:
    """Return current, frozen-start, and typed catalog model lineage for one rules unit."""

    requested_unit_id = _identifier(
        unit_instance_id,
        field_name="Historical rules-unit unit_instance_id",
    )
    catalog_history = _catalog_history(state=state, event_records=event_records)
    model_unit_by_id, _catalog_model_ids, _initial_model_ids = _historical_model_inventory(
        state=state,
        catalog_history=catalog_history,
    )
    current_views = current_rules_unit_views_for_canonical_identity(
        state=state,
        unit_instance_id=requested_unit_id,
    )
    component_ids = {
        component_id for view in current_views for component_id in view.component_unit_instance_ids
    }
    for record in state.starting_attached_unit_records:
        if record.attached_unit_instance_id == requested_unit_id:
            component_ids.update(record.component_unit_instance_ids)
            continue
        component_ids.update(
            component_id
            for component_id in record.component_unit_instance_ids
            if component_id in component_ids
        )
    return frozenset(
        model_id
        for model_id, component_unit_id in model_unit_by_id.items()
        if component_unit_id in component_ids
    )


def _authority_mutations_by_event_index(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    catalog_history: _CatalogHistory,
    model_unit_by_id: dict[str, str],
    restoration_model_ids_by_index: dict[int, tuple[str, ...]],
    cleanup_model_ids_by_index: dict[int, tuple[str, ...]],
) -> dict[int, tuple[_AuthorityMutation, ...]]:
    materialization_by_index = {
        materialization.event_index: materialization
        for materialization in catalog_history.materializations
    }
    replacement_by_index = {
        replacement.event_index: replacement for replacement in catalog_history.replacements
    }
    mutations: dict[int, tuple[_AuthorityMutation, ...]] = {}
    for event_index, event in enumerate(event_records):
        event_mutations: list[_AuthorityMutation] = []
        if event_index in catalog_history.mirror_event_indexes:
            mutations[event_index] = ()
            continue
        materialization = materialization_by_index.get(event_index)
        if materialization is not None:
            event_mutations.extend(
                _creation_mutation(
                    model.model_instance_id,
                    source=CATALOG_MODELS_MATERIALIZED_EVENT,
                )
                for model in materialization.models
            )
        elif (replacement := replacement_by_index.get(event_index)) is not None:
            event_mutations.extend(
                _prune_mutation(model_id, source=CATALOG_UNIT_DATASHEET_REPLACED_EVENT)
                for model_id in replacement.pruned_model_instance_ids
            )
            event_mutations.extend(
                _exists_assertion(model_id, source=CATALOG_UNIT_DATASHEET_REPLACED_EVENT)
                for model_id in replacement.retained_model_instance_ids
            )
        elif event.event_type == MODEL_LOGICAL_DEATH_RECORDED_EVENT:
            event_mutations.append(
                _model_logical_death_mutation(
                    state=state,
                    event=event,
                    model_unit_by_id=model_unit_by_id,
                )
            )
        elif event.event_type == _MODEL_DESTROYED_EVENT:
            event_mutations.append(
                _model_destroyed_mutation(
                    state=state,
                    event=event,
                    model_unit_by_id=model_unit_by_id,
                )
            )
        elif event.event_type == _FIGHT_ON_DEATH_AWAITING_EVENT:
            event_mutations.append(
                _fight_on_death_awaiting_mutation(
                    state=state,
                    event=event,
                    model_unit_by_id=model_unit_by_id,
                )
            )
        elif event.event_type == _FIGHT_ON_DEATH_REMOVED_EVENT:
            event_mutations.extend(
                _fight_on_death_cleanup_mutations(
                    state=state,
                    event=event,
                    model_unit_by_id=model_unit_by_id,
                )
            )
        elif event_index in restoration_model_ids_by_index:
            event_mutations.extend(
                _restoration_mutations(
                    event=event,
                    authenticated_model_ids=restoration_model_ids_by_index[event_index],
                )
            )
        elif event.event_type == PRIMARY_RESERVE_ENTRY_MUTATION_EVENT:
            event_mutations.extend(
                _null_transition_reserve_exit_mutations(
                    state=state,
                    event=event,
                    model_unit_by_id=model_unit_by_id,
                )
            )
        else:
            transition = authoritative_battlefield_transition_batch_or_none(event=event)
            if (
                transition is not None
                and prior_fall_back_applied_transition_or_none(
                    event_records=event_records,
                    event_index=event_index,
                    event=event,
                )
                is not None
            ):
                transition = None
            if transition is not None:
                event_mutations.extend(
                    _physical_transition_mutations(
                        transition=transition,
                        known_model_ids=frozenset(model_unit_by_id),
                        source=event.event_type,
                    )
                )
            event_mutations.extend(
                _destroyed_transport_disembark_destruction_mutations(
                    event=event,
                    model_unit_by_id=model_unit_by_id,
                )
            )
        event_mutations.extend(
            _physical_exit_mutation(model_id, source="end_turn_cleanup")
            for model_id in cleanup_model_ids_by_index.get(event_index, ())
        )
        if len({mutation.model_instance_id for mutation in event_mutations}) != len(
            event_mutations
        ):
            raise GameLifecycleError(
                "Fight model authority event contains overlapping model mutations."
            )
        mutations[event_index] = tuple(event_mutations)
    return mutations


def _destroyed_transport_disembark_destruction_mutations(
    *,
    event: EventRecord,
    model_unit_by_id: dict[str, str],
) -> tuple[_AuthorityMutation, ...]:
    if event.event_type != "unit_disembarked":
        return ()
    payload = _event_payload(event, field_name="Destroyed Transport disembark")
    raw_disembark = payload.get("destroyed_transport_disembark")
    if raw_disembark is None:
        return ()
    if not isinstance(raw_disembark, dict):
        raise GameLifecycleError("Destroyed Transport disembark authority is invalid.")
    try:
        disembark = DestroyedTransportDisembark.from_payload(
            cast(DestroyedTransportDisembarkPayload, raw_disembark)
        )
    except (GeometryError, KeyError, PlacementError, TypeError, ValueError) as exc:
        raise GameLifecycleError("Destroyed Transport disembark authority is invalid.") from exc
    if not disembark.destroyed_model_instance_ids:
        return ()
    if disembark.disembark_mode is not DisembarkModeKind.EMERGENCY_DISEMBARK:
        raise GameLifecycleError("Destroyed Transport omitted-model authority mode drift.")
    placed_model_ids = {
        placement.model_instance_id
        for placement in disembark.placement.selection.attempted_placement.model_placements
    }
    if placed_model_ids.intersection(disembark.destroyed_model_instance_ids):
        raise GameLifecycleError("Destroyed Transport omitted-model authority overlaps placement.")
    for model_id in disembark.destroyed_model_instance_ids:
        if _known_model_unit_id(model_id, model_unit_by_id=model_unit_by_id) != (
            disembark.unit_instance_id
        ):
            raise GameLifecycleError("Destroyed Transport omitted-model authority lineage drift.")
    return tuple(
        _AuthorityMutation(
            model_instance_id=model_id,
            after_exists=True,
            after_living=False,
            after_placed=False,
            before_exists=True,
            before_living=True,
            before_placed=False,
            source="unit_disembarked:destroyed_transport",
        )
        for model_id in disembark.destroyed_model_instance_ids
    )


def _model_destroyed_mutation(
    *,
    state: GameState,
    event: EventRecord,
    model_unit_by_id: dict[str, str],
) -> _AuthorityMutation:
    payload = _event_payload(event, field_name="model_destroyed")
    _require_game_id(payload, state=state, field_name="model_destroyed")
    authority = consumed_model_destruction_cause_authority_for_event(
        state=state,
        event=event,
    )
    logical_death_event = authority.logical_death_event
    logical_death = model_logical_death_record_from_event(logical_death_event)
    model_id = _payload_identifier(payload, key="model_instance_id")
    physical_unit_id = _known_model_unit_id(model_id, model_unit_by_id=model_unit_by_id)
    target_unit_id = _payload_identifier(payload, key="target_unit_instance_id")
    if not rules_unit_identities_share_lineage(
        state=state,
        first_unit_instance_id=target_unit_id,
        second_unit_instance_id=physical_unit_id,
    ):
        raise GameLifecycleError("model_destroyed target lineage drift.")
    placement = _model_placement(payload.get("destroyed_model_placement"), "model_destroyed")
    if placement.model_instance_id != model_id or placement.unit_instance_id != physical_unit_id:
        raise GameLifecycleError("model_destroyed placement identity drift.")
    transition = _transition_payload(payload.get("transition_batch"), "model_destroyed")
    if (
        transition.placements
        or transition.displacements
        or len(transition.removals) != 1
        or transition.removals[0].model_instance_id != model_id
        or transition.removals[0].removal_kind is not BattlefieldRemovalKind.DESTROYED
        or payload.get("removal_record") != transition.removals[0].to_payload()
    ):
        raise GameLifecycleError("model_destroyed removal transition drift.")
    if logical_death.destroyed_model_placement != placement:
        raise GameLifecycleError("model_destroyed logical-death placement drift.")
    return _AuthorityMutation(
        model_instance_id=model_id,
        after_exists=True,
        after_living=False,
        after_placed=False,
        before_exists=True,
        before_living=False,
        before_placed=logical_death.placement_retained,
        source=_MODEL_DESTROYED_EVENT,
    )


def _model_logical_death_mutation(
    *,
    state: GameState,
    event: EventRecord,
    model_unit_by_id: dict[str, str],
) -> _AuthorityMutation:
    record = model_logical_death_record_from_event(event)
    if record.game_id != state.game_id:
        raise GameLifecycleError("Logical-death event game identity drift.")
    physical_unit_id = _known_model_unit_id(
        record.model_instance_id,
        model_unit_by_id=model_unit_by_id,
    )
    if (
        record.physical_unit_instance_id != physical_unit_id
        or not rules_unit_identities_share_lineage(
            state=state,
            first_unit_instance_id=record.rules_unit_instance_id,
            second_unit_instance_id=physical_unit_id,
        )
    ):
        raise GameLifecycleError("Logical-death event model lineage drift.")
    return _AuthorityMutation(
        model_instance_id=record.model_instance_id,
        after_exists=True,
        after_living=False,
        after_placed=record.placement_retained,
        before_exists=True,
        before_living=True,
        before_placed=True,
        source=MODEL_LOGICAL_DEATH_RECORDED_EVENT,
    )


def _fight_on_death_awaiting_mutation(
    *,
    state: GameState,
    event: EventRecord,
    model_unit_by_id: dict[str, str],
) -> _AuthorityMutation:
    payload = _event_payload(event, field_name="Fight On Death awaiting")
    _require_game_id(payload, state=state, field_name="Fight On Death awaiting")
    model_id = _payload_identifier(payload, key="model_instance_id")
    unit_id = _payload_identifier(payload, key="unit_instance_id")
    _payload_identifier(payload, key="effect_id")
    expected_unit_id = _known_model_unit_id(model_id, model_unit_by_id=model_unit_by_id)
    placement = _model_placement(
        payload.get("model_placement"),
        "Fight On Death awaiting",
    )
    if (
        unit_id != expected_unit_id
        or placement.model_instance_id != model_id
        or placement.unit_instance_id != expected_unit_id
    ):
        raise GameLifecycleError("Fight On Death awaiting placement identity drift.")
    return _AuthorityMutation(
        model_instance_id=model_id,
        after_exists=True,
        after_living=False,
        after_placed=True,
        before_exists=True,
        before_living=False,
        before_placed=False,
        source=_FIGHT_ON_DEATH_AWAITING_EVENT,
    )


def _fight_on_death_cleanup_mutations(
    *,
    state: GameState,
    event: EventRecord,
    model_unit_by_id: dict[str, str],
) -> tuple[_AuthorityMutation, ...]:
    payload = _event_payload(event, field_name="Fight On Death cleanup")
    _require_game_id(payload, state=state, field_name="Fight On Death cleanup")
    model_ids = _payload_identifier_list(payload, key="model_instance_ids")
    raw_unit_id = payload.get("unit_instance_id")
    unit_id = (
        None
        if raw_unit_id is None
        else _identifier(raw_unit_id, field_name="Fight On Death cleanup unit_instance_id")
    )
    if unit_id is not None and any(
        not rules_unit_identities_share_lineage(
            state=state,
            first_unit_instance_id=unit_id,
            second_unit_instance_id=_known_model_unit_id(
                model_id,
                model_unit_by_id=model_unit_by_id,
            ),
        )
        for model_id in model_ids
    ):
        raise GameLifecycleError("Fight On Death cleanup lineage drift.")
    for model_id in model_ids:
        _known_model_unit_id(model_id, model_unit_by_id=model_unit_by_id)
    return tuple(
        _AuthorityMutation(
            model_instance_id=model_id,
            after_exists=True,
            after_living=False,
            after_placed=False,
            before_exists=True,
            before_living=False,
            before_placed=True,
            source=_FIGHT_ON_DEATH_REMOVED_EVENT,
        )
        for model_id in model_ids
    )


def _restoration_mutations(
    *,
    event: EventRecord,
    authenticated_model_ids: tuple[str, ...],
) -> tuple[_AuthorityMutation, ...]:
    payload = _event_payload(event, field_name="Model restoration")
    if event.event_type == _HEALING_STEP_EVENT:
        raw_step = payload.get("step")
        if not isinstance(raw_step, dict):
            raise GameLifecycleError("Healing restoration step is invalid.")
        try:
            step = HealingStep.from_payload(cast(HealingStepPayload, raw_step))
        except (GeometryError, KeyError, PlacementError, TypeError, ValueError) as exc:
            raise GameLifecycleError("Healing restoration step is invalid.") from exc
        if step.model_instance_id is None or authenticated_model_ids != (step.model_instance_id,):
            raise GameLifecycleError("Healing restoration authenticated model drift.")
        if step.step_kind is HealingStepKind.REVIVE_MODEL:
            if step.transition_batch is None:
                raise GameLifecycleError("Healing restoration placement is missing.")
            transition_mutations = _physical_transition_mutations(
                transition=step.transition_batch,
                known_model_ids=frozenset(authenticated_model_ids),
                source=_HEALING_STEP_EVENT,
            )
            if len(transition_mutations) != 1 or (
                transition_mutations[0].model_instance_id != step.model_instance_id
                or transition_mutations[0].before_placed is not False
                or transition_mutations[0].after_placed is not True
            ):
                raise GameLifecycleError("Healing restoration placement drift.")
            placed = True
        elif step.step_kind is HealingStepKind.REVIVE_MODEL_EMBARKED:
            placed = False
        else:
            raise GameLifecycleError("Authenticated healing event is not a restoration.")
        return (
            _AuthorityMutation(
                model_instance_id=step.model_instance_id,
                after_exists=True,
                after_living=True,
                after_placed=placed,
                before_exists=True,
                before_living=False,
                before_placed=False,
                source=_HEALING_STEP_EVENT,
            ),
        )
    if event.event_type != RETURN_ON_DEATH_SET_BACK_UP_COMPLETED_EVENT_TYPE:
        raise GameLifecycleError("Authenticated restoration event type is unsupported.")
    placement = _unit_placement(payload.get("placement"), "Return-on-death restoration")
    placement_model_ids = tuple(
        sorted(model.model_instance_id for model in placement.model_placements)
    )
    if placement_model_ids != authenticated_model_ids:
        raise GameLifecycleError("Return-on-death restoration model inventory drift.")
    return tuple(
        _AuthorityMutation(
            model_instance_id=model_id,
            after_exists=True,
            after_living=True,
            after_placed=True,
            before_exists=True,
            before_living=False,
            before_placed=False,
            source=RETURN_ON_DEATH_SET_BACK_UP_COMPLETED_EVENT_TYPE,
        )
        for model_id in authenticated_model_ids
    )


def _null_transition_reserve_exit_mutations(
    *,
    state: GameState,
    event: EventRecord,
    model_unit_by_id: dict[str, str],
) -> tuple[_AuthorityMutation, ...]:
    payload = _event_payload(event, field_name="Reserve-entry mutation")
    _require_game_id(payload, state=state, field_name="Reserve-entry mutation")
    if payload.get("transition_batch") is not None:
        return ()
    provider = PrimaryReserveEntryProvider.from_payload(payload.get("provider"))
    reserve_entry = payload.get("reserve_entry_state")
    if not isinstance(reserve_entry, dict):
        raise GameLifecycleError("Reserve-entry mutation state is invalid.")
    reserve_unit_id = _payload_identifier(reserve_entry, key="unit_instance_id")
    reserve_player_id = _payload_identifier(reserve_entry, key="player_id")
    model_ids = _payload_identifier_list(payload, key="removed_model_instance_ids")
    if (
        reserve_entry.get("reserve_kind") != "strategic_reserves"
        or provider.target_rules_unit_instance_id != reserve_unit_id
        or provider.player_id != reserve_player_id
        or payload.get("occurrence_id") != provider.occurrence_id
        or payload.get("source_id") != provider.occurrence_id
        or any(
            not rules_unit_identities_share_lineage(
                state=state,
                first_unit_instance_id=reserve_unit_id,
                second_unit_instance_id=_known_model_unit_id(
                    model_id,
                    model_unit_by_id=model_unit_by_id,
                ),
            )
            for model_id in model_ids
        )
    ):
        raise GameLifecycleError("Reserve-entry null-transition identity drift.")
    return tuple(
        _physical_exit_mutation(model_id, source=PRIMARY_RESERVE_ENTRY_MUTATION_EVENT)
        for model_id in model_ids
    )


def _physical_transition_mutations(
    *,
    transition: BattlefieldTransitionBatch,
    known_model_ids: frozenset[str],
    source: str,
) -> tuple[_AuthorityMutation, ...]:
    mutations: list[_AuthorityMutation] = []
    for placement in transition.placements:
        _require_known_model_id(placement.model_instance_id, known_model_ids=known_model_ids)
        mutations.append(_physical_entry_mutation(placement.model_instance_id, source=source))
    for displacement in transition.displacements:
        _require_known_model_id(displacement.model_instance_id, known_model_ids=known_model_ids)
        mutations.append(
            _AuthorityMutation(
                model_instance_id=displacement.model_instance_id,
                after_exists=True,
                after_living=None,
                after_placed=True,
                before_exists=True,
                before_living=None,
                before_placed=True,
                source=source,
            )
        )
    for removal in transition.removals:
        _require_known_model_id(removal.model_instance_id, known_model_ids=known_model_ids)
        mutations.append(_physical_exit_mutation(removal.model_instance_id, source=source))
    return tuple(mutations)


def _creation_mutation(model_id: str, *, source: str) -> _AuthorityMutation:
    return _AuthorityMutation(
        model_instance_id=model_id,
        after_exists=True,
        after_living=True,
        after_placed=True,
        before_exists=False,
        before_living=False,
        before_placed=False,
        source=source,
    )


def _prune_mutation(model_id: str, *, source: str) -> _AuthorityMutation:
    return _AuthorityMutation(
        model_instance_id=model_id,
        after_exists=False,
        after_living=False,
        after_placed=False,
        before_exists=True,
        before_living=False,
        before_placed=False,
        source=source,
    )


def _exists_assertion(model_id: str, *, source: str) -> _AuthorityMutation:
    return _AuthorityMutation(
        model_instance_id=model_id,
        after_exists=True,
        after_living=None,
        after_placed=None,
        before_exists=True,
        before_living=None,
        before_placed=None,
        source=source,
    )


def _physical_entry_mutation(model_id: str, *, source: str) -> _AuthorityMutation:
    return _AuthorityMutation(
        model_instance_id=model_id,
        after_exists=True,
        after_living=None,
        after_placed=True,
        before_exists=True,
        before_living=None,
        before_placed=False,
        source=source,
    )


def _physical_exit_mutation(model_id: str, *, source: str) -> _AuthorityMutation:
    return _AuthorityMutation(
        model_instance_id=model_id,
        after_exists=True,
        after_living=None,
        after_placed=False,
        before_exists=True,
        before_living=None,
        before_placed=True,
        source=source,
    )


def _authenticated_restoration_model_ids_by_index(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> dict[int, tuple[str, ...]]:
    if not any(
        event.event_type in {_HEALING_STEP_EVENT, RETURN_ON_DEATH_SET_BACK_UP_COMPLETED_EVENT_TYPE}
        for event in event_records
    ):
        return {}
    event_log = EventLog.from_payload([event.to_payload() for event in event_records])
    restorations = model_restoration_events_for_event_log_interval(
        state=state,
        event_log=event_log,
        start_order_exclusive=-1,
        decision_records=decision_records,
    )
    values = {index: model_ids for index, _event_id, model_ids in restorations}
    if len(values) != len(restorations):
        raise GameLifecycleError("Model restoration history event indexes are duplicated.")
    return values


def _end_turn_cleanup_model_ids_by_event_index(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    known_model_ids: frozenset[str],
) -> dict[int, tuple[str, ...]]:
    if not any(cleanup.removals for cleanup in state.end_turn_cleanup_states):
        return {}
    departure_by_id = {
        departure.departure_id: departure
        for departure in state.primary_battlefield_departure_states
    }
    if len(departure_by_id) != len(state.primary_battlefield_departure_states):
        raise GameLifecycleError("End-turn cleanup departure identities are duplicated.")
    event_index_by_departure_id: dict[str, int] = {}
    for event_index, event in enumerate(event_records):
        if event.event_type != PRIMARY_BATTLEFIELD_DEPARTURE_RECORDED_EVENT:
            continue
        payload = _event_payload(event, field_name="Primary battlefield departure")
        _require_game_id(payload, state=state, field_name="Primary battlefield departure")
        departure = PrimaryBattlefieldDepartureState.from_payload(
            payload.get("primary_battlefield_departure_state")
        )
        if (
            departure_by_id.get(departure.departure_id) != departure
            or payload.get("battle_round") != departure.battle_round
            or payload.get("active_player_id") != departure.active_player_id
            or payload.get("phase") != departure.phase
        ):
            raise GameLifecycleError("Primary battlefield departure event drift.")
        if departure.departure_id in event_index_by_departure_id:
            raise GameLifecycleError("Primary battlefield departure event is duplicated.")
        event_index_by_departure_id[departure.departure_id] = event_index

    result: dict[int, list[str]] = {}
    claimed_departure_ids: set[str] = set()
    for cleanup in state.end_turn_cleanup_states:
        if cleanup.game_id != state.game_id:
            raise GameLifecycleError("End-turn cleanup game identity drift.")
        transition_ids = tuple(
            sorted(removal.model_instance_id for removal in cleanup.transition_batch.removals)
        )
        cleanup_ids = tuple(sorted(cleanup.removed_model_instance_ids))
        if (
            cleanup.transition_batch.placements
            or cleanup.transition_batch.displacements
            or transition_ids != cleanup_ids
            or any(
                removal.removal_kind is not BattlefieldRemovalKind.DESTROYED
                for removal in cleanup.transition_batch.removals
            )
        ):
            raise GameLifecycleError("End-turn cleanup transition drift.")
        expected_by_unit: dict[str, set[str]] = {}
        for removal in cleanup.removals:
            _require_known_model_id(
                removal.model_instance_id,
                known_model_ids=known_model_ids,
            )
            expected_by_unit.setdefault(removal.unit_instance_id, set()).add(
                removal.model_instance_id
            )
        for unit_id, expected_model_ids in expected_by_unit.items():
            source_id = f"{cleanup.cleanup_id}:{unit_id}"
            departures = tuple(
                departure
                for departure in state.primary_battlefield_departure_states
                if departure.source_id == source_id
            )
            if not departures or (
                {
                    model_id
                    for departure in departures
                    for model_id in departure.removed_model_instance_ids
                }
                != expected_model_ids
            ):
                raise GameLifecycleError("End-turn cleanup departure coverage drift.")
            for departure in departures:
                if (
                    departure.departure_id in claimed_departure_ids
                    or departure.removal_kind is not BattlefieldRemovalKind.DESTROYED
                ):
                    raise GameLifecycleError("End-turn cleanup departure reuse drift.")
                departure_event_index = event_index_by_departure_id.get(departure.departure_id)
                if departure_event_index is None:
                    raise GameLifecycleError("End-turn cleanup departure lacks its recorded event.")
                claimed_departure_ids.add(departure.departure_id)
                result.setdefault(departure_event_index, []).extend(
                    departure.removed_model_instance_ids
                )
    return {event_index: tuple(sorted(model_ids)) for event_index, model_ids in result.items()}


def _catalog_history(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
) -> _CatalogHistory:
    materializations: list[_CatalogMaterialization] = []
    replacements: list[_CatalogReplacement] = []
    mirror_indexes: set[int] = set()
    for event_index, event in enumerate(event_records):
        if event.event_type == CATALOG_MODELS_MATERIALIZED_EVENT:
            payload = _event_payload(event, field_name="Catalog materialization")
            _require_game_id(payload, state=state, field_name="Catalog materialization")
            source_unit_id = _payload_identifier(payload, key="source_unit_instance_id")
            model_ids = _payload_identifier_list(payload, key="model_instance_ids")
            raw_models = payload.get("models")
            if not isinstance(raw_models, list) or not raw_models:
                raise GameLifecycleError("Catalog materialization models are invalid.")
            try:
                models = tuple(
                    ModelInstance.from_payload(cast(ModelInstancePayload, raw_model))
                    for raw_model in raw_models
                    if isinstance(raw_model, dict)
                )
            except (GeometryError, KeyError, TypeError, UnitFactoryError, ValueError) as exc:
                raise GameLifecycleError("Catalog materialization models are invalid.") from exc
            if (
                len(models) != len(raw_models)
                or tuple(model.model_instance_id for model in models) != model_ids
                or any(not model.is_alive for model in models)
            ):
                raise GameLifecycleError("Catalog materialization model inventory drift.")
            transition = authoritative_battlefield_transition_batch_or_none(event=event)
            if transition is None or (
                transition.removals
                or transition.displacements
                or tuple(placement.model_instance_id for placement in transition.placements)
                != model_ids
            ):
                raise GameLifecycleError("Catalog materialization transition drift.")
            mirror_index = event_index + 1
            if mirror_index >= len(event_records):
                raise GameLifecycleError("Catalog materialization placement mirror is missing.")
            mirror = event_records[mirror_index]
            mirror_payload = _event_payload(mirror, field_name="Catalog placement mirror")
            mirror_transition = authoritative_battlefield_transition_batch_or_none(event=mirror)
            if (
                mirror.event_type != _CATALOG_PLACEMENT_MIRROR_EVENT
                or mirror_payload.get("source_event_id") != event.event_id
                or mirror_payload.get("source_unit_instance_id") != source_unit_id
                or _payload_identifier_list(mirror_payload, key="model_instance_ids") != model_ids
                or mirror_transition != transition
                or mirror_index in mirror_indexes
            ):
                raise GameLifecycleError("Catalog materialization placement mirror drift.")
            mirror_indexes.add(mirror_index)
            materializations.append(
                _CatalogMaterialization(
                    event_index=event_index,
                    source_unit_instance_id=source_unit_id,
                    models=models,
                    transition_batch=transition,
                    mirror_event_index=mirror_index,
                )
            )
        elif event.event_type == CATALOG_UNIT_DATASHEET_REPLACED_EVENT:
            payload = _event_payload(event, field_name="Catalog datasheet replacement")
            _require_game_id(payload, state=state, field_name="Catalog datasheet replacement")
            unit_id = _payload_identifier(payload, key="unit_instance_id")
            retained_ids = _payload_identifier_list(
                payload,
                key="retained_model_instance_ids",
                allow_empty=True,
            )
            pruned_ids = _payload_identifier_list(
                payload,
                key="pruned_model_instance_ids",
                allow_empty=True,
            )
            if set(retained_ids).intersection(pruned_ids):
                raise GameLifecycleError("Catalog datasheet replacement model inventory drift.")
            replacements.append(
                _CatalogReplacement(
                    event_index=event_index,
                    unit_instance_id=unit_id,
                    retained_model_instance_ids=retained_ids,
                    pruned_model_instance_ids=pruned_ids,
                )
            )
    return _CatalogHistory(
        materializations=tuple(materializations),
        replacements=tuple(replacements),
        mirror_event_indexes=frozenset(mirror_indexes),
    )


def _historical_model_inventory(
    *,
    state: GameState,
    catalog_history: _CatalogHistory,
) -> tuple[dict[str, str], frozenset[str], frozenset[str]]:
    model_unit_by_id: dict[str, str] = {}
    current_model_ids: set[str] = set()
    for army in state.army_definitions:
        for unit in army.units:
            for model in unit.own_models:
                _record_model_unit(
                    model.model_instance_id,
                    unit.unit_instance_id,
                    model_unit_by_id=model_unit_by_id,
                )
                current_model_ids.add(model.model_instance_id)
    for record in state.starting_attached_unit_records:
        for component_id, model_ids in record.starting_model_instance_ids_by_component:
            for model_id in model_ids:
                _record_model_unit(
                    model_id,
                    component_id,
                    model_unit_by_id=model_unit_by_id,
                )
    catalog_model_ids: set[str] = set()
    for materialization in catalog_history.materializations:
        for model in materialization.models:
            model_id = model.model_instance_id
            if model_id in catalog_model_ids:
                raise GameLifecycleError("Catalog materialized model identity is duplicated.")
            catalog_model_ids.add(model_id)
            _record_model_unit(
                model_id,
                materialization.source_unit_instance_id,
                model_unit_by_id=model_unit_by_id,
            )
    for replacement in catalog_history.replacements:
        for model_id in (
            *replacement.retained_model_instance_ids,
            *replacement.pruned_model_instance_ids,
        ):
            _record_model_unit(
                model_id,
                replacement.unit_instance_id,
                model_unit_by_id=model_unit_by_id,
            )
    initial_model_ids = frozenset(model_unit_by_id).difference(catalog_model_ids)
    return model_unit_by_id, frozenset(catalog_model_ids), initial_model_ids


def _current_authority_by_model_id(
    *,
    state: GameState,
    known_model_ids: frozenset[str],
) -> dict[str, _ModelAuthority]:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Fight model authority history requires battlefield_state.")
    current_models = {
        model.model_instance_id: model
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    if len(current_models) != sum(
        len(unit.own_models) for army in state.army_definitions for unit in army.units
    ):
        raise GameLifecycleError("Fight model authority current model inventory is duplicated.")
    placed_model_ids = frozenset(battlefield.placed_model_ids())
    if not placed_model_ids <= set(current_models):
        raise GameLifecycleError("Fight model authority battlefield inventory is unknown.")
    return {
        model_id: (
            _MISSING_AUTHORITY
            if (model := current_models.get(model_id)) is None
            else _ModelAuthority(
                exists=True,
                living=model.is_alive,
                placed=model_id in placed_model_ids,
            )
        )
        for model_id in known_model_ids
    }


def _record_model_unit(
    model_id: str,
    unit_id: str,
    *,
    model_unit_by_id: dict[str, str],
) -> None:
    requested_model_id = _identifier(model_id, field_name="Historical model_instance_id")
    requested_unit_id = _identifier(unit_id, field_name="Historical unit_instance_id")
    existing = model_unit_by_id.get(requested_model_id)
    if existing is not None and existing != requested_unit_id:
        raise GameLifecycleError("Historical model physical ownership is ambiguous.")
    model_unit_by_id[requested_model_id] = requested_unit_id


def _known_model_unit_id(
    model_id: str,
    *,
    model_unit_by_id: dict[str, str],
) -> str:
    requested_model_id = _identifier(model_id, field_name="Historical model_instance_id")
    unit_id = model_unit_by_id.get(requested_model_id)
    if unit_id is None:
        raise GameLifecycleError("Fight model authority references an unknown model.")
    return unit_id


def _require_known_model_id(model_id: str, *, known_model_ids: frozenset[str]) -> None:
    if model_id not in known_model_ids:
        raise GameLifecycleError("Fight model authority transition references an unknown model.")


def _validate_typed_inputs(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.event_log import EventRecord
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Fight model authority history requires GameState.")
    if type(event_records) is not tuple or any(
        type(event) is not EventRecord for event in event_records
    ):
        raise GameLifecycleError("Fight model authority history requires EventRecords.")
    if type(decision_records) is not tuple or any(
        type(record) is not DecisionRecord for record in decision_records
    ):
        raise GameLifecycleError("Fight model authority history requires DecisionRecords.")


def _event_payload(event: EventRecord, *, field_name: str) -> dict[str, JsonValue]:
    if not isinstance(event.payload, dict):
        raise GameLifecycleError(f"{field_name} event payload must be an object.")
    return event.payload


def _require_game_id(
    payload: dict[str, JsonValue],
    *,
    state: GameState,
    field_name: str,
) -> None:
    if payload.get("game_id") != state.game_id:
        raise GameLifecycleError(f"{field_name} game identity drift.")


def _payload_identifier(
    payload: dict[str, JsonValue],
    *,
    key: str,
) -> str:
    return _identifier(payload.get(key), field_name=key)


def _payload_identifier_list(
    payload: dict[str, JsonValue],
    *,
    key: str,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    raw = payload.get(key)
    if not isinstance(raw, list):
        raise GameLifecycleError(f"{key} must be an identifier list.")
    values = tuple(_identifier(value, field_name=key) for value in raw)
    if (not values and not allow_empty) or len(set(values)) != len(values):
        raise GameLifecycleError(f"{key} must contain unique identifiers.")
    return values


def _identifier(value: object, *, field_name: str) -> str:
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"{field_name} must be an identifier.")
    return value


def _model_placement(value: object, field_name: str) -> ModelPlacement:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{field_name} model placement is invalid.")
    try:
        return ModelPlacement.from_payload(cast(ModelPlacementPayload, value))
    except (GeometryError, KeyError, PlacementError, TypeError, ValueError) as exc:
        raise GameLifecycleError(f"{field_name} model placement is invalid.") from exc


def _unit_placement(value: object, field_name: str) -> UnitPlacement:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{field_name} unit placement is invalid.")
    try:
        return UnitPlacement.from_payload(cast(UnitPlacementPayload, value))
    except (GeometryError, KeyError, PlacementError, TypeError, ValueError) as exc:
        raise GameLifecycleError(f"{field_name} unit placement is invalid.") from exc


def _transition_payload(value: object, field_name: str) -> BattlefieldTransitionBatch:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{field_name} transition batch is invalid.")
    try:
        return BattlefieldTransitionBatch.from_payload(
            cast(BattlefieldTransitionBatchPayload, value)
        )
    except (GeometryError, KeyError, PlacementError, TypeError, ValueError) as exc:
        raise GameLifecycleError(f"{field_name} transition batch is invalid.") from exc


__all__ = (
    "ModelAuthorityTimeline",
    "build_model_authority_timeline",
    "historical_rules_unit_model_ids",
)
