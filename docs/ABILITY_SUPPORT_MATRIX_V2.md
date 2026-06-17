# Ability Support Matrix V2

This matrix summarizes the category-first support artifact in
`data/generated/ability_coverage/ability_support_category_rows.json`.
The raw per-ability rows remain available in
`data/generated/ability_coverage/ability_coverage_rows.json`.

Support stages:

- `descriptor_only`: catalog descriptor exists, but no structured executable IR is available.
- `ir_compiled_unsupported`: rule text compiled to IR with preserved diagnostics, but the IR is not supported.
- `generic_ir_executable`: rule text compiled to supported generic IR and can execute through the generic IR handler.
- `engine_consumed`: a structured descriptor or supported generic IR is consumed by a phase/query host through a named runtime consumer.

Current coverage categories:

| Category | Support status | Runtime consumers | Abilities | Datasheets | Semantic category |
| --- | --- | --- | --- | --- | --- |
| Charge Roll Modifier | `engine_consumed` | `catalog-ir:charge-roll-modifier` | Instrument of Chaos | Bloodcrushers, Bloodletters | `wargear.roll_modifier.charge.this_unit` |
| Datasheet Descriptor | `descriptor_only` | None | Bane of Cowards, Brass Stampede | Bloodcrushers, Bloodletters | `datasheet.descriptor` |
| Deep Strike Reserve Arrival | `engine_consumed` | `descriptor:movement:deep-strike-placement`, `descriptor:reserve-declaration:deep-strike` | Deep Strike | Bloodcrushers, Bloodletters | `core.reserve.deep_strike` |
| Faction Descriptor | `descriptor_only` | None | The Shadow of Chaos | Bloodcrushers, Bloodletters | `faction.descriptor` |
| Leadership Characteristic | `engine_consumed` | `catalog-ir:leadership-characteristic-query` | Daemonic Icon | Bloodcrushers, Bloodletters | `wargear.characteristic_set.leadership.this_unit` |
