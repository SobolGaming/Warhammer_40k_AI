"""An opt-in player policy for the formation left by a potential casualty."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from warhammer40k_core.adapters.projection import GameViewPayload
from warhammer40k_core.ai.finite_candidates import FiniteCandidateSet
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyAction, PolicyError
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.damage_allocation import SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.unit_coherency import UnitCoherencyContext
from warhammer40k_core.geometry.model_geometry import ModelGeometry, ModelGeometryPayload
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume

ALLOCATION_COHERENCY_POLICY_ID = "post-casualty-coherency-v1"


@dataclass(frozen=True, slots=True)
class AllocationCoherencyPolicy:
    """Score one hypothetical removal from a standalone unit under the public rules."""

    ruleset: RulesetDescriptor

    def choose(self, context: PlayerDecisionContext) -> PolicyAction:
        scores = self.score_options(context)
        # max retains the first issued option when coherency scores tie.
        return context.select_option(max(scores, key=scores.__getitem__))

    def score_options(self, context: PlayerDecisionContext) -> dict[str, bool]:
        if (
            context.route.stage != "battle"
            or context.route.decision_type != SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE
        ):
            raise PolicyError("Allocation coherency requires a damage allocation model request.")
        candidates = FiniteCandidateSet.from_context(context)
        view = context.observation

        payload = context.request["payload"]
        allocation = payload.get("allocation_context") if isinstance(payload, dict) else None
        if not isinstance(allocation, dict):
            raise PolicyError("Damage allocation request lacks the target formation.")
        unit_id = allocation.get("target_unit_instance_id")
        living_ids = allocation.get("alive_model_ids")
        if not isinstance(unit_id, str) or not isinstance(living_ids, list):
            raise PolicyError("Damage allocation request lacks the target unit or living models.")
        model_ids = tuple(_model_id(value) for value in living_ids)
        models = _visible_formation(view, context.route.actor_id, unit_id, model_ids)

        coherency = UnitCoherencyContext.from_ruleset_descriptor(
            self.ruleset, unit_instance_id=unit_id
        )
        scores: dict[str, bool] = {}
        for candidate in candidates.candidates:
            option = candidate.option
            option_payload = option["payload"]
            selected = (
                option_payload.get("selected_model_id")
                if isinstance(option_payload, dict)
                else None
            )
            selected_id = _model_id(selected)
            if selected_id not in model_ids:
                raise PolicyError("Issued damage allocation model is outside the target formation.")
            survivors = tuple(model for model in models if model.model_id != selected_id)
            scores[option["option_id"]] = coherency.validate_models(survivors).is_coherent
        return scores


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
