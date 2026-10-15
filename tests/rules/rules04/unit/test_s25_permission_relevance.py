from typing import TYPE_CHECKING, cast

from tests.shared.category_migration.s25_permission_relevance import (
    SHARED_PERMISSION_SOURCE,
    Characteristic,
    Counter,
    DecisionError,
    GameLifecycleError,
    JsonValue,
    LifecycleStatusKind,
    ModifierIgnoreKind,
    ModifierPermissionAttackContext,
    WeaponDeclarationPayload,
    WeaponSelectionContext,
    WeaponSelectionContextPayload,
    assert_checkpoint,
    declared_activated_relevance_ability,
    json,
    modifier_ignore_permissions_for_subject,
    modifier_ignore_sources_for_gathering,
    native_profile_request,
    proposal_from_request,
    pytest,
    replace,
    submit_fixture_request,
    validate_json_value,
    validate_save_gathering_characteristics,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.catalog_modifier_ignore_sources import (
        ModifierIgnoreSourceTemplate,
    )


@pytest.mark.parametrize("player", ["player-a", "player-b"])
@pytest.mark.parametrize(
    "mode",
    [
        "unused-wound",
        "unused-damage-roll",
        "unused-characteristics",
        "duplicate-rapid-fire",
        "unused-wound-one",
        "unused-damage-roll-one",
        "unused-characteristics-one",
        "unused-defender-characteristics",
        "unused-defender-save-with-inv-provider",
        "unused-defender-zero-ap-save-roll",
    ],
)
def test_normal_native_relevant_operations_and_owned_selected_sources(
    player: str, mode: str
) -> None:
    session, request = native_profile_request(player=player, mode="activated-own-" + mode)
    if mode == "unused-defender-save-with-inv-provider":
        # Read the actual already-loaded bundle as native dispatch does; no injection.
        bundle = session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
        registry = bundle.runtime_modifier_registry
        bindings = registry.save_option_modifier_bindings
        assert bindings
        assert all(
            binding.gathering_modified_characteristics == (Characteristic.INVULNERABLE_SAVE,)
            for binding in bindings
        )
    target = "army-beta:scalar" if player == "player-a" else "army-alpha:scalar"
    proposal = proposal_from_request(request=request, target_unit_id=target).to_payload()
    offered = cast(
        dict[str, JsonValue], cast(dict[str, JsonValue], request.payload)["proposal_request"]
    )
    weapons = cast(list[dict[str, JsonValue]], offered["available_weapons"])
    candidates = cast(list[dict[str, JsonValue]], offered["target_candidates"])
    first = proposal["declarations"][0]
    matching = [w for w in weapons if w["weapon_profile_id"] == first["weapon_profile_id"]]
    declarations: list[WeaponDeclarationPayload] = []
    selected_sources: list[dict[str, JsonValue]] = []
    declared_source = declared_activated_relevance_ability(mode).source_id
    for weapon in matching[:2]:
        selected_ids: list[str] = []
        if mode == "duplicate-rapid-fire":
            candidate = next(
                row
                for row in candidates
                if row["weapon_instance_id"] == weapon["weapon_instance_id"]
                and row["target_unit_instance_id"] == target
            )
            context = WeaponSelectionContext.from_payload(
                cast(WeaponSelectionContextPayload, candidate["weapon_ability_selection_context"])
            )
            selections = context.selection_requests(actor_id=player)
            assert len(selections) == 1
            assert len(selections[0].options) == 2
            for selection in selections:
                own = [
                    option
                    for option in selection.options
                    if cast(dict[str, JsonValue], option.payload)["ability_source"]
                    == validate_json_value(
                        next(
                            source.to_payload()
                            for _, sources in context.instance_groups()
                            for source in sources
                            if source.source_id
                            == f"{declared_source}:{declared_source}:clause:grant_weapon_ability"
                        )
                    )
                ]
                assert len(own) == 1
                selected_ids.append(own[0].option_id)
                selected_sources.append(
                    cast(
                        dict[str, JsonValue],
                        cast(dict[str, JsonValue], own[0].payload)["ability_source"],
                    )
                )
        declarations.append(
            {
                **first,
                "attacker_model_instance_id": cast(str, weapon["model_instance_id"]),
                "weapon_instance_id": cast(str, weapon["weapon_instance_id"]),
                "selected_weapon_ability_ids": selected_ids,
            }
        )
    proposal["declarations"] = declarations
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="s25-relevance:declaration",
        payload=validate_json_value(proposal),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    state = session.lifecycle.state
    assert state is not None
    assert state.shooting_phase_state is not None
    sequence = state.shooting_phase_state.attack_sequence
    assert sequence is not None
    group = sequence.current_gathered_group
    assert group is not None
    assert group.pool_indices == (0, 1)
    assert group.total_attacks == 4
    assert len({snapshot.raw_signature_json for snapshot in group.native_snapshots}) == 2
    assert len({snapshot.pool_sha256 for snapshot in group.native_snapshots}) == 2
    assert len({snapshot.source_proof_json for snapshot in group.native_snapshots}) == (
        1 if mode.startswith("unused-defender-") else 2
    )
    assert len({snapshot.rules_json for snapshot in group.native_snapshots}) == 1
    if mode == "unused-defender-zero-ap-save-roll":
        # The native snapshot deliberately exposes only a digest envelope.
        proof = json.loads(group.native_snapshots[0].source_proof_json)
        assert set(proof) == {"source_proof_sha256"}
        bundle = session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
        target_player = "player-b" if player == "player-a" else "player-a"
        pool = sequence.attack_pools[0]
        templates = [
            template.raw_payload
            for candidate_model in pool.target_in_range_model_ids
            for template in modifier_ignore_sources_for_gathering(
                state=state,
                ability_index=bundle.runtime_modifier_registry.modifier_permission_index(
                    target_player
                ),
                unit_instance_id=target,
                kind=ModifierIgnoreKind.SAVE_ROLL,
                model_instance_id=candidate_model,
                attack_context=ModifierPermissionAttackContext(
                    sequence.attacking_unit_instance_id,
                    pool.attacker_model_instance_id,
                    target,
                    "target",
                    sequence.source_phase,
                    pool.weapon_profile,
                    None,
                    None,
                ),
            ).persisted_source_templates
        ]
        assert len(templates) == 2
        captured_effects = {effect.effect_id: effect for effect in state.persisting_effects}
        expected_target_models = set(pool.target_in_range_model_ids[:2])
        for template in templates:
            subject = cast(dict[str, JsonValue], template["subject"])
            source = cast(dict[str, JsonValue], template["source"])
            persisted = cast(dict[str, JsonValue], template["persisting_effect"])
            assert template["kind"] == ModifierIgnoreKind.SAVE_ROLL.value
            assert subject["subject_model_instance_id"] in expected_target_models
            assert source["source_model_instance_id"] == subject["subject_model_instance_id"]
            assert source["role"] == "target"
            assert source["target_kind"] == "this_model"
            assert persisted == validate_json_value(
                captured_effects[cast(str, persisted["effect_id"])].to_payload()
            )
        # Explicit pure owner check: unused grammar is still rejected by the
        # original occurrence API. The native consumer skips its empty inventory.
        first_target_model = cast(
            str, cast(dict[str, JsonValue], templates[0]["subject"])["subject_model_instance_id"]
        )
        with pytest.raises(GameLifecycleError, match="condition kind is unsupported"):
            modifier_ignore_permissions_for_subject(
                state=state,
                ability_index=bundle.runtime_modifier_registry.modifier_permission_index(
                    target_player
                ),
                unit_instance_id=target,
                kind=ModifierIgnoreKind.SAVE_ROLL,
                model_instance_id=first_target_model,
                attack_context=ModifierPermissionAttackContext(
                    sequence.attacking_unit_instance_id,
                    sequence.attack_pools[0].attacker_model_instance_id,
                    target,
                    "target",
                    sequence.source_phase,
                    sequence.attack_pools[0].weapon_profile,
                    None,
                    None,
                ),
            )
    for index in range(4):
        physical = sequence.attack_pools[index // 2]
        current = replace(sequence, attack_index=index).current_pool()
        assert current.attacker_model_instance_id == physical.attacker_model_instance_id
        assert current.weapon_selection_context == physical.weapon_selection_context
        assert current.selected_weapon_ability_ids == physical.selected_weapon_ability_ids
    if selected_sources:
        assert len(selected_sources) == 2
        assert (
            selected_sources[0]["source_instance_id"] != selected_sources[1]["source_instance_id"]
        )
        assert selected_sources[0]["instance_id"] != selected_sources[1]["instance_id"]
        for key in ("source_id", "owner_id", "slot_id", "ability_id"):
            assert selected_sources[0][key] == selected_sources[1][key]
        assert [list(pool.selected_weapon_ability_ids) for pool in sequence.attack_pools] == [
            [cast(str, source["instance_id"])] for source in selected_sources
        ]
    pending = session.advance_until_decision_or_terminal().decision_request
    assert pending is not None
    before = session.to_persistence_payload()
    with pytest.raises(DecisionError, match="finite action space"):
        session.submit_option(
            request_id=pending.request_id,
            option_id="s25-relevance-invalid-option",
            result_id="s25-relevance-invalid",
        )
    assert session.to_persistence_payload() == before
    assert_checkpoint(session)
    for _ in range(100):
        if any(
            event.event_type == "attack_sequence_completed"
            for event in session.lifecycle.decision_controller.event_log.records
        ):
            break
        pending = session.advance_until_decision_or_terminal().decision_request
        assert pending is not None
        submit_fixture_request(session, pending)
    else:
        raise AssertionError("S25 native relevance/grant control did not complete.")
    assert_checkpoint(session)
    records = session.lifecycle.decision_controller.records
    assert not any(record.request.decision_type == "select_modifier_ignores" for record in records)
    events = session.lifecycle.decision_controller.event_log.records
    activations = [
        event.payload
        for event in events
        if event.event_type == "catalog_any_phase_once_per_battle_ability_activated"
        and isinstance(event.payload, dict)
    ]
    assert len(activations) == (1 if mode.endswith("-one") else 2)
    expected_models = (
        set(sequence.attack_pools[0].target_in_range_model_ids[:2])
        if mode.startswith("unused-defender-")
        else {
            row["attacker_model_instance_id"]
            for row in proposal["declarations"][: 1 if mode.endswith("-one") else 2]
        }
    )
    assert {cast(str, row["source_model_instance_id"]) for row in activations} == expected_models
    stages: dict[str, list[int]] = {"hit": [], "wound": []}
    for index, event in enumerate(events):
        if event.event_type == "dice_rolled" and isinstance(event.payload, dict):
            spec = cast(dict[str, JsonValue], event.payload["spec"])
            for name in stages:
                if spec.get("roll_type") == "attack_sequence." + name:
                    stages[name].append(index)
    assert len(stages["hit"]) == 4
    assert stages["wound"]
    assert max(stages["hit"]) < min(stages["wound"])


__all__: list[str] = []
__all__ += ["SHARED_PERMISSION_SOURCE", "Counter", "ModifierIgnoreSourceTemplate"]
__all__ += ["validate_save_gathering_characteristics"]
