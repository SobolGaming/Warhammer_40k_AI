from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Self, cast

from warhammer40k_core.core.ruleset_descriptor import battle_phase_kind_from_token
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import ModelPlacement, ModelPlacementPayload
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.retained_attack_permissions import (
    RETAINED_ATTACK_REACTION_KINDS,
    RetainedAttackAction,
    retained_attack_actions,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_fight_on_death_2026_09,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.damage_allocation import (
        DestructionReactionSource,
    )
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.model_destruction_cause_authority import (
        ModelDestructionCauseAuthority,
    )


RETAINED_DESTRUCTION_EFFECT_KIND = "retained_model_destruction"
RETENTION_CONTEXT_KIND = "fight_on_death_retention"
FIGHT_ON_DEATH_SOURCE_ID = core_fight_on_death_2026_09.FIGHT_ON_DEATH_SOURCE_ID
_identifier = IdentifierValidator(GameLifecycleError)


class RetainedDestructionStage(StrEnum):
    OFFERED = "offered"
    WAITING = "waiting_for_unit_attack"
    READY = "ready_for_destruction_reactions"
    RESOLVING = "resolving_destruction_reactions"
    SUSPENDED = "waiting_for_retained_casualty"
    REMOVED = "removed_resolving_reactions"
    DECLINED = "declined"
    NOT_TRIGGERED = "not_triggered"


class DestructionOwnerKind(StrEnum):
    ATTACK = "attack"
    ATTACK_COLLATERAL = "attack_collateral"
    RULE = "rule"


@dataclass(frozen=True, slots=True)
class RetainedModelDestruction:
    """An unconsumed logical death and its original engine continuation.

    Keeping this record never changes placement. Only the destruction owner may
    consume the cause and remove the model, after the retained interval ends.
    """

    cause_id: str
    logical_death_event_id: str
    placement: ModelPlacement
    owner_kind: DestructionOwnerKind
    owner_context: dict[str, JsonValue]
    sources: tuple[DestructionReactionSource, ...]
    eligible_sources: tuple[DestructionReactionSource, ...]
    stage: RetainedDestructionStage
    excluded_actions: tuple[RetainedAttackAction, ...] = ()
    request_id: str | None = None
    result_id: str | None = None
    selected_source_id: str | None = None
    selected_action: RetainedAttackAction | None = None
    completion_reason: str | None = None
    owner_progress: dict[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.damage_allocation import (
            DestructionReactionSource,
        )

        for name in ("cause_id", "logical_death_event_id"):
            _identifier(name, getattr(self, name))
        for name in ("request_id", "result_id", "selected_source_id"):
            value = getattr(self, name)
            if value is not None:
                _identifier(name, value)
        if type(self.placement) is not ModelPlacement:
            raise GameLifecycleError("Retained destruction requires exact model placement.")
        if type(self.owner_kind) is not DestructionOwnerKind:
            raise GameLifecycleError("Retained destruction owner kind is invalid.")
        if type(self.stage) is not RetainedDestructionStage:
            raise GameLifecycleError("Retained destruction stage is invalid.")
        context = validate_json_value(self.owner_context)
        if not isinstance(context, dict):
            raise GameLifecycleError("Retained destruction owner context must be an object.")
        object.__setattr__(self, "owner_context", context)
        if self.owner_progress is not None:
            progress = validate_json_value(self.owner_progress)
            if not isinstance(progress, dict):
                raise GameLifecycleError("Retained destruction owner progress must be an object.")
            object.__setattr__(self, "owner_progress", progress)
        for sources in (self.sources, self.eligible_sources):
            if type(sources) is not tuple or any(
                type(source) is not DestructionReactionSource for source in sources
            ):
                raise GameLifecycleError("Retained destruction source inventory is invalid.")
            if len({source.source_id for source in sources}) != len(sources):
                raise GameLifecycleError("Retained destruction sources are duplicated.")
        if any(source not in self.sources for source in self.eligible_sources):
            raise GameLifecycleError("Retained destruction eligible source authority drift.")
        if any(
            not source.optional or source.reaction_kind not in RETAINED_ATTACK_REACTION_KINDS
            for source in self.eligible_sources
        ):
            raise GameLifecycleError("Retention options require optional attack sources.")
        if (
            type(self.excluded_actions) is not tuple
            or any(type(action) is not RetainedAttackAction for action in self.excluded_actions)
            or self.excluded_actions not in ((), (RetainedAttackAction.SHOOT,))
        ):
            raise GameLifecycleError("Retained destruction excluded actions are invalid.")
        if self.selected_action is not None and self.selected_action in self.excluded_actions:
            raise GameLifecycleError("Retained action was excluded from its source decision.")
        selected_source = next(
            (
                source
                for source in self.eligible_sources
                if source.source_id == self.selected_source_id
            ),
            None,
        )
        if selected_source is None:
            if self.selected_action is not None:
                raise GameLifecycleError("Retained action lacks its selected source.")
        elif self.selected_action not in retained_attack_actions(selected_source):
            raise GameLifecycleError("Retained action is not authorized by its selected source.")
        if self.owner_progress is not None and (
            self.owner_kind is DestructionOwnerKind.RULE
            or self.stage
            not in (
                RetainedDestructionStage.RESOLVING,
                RetainedDestructionStage.SUSPENDED,
                RetainedDestructionStage.REMOVED,
            )
        ):
            raise GameLifecycleError("Retained destruction progress has no active attack owner.")
        if self.stage is RetainedDestructionStage.NOT_TRIGGERED:
            if (
                self.eligible_sources
                or self.request_id is not None
                or self.result_id is not None
                or self.selected_source_id is not None
            ):
                raise GameLifecycleError("Untriggered retention cannot contain a decision.")
        elif self.request_id is None or not self.eligible_sources:
            raise GameLifecycleError("Retained destruction is missing its source decision.")
        if self.stage is RetainedDestructionStage.OFFERED and (
            self.result_id is not None or self.selected_source_id is not None
        ):
            raise GameLifecycleError("Pending retention already contains a result.")
        if self.stage is RetainedDestructionStage.DECLINED and (
            self.result_id is None or self.selected_source_id is not None
        ):
            raise GameLifecycleError("Declined retention decision drift.")
        if (self.is_retained or self.stage is RetainedDestructionStage.REMOVED) and (
            self.result_id is None
            or self.selected_source_id not in {source.source_id for source in self.eligible_sources}
        ):
            raise GameLifecycleError("Retained destruction requires an accepted source.")
        if self.completion_reason not in (
            None,
            "unit_fight_completed",
            "model_shoot_completed",
            "phase_end",
        ):
            raise GameLifecycleError("Retained destruction completion reason is invalid.")
        if (self.completion_reason is not None) != (
            self.stage
            in (
                RetainedDestructionStage.READY,
                RetainedDestructionStage.RESOLVING,
                RetainedDestructionStage.SUSPENDED,
                RetainedDestructionStage.REMOVED,
            )
        ):
            raise GameLifecycleError("Retained destruction completion boundary drift.")

    @property
    def effect_id(self) -> str:
        return f"retained-destruction:{self.cause_id}"

    @property
    def model_instance_id(self) -> str:
        return self.placement.model_instance_id

    @property
    def is_retained(self) -> bool:
        return self.stage in (
            RetainedDestructionStage.WAITING,
            RetainedDestructionStage.READY,
            RetainedDestructionStage.RESOLVING,
            RetainedDestructionStage.SUSPENDED,
        )

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            validate_json_value(
                {
                    "cause_id": self.cause_id,
                    "logical_death_event_id": self.logical_death_event_id,
                    "placement": self.placement.to_payload(),
                    "owner_kind": self.owner_kind.value,
                    "owner_context": self.owner_context,
                    "sources": [source.to_payload() for source in self.sources],
                    "eligible_sources": [source.to_payload() for source in self.eligible_sources],
                    "excluded_actions": [action.value for action in self.excluded_actions],
                    "stage": self.stage.value,
                    "request_id": self.request_id,
                    "result_id": self.result_id,
                    "selected_source_id": self.selected_source_id,
                    "selected_action": None
                    if self.selected_action is None
                    else self.selected_action.value,
                    "completion_reason": self.completion_reason,
                    "owner_progress": self.owner_progress,
                }
            ),
        )

    @classmethod
    def from_payload(cls, payload: JsonValue) -> Self:
        if not isinstance(payload, dict) or set(payload) != {
            "cause_id",
            "logical_death_event_id",
            "placement",
            "owner_kind",
            "owner_context",
            "sources",
            "eligible_sources",
            "stage",
            "excluded_actions",
            "request_id",
            "result_id",
            "selected_source_id",
            "selected_action",
            "completion_reason",
            "owner_progress",
        }:
            raise GameLifecycleError("Retained destruction payload fields drift.")
        context = payload["owner_context"]
        placement = payload["placement"]
        if not isinstance(context, dict) or not isinstance(placement, dict):
            raise GameLifecycleError("Retained destruction placement or context is invalid.")
        exclusions = payload["excluded_actions"]
        if not isinstance(exclusions, list) or exclusions not in ([], ["shoot"]):
            raise GameLifecycleError("Retained destruction excluded actions are invalid.")
        try:
            owner = DestructionOwnerKind(_identifier("owner_kind", payload["owner_kind"]))
            stage = RetainedDestructionStage(_identifier("stage", payload["stage"]))
            selected_action = (
                None
                if payload["selected_action"] is None
                else RetainedAttackAction(
                    _identifier("selected_action", payload["selected_action"])
                )
            )
        except ValueError as exc:
            raise GameLifecycleError("Retained destruction owner or stage is unsupported.") from exc
        from warhammer40k_core.engine.placement_errors import PlacementError

        try:
            model_placement = ModelPlacement.from_payload(cast(ModelPlacementPayload, placement))
        except PlacementError as exc:
            raise GameLifecycleError("Retained destruction placement is invalid.") from exc
        return cls(
            cause_id=_identifier("cause_id", payload["cause_id"]),
            logical_death_event_id=_identifier(
                "logical_death_event_id", payload["logical_death_event_id"]
            ),
            placement=model_placement,
            owner_kind=owner,
            owner_context=context,
            sources=_sources_from_payload(payload["sources"]),
            eligible_sources=_sources_from_payload(payload["eligible_sources"]),
            excluded_actions=tuple(
                RetainedAttackAction(_identifier("excluded_action", action))
                for action in exclusions
            ),
            stage=stage,
            request_id=_optional_identifier(payload, "request_id"),
            result_id=_optional_identifier(payload, "result_id"),
            selected_source_id=_optional_identifier(payload, "selected_source_id"),
            selected_action=selected_action,
            completion_reason=_optional_identifier(payload, "completion_reason"),
            owner_progress=_optional_object(payload["owner_progress"]),
        )


def retained_destructions(*, state: GameState) -> tuple[RetainedModelDestruction, ...]:
    records: list[RetainedModelDestruction] = []
    for effect in state.persisting_effects:
        payload = effect.effect_payload
        if (
            not isinstance(payload, dict)
            or payload.get("effect_kind") != RETAINED_DESTRUCTION_EFFECT_KIND
        ):
            continue
        if set(payload) != {"effect_kind", "destruction"}:
            raise GameLifecycleError("Retained destruction effect fields drift.")
        record = RetainedModelDestruction.from_payload(payload["destruction"])
        if (
            effect.effect_id != record.effect_id
            or effect.source_rule_id != FIGHT_ON_DEATH_SOURCE_ID
        ):
            raise GameLifecycleError("Retained destruction effect identity drift.")
        if (
            effect.owner_player_id != record.placement.player_id
            or effect.target_unit_instance_ids != (record.placement.unit_instance_id,)
        ):
            raise GameLifecycleError("Retained destruction effect ownership drift.")
        phase = state.current_battle_phase
        if (
            phase is None
            or effect.started_battle_round != state.battle_round
            or (
                effect.started_phase is not battle_phase_kind_from_token(phase.value)
                or effect.expiration
                != EffectExpiration.end_phase(
                    battle_round=state.battle_round,
                    phase=battle_phase_kind_from_token(phase.value),
                    player_id=_identifier("active_player_id", state.active_player_id),
                )
            )
        ):
            raise GameLifecycleError("Retained destruction phase drift.")
        records.append(record)
    if len({record.model_instance_id for record in records}) != len(records):
        raise GameLifecycleError("Retained destruction model authority is duplicated.")
    return tuple(records)


def retained_destruction_for_model(
    *, state: GameState, model_instance_id: str
) -> RetainedModelDestruction | None:
    return next(
        (
            record
            for record in retained_destructions(state=state)
            if record.model_instance_id == model_instance_id
        ),
        None,
    )


def pending_cause_for_model(
    *, state: GameState, model_instance_id: str
) -> ModelDestructionCauseAuthority:
    causes = tuple(
        cause
        for cause in state.model_destruction_cause_authorities
        if cause.model_instance_id == model_instance_id and not cause.is_consumed
    )
    if len(causes) != 1:
        raise GameLifecycleError("Retention requires exactly one unconsumed destruction cause.")
    return causes[0]


def validate_retained_placement(*, state: GameState, record: RetainedModelDestruction) -> None:
    from warhammer40k_core.engine.damage_allocation import model_by_id, model_owner_player_id
    from warhammer40k_core.engine.model_logical_death import model_logical_death_record_from_event

    battlefield = state.battlefield_state
    causes = tuple(
        cause
        for cause in state.model_destruction_cause_authorities
        if cause.cause_id == record.cause_id
    )
    if len(causes) != 1:
        raise GameLifecycleError("Retained destruction cause authority is missing or duplicated.")
    cause = causes[0]
    logical = model_logical_death_record_from_event(cause.logical_death_event)
    if (
        logical.destroyed_model_placement != record.placement
        or not logical.placement_retained
        or cause.logical_death_event.event_id != record.logical_death_event_id
        or state.unit_instance_id_for_model(record.model_instance_id)
        != record.placement.unit_instance_id
        or model_owner_player_id(state=state, model_instance_id=record.model_instance_id)
        != record.placement.player_id
    ):
        raise GameLifecycleError("Retained destruction original placement or ownership drift.")
    if model_by_id(state=state, model_instance_id=record.model_instance_id).is_alive:
        raise GameLifecycleError("Retained destruction model is alive.")
    if record.stage is RetainedDestructionStage.REMOVED:
        if (
            battlefield is None
            or record.model_instance_id not in battlefield.removed_model_ids
            or battlefield.model_placement_or_none(record.model_instance_id) is not None
            or not cause.is_consumed
        ):
            raise GameLifecycleError("Retained destruction removal authority drift.")
        return
    if (
        battlefield is None
        or battlefield.model_placement_or_none(record.model_instance_id) != record.placement
    ):
        raise GameLifecycleError("Retained destruction fixed placement drift.")
    cause = pending_cause_for_model(state=state, model_instance_id=record.model_instance_id)
    if (
        cause.cause_id != record.cause_id
        or cause.logical_death_event.event_id != record.logical_death_event_id
    ):
        raise GameLifecycleError("Retained destruction logical death authority drift.")


def destruction_cause_ancestor_ids(*, state: GameState, cause_id: str) -> frozenset[str]:
    causes = {cause.cause_id: cause for cause in state.model_destruction_cause_authorities}
    if cause_id not in causes:
        raise GameLifecycleError("Retained destruction ancestry has no cause.")
    remaining = list(causes[cause_id].parent_cause_ids)
    ancestors: set[str] = set()
    while remaining:
        ancestor_id = remaining.pop()
        if ancestor_id == cause_id or ancestor_id not in causes:
            raise GameLifecycleError("Retained destruction ancestry is invalid.")
        if ancestor_id not in ancestors:
            ancestors.add(ancestor_id)
            remaining.extend(causes[ancestor_id].parent_cause_ids)
    return frozenset(ancestors)


def record_retained_destruction(*, state: GameState, record: RetainedModelDestruction) -> None:
    validate_retained_placement(state=state, record=record)
    phase = state.current_battle_phase
    if phase is None:
        raise GameLifecycleError("Retained destruction requires a battle phase.")
    phase_kind = battle_phase_kind_from_token(phase.value)
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=record.effect_id,
            source_rule_id=FIGHT_ON_DEATH_SOURCE_ID,
            owner_player_id=record.placement.player_id,
            target_unit_instance_ids=(record.placement.unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=phase_kind,
            expiration=EffectExpiration.end_phase(
                battle_round=state.battle_round,
                phase=phase_kind,
                player_id=_identifier("active_player_id", state.active_player_id),
            ),
            effect_payload={
                "effect_kind": RETAINED_DESTRUCTION_EFFECT_KIND,
                "destruction": record.to_payload(),
            },
        )
    )


