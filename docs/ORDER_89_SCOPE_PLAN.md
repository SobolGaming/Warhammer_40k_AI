# Order 89 / P02H — healing selection and scope

Violated invariant: Core 02.02.04 applies to any unit with wounded models, and
ordinary unit healing may revive only non-Character models. A model-specific
heal must affect only its selected/source model and discard excess wounds.
Player choices remain finite engine decisions with source-correct ownership.

## Source authority

The September 26 retrieval of the GDM page asset retained by Order 84 has SHA-256
`6f4d27c5670489e9b6310bb8f43e837d8abaf2d5f7a8c8938f56690190edad0e`.
Core row `rule:02:02.02.04:1` retains fingerprint
`895eda0b8b573435e6765051b85b6a99e10344e7312cde45de5822b87ad5a375`.
All five blocks were reviewed. Only formatting control characters were removed
from the transcription. `gw-11e-core-modifiers:healing` registers that Datasheet
Wounds clause in the existing characteristic source package, preserving all prior
observation tuples and official historical PDF provenance. The exact timestamp,
transcription hash and provider tuple are committed in the source audit.
`uv run python tools/build_core_modifiers_source.py --check` reproduces it offline.
GDM is a project-authoritative maintained App-data mirror under the existing
policy, not GW-owned or a newly verified official App build. No co-versioned
agreement or replacement of the historical negative audit is claimed.

Core unit healing restores one wound at a time, prioritizing living wounded
models, then reviving a destroyed non-Character with one wound. A living Character
can heal. A model heal cannot spill into another model or revive a casualty.
The controlling player resolves ordinary choices; source-assigned
`selection_actor_player_id` remains explicit and takes precedence. Revival
placement remains owned by the receiving unit's player.

## Ownership and bug-class audit

`healing` owns candidates, finite requests and wound mutation. `healing_source_context`
validates source scope and resolves the selected/source-model lock. It no longer
uses attachment markers, source-ID prefixes or normalized keyword strings to
allow multiple wounded models. Character exclusion reads canonical model tokens,
so an attached Character does not exclude its bodyguards. Explicit revival uses
the existing `revive_destroyed_models_only` authority and source candidate filter;
it can return Characters where that source permits them. Full-health revival
requires that explicit scope. Contradictory scopes, malformed flags (including flags shadowed by a model lock),
and foreign model IDs fail closed.

The producer sweep covered every `HealingEffect` constructor:

| Producer | Required scope and selection |
|---|---|
| Core and Necrons Reanimation | Ordinary unit healing; controlling player or explicit source actor |
| Catalog Command restoration | Explicit full-health return or one selected wounded model; owner |
| Generic Stratagem restoration/return | Existing model lock or explicit revival flags; source actor with owner as the Core default |
| Catalog destroyed-enemy model restoration | Bind the actual source model, canonicalize its attached rules unit; discard excess |
| Catalog failed Battle-shock Aura healing | Bind the retained RuleIR source model, never another wounded model |
| Daemonic Manifestation | Non-Battleline: one owner-selected wounded model, discarding excess. Battleline: existing source-filtered optional full-health return |

The sweep found and removed additional multiple-wounded rejection in the catalog
model-healing query and Manifestation. The frozen catalog and faction modules
extract the affected sub-effects into small modules before extension. No new
named handler or hook is registered: Manifestation remains the existing approved
army orchestrator, delegating reusable healing to the shared owner. Its loaded
pending-source validator reconstructs source eligibility, Battle-shock provenance,
D3 and wounded candidates before allowing a model choice. Pending Core healing
restore rebuilds the exact engine request, including actor and options.

Off-battlefield return wounds/equipment/capacity remain Order 90. This PR does not
claim that existing embarked full-health or non-cargo reserve revival is repaired.

## Adapter, replay and acceptance

The existing finite and parameterized decision families remain. Model-specific
sources can bind `source_context.healing_model_instance_id`; the context is an
engine-authored opaque JSON value in the existing contract. No schema/envelope
change or compatibility shim is needed. Exact engine-build identity prevents old
histories from being loaded under changed semantics. The adapter contract records
the corrected default actor, model restriction and explicit revival distinction.

Regressions cover ordinary and attached multiple wounds, owner and source-assigned
opponent choices, wounded/full/destroyed model targets, Character-only and mixed
casualties, explicit Character revival to full health, non-Character revival to one
wound, model locks and excess loss, invalid scope and foreign identity, forged
pending actors/options, both viewers, JSON persistence and exact replay. Damage
preconditions in the new facade fixtures use real model-directed mortal-wound
allocation and recorded destruction. The loaded Manifestation consumer and existing
catalog/Stratagem/Command/Necrons suites cover producer integration. The failed
Battle-shock Aura consumer specifically exercises wounded, full and destroyed
source models alongside another wounded model and a casualty, with a fixed
excess-wound roll and no generated choice. Static audits
protect shared mutation, canonical tokens and removal of the rejection bug class.

Performance and aggregate validation are recorded in
[the validation record](performance/order89/README.md). Core Rules and complete-game
performance certification remain outstanding under their separate roadmaps.
