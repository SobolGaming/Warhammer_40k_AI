from __future__ import annotations

import importlib
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType, ModuleType
from typing import Self, cast

from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.faction_content.bundle import (
    DEFAULT_RUNTIME_CONTENT_CONTRIBUTION_ID,
    RuntimeContentContribution,
)
from warhammer40k_core.engine.faction_content.manifest import (
    RuntimeContentManifest,
    RuntimeContentModuleFamily,
)
from warhammer40k_core.engine.phase import GameLifecycleError


@dataclass(frozen=True, slots=True)
class RuntimeContentModuleRef:
    family: RuntimeContentModuleFamily
    content_id: str
    module_path: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "family",
            _module_family_from_token(self.family),
        )
        object.__setattr__(
            self,
            "content_id",
            _validate_identifier("content_id", self.content_id),
        )
        object.__setattr__(
            self,
            "module_path",
            _validate_module_path("module_path", self.module_path),
        )


@dataclass(frozen=True, slots=True)
class RuntimeContentModuleIndex:
    faction_modules: Mapping[str, str]
    detachment_modules: Mapping[str, str]
    enhancement_modules: Mapping[str, str]
    stratagem_modules: Mapping[str, str]
    datasheet_modules: Mapping[str, str]
    wargear_modules: Mapping[str, str]
    weapon_profile_modules: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "faction_modules",
            _validate_module_mapping("faction_modules", self.faction_modules),
        )
        object.__setattr__(
            self,
            "detachment_modules",
            _validate_module_mapping("detachment_modules", self.detachment_modules),
        )
        object.__setattr__(
            self,
            "enhancement_modules",
            _validate_module_mapping("enhancement_modules", self.enhancement_modules),
        )
        object.__setattr__(
            self,
            "stratagem_modules",
            _validate_module_mapping("stratagem_modules", self.stratagem_modules),
        )
        object.__setattr__(
            self,
            "datasheet_modules",
            _validate_module_mapping("datasheet_modules", self.datasheet_modules),
        )
        object.__setattr__(
            self,
            "wargear_modules",
            _validate_module_mapping("wargear_modules", self.wargear_modules),
        )
        object.__setattr__(
            self,
            "weapon_profile_modules",
            _validate_module_mapping("weapon_profile_modules", self.weapon_profile_modules),
        )

    @classmethod
    def empty(cls) -> Self:
        return cls(
            faction_modules={},
            detachment_modules={},
            enhancement_modules={},
            stratagem_modules={},
            datasheet_modules={},
            wargear_modules={},
            weapon_profile_modules={},
        )

    def refs_for_activation(
        self,
        activation: RuntimeContentActivation,
    ) -> tuple[RuntimeContentModuleRef, ...]:
        if type(activation) is not RuntimeContentActivation:
            raise GameLifecycleError("Runtime content module lookup requires activation.")
        refs = (
            *_refs_for_ids(
                family=RuntimeContentModuleFamily.FACTION,
                values=activation.selected_faction_ids,
                mapping=self.faction_modules,
            ),
            *_refs_for_ids(
                family=RuntimeContentModuleFamily.DETACHMENT,
                values=activation.selected_detachment_ids,
                mapping=self.detachment_modules,
            ),
            *_refs_for_ids(
                family=RuntimeContentModuleFamily.ENHANCEMENT,
                values=activation.selected_enhancement_ids,
                mapping=self.enhancement_modules,
            ),
            *_refs_for_ids(
                family=RuntimeContentModuleFamily.STRATAGEM,
                values=activation.selected_stratagem_ids,
                mapping=self.stratagem_modules,
            ),
            *_refs_for_ids(
                family=RuntimeContentModuleFamily.DATASHEET,
                values=activation.selected_datasheet_ids,
                mapping=self.datasheet_modules,
            ),
            *_optional_refs_for_ids(
                family=RuntimeContentModuleFamily.WARGEAR,
                values=activation.selected_wargear_ids,
                mapping=self.wargear_modules,
            ),
            *_optional_refs_for_ids(
                family=RuntimeContentModuleFamily.WEAPON_PROFILE,
                values=activation.selected_weapon_profile_ids,
                mapping=self.weapon_profile_modules,
            ),
        )
        return tuple(
            sorted(refs, key=lambda ref: (ref.module_path, ref.family.value, ref.content_id))
        )

    def module_paths_for_activation(self, activation: RuntimeContentActivation) -> tuple[str, ...]:
        return tuple(sorted({ref.module_path for ref in self.refs_for_activation(activation)}))


