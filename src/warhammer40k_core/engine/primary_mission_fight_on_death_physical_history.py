from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from warhammer40k_core.engine.battlefield_state import ModelPlacement, ModelPlacementPayload
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry.pose import Pose


@dataclass(frozen=True, slots=True)
class PhysicalAuthorityState:
    presence: str | None
    pose: Pose | None
    wounds_remaining: int | None


def apply_fight_on_death_awaiting(
    *,
    authority: dict[str, PhysicalAuthorityState],
    event: EventRecord,
) -> None:
    expected_keys = {
        "game_id",
        "battle_round",
        "phase",
        "model_instance_id",
        "unit_instance_id",
        "source_id",
        "source_rule_id",
        "effect_id",
        "model_placement",
    }
    if not isinstance(event.payload, dict) or set(event.payload) != expected_keys:
        raise GameLifecycleError("Fight On Death physical authority payload drifted.")
    payload = event.payload
    for key in (
        "game_id",
        "phase",
        "model_instance_id",
        "unit_instance_id",
        "source_id",
        "source_rule_id",
        "effect_id",
    ):
        if type(payload[key]) is not str or not payload[key]:
            raise GameLifecycleError("Fight On Death physical authority identity is invalid.")
    if type(payload["battle_round"]) is not int or payload["battle_round"] < 1:
        raise GameLifecycleError("Fight On Death physical authority round is invalid.")
    raw_placement = payload["model_placement"]
    if not isinstance(raw_placement, dict):
        raise GameLifecycleError("Fight On Death physical authority placement is invalid.")
    placement = ModelPlacement.from_payload(cast(ModelPlacementPayload, raw_placement))
    model_id = cast(str, payload["model_instance_id"])
    if (
        placement.model_instance_id != model_id
        or placement.unit_instance_id != payload["unit_instance_id"]
    ):
        raise GameLifecycleError("Fight On Death physical authority placement drifted.")
    prior = authority.get(model_id)
    if prior is not None and (
        prior.presence != "destroyed" or prior.pose is not None or prior.wounds_remaining != 0
    ):
        raise GameLifecycleError("Fight On Death physical authority history is discontinuous.")
    authority[model_id] = PhysicalAuthorityState(
        presence="battlefield",
        pose=placement.pose,
        wounds_remaining=0,
    )


def apply_fight_on_death_removed(
    *,
    authority: dict[str, PhysicalAuthorityState],
    event: EventRecord,
) -> None:
    if not isinstance(event.payload, dict) or frozenset(event.payload) not in {
        frozenset(
            {
                "game_id",
                "battle_round",
                "phase",
                "model_instance_ids",
                "reason",
            }
        ),
        frozenset(
            {
                "game_id",
                "battle_round",
                "phase",
                "unit_instance_id",
                "model_instance_ids",
                "reason",
            }
        ),
    }:
        raise GameLifecycleError("Fight On Death cleanup physical authority drifted.")
    payload = event.payload
    if (
        type(payload["game_id"]) is not str
        or not payload["game_id"]
        or type(payload["battle_round"]) is not int
        or payload["battle_round"] < 1
        or payload["phase"] != "fight"
        or payload["reason"] not in {"phase_end", "unit_fight_completed"}
    ):
        raise GameLifecycleError("Fight On Death cleanup physical context is invalid.")
    unit_id = payload.get("unit_instance_id")
    if unit_id is not None and (type(unit_id) is not str or not unit_id):
        raise GameLifecycleError("Fight On Death cleanup physical unit is invalid.")
    raw_model_ids = payload["model_instance_ids"]
    if (
        not isinstance(raw_model_ids, list)
        or not raw_model_ids
        or any(type(model_id) is not str or not model_id for model_id in raw_model_ids)
        or len(set(raw_model_ids)) != len(raw_model_ids)
    ):
        raise GameLifecycleError("Fight On Death cleanup model inventory is invalid.")
    for model_id in cast(list[str], raw_model_ids):
        prior = authority.get(model_id)
        if prior is not None and (
            prior.presence != "battlefield" or prior.pose is None or prior.wounds_remaining != 0
        ):
            raise GameLifecycleError("Fight On Death cleanup history is discontinuous.")
        authority[model_id] = PhysicalAuthorityState(
            presence="destroyed",
            pose=None,
            wounds_remaining=0,
        )


__all__ = (
    "PhysicalAuthorityState",
    "apply_fight_on_death_awaiting",
    "apply_fight_on_death_removed",
)
