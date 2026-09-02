# Core Rules Maintained App-data Mirror Review

This report is generated from the checked-in offline governance audit. It records the two non-affiliated providers that repository-owner policy accepts as maintained direct Warhammer App-data mirrors for Warhammer 40,000 11th Edition Core Rules. Neither provider is presented as owned by, affiliated with, or endorsed by Games Workshop.

Policy: `core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02`.

## Provider registry

| Provider | Reviewed URL | Authority | Runtime input |
|---|---|---|---|
| 40k.app | [40k-app](https://www.40k.app/rules) | project_authoritative_maintained_direct_app_data_mirror | no |
| Game Datamissions | [game-datamissions](https://game-datamissions.com/11th/rules/changelog) | project_authoritative_maintained_direct_app_data_mirror | no |

## Retained governance observations

These provider-level records establish the governance boundary only. They do not substitute for the exact operative rule transcription and source-observation fingerprint required in each implementation PR.

| Observation | Provider | App-data version or timestamp | Transcription SHA-256 | Observation fingerprint |
|---|---|---|---|---|
| `40k-app-core-rules-observed-2026-08-25` | 40k.app | 2026-08-25T00:00:00-04:00 | `c392a03e240536e5fe5ca489c777b596047cd9c0bb9023ff902392dd30c360de` | `ae80bd86900f54bc80f2ab711b80a3dc8b1ba70d1e8764a9a831bb63cc2742a5` |
| `game-datamissions-core-rules-data-931` | Game Datamissions | App-data 931 | `99d400c59b8879a6c0bc6b9324435c677f22af27e0610810fb8fae0d21770d81` | `1c4cdfada35a93ef2773cbed06d9267175edb321423316d5f9dac29dc23b8668` |
| `game-datamissions-core-rules-data-946` | Game Datamissions | App-data 946 | `d5b30faddcf23204073ca566ccb53a0a355ec893382413c542e74738f27296ab` | `d56418ca2a27645d032519c4fe11c97ae5520c50d0cb5b54201e97534a2d3279` |

## Fail-closed comparison rule

Source-package validation groups project-authoritative mirror records by stable rule source ID and App-data version. When two named providers are present for the same group, their transcription hashes must match. A mismatch is rejected and requires an official-App comparison before certification; it is never resolved by provider preference or silent fallback.

The live provider sites are not runtime inputs. Engine loaders consume only reviewed, normalized, hash-pinned source artifacts.
