from __future__ import annotations

from warhammer40k_core.engine.faction_content.loader import RuntimeContentModuleIndex

_BASE = "warhammer40k_core.engine.faction_content.warhammer_40000_11th"
_EMPTY = f"{_BASE}.common.empty"


def runtime_content_module_index() -> RuntimeContentModuleIndex:
    return RuntimeContentModuleIndex(
        faction_modules={
            "core-marine-force": _EMPTY,
            "death-guard": f"{_BASE}.death_guard.manifest",
        },
        detachment_modules={
            "core-combined-arms": _EMPTY,
            "flyblown-host": f"{_BASE}.death_guard.detachments.flyblown_host.manifest",
            "tallyband-summoners": (
                f"{_BASE}.death_guard.detachments.tallyband_summoners.manifest"
            ),
        },
        enhancement_modules={},
        stratagem_modules={},
        datasheet_modules={
            "core-boyz-like-infantry": _EMPTY,
            "core-character-leader": _EMPTY,
            "core-character-support": _EMPTY,
            "core-deep-strike-unit": _EMPTY,
            "core-intercessor-like-infantry": _EMPTY,
            "core-transport": _EMPTY,
            "core-vehicle-monster": _EMPTY,
            "plague-marines": f"{_BASE}.death_guard.units.plague_marines",
            "typhus": f"{_BASE}.death_guard.units.typhus",
        },
        wargear_modules={
            "core-bolt-rifle": _EMPTY,
            "core-drop-carbine": _EMPTY,
            "core-heavy-cannon": _EMPTY,
            "core-leader-blade": _EMPTY,
            "core-mob-shoota": _EMPTY,
            "core-transport-array": _EMPTY,
            "plague-weapons": f"{_BASE}.death_guard.wargear.plague_weapons",
        },
        weapon_profile_modules={
            "core-bolt-rifle:standard": _EMPTY,
            "core-drop-carbine:standard": _EMPTY,
            "core-heavy-cannon:standard": _EMPTY,
            "core-leader-blade:standard": _EMPTY,
            "core-mob-shoota:standard": _EMPTY,
            "core-transport-array:standard": _EMPTY,
        },
    )
