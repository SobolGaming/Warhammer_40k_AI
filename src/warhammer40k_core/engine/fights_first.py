from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.catalog_conditional_leader_queries import (
    CONDITIONAL_LEADER_ABILITY_DESCRIPTOR_ID,
    CONDITIONAL_NOT_LEADING_ABILITY_DESCRIPTOR_ID,
    conditional_leader_grant_effect_applies,
    conditional_not_leading_grant_effect_applies,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.fights_first_native import validate_native_fights_first_effects
from warhammer40k_core.engine.generic_rule_effect_payloads import (
    generic_rule_effect_payload_grants_ability,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_unit_effects import rules_unit_effect_applications
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_identities_share_lineage,
    rules_unit_view_by_id,
    rules_unit_views_from_armies,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_fights_first_2026_09 import (
    FIGHTS_FIRST_SOURCE_ID as FIGHTS_FIRST_SOURCE_ID,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


FIGHTS_FIRST_EFFECT_KIND = "fights_first"
CHARGE_FIGHTS_FIRST_EFFECT_KIND = "charge_grants_fights_first"


class FightsFirstSourcePayload(TypedDict):
    unit_instance_id: str
    effect_id: str
    source_rule_id: str
    effect_kind: str


class FightsFirstRegistryPayload(TypedDict):
    sources: list[FightsFirstSourcePayload]


@dataclass(frozen=True, slots=True)
class FightsFirstSource:
    unit_instance_id: str
    effect_id: str
    source_rule_id: str
    effect_kind: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("FightsFirstSource unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "effect_id",
            _validate_identifier("FightsFirstSource effect_id", self.effect_id),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("FightsFirstSource source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "effect_kind",
            _validate_identifier("FightsFirstSource effect_kind", self.effect_kind),
        )

    def to_payload(self) -> FightsFirstSourcePayload:
        return {
            "unit_instance_id": self.unit_instance_id,
            "effect_id": self.effect_id,
            "source_rule_id": self.source_rule_id,
            "effect_kind": self.effect_kind,
        }

    @classmethod
    def from_payload(cls, payload: FightsFirstSourcePayload) -> Self:
        return cls(
            unit_instance_id=payload["unit_instance_id"],
            effect_id=payload["effect_id"],
            source_rule_id=payload["source_rule_id"],
            effect_kind=payload["effect_kind"],
        )


@dataclass(frozen=True, slots=True)
class FightsFirstRegistry:
    sources: tuple[FightsFirstSource, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "sources", _validate_fights_first_sources(self.sources))

    @classmethod
    def from_state(cls, state: GameState) -> Self:
        effects = tuple(state.persisting_effects)
        validate_native_fights_first_effects(
            armies=tuple(state.army_definitions), effects=effects, stage=state.stage
        )
        if not any(_is_fights_first_payload(effect.effect_payload) for effect in effects):
            return cls()
        sources: list[FightsFirstSource] = []
        for identity in rules_unit_views_from_armies(armies=tuple(state.army_definitions)):
            view = rules_unit_view_by_id(state=state, unit_instance_id=identity.unit_instance_id)
            present, grants = fights_first_model_inventory(state=state, view=view)
            covered = {model_id for _, ids in grants for model_id in ids}
            if present and covered == set(present):
                sources.extend(source for source, _ in grants)
        return cls(tuple(sources))

    def has_unit(self, unit_instance_id: str) -> bool:
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        return any(source.unit_instance_id == requested_unit_id for source in self.sources)

    def has_unit_lineage(
        self,
        *,
        state: GameState,
        unit_instance_id: str,
        effect_kind: str | None = None,
    ) -> bool:
        requested_rules_unit_id = rules_unit_view_by_id(
            state=state,
            unit_instance_id=unit_instance_id,
        ).unit_instance_id
        requested_effect_kind = (
            None if effect_kind is None else _validate_identifier("effect_kind", effect_kind)
        )
        return any(
            (requested_effect_kind is None or source.effect_kind == requested_effect_kind)
            and (
                source.unit_instance_id == requested_rules_unit_id
                or rules_unit_identities_share_lineage(
                    state=state,
                    first_unit_instance_id=requested_rules_unit_id,
                    second_unit_instance_id=source.unit_instance_id,
                )
            )
            for source in self.sources
        )

    def charged_unit_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    source.unit_instance_id
                    for source in self.sources
                    if source.effect_kind == CHARGE_FIGHTS_FIRST_EFFECT_KIND
                }
            )
        )

    def to_payload(self) -> FightsFirstRegistryPayload:
        return {"sources": [source.to_payload() for source in self.sources]}

    @classmethod
    def from_payload(cls, payload: FightsFirstRegistryPayload) -> Self:
        return cls(tuple(FightsFirstSource.from_payload(source) for source in payload["sources"]))


def fights_first_model_inventory(
    *,
    state: GameState,
    view: RulesUnitView,
) -> tuple[tuple[str, ...], tuple[tuple[FightsFirstSource, tuple[str, ...]], ...]]:
    """Keep partial grants model-scoped before applying the every-model predicate."""
    present = tuple(
        sorted(
            model.model_instance_id
            for model in view.own_models
            if model.is_alive or model.model_instance_id in view.retained_model_ids
        )
    )
    grants: list[tuple[FightsFirstSource, tuple[str, ...]]] = []
    for application in rules_unit_effect_applications(state, view.unit_instance_id):
        effect = application.effect
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            continue
        kind = payload.get("effect_kind")
        if not _is_fights_first_payload(payload):
            continue
        descriptor = payload.get("descriptor_id")
        if (
            descriptor == CONDITIONAL_LEADER_ABILITY_DESCRIPTOR_ID
            and not conditional_leader_grant_effect_applies(
                state=state,
                effect=effect,
                rules_unit_instance_id=view.unit_instance_id,
            )
        ):
            continue
        if (
            descriptor == CONDITIONAL_NOT_LEADING_ABILITY_DESCRIPTOR_ID
            and not conditional_not_leading_grant_effect_applies(effect=effect)
        ):
            continue
        ids = set(present)
        if "native_model_ids" in payload:
            raw_ids = payload["native_model_ids"]
            if not isinstance(raw_ids, list) or any(type(value) is not str for value in raw_ids):
                raise GameLifecycleError("Native Fights First model scope is malformed.")
            ids.intersection_update(cast(list[str], raw_ids))
        else:
            target = payload.get("target")
            if isinstance(target, dict) and target.get("kind") == "this_model":
                context = payload.get("context")
                if (
                    not isinstance(context, dict)
                    or type(context.get("source_model_instance_id")) is not str
                ):
                    raise GameLifecycleError(
                        "Model Fights First grant requires explicit source model."
                    )
                ids.intersection_update((cast(str, context["source_model_instance_id"]),))
        if ids:
            grants.append(
                (
                    FightsFirstSource(
                        unit_instance_id=view.unit_instance_id,
                        effect_id=effect.effect_id,
                        source_rule_id=effect.source_rule_id,
                        effect_kind=CHARGE_FIGHTS_FIRST_EFFECT_KIND
                        if kind == CHARGE_FIGHTS_FIRST_EFFECT_KIND
                        else FIGHTS_FIRST_EFFECT_KIND,
                    ),
                    tuple(sorted(ids)),
                )
            )
    return present, tuple(grants)


def _is_fights_first_payload(payload: JsonValue) -> bool:
    return isinstance(payload, dict) and (
        payload.get("effect_kind") in {FIGHTS_FIRST_EFFECT_KIND, CHARGE_FIGHTS_FIRST_EFFECT_KIND}
        or generic_rule_effect_payload_grants_ability(payload, ability="fights_first")
    )


def _validate_fights_first_sources(values: object) -> tuple[FightsFirstSource, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("FightsFirstRegistry sources must be a tuple.")
    sources = tuple(
        _validate_fights_first_source(value) for value in cast(tuple[object, ...], values)
    )
    seen: set[tuple[str, str]] = set()
    for source in sources:
        key = (source.unit_instance_id, source.effect_id)
        if key in seen:
            raise GameLifecycleError("FightsFirstRegistry sources must be unique.")
        seen.add(key)
    return tuple(sorted(sources, key=lambda source: (source.unit_instance_id, source.effect_id)))


def _validate_fights_first_source(value: object) -> FightsFirstSource:
    if type(value) is not FightsFirstSource:
        raise GameLifecycleError("FightsFirstRegistry sources must contain FightsFirstSource.")
    return value


_validate_identifier = IdentifierValidator(GameLifecycleError)
