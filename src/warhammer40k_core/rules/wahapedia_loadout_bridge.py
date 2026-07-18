from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

LOADOUT_CLAUSE_RE = re.compile(
    r"(?P<subjects>[^.]+?) (?:is|are) equipped with: (?P<items>[^.]+)\.?",
    re.IGNORECASE,
)
LOADOUT_ITEM_COUNT_RE = re.compile(r"^(?P<count>\d+)\s+(?P<name>.+)$")


@dataclass(frozen=True, slots=True)
class LoadoutAssignments:
    profile_ids_by_wargear_name: dict[str, tuple[str, ...]]
    wargear_count_by_name_and_profile_id: dict[tuple[str, str], int]

    def wargear_name_keys(self) -> frozenset[str]:
        return frozenset(self.profile_ids_by_wargear_name)

    def profile_ids_for(self, wargear_name: str) -> tuple[str, ...]:
        key = _name_key(wargear_name)
        profile_ids = self.profile_ids_by_wargear_name.get(key)
        if profile_ids is None and f"{key}s" in self.profile_ids_by_wargear_name:
            profile_ids = self.profile_ids_by_wargear_name[f"{key}s"]
        return () if profile_ids is None else profile_ids

    def count_for(self, wargear_name: str, *, model_profile_id: str) -> int:
        key = _name_key(wargear_name)
        count = self.wargear_count_by_name_and_profile_id.get((key, model_profile_id))
        if count is None:
            count = self.wargear_count_by_name_and_profile_id.get((f"{key}s", model_profile_id))
        if count is None and key.endswith("s"):
            count = self.wargear_count_by_name_and_profile_id.get((key[:-1], model_profile_id))
        return 0 if count is None else count


def uniform_loadout_wargear_count(
    *,
    loadout_assignments: LoadoutAssignments | None,
    wargear_name: str,
    model_profile_ids: tuple[str, ...],
    error_type: type[ValueError],
) -> int:
    if loadout_assignments is None:
        return 1
    counts = {
        loadout_assignments.count_for(wargear_name, model_profile_id=model_profile_id)
        for model_profile_id in model_profile_ids
    }
    if len(counts) != 1 or 0 in counts:
        raise error_type(
            "Default wargear count must be positive and identical across assigned profiles."
        )
    return next(iter(counts))


def parse_loadout_assignments(
    *,
    loadout: str,
    model_profile_by_name: dict[str, str],
    all_model_profile_ids: tuple[str, ...],
    error_type: type[ValueError],
) -> LoadoutAssignments | None:
    stripped = " ".join(loadout.strip().split())
    if not stripped:
        return None
    matches = tuple(LOADOUT_CLAUSE_RE.finditer(stripped))
    if not matches or "".join(match.group(0) for match in matches) != stripped:
        raise error_type("Unsupported datasheet loadout row shape.")
    profile_ids_by_wargear_name: dict[str, set[str]] = {}
    wargear_count_by_name_and_profile_id: dict[tuple[str, str], int] = {}
    nothing_seen = False
    for match in matches:
        profile_ids = _profile_ids_for_subjects(
            subjects=match.group("subjects"),
            model_profile_by_name=model_profile_by_name,
            all_model_profile_ids=all_model_profile_ids,
            error_type=error_type,
        )
        for item in match.group("items").split(";"):
            wargear_name, count = _loadout_wargear_name(item, error_type=error_type)
            key = _name_key(wargear_name)
            if key == _name_key("nothing"):
                nothing_seen = True
                continue
            profile_ids_by_wargear_name.setdefault(key, set()).update(profile_ids)
            for profile_id in profile_ids:
                count_key = (key, profile_id)
                if count_key in wargear_count_by_name_and_profile_id:
                    raise error_type(
                        "Datasheet loadout assigns the same wargear more than once to a profile."
                    )
                wargear_count_by_name_and_profile_id[count_key] = count
    if nothing_seen and profile_ids_by_wargear_name:
        raise error_type("Datasheet loadout mixes nothing with model wargear.")
    if nothing_seen:
        return LoadoutAssignments(
            profile_ids_by_wargear_name={},
            wargear_count_by_name_and_profile_id={},
        )
    if not profile_ids_by_wargear_name:
        raise error_type("Datasheet loadout contains no wargear items.")
    return LoadoutAssignments(
        profile_ids_by_wargear_name={
            key: tuple(sorted(profile_ids))
            for key, profile_ids in sorted(profile_ids_by_wargear_name.items())
        },
        wargear_count_by_name_and_profile_id=dict(
            sorted(wargear_count_by_name_and_profile_id.items())
        ),
    )


def _profile_ids_for_subjects(
    *,
    subjects: str,
    model_profile_by_name: dict[str, str],
    all_model_profile_ids: tuple[str, ...],
    error_type: type[ValueError],
) -> tuple[str, ...]:
    normalized = " ".join(subjects.strip().split())
    if len(all_model_profile_ids) == 1:
        return all_model_profile_ids
    if normalized.casefold() in {"every model", "every model in this unit"}:
        return all_model_profile_ids
    for article in ("Every ", "The ", "An ", "A "):
        if normalized.casefold().startswith(article.casefold()):
            normalized = normalized[len(article) :]
            break
    profile_ids: list[str] = []
    for model_name in normalized.split(" and "):
        key = _name_key(model_name)
        profile_id = model_profile_by_name.get(key)
        if profile_id is None and key.endswith("s"):
            profile_id = model_profile_by_name.get(key[:-1])
        if profile_id is None:
            raise error_type(
                f"Datasheet loadout references an unknown model profile: {model_name}."
            )
        profile_ids.append(profile_id)
    if not profile_ids:
        raise error_type("Datasheet loadout contains no model subjects.")
    return tuple(dict.fromkeys(profile_ids))


def _loadout_wargear_name(item_name: str, *, error_type: type[ValueError]) -> tuple[str, int]:
    stripped = item_name.strip()
    if not stripped:
        raise error_type("Datasheet loadout contains an empty wargear item.")
    match = LOADOUT_ITEM_COUNT_RE.fullmatch(stripped)
    if match is None:
        return stripped, 1
    count = int(match.group("count"))
    if count < 1:
        raise error_type("Datasheet loadout wargear count must be positive.")
    name = match.group("name").strip()
    if not name:
        raise error_type("Datasheet loadout contains an empty counted wargear item.")
    return name, count


def _name_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    lowered = normalized.casefold().replace("'", "").replace("&", " and ")
    return "-".join(part for part in re.split(r"[^a-z0-9]+", lowered) if part)
