"""An opt-in player policy for the formation left by a potential casualty."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import cast

from warhammer40k_core.adapters.projection import GameViewPayload
from warhammer40k_core.ai.finite_candidates import FiniteCandidateSet
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyAction, PolicyError
from warhammer40k_core.core.ruleset_descriptor import CoherencyPolicyKind, RulesetDescriptor
from warhammer40k_core.engine.damage_allocation import SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.unit_coherency import UnitCoherencyContext
from warhammer40k_core.geometry.base import OvalBase
from warhammer40k_core.geometry.milli_inch import inches_to_ticks
from warhammer40k_core.geometry.milli_inch_oval import CanonicalOval
from warhammer40k_core.geometry.milli_inch_oval_oval_distance import oval_oval_distance_ticks
from warhammer40k_core.geometry.milli_inch_polygon import MAX_COORDINATE_TICKS, MIN_COORDINATE_TICKS
from warhammer40k_core.geometry.model_geometry import ModelGeometry, ModelGeometryPayload
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume

ALLOCATION_COHERENCY_POLICY_ID = "post-casualty-coherency-v1"
ALLOCATION_COHERENCY_TIE_BREAK_POLICY_ID = "post-casualty-coherency-one-removal-v1"
_MAX_TIE_BREAK_MODELS = 5


@dataclass(frozen=True, slots=True)
class AllocationCoherencyPolicy:
    """Score one hypothetical removal from a standalone unit under the public rules."""

    ruleset: RulesetDescriptor

    def choose(self, context: PlayerDecisionContext) -> PolicyAction:
        scores = self.score_options(context)
        # max retains the first issued option when coherency scores tie.
        return context.select_option(max(scores, key=scores.__getitem__))

    def score_options(self, context: PlayerDecisionContext) -> dict[str, bool]:
        coherency, models, choices = _allocation(context, self.ruleset)
        return {
            option_id: coherency.validate_models(_without_model(models, model_id)).is_coherent
            for option_id, model_id in choices.items()
        }


@dataclass(frozen=True, slots=True)
class AllocationCoherencyTieBreakPolicy(AllocationCoherencyPolicy):
    """Prefer an issued casualty that would leave at most one required cleanup loss."""

    def choose(self, context: PlayerDecisionContext) -> PolicyAction:
        coherency, models, choices = _allocation(context, self.ruleset)
        first_issued = next(iter(choices))
        for option_id, model_id in choices.items():
            if coherency.validate_models(_without_model(models, model_id)).is_coherent:
                return context.select_option(option_id)

        if (
            len(choices) < 2
            or len(models) > _MAX_TIE_BREAK_MODELS
            or len(set(choices.values())) != len(choices)
            or not _has_complete_own_formation(context, coherency.unit_instance_id, models)
            or not _canonical_distances_agree(coherency, models)
        ):
            return context.select_option(first_issued)

        # A pair can be visited from either issued casualty. Validate it at most once.
        tried_pairs: set[frozenset[str]] = set()
        for option_id, model_id in choices.items():
            survivors = _without_model(models, model_id)
            for other in survivors:
                pair = frozenset((model_id, other.model_id))
                if pair in tried_pairs:
                    continue
                if coherency.validate_models(_without_model(survivors, other.model_id)).is_coherent:
                    return context.select_option(option_id)
                tried_pairs.add(pair)
        return context.select_option(first_issued)


def _allocation(
    context: PlayerDecisionContext, ruleset: RulesetDescriptor
) -> tuple[UnitCoherencyContext, tuple[Model, ...], dict[str, str]]:
    if (
        context.route.stage != "battle"
        or context.route.decision_type != SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE
    ):
        raise PolicyError("Allocation coherency requires a damage allocation model request.")
    candidates = FiniteCandidateSet.from_context(context)
    payload = context.request["payload"]
    allocation = payload.get("allocation_context") if isinstance(payload, dict) else None
    if not isinstance(allocation, dict):
        raise PolicyError("Damage allocation request lacks the target formation.")
    unit_id = allocation.get("target_unit_instance_id")
    living_ids = allocation.get("alive_model_ids")
    if not isinstance(unit_id, str) or not isinstance(living_ids, list):
        raise PolicyError("Damage allocation request lacks the target unit or living models.")
    model_ids = tuple(_model_id(value) for value in living_ids)
    models = _visible_formation(context.observation, context.route.actor_id, unit_id, model_ids)

    choices: dict[str, str] = {}
    for candidate in candidates.candidates:
        option = candidate.option
        option_payload = option["payload"]
        selected = (
            option_payload.get("selected_model_id") if isinstance(option_payload, dict) else None
        )
        model_id = _model_id(selected)
        if model_id not in model_ids:
            raise PolicyError("Issued damage allocation model is outside the target formation.")
        choices[option["option_id"]] = model_id
    return (
        UnitCoherencyContext.from_ruleset_descriptor(ruleset, unit_instance_id=unit_id),
        models,
        choices,
    )


def _without_model(models: tuple[Model, ...], model_id: str) -> tuple[Model, ...]:
    return tuple(model for model in models if model.model_id != model_id)


def _has_complete_own_formation(
    context: PlayerDecisionContext, unit_id: str, models: tuple[Model, ...]
) -> bool:
    view = context.observation
    actor_id = context.route.actor_id
    unit = view.get("unit_display_by_id", {}).get(unit_id)
    battlefield = view["battlefield_view"]
    if (
        unit is None
        or unit["owner_player_id"] != actor_id
        or unit["redaction"]["hidden"]
        or battlefield is None
    ):
        return False
    entities = battlefield["authoritative"]["models_by_id"]
    placed_ids = {
        model_id
        for model_id, entity in entities.items()
        if entity["owner_player_id"] == actor_id
        and entity["rules_unit_instance_id"] == unit_id
        and entity["state"] == "placed"
    }
    model_ids = {model.model_id for model in models}
    if model_ids != placed_ids or not model_ids.issubset(unit["model_instance_ids"]):
        return False
    # The physical unit inventory also accounts for prior casualties.
    for model_id in unit["model_instance_ids"]:
        display = view["model_display_by_id"].get(model_id)
        if display is None or display["redaction"]["hidden"]:
            return False
        wounds = display.get("wounds_remaining")
        if wounds is None or (wounds <= 0 if model_id in model_ids else wounds != 0):
            return False
    return True


def _canonical_distances_agree(coherency: UnitCoherencyContext, models: tuple[Model, ...]) -> bool:
    policy = coherency.coherency_policy
    horizontal = policy.max_horizontal_inches
    if policy.policy_kind is not CoherencyPolicyKind.NEIGHBOR_COUNT or horizontal is None:
        return False
    base = models[0].base
    if not isinstance(base, OvalBase) or any(model.base != base for model in models):
        return False
    limits = tuple(
        (limit, inches_to_ticks(limit))
        for limit in (horizontal, policy.max_unit_span_inches)
        if limit is not None
    )
    length, width = inches_to_ticks(base.length), inches_to_ticks(base.width)
    if not 1 <= width <= length <= MAX_COORDINATE_TICKS:
        return False

    ovals: list[CanonicalOval] = []
    z = models[0].pose.position.z
    for model in models:
        pose = model.pose
        # Coplanar bases have zero vertical gap under the native validator.
        if pose.position.z != z or pose.facing.degrees % 45:
            return False
        center = inches_to_ticks(pose.position.x), inches_to_ticks(pose.position.y)
        if not all(MIN_COORDINATE_TICKS <= value <= MAX_COORDINATE_TICKS for value in center):
            return False
        ovals.append(CanonicalOval(center, length, width, int(pose.facing.degrees)))

    for (model, oval), (other, other_oval) in combinations(zip(models, ovals, strict=True), 2):
        native_gap = model.base_distance_to(other)
        gap_ticks = oval_oval_distance_ticks(oval, other_oval)
        if any((native_gap <= limit) != (gap_ticks <= ticks) for limit, ticks in limits):
            return False
    return True


def _model_id(value: JsonValue) -> str:
    if not isinstance(value, str) or not value:
        raise PolicyError("Damage allocation model identity is missing.")
    return value


def _visible_formation(
    view: GameViewPayload, actor_id: str, unit_id: str, model_ids: tuple[str, ...]
) -> tuple[Model, ...]:
    battlefield = view["battlefield_view"]
    if battlefield is None:
        raise PolicyError("Allocation coherency requires a projected battlefield.")
    entities = battlefield["authoritative"]["models_by_id"]
    models: list[Model] = []
    for model_id in model_ids:
        entity = entities.get(model_id)
        display = view["model_display_by_id"].get(model_id)
        if (
            entity is None
            or entity["owner_player_id"] != actor_id
            or entity["rules_unit_instance_id"] != unit_id
            or entity["state"] != "placed"
            or entity["pose"] is None
            or display is None
            or display["redaction"]["hidden"]
            or not isinstance(display["geometry"], dict)
        ):
            raise PolicyError("Allocation coherency requires visible geometry for the target unit.")
        if entity["unit_instance_id"] != unit_id:
            raise PolicyError("Allocation coherency requires a standalone target unit.")
        geometry = ModelGeometry.from_payload(cast(ModelGeometryPayload, display["geometry"]))
        pose = entity["pose"]
        position = pose["position"]
        models.append(
            Model(
                model_id=model_id,
                pose=Pose.at(
                    position["x_inches"],
                    position["y_inches"],
                    position["z_inches"],
                    pose["facing_degrees"],
                ),
                base=geometry.base_shape(),
                volume=ModelVolume(height=geometry.height_inches),
                body_parts=geometry.body_parts,
                measures_every_part="FRAME" in display["keywords"],
            )
        )
    return tuple(models)