def replace_retained_destruction(
    *, state: GameState, original: RetainedModelDestruction, updated: RetainedModelDestruction
) -> None:
    current = retained_destruction_for_model(
        state=state, model_instance_id=original.model_instance_id
    )
    if (
        current != original
        or updated.cause_id != original.cause_id
        or updated.placement != original.placement
        or updated.logical_death_event_id != original.logical_death_event_id
        or updated.owner_kind is not original.owner_kind
        or updated.owner_context != original.owner_context
        or updated.sources != original.sources
        or updated.eligible_sources != original.eligible_sources
        or updated.request_id != original.request_id
    ):
        raise GameLifecycleError("Retained destruction replacement authority drift.")
    validate_retained_placement(state=state, record=updated)
    effect = next(
        effect for effect in state.persisting_effects if effect.effect_id == original.effect_id
    )
    replacement = replace(
        effect,
        effect_payload={
            "effect_kind": RETAINED_DESTRUCTION_EFFECT_KIND,
            "destruction": updated.to_payload(),
        },
    )
    state.remove_persisting_effects_by_id((original.effect_id,))
    state.record_persisting_effect(replacement)


def _sources_from_payload(value: JsonValue) -> tuple[DestructionReactionSource, ...]:
    from warhammer40k_core.engine.damage_allocation import (
        DestructionReactionSource,
        DestructionReactionSourcePayload,
    )

    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise GameLifecycleError("Retained destruction source payload must be an object array.")
    return tuple(
        DestructionReactionSource.from_payload(cast(DestructionReactionSourcePayload, item))
        for item in value
    )


def _optional_identifier(payload: dict[str, JsonValue], key: str) -> str | None:
    value = payload[key]
    return None if value is None else _identifier(key, value)


def _optional_object(value: JsonValue) -> dict[str, JsonValue] | None:
    if value is None or isinstance(value, dict):
        return value
    raise GameLifecycleError("Retained destruction owner progress must be an object.")
