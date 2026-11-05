# Project documentation

Start with the repository [README](../README.md) for installation, validation and
the battlefield viewer. CORE V2 is still under development; source catalog entries
and component tests do not certify a complete playable roster.

| Need | Maintained reference |
|---|---|
| View a battlefield | [Viewer guide](BATTLEFIELD_VIEWER.md) |
| Understand supported content and limits | [Faction support](FACTION_SUPPORT.md), [mission status](MISSION_IMPLEMENTATION_STATUS.md) |
| Understand engine boundaries | [Architecture](../ARCHITECTURE_V2.md), [contributor rules](../AGENTS.md) |
| Implement an adapter or AI policy | [Decision contract](ADAPTER_DECISION_CONTRACT.md), [external contract](../contracts/README.md) |
| Check current rules interpretations | [Rules semantics](CURRENT_RULES.md), [Core source policy](CORE_RULES_SOURCE_POLICY.md) |
| Check remaining acceptance work | [Core requirements](CORE_RULES_REMEDIATION_ROADMAP.md), [faction requirements](FACTION_RULES_REMEDIATION_ROADMAP.md) |
| Change source content | [Faction source policy](FACTION_RULES_SOURCE_POLICY.md), [source fixture boundaries](SOURCE_FIXTURE_HASH_BOUNDARIES.md) |
| Validate a change | [Test commands](../README.md#test-commands), [review policy](SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md), [performance policy](performance/PERFORMANCE_POLICY.md) |

Keep this tree for current instructions, contracts and support limits. Completed
plans, per-PR delivery reports and bug-fix journals belong in issues and pull
requests. Their earlier versions remain in Git history; do not create another
archive directory. When closing work, update its maintained reference and tests.

Source evidence, generated catalogs, compatibility baselines and regression inputs
have independent consumers and retention rules. This narrative cleanup does not
retire them. Performance history and its finite provenance controls remain pending
a separate cleanup, including the two prose inputs `ORDER_124_SCOPE_PLAN.md` and
`SECTION24_CORE_ABILITIES_SCOPE.md` and the `CI*_SCOPE.md` performance contracts.
The single `contracts/migrations/44.3.33-to-44.4.0.md` input is also retained by
those controls; the other completed migration narratives are in Git history.

The retained audit JSON under `data/source_audits/` remains authoritative for
historical observations. Its validators still consume selected exact Order plans
and the generated Order 84, 94, 95 and 97 reports. These machine inputs remain
until the source/audit cleanup can retire their owning checks together. References
in frozen evidence retain their historical meaning.
