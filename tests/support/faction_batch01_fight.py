"""Finite native Fight submissions for a bounded real consumer engagement."""

from __future__ import annotations

from typing import Any, cast

from tests.support.faction_batch01 import Scene, request
from tests.support.section04_fixtures import weapon_rows
from tests.support.section12_fixtures import melee_payload, move_payload

from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.stratagems import stratagem_decline_payload


def fight_to_end(s: Scene) -> list[dict[str, Any]]:
    """Use each available fighter's real weapon and native allocation choices."""
    status = s.session.advance_until_decision_or_terminal()
    rerolls: list[dict[str, Any]] = []
    for i in range(250):
        assert status.status_kind not in {
            LifecycleStatusKind.INVALID,
            LifecycleStatusKind.UNSUPPORTED,
        }, status
        if s.state.current_battle_phase is not BattlePhase.FIGHT:
            return rerolls
        r = request(status)
        result_id = f"batch01:fight:{i}"
        if r.decision_type == "submit_movement_proposal":
            # Native typed decline of optional Pile In/Consolidation; no endpoint shortcut.
            status = s.session.submit_parameterized_payload(
                request_id=r.request_id, payload=move_payload(r), result_id=result_id
            )
            continue
        if r.decision_type == "submit_stratagem_target_proposal":
            status = s.session.submit_parameterized_payload(
                request_id=r.request_id, payload=stratagem_decline_payload(), result_id=result_id
            )
            continue
        if r.decision_type == "submit_melee_declaration":
            payload = cast(dict[str, JsonValue], melee_payload(r, attack=False))
            declarations: list[JsonValue] = []
            seen: set[str] = set()
            for row in weapon_rows(r):
                mid = cast(str, row["model_instance_id"])
                targets = cast(list[str], row["engaged_target_unit_instance_ids"])
                if mid in seen or not targets:
                    continue
                seen.add(mid)
                declarations.append(
                    {
                        "attacker_model_instance_id": mid,
                        "wargear_id": row["wargear_id"],
                        "weapon_profile_id": row["weapon_profile_id"],
                        "weapon_instance_id": row["weapon_instance_id"],
                        "selected_weapon_ability_ids": [],
                        "target_allocations": [{"target_unit_instance_id": targets[0]}],
                    }
                )
            payload["declarations"] = declarations
            status = s.session.submit_parameterized_payload(
                request_id=r.request_id, payload=validate_json_value(payload), result_id=result_id
            )
            continue
        if r.is_parameterized_submission_request():
            raise AssertionError(f"Unexpected Fight proposal {r.decision_type}")
        option = next(
            (o for o in r.options if o.option_id in {"decline", "keep", "keep_all_modifiers"}),
            r.options[0],
        )
        if r.decision_type == "select_dice_reroll" and isinstance(r.payload, dict):
            source = r.payload.get("source_rule_id")
            if isinstance(source, str) and "000004080:3" in source:
                rerolls.append(cast(dict[str, Any], r.payload))
                option = next(o for o in r.options if o.option_id != "decline")
        status = s.session.submit_option(
            request_id=r.request_id, option_id=option.option_id, result_id=result_id
        )
    raise AssertionError("Bounded native Fight did not terminate")