def load_runtime_content_contributions(
    *,
    activation: RuntimeContentActivation,
    manifest: RuntimeContentManifest,
) -> tuple[RuntimeContentContribution, ...]:
    if type(activation) is not RuntimeContentActivation:
        raise GameLifecycleError("Runtime content loading requires activation.")
    if type(manifest) is not RuntimeContentManifest:
        raise GameLifecycleError("Runtime content loading requires a manifest.")
    _validate_resolved_activation_matches_manifest(activation=activation, manifest=manifest)
    contributions: list[RuntimeContentContribution] = []
    for module_path in activation.selected_module_paths:
        module = importlib.import_module(module_path)
        contribution = _runtime_contribution_from_module(module)
        contributions.append(contribution)
    return tuple(contributions)


def _runtime_contribution_from_module(module: ModuleType) -> RuntimeContentContribution:
    if type(module) is not ModuleType:
        raise GameLifecycleError("Runtime content loader requires a Python module.")
    if "runtime_contribution" not in module.__dict__:
        raise GameLifecycleError("Runtime content module must expose runtime_contribution().")
    factory = module.__dict__["runtime_contribution"]
    if not callable(factory):
        raise GameLifecycleError("Runtime content module runtime_contribution must be callable.")
    contribution = factory()
    if type(contribution) is not RuntimeContentContribution:
        raise GameLifecycleError(
            "Runtime content module returned invalid RuntimeContentContribution."
        )
    if contribution.contribution_id == DEFAULT_RUNTIME_CONTENT_CONTRIBUTION_ID:
        contribution = contribution.with_contribution_id(module.__name__)
    return contribution


def _validate_resolved_activation_matches_manifest(
    *,
    activation: RuntimeContentActivation,
    manifest: RuntimeContentManifest,
) -> None:
    if not activation.activation_hash:
        raise GameLifecycleError("Runtime content loading requires resolved activation.")
    expected = manifest.resolve_activation(
        RuntimeContentActivation(
            selected_faction_ids=activation.selected_faction_ids,
            selected_detachment_ids=activation.selected_detachment_ids,
            selected_enhancement_ids=activation.selected_enhancement_ids,
            selected_stratagem_ids=activation.selected_stratagem_ids,
            selected_datasheet_ids=activation.selected_datasheet_ids,
            selected_wargear_ids=activation.selected_wargear_ids,
            selected_weapon_profile_ids=activation.selected_weapon_profile_ids,
            selected_weapon_keywords=activation.selected_weapon_keywords,
            loaded_unit_instance_ids=activation.loaded_unit_instance_ids,
        ),
        fail_on_required_unsupported=False,
    )
    if activation != expected:
        raise GameLifecycleError(
            "Runtime content loading activation does not match manifest closure."
        )


def _refs_for_ids(
    *,
    family: RuntimeContentModuleFamily,
    values: tuple[str, ...],
    mapping: Mapping[str, str],
) -> tuple[RuntimeContentModuleRef, ...]:
    refs: list[RuntimeContentModuleRef] = []
    for content_id in values:
        module_path = mapping.get(content_id)
        if module_path is None:
            raise GameLifecycleError("Runtime content module index is missing selected support.")
        refs.append(
            RuntimeContentModuleRef(
                family=family,
                content_id=content_id,
                module_path=module_path,
            )
        )
    return tuple(refs)


def _optional_refs_for_ids(
    *,
    family: RuntimeContentModuleFamily,
    values: tuple[str, ...],
    mapping: Mapping[str, str],
) -> tuple[RuntimeContentModuleRef, ...]:
    refs: list[RuntimeContentModuleRef] = []
    for content_id in values:
        module_path = mapping.get(content_id)
        if module_path is None:
            continue
        refs.append(
            RuntimeContentModuleRef(
                family=family,
                content_id=content_id,
                module_path=module_path,
            )
        )
    return tuple(refs)


def _validate_module_mapping(field_name: str, value: object) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError(f"Runtime content {field_name} must be a mapping.")
    validated: dict[str, str] = {}
    for raw_content_id, raw_module_path in cast(Mapping[object, object], value).items():
        content_id = _validate_identifier("content_id", raw_content_id)
        module_path = _validate_module_path("module_path", raw_module_path)
        if content_id in validated:
            raise GameLifecycleError(f"Runtime content {field_name} must not duplicate IDs.")
        validated[content_id] = module_path
    return MappingProxyType(dict(sorted(validated.items())))


def _module_family_from_token(token: object) -> RuntimeContentModuleFamily:
    if type(token) is RuntimeContentModuleFamily:
        return token
    if type(token) is not str:
        raise GameLifecycleError("RuntimeContentModuleFamily token must be a string.")
    try:
        return RuntimeContentModuleFamily(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported RuntimeContentModuleFamily token: {token}.") from exc


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Runtime content {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Runtime content {field_name} must not be empty.")
    return stripped


def _validate_module_path(field_name: str, value: object) -> str:
    module_path = _validate_identifier(field_name, value)
    if module_path.startswith(".") or module_path.endswith(".") or ".." in module_path:
        raise GameLifecycleError("Runtime content module path must be absolute and normalized.")
    return module_path
