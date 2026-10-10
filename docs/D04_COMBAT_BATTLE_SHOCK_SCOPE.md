# D04 local Combat Disembark correction

Scope is authoritative Battle-shock for native Combat Disembark against base
`7a2da43900757b57ced6b11db4a6e011b7f1297d`, tree
`1bbf86fd3428cff14ed94b2ca978f62807c38358`. Human approval on October 9 at
21:00 UTC selected the bounded corrections; only D04 is implemented here.
Remote publication, merge, main CI monitoring, D06/D07/D09/D10 and Emergency
Disembark status integration are outside this checkout's authorization.

The selected acceptance is retained in the authenticated local preflight packet
`d04-evidence-01/D04-small-separate-correction-scope-04.md`, SHA256
`55f7d63c38305fca27bed22a801c4d6195be138dbbb917b5ed3af514cf3ae936`.
The full baseline's 5,819 Git blobs and the retained 72-file reproduction packet
were independently authenticated. Original PR576 and source5 checkout remain
read-only historical inputs. The earlier paused model-policy receipt remains
unchanged: parent supplied the subsequent human Sol-6.1 High / 1.5-speed direction
and explicit accepted creation settings `gpt-6.1-sol`, `high`, `fast`.
This records requested settings, without claiming independent runtime attestation.

## Literal source and authority

| Frozen complete source | Required behavior | SHA256 |
|---|---|---|
| `rule:18:18.04:1`, block23 | Combat passenger becomes Battle-shocked; charge prohibition lasts through end of turn. | `ed5ace0412d4f87e7f436e64eb56f5081325cbc6b3c0a1dda347562c890144b9` |
| `rule:01:01.07:1`, blocks4–7 | Shared OC, controlling-player Stratagem target and Action start/completion restrictions, with admitted explicit permissions. | `a9f7dceb2ac5c8765ff56fce941d0d7686d332c5f32909b62f119c94bc0c4e5e` |
| `rule:08:08.03:1`, blocks1–4 | Previously shocked units test in their own ordinary Command step even above half; ordinary success clears status. | `a4cf92589862882bc5f598df82d8f95264d139bb19c21b429449f0240b436aa1` |

The former result marker did not populate authoritative shock state. Shared
consumers consequently saw an unshocked surviving passenger; restore and replay
preserved that defect. `combat_disembark_battle_shock` now routes accepted Combat
setup plus completed hazard to `apply_direct_battle_shock_state`. Grouped movement
hazard emission and scalar native placement/continuation call the same owner.
Scalar placement completes shock after the pending-hazard return; lifecycle
continuation completes Combat shock before phase advancement or parent resumption.
Generic damage/FNP services retain their accepted-history-independent contracts.
The scalar lifecycle branch excludes Emergency. No Emergency status integration
is included.

Direct status carries accepted request/result, source rule and exact setup/hazard
event identities. Shared historical reconstruction authenticates accepted proposal,
physical surviving inventory and canonical owner before recreating the status.
No Leadership roll, Battle-shock test result or test-outcome trigger is invented.
Pending hazard leaves status unapplied. Completion applies once to a survivor;
existing status remains unique and destroyed cargo gains no survivor status.
Existing direct-state Action interruption and permission handling remain shared.

Charge expiry remains the current turn boundary. Combat's marker becomes
`until_cleared`; shared Command selection, failure retention and ordinary-success
clearing control the authoritative lifetime. Three directly affected current
assertions are inventoried in `data/source_audits/d04/assertion-exceptions.json`,
with the complete baseline test file preserved byte-for-byte. Every other
original assertion and fixture remains intact. The complete current audit retains
its fourteen historical changed links and separately authenticates the single
new selected source link. Original selected sources, archives and ceilings stay
unchanged.

Contract44.3.26 documents the direct causal event and corrected lifetime under
existing proposal/event/viewer envelopes. Earlier runtime histories require their
original runtime; no compatibility shim is added.

## Evidence and remaining gates

Development controls use public pregame/deployment and placement submissions from
the retained analytical Core cargo/HILLS recipe. Native survivor, unshocked ground
Tactical, malformed-source atomic retry and both ordinary Command pass/fail paths
have passed. Relevant checkpoints compare JSON restore, forks, all viewer roles,
events and exact source-bound replay. Runtime pass is established by current
receipts separately from the static source inventory.

Native target binding, per-model/normal objective consumers, pending hazard
continuation, canonical attached survivor and ten-model all-killed controls have
passed bounded current runs. All-killed uses a predeclared deterministic submitted
result identity; actual engine RNG rolls, not a detached forecast, establish the
control. Shared-owner idempotence is tested against native attached shocked state;
no second native Combat decision is claimed. No actual native illegal CP spend, Action start/completion or
scoring delta is claimed. Exact unavailable prerequisites and existing legitimate
shared-consumer controls must remain explicit. No faction grant or provider
certification follows from analytical cargo/body inputs.

Parent confirmed both audit reviewers heavy-idle and allows announced quiet
source/smoke validation once stable. Full behavior remains held pending original
isolated16 authentication and explicit parent release. Required type,
contract/client/wheel, shard inventory, performance assessment/smoke and complete
current gates remain pending until executed on stable inputs. Parent arranges
independent coding/rules reviews on frozen HEAD/TREE/BASE, full source,
acceptance, policy and canonical archive; later changes need exact-final renewals.
Apply `docs/SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md`: block on incorrect rules,
normal legal-play and engine-generated valid-state save/load/replay failures and
explicitly required supported input boundaries. Coordinated edited-history
hardening remains separate. This local task does not establish PFINAL closure.

At the native Combat checkpoint, no Action-start or selected-to-fight request is
advertised. An actual Action execution would require an active mission/card Action
at its legal start timing; Epic Challenge would require a genuine Fight selection
and window. Those execution prerequisites are not supplied by this control.
The objective resolver has actual in-range passenger contributors with effective
OC zero; the carrier also contributes, so no scoring delta is inferred. Existing
legitimate shared Action start/interruption/permission, Stratagem suppression/
pre-spend guards and attached OC controls are rerun separately. Direct owner
idempotence retains the actual accepted source result and leaves all events and
state unchanged. These qualifications preserve the supported consumer boundary.
