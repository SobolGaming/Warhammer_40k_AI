"""Deterministic finite membership decisions and authenticated split transcripts."""

from __future__ import annotations

import hashlib
from dataclasses import replace

from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.event_log import canonical_json, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies
from warhammer40k_core.engine.unit_split_permissions import (
    UnitSplitPermission,
    unit_split_permissions,
)
from warhammer40k_core.engine.unit_splitting import build_split_army

SELECT_UNIT_SPLIT_MEMBERSHIP_DECISION_TYPE = "select_unit_split_membership"


def replay_unit_split_decisions(
    *, game_id: str, armies: tuple[ArmyDefinition, ...], records: tuple[DecisionRecord, ...]
) -> tuple[tuple[ArmyDefinition, ...], DecisionRequest | None]:
    """Rebuild partitions from source-owned models and validated finite decisions.

    The returned next request is also the pre-pop authority. Neither a serialized
    pending request nor a serialized membership record grants its own permission.
    """
    transcript = tuple(
        r for r in records if r.request.decision_type == SELECT_UNIT_SPLIT_MEMBERSHIP_DECISION_TYPE
    )
    cursor = 0
    restored = [
        replace(a, units=a.source_units(), unit_splits=()) if a.unit_splits else a for a in armies
    ]
    pending: DecisionRequest | None = None
    for army_index, source_army in enumerate(restored):
        for permission in unit_split_permissions(source_army):
            army = restored[army_index]
            if any(
                r.source_unit_instance_id == permission.target_unit_id for r in army.unit_splits
            ):
                continue
            view = rules_unit_view_from_armies(
                armies=(army,), unit_instance_id=permission.target_unit_id
            )
            models = tuple(sorted(m.model_instance_id for m in view.own_models))
            if len(models) < 2:
                continue
            if any(not m.is_alive for m in view.own_models):
                raise GameLifecycleError("Pre-battle split cannot contain destroyed source models.")
            first: tuple[str, ...] = ()
            split_root = _split_request_root(game_id, permission)
            for step in range(len(models) + 1):
                request = _membership_request(
                    game_id=game_id,
                    permission=permission,
                    root=split_root,
                    model_ids=models,
                    first=first,
                    step=step,
                    army_fingerprint=hashlib.sha256(
                        canonical_json(
                            replace(
                                army,
                                units=tuple(sorted(army.units, key=lambda u: u.unit_instance_id)),
                            ).to_payload()
                        ).encode()
                    ).hexdigest(),
                )
                if cursor == len(transcript):
                    pending = request
                    return tuple(restored), pending
                record = transcript[cursor]
                if record.request != request:
                    raise GameLifecycleError(
                        "Unit split decision source, timing, membership or request drift."
                    )
                record.result.validate_for_request(request)
                cursor += 1
                choice = record.result.selected_option_id
                if choice == "decline":
                    break
                if step == 0:
                    continue
                if choice == "successor:0":
                    first = (*first, models[step - 1])
                if step == len(models):
                    restored[army_index] = build_split_army(
                        army=army,
                        unit_instance_id=permission.target_unit_id,
                        first_model_ids=first,
                        request_id=split_root,
                        source_id=permission.source_id,
                        specified_strengths=permission.specified_strengths,
                    )
    if cursor != len(transcript):
        raise GameLifecycleError(
            "Unit split transcript contains an unauthorized or repeated decision."
        )
    return tuple(restored), pending


def _split_request_root(game_id: str, permission: UnitSplitPermission) -> str:
    key = canonical_json(
        [
            game_id,
            permission.player_id,
            permission.source_id,
            permission.source_unit_id,
            permission.target_unit_id,
        ]
    )
    return "unit-split-request:" + hashlib.sha256(key.encode()).hexdigest()


def _membership_request(
    *,
    game_id: str,
    permission: UnitSplitPermission,
    root: str,
    model_ids: tuple[str, ...],
    first: tuple[str, ...],
    step: int,
    army_fingerprint: str,
) -> DecisionRequest:
    strengths = permission.specified_strengths
    feasible = strengths is not None and sum(strengths) == len(model_ids)
    limits = strengths if feasible else ((len(model_ids) + 1) // 2,) * 2
    if limits is None:
        raise GameLifecycleError("Unit split count limits are missing.")
    if step == 0:
        options = [DecisionOption("split", "Split this unit", {"action": "split"})]
        if permission.optional:
            options.append(
                DecisionOption("decline", "Keep this unit together", {"action": "decline"})
            )
    else:
        assigned = (len(first), step - 1 - len(first))
        options = [
            DecisionOption(
                f"successor:{index}",
                f"Assign to unit {index + 1}",
                {"model_instance_id": model_ids[step - 1], "successor_index": index},
            )
            for index in (0, 1)
            if assigned[index] < limits[index]
        ]
    return DecisionRequest(
        request_id=f"{root}:{step}",
        decision_type=SELECT_UNIT_SPLIT_MEMBERSHIP_DECISION_TYPE,
        actor_id=permission.player_id,
        payload=validate_json_value(
            {
                "game_id": game_id,
                "setup_step": "declare_battle_formations",
                "secret": True,
                "source_rule_id": permission.source_id,
                "source_unit_instance_id": permission.source_unit_id,
                "unit_instance_id": permission.target_unit_id,
                "split_request_id": root,
                "model_ids": list(model_ids),
                "first_model_ids": list(first),
                "step": step,
                "specified_strengths": None if strengths is None else list(strengths),
                "used_balanced_fallback": strengths is not None and not feasible,
                "army_fingerprint": army_fingerprint,
            }
        ),
        options=tuple(options),
    )
