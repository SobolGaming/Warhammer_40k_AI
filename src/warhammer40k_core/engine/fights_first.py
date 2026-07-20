from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.catalog_conditional_leader_queries import (
    CONDITIONAL_LEADER_ABILITY_DESCRIPTOR_ID,
    conditional_leader_grant_effect_applies,
)
from warhammer40k_core.engine.generic_rule_effect_payloads import (
    generic_rule_effect_payload_grants_ability,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

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
        sources: list[FightsFirstSource] = []
        for effect in state.persisting_effects:
            effect_payload = effect.effect_payload
            if not isinstance(effect_payload, dict):
                continue
            base_effect_kind = effect_payload.get("effect_kind")
            for unit_instance_id in effect.target_unit_instance_ids:
                rules_unit = rules_unit_view_by_id(
                    state=state,
                    unit_instance_id=unit_instance_id,
                )
                effect_kind = base_effect_kind
                if (
                    effect_payload.get("descriptor_id") == CONDITIONAL_LEADER_ABILITY_DESCRIPTOR_ID
                    and generic_rule_effect_payload_grants_ability(
                        effect_payload,
                        ability="fights_first",
                    )
                    and conditional_leader_grant_effect_applies(
                        state=state,
                        effect=effect,
                        rules_unit_instance_id=rules_unit.unit_instance_id,
                    )
                ):
                    effect_kind = FIGHTS_FIRST_EFFECT_KIND
                if effect_kind not in {
                    FIGHTS_FIRST_EFFECT_KIND,
                    CHARGE_FIGHTS_FIRST_EFFECT_KIND,
                }:
                    continue
                sources.append(
                    FightsFirstSource(
                        unit_instance_id=rules_unit.unit_instance_id,
                        effect_id=effect.effect_id,
                        source_rule_id=effect.source_rule_id,
                        effect_kind=effect_kind,
                    )
                )
        return cls(tuple(sources))

    def has_unit(self, unit_instance_id: str) -> bool:
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        return any(source.unit_instance_id == requested_unit_id for source in self.sources)

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
