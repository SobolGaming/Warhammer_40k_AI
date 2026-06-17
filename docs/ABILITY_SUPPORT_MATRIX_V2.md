# Ability Support Matrix V2

This matrix summarizes the current structured ability coverage artifact in
`data/generated/ability_coverage/ability_coverage_rows.json`.

Support stages:

- `descriptor_only`: catalog descriptor exists, but no structured executable IR is available.
- `ir_compiled_unsupported`: rule text compiled to IR with preserved diagnostics, but the IR is not supported.
- `generic_ir_executable`: rule text compiled to supported generic IR and can execute through the generic IR handler.
- `engine_consumed`: supported generic IR is consumed by a phase/query host through a named runtime consumer.

Current coverage slice:

| Datasheet | Ability | Source | Semantic category | Support stage | Runtime consumer |
| --- | --- | --- | --- | --- | --- |
| Bloodcrushers | Deep Strike | core | `core.descriptor` | `descriptor_only` |  |
| Bloodcrushers | Brass Stampede | datasheet | `datasheet.descriptor` | `descriptor_only` |  |
| Bloodcrushers | The Shadow of Chaos | faction | `faction.descriptor` | `descriptor_only` |  |
| Bloodcrushers | Daemonic Icon | wargear | `wargear.characteristic_set.leadership.this_unit` | `engine_consumed` | `catalog-ir:leadership-characteristic-query` |
| Bloodcrushers | Instrument of Chaos | wargear | `wargear.roll_modifier.charge.this_unit` | `engine_consumed` | `catalog-ir:charge-roll-modifier` |
