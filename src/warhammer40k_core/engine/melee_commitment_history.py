"""Authenticate melee commitments, their physical rolls and accepted split budgets."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.dice import DiceRollSpec
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.engine.fight_order_records import (
    FightActivationSelection,
    FightActivationSelectionPayload,
)
from warhammer40k_core.engine.fight_resolution import (
    SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
    melee_declaration_proposal_from_payload,
)
from warhammer40k_core.engine.melee_commitment_dispatch import (
    current_selection_request,
    validate_declaration_commitment,
)
from warhammer40k_core.engine.melee_weapon_commitment import (
    COMMITMENT_KEY,
    MELEE_COMMITMENT_EVENT,
    MELEE_CONVENTION_ID,
    SELECT_MELEE_WEAPON_DECISION_TYPE,
    budgets_from_commitment,
    chosen_rows,
    identifier,
    object_payload,
    selection_request,
    selection_stages,
    weapon_profile,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool, RangedAttackPoolPayload
from warhammer40k_core.engine.weapon_instances import equipped_weapon_profile_instances_for_model

if TYPE_CHECKING:
    from warhammer40k_core.engine.lifecycle import GameLifecycle


def _inventory(rows: tuple[JsonValue, ...], host: GameLifecycle) -> None:
    state, config = host.state, host.config
    if state is None:
        raise GameLifecycleError("Melee commitment requires catalog and state.")
    models = {
        model.model_instance_id: model
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    for raw in rows:
        row = object_payload(raw)
        model_id = identifier(row, "model_instance_id")
        if model_id not in models:
            raise GameLifecycleError("Melee commitment model is not in authoritative inventory.")
        matches = [
            weapon
            for weapon in equipped_weapon_profile_instances_for_model(
                model=models[model_id], army_catalog=config.army_catalog
            )
            if weapon.weapon_instance_id == row["weapon_instance_id"]
            and weapon.wargear_id == row["wargear_id"]
            and weapon.weapon_profile.profile_id == row["weapon_profile_id"]
        ]
        if len(matches) != 1 or matches[0].weapon_profile != weapon_profile(row):
            raise GameLifecycleError("Melee commitment physical source profile drifted.")


def validate_melee_commitment_history(host: GameLifecycle) -> None:
    decisions = host.decision_controller
    if (
        not any(
            record.request.decision_type == SELECT_MELEE_WEAPON_DECISION_TYPE
            for record in decisions.records
        )
        and not any(
            event.event_type == MELEE_COMMITMENT_EVENT for event in decisions.event_log.records
        )
        and not any(
            request.decision_type == SELECT_MELEE_WEAPON_DECISION_TYPE
            for request in decisions.queue.pending_requests
        )
    ):
        if any(
            COMMITMENT_KEY in object_payload(request.payload)
            for request in decisions.queue.pending_requests
            if request.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE
        ):
            raise GameLifecycleError("Pending melee declaration has an orphan commitment.")
        return
    records = {record.result.result_id: record for record in decisions.records}
    activations: dict[str, FightActivationSelection] = {}
    selected: dict[str, list[DecisionRecord]] = {}
    inventories: dict[str, tuple[JsonValue, ...]] = {}
    commitments: dict[str, dict[str, JsonValue]] = {}
    physical: dict[str, JsonValue] = {}
    random: dict[str, int] = {}
    consumed: set[str] = set()
    melee_dice: set[str] = set()
    completed_declarations: set[str] = set()
    initial_pools: dict[str, tuple[RangedAttackPool, ...]] = {}
    for event in decisions.event_log.records:
        body = event.payload
        if not isinstance(body, dict):
            continue
        if event.event_type in {"fight_activation_selected", "fight_interrupt_activation_selected"}:
            activation = FightActivationSelection.from_payload(
                cast(FightActivationSelectionPayload, object_payload(body["activation_selection"]))
            )
            if activation.result_id not in records:
                raise GameLifecycleError("Melee commitment activation has no accepted decision.")
            activations[activation.result_id] = activation
        elif event.event_type == "decision_recorded":
            result = object_payload(body["result"])
            result_id = identifier(result, "result_id")
            record = records[result_id]
            if record.request.decision_type != SELECT_MELEE_WEAPON_DECISION_TYPE:
                continue
            request_body = object_payload(record.request.payload)
            activation_id = identifier(request_body, "activation_result_id")
            if activation_id not in activations or activation_id in commitments:
                raise GameLifecycleError("Melee selection is outside its activation commitment.")
            rows_value = request_body["available_weapons"]
            if not isinstance(rows_value, list):
                raise GameLifecycleError("Melee commitment inventory is malformed.")
            rows = tuple(rows_value)
            if activation_id not in inventories:
                _inventory(rows, host)
                inventories[activation_id] = rows
            if rows != inventories[activation_id]:
                raise GameLifecycleError("Melee selection inventory changed during commitment.")
            earlier = selected.setdefault(activation_id, [])
            if len(earlier) >= len(selection_stages(rows)):
                raise GameLifecycleError("Melee selection has an extra stage.")
            expected = selection_request(
                request_id=record.request.request_id,
                activation=activations[activation_id],
                rows=rows,
                index=len(earlier),
                previous=tuple(earlier),
            )
            if expected != record.request:
                raise GameLifecycleError("Melee selection stage or physical options drifted.")
            record.result.validate_for_request(expected)
            earlier.append(record)
            chosen_rows(rows, tuple(earlier))
        elif event.event_type == "dice_rolled":
            roll_id = identifier(body, "roll_id")
            physical[roll_id] = body
            spec_payload = object_payload(body["spec"])
            if identifier(spec_payload, "reason").startswith("Committed melee Attacks for "):
                if roll_id in melee_dice:
                    raise GameLifecycleError("Melee physical dice are duplicated.")
                ready_scopes = {
                    f"random_characteristic.attacks.per_weapon.melee-commitment:{activation_id}:"
                    f"{row['weapon_instance_id']}:{row['weapon_profile_id']}"
                    for activation_id, choices in selected.items()
                    if len(choices) == len(selection_stages(inventories[activation_id]))
                    and activation_id not in commitments
                    for row in chosen_rows(inventories[activation_id], tuple(choices))
                }
                if spec_payload["roll_type"] not in ready_scopes:
                    raise GameLifecycleError(
                        "Melee attack dice preceded complete weapon selection."
                    )
                melee_dice.add(roll_id)
        elif event.event_type == "random_characteristic_rolled":
            key = canonical_json(body)
            random[key] = random.get(key, 0) + 1
        elif event.event_type == MELEE_COMMITMENT_EVENT:
            activation_id = identifier(body, "activation_result_id")
            if activation_id not in selected or activation_id in commitments:
                raise GameLifecycleError("Melee commitment lacks unique accepted weapon choices.")
            activation = activations[activation_id]
            rows, choices = inventories[activation_id], tuple(selected[activation_id])
            if len(choices) != len(selection_stages(rows)):
                raise GameLifecycleError(
                    "Melee dice were generated before all weapons were committed."
                )
            budgets = budgets_from_commitment(body)
            selected_rows = chosen_rows(rows, choices)
            if tuple(budgets) != tuple(row["weapon_instance_id"] for row in selected_rows):
                raise GameLifecycleError("Melee commitment differs from selected physical weapons.")
            for row in selected_rows:
                budget = budgets[identifier(row, "weapon_instance_id")]
                if (
                    budget.model_instance_id != row["model_instance_id"]
                    or budget.wargear_id != row["wargear_id"]
                    or budget.weapon_profile_id != row["weapon_profile_id"]
                    or budget.source_attack_profile != weapon_profile(row).attack_profile
                ):
                    raise GameLifecycleError("Melee budget changed its committed source.")
                roll = budget.roll
                if roll is None:
                    continue
                scope = (
                    f"melee-commitment:{activation_id}:"
                    f"{budget.weapon_instance_id}:{budget.weapon_profile_id}"
                )
                expression = budget.source_attack_profile.dice_expression
                if expression is None:
                    raise GameLifecycleError("Melee dice have no source expression.")
                spec = DiceRollSpec(
                    expression=expression,
                    reason=f"Committed melee Attacks for {budget.weapon_profile_id}",
                    actor_id=activation.player_id,
                    roll_type=f"random_characteristic.attacks.per_weapon.{scope}",
                )
                original = roll.roll_state.original_result
                if (
                    roll.scope_id != scope
                    or original.spec != spec
                    or physical.get(original.roll_id) != original.to_payload()
                    or random.get(canonical_json(roll.to_payload())) != 1
                    or roll.roll_state.rerolls
                    or roll.roll_state.result_override is not None
                    or original.roll_id in consumed
                ):
                    raise GameLifecycleError("Melee budget physical dice evidence drifted.")
                consumed.add(original.roll_id)
            expected_body: dict[str, JsonValue] = {
                "convention_id": MELEE_CONVENTION_ID,
                "activation_result_id": activation_id,
                "activation_request_id": activation.request_id,
                "unit_instance_id": activation.unit_instance_id,
                "player_id": activation.player_id,
                "selection_result_ids": [record.result.result_id for record in choices],
                "weapons": [budget.to_payload() for budget in budgets.values()],
            }
            if body != expected_body:
                raise GameLifecycleError("Melee commitment source context drifted.")
            commitments[activation_id] = body
        elif event.event_type == "melee_declaration_accepted":
            proposal = melee_declaration_proposal_from_payload(body["proposal"])
            activation_id = proposal.source_decision_result_id
            if activation_id not in selected:
                continue
            if activation_id not in commitments or activation_id in completed_declarations:
                raise GameLifecycleError("Melee target declaration lacks its unique commitment.")
            record = records[identifier(body, "result_id")]
            declaration_budgets = validate_declaration_commitment(
                decisions=decisions, request=record.request, proposal=proposal
            )
            if (
                declaration_budgets is None
                or melee_declaration_proposal_from_payload(record.result.payload) != proposal
            ):
                raise GameLifecycleError("Melee accepted declaration drifted.")
            raw_pools = body["attack_pools"]
            if not isinstance(raw_pools, list):
                raise GameLifecycleError("Committed melee declaration requires attack pools.")
            pools = tuple(
                RangedAttackPool.from_payload(cast(RangedAttackPoolPayload, object_payload(raw)))
                for raw in raw_pools
            )
            from warhammer40k_core.engine.melee_pool_authority import validate_committed_pools

            accepted_rows = chosen_rows(inventories[activation_id], tuple(selected[activation_id]))
            request_rows = object_payload(
                object_payload(record.request.payload)["proposal_request"]
            )["available_weapons"]
            if not isinstance(request_rows, list) or {
                identifier(object_payload(row), "weapon_instance_id"): row for row in request_rows
            } != {identifier(row, "weapon_instance_id"): row for row in accepted_rows}:
                raise GameLifecycleError(
                    "Melee declaration inventory differs from committed sources."
                )
            validate_committed_pools(
                proposal=proposal, rows=accepted_rows, budgets=declaration_budgets, pools=pools
            )
            initial_pools[identifier(body, "attack_sequence_id")] = pools
            completed_declarations.add(activation_id)
    if melee_dice != consumed:
        raise GameLifecycleError("Melee attack generation contains orphan physical dice.")
    for activation_id, recorded_choices in selected.items():
        if (
            len(recorded_choices) == len(selection_stages(inventories[activation_id]))
            and activation_id not in commitments
        ):
            raise GameLifecycleError("Complete melee weapon selection lost its attack budget.")
    for request in decisions.queue.pending_requests:
        if request.decision_type == SELECT_MELEE_WEAPON_DECISION_TYPE:
            if request != current_selection_request(host, request.request_id):
                raise GameLifecycleError("Pending melee weapon selection drifted.")
        elif request.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE:
            body = object_payload(request.payload)
            proposal_request = object_payload(body["proposal_request"])
            activation_id = identifier(proposal_request, "source_decision_result_id")
            if body.get(COMMITMENT_KEY) != commitments.get(activation_id):
                raise GameLifecycleError("Pending melee split lost its committed budget.")
    state = host.state
    fight = None if state is None else state.fight_phase_state
    while fight is not None:
        for sequence in (fight.attack_sequence, fight.pending_completed_attack_sequence):
            if sequence is None or sequence.sequence_id not in initial_pools:
                continue
            from warhammer40k_core.engine.shooting_target_replacement_authority import (
                validate_sequence_authority,
            )

            declaration_record = next(
                record
                for record in decisions.records
                if record.request.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE
                and any(
                    event.event_type == "melee_declaration_accepted"
                    and isinstance(event.payload, dict)
                    and event.payload.get("result_id") == record.result.result_id
                    and event.payload.get("attack_sequence_id") == sequence.sequence_id
                    for event in decisions.event_log.records
                )
            )
            validate_sequence_authority(decisions, declaration_record, sequence)
        fight = fight.suspended_state
