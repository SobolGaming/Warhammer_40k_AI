"""Deterministic identifier-only variant of the canonical native config fixture."""

from warhammer40k_core.engine.event_log import JsonValue


def ordinal_identity_config_payload(
    payload: JsonValue, *, player_a_id: str | None = None, game_id: str | None = None
) -> dict[str, JsonValue]:
    assert isinstance(payload, dict)
    armies = payload["army_muster_requests"]
    assert isinstance(armies, list)
    replacements: dict[str, str] = {}
    if player_a_id is not None:
        replacements["player-a"] = player_a_id
    selections_seen: set[str] = set()
    for army in armies:
        assert isinstance(army, dict)
        army_id = army["army_id"]
        selections = army["unit_selections"]
        assert isinstance(army_id, str)
        assert isinstance(selections, list)
        for selection in selections:
            assert isinstance(selection, dict)
            selection_id = selection["unit_selection_id"]
            assert isinstance(selection_id, str)
            if selection_id not in selections_seen:
                selections_seen.add(selection_id)
                replacements[selection_id] = f"configured-unit:event-{len(selections_seen):06d}"
            chosen = replacements[selection_id]
            replacements[f"{army_id}:{selection_id}"] = f"{army_id}:{chosen}"

    def rename(value: JsonValue) -> JsonValue:
        if isinstance(value, dict):
            return {replacements.get(key, key): rename(item) for key, item in value.items()}
        if isinstance(value, list):
            return [rename(item) for item in value]
        return replacements.get(value, value) if isinstance(value, str) else value

    result = rename(payload)
    assert isinstance(result, dict)
    if game_id is not None:
        result["game_id"] = game_id
    return result
