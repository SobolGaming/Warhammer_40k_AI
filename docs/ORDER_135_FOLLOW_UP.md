# Order135 / PR576 follow-up inventory

The owner cut off further exploratory expansion on 8 October 2026. This PR finishes the already approved repairs and their directly affected regressions and trust boundaries. All required gates still apply. No successor implementation order is selected.

The immutable original 35-item auditor queue and exact source/owner/next-boundary details remain in [the historical queue](../data/source_audits/order135/pr576-historical-review-queue.json). [The current allocation](../data/source_audits/order135/pr576-follow-up-inventory.json) preserves every original row and adds the cutoff disposition. Static trace coverage of all 1,078 obligations and five FAQs is not full Core runtime compliance.

| Item | PR576 disposition | Source / next assessment |
| --- | --- | --- |
| R01-B04 | ALREADY_APPROVED_REPAIR_FINAL_VALIDATION_REQUIRED | 18.04 distance/01.04.01 FRAME wholephysicalparts |
| R02-B05 | ALREADY_APPROVED_REPAIR_FINAL_VALIDATION_REQUIRED | 18.01 startingcargo; native valid-state save/replay acceptance |
| R03-B06 | ALREADY_APPROVED_REPAIR_FINAL_VALIDATION_REQUIRED | 15.12 target/window and12.04 eligible independentFFband |
| R04-FIGHT-TRANSITION | ALREADY_APPROVED_REPAIR_FINAL_VALIDATION_REQUIRED | 12.04 blocks6/8 playerowedSelection enteringRemaining |
| D01-PASS-SCOPE | ALREADY_APPROVED_REPAIR_FINAL_VALIDATION_REQUIRED | 12.04.01block1 ALLeligiblefriendlyunits>5, acceptedpass selectionopponent |
| D02-ATTACK-STEP-ORDER | ALREADY_APPROVED_REPAIR_FINAL_VALIDATION_REQUIRED | 05.00block2 allrolls eachstep simultaneous;04.03gatheridentical;05.01/.02/.03 |
| D03-COMBAT-EXISTENTIAL | ALREADY_APPROVED_REPAIR_FINAL_VALIDATION_REQUIRED | 18.04blocks10/12/13 Tacticalifpossible elseCombat |
| D04-DISEMBARK-SHOCK | FOLLOW_UP_NO_IMPLEMENTATION_ORDER_OR_REPAIR_AUTHORIZATION | 18.04Combat/18.05Emergency immediateBattleShock;01.07/14OC/16Actions/15targeting |
| D05-DISEMBARK-CONTEXT | D03_REQUIRED_CURRENT_CONTEXT_PROPAGATION_NO_SEPARATE_GLOBAL_CLOSURE | 18.04sharedsetup→03.02→13.06stable/nooverhang andactualbattlefield |
| D06-EMBARK-FRAME | FOLLOW_UP_NO_IMPLEMENTATION_ORDER_OR_REPAIR_AUTHORIZATION | 18.02everymodelwithin3;01.04default3D;17.02FRAMEparts |
| D07-UPPER-KEYWORDS | FOLLOW_UP_NO_IMPLEMENTATION_ORDER_OR_REPAIR_AUTHORIZATION | 13.06blocks12–14 allowedINFANTRY/BEASTS/SWARM/FLY/MONSTER |
| D08-FRAME-POSITION-BOUNDARIES | FOLLOW_UP_NO_IMPLEMENTATION_ORDER_OR_REPAIR_AUTHORIZATION | 20.04wholeedge6/enemy>8;24.09DeepStrike/24.20Infiltrate/24.31–32Scout;01.04FRAMEpointdistance |
| D09-HEAVY-SHORT-ADVANCE | FOLLOW_UP_NO_IMPLEMENTATION_ORDER_OR_REPAIR_AUTHORIZATION | 24.16ownShooting/unengaged/noSetup/allmodelmoved<=3 only; Assaultshootingpermission |
| D10-SHOOTING-PHYSICAL-PROFILE | FOLLOW_UP_NO_IMPLEMENTATION_ORDER_OR_REPAIR_AUTHORIZATION | 04.01.03 chooseonephysicalweaponprofile perattackselection |
| D11-ONE-SHOT-PROFILE | FOLLOW_UP_NO_IMPLEMENTATION_ORDER_OR_REPAIR_AUTHORIZATION | 24.26onceperphysicalweapon perbattle, stableafterrevival |
| D12-EPIC-CHARACTER | FOLLOW_UP_NO_IMPLEMENTATION_ORDER_OR_REPAIR_AUTHORIZATION | 15.03aliveplacedCHARACTERmodel inselectedfriendlyunit |
| D13-COHERENCY-CHOICE | FOLLOW_UP_NO_IMPLEMENTATION_ORDER_OR_REPAIR_AUTHORIZATION | 03.03block5 controllingplayers removeoneatatimeuntilcoherent |
| D14-SCOUTS-MIXED | FOLLOW_UP_NO_IMPLEMENTATION_ORDER_OR_REPAIR_AUTHORIZATION | 24.02block2 lowestnumbernotshared;24.32doesnotaddelectionexception |
| D15-TERRAIN-OBJECTIVE-CAP | FOLLOW_UP_NO_IMPLEMENTATION_ORDER_OR_REPAIR_AUTHORIZATION | 14.02block1 rangeofterrainobjective=withinterrainarea;13.01/01.04.01basefootprintarea |
| S16-FIGHT-SNAPSHOT | FOLLOW_UP_NO_IMPLEMENTATION_ORDER_OR_REPAIR_AUTHORIZATION | 12.00PileInstepbeforeFightstep;12.04eligibility/12.06Overrun atFightSTEPstart |
| S17-CONSOLIDATE-HISTORY | FOLLOW_UP_NO_IMPLEMENTATION_ORDER_OR_REPAIR_AUTHORIZATION | 12.08uniteligibletofightatANYpointduringFightphase mayConsolidate |
| S18-OBJECTIVE-AXIS | FOLLOW_UP_NO_IMPLEMENTATION_ORDER_OR_REPAIR_AUTHORIZATION | 14.01.01within3horizontalAND5vertical;01.04physicalpointsemantics |
| S19-EMERGENCY-PHYSICAL-PROOF | FOLLOW_UP_NO_IMPLEMENTATION_ORDER_OR_REPAIR_AUTHORIZATION | 18.05closestlegal/omitonlyunplaceable;01.04FRAMEallparts |
| S20-PATH-BODY-DISCOVERY | FOLLOW_UP_NO_IMPLEMENTATION_ORDER_OR_REPAIR_AUTHORIZATION | 03.01allpathnotthroughforbidden;13.06Densefloor/contact;17.02FRAME |
| S21-PLUNGING-SOURCE-SCOPE | FOLLOW_UP_NO_IMPLEMENTATION_ORDER_OR_REPAIR_AUTHORIZATION | 22.05requiresupperDensefeatureheight+currentmodelscope/TOWERING12 |
| S22-LONE-VISIBILITY | FOLLOW_UP_NO_IMPLEMENTATION_ORDER_OR_REPAIR_AUTHORIZATION | 24.24default12directvisibilityonly/24.24.01alllivingmodels |
| S23-DEVASTATING-ZERO | FOLLOW_UP_NO_IMPLEMENTATION_ORDER_OR_REPAIR_AUTHORIZATION | 24.10mortaldamage=Damagecharacteristic;02.02.01terminalSET0 |
| S24-OUTPHASE-FIRING-DECK | FOLLOW_UP_NO_IMPLEMENTATION_ORDER_OR_REPAIR_AUTHORIZATION | 18.08FiringDeck inyourShootingphase |
| S25-IDENTICAL-POOL | FOLLOW_UP_NO_IMPLEMENTATION_ORDER_OR_REPAIR_AUTHORIZATION | 04.03block4 mandatorygatherALLidentical;04.03.01sameoperativecharacteristics/rules |
| T26-DEMISE-REMOVAL | FOLLOW_UP_NO_IMPLEMENTATION_ORDER_OR_REPAIR_AUTHORIZATION | FAQab92e97b...block2 aftermodelsremoved;05.04.04block2/05.04.05block2 triggeredrulesTHENremove |
| T27-ORDINARY-TRANSPORT | FOLLOW_UP_NO_IMPLEMENTATION_ORDER_OR_REPAIR_AUTHORIZATION | 18.01anyfriendlyTRANSPORT startingcargo;18.02postMoveembark |
| T28-FORTIFICATION-ALIAS | FOLLOW_UP_NO_IMPLEMENTATION_ORDER_OR_REPAIR_AUTHORIZATION | 24.27Pistol==CloseQuarters allpurposes;10.06extra-1 |
| Q29-ASSERTION-LABELS | RETAINED_DISPOSITION_NO_IMPLEMENTATION_SELECTED | 05.04.04unattributed;01.05rerolled/assigned;01.06Ld; generalnativeproduceracceptance |
| C30-QUARTER-FRAME | RETAINED_DISPOSITION_NO_IMPLEMENTATION_SELECTED | 01.04.01FRAMEwholepartsforSPECIFIEDDISTANCE vsareafootprintexample;01.04.05quarters |
| C31-ELEVATED-EMPTY | RETAINED_DISPOSITION_NO_IMPLEMENTATION_SELECTED | 03.02generalsetup;13.06surfaceclausesexplicitlyterrainfeatures |

A demonstrated legal-play rejection introduced by the new Combat eligibility gate remains a blocker for this PR. The bounded ordinary supported-terrain and tall-FRAME positives do not prove complete feasibility for every admitted scene. Relaxed satisfiability without a verified legal witness remains unresolved; it cannot authorize Combat.

Gathered Hit/Wound completion does not certify grouped Save chronology or every identical-pool interpretation. The owner’s ordinary Deadly Demise clarification does not force-remove an enemy with independently valid retention or establish a universal mutual-retention priority. These qualifications are retained for scoped review and separately selected follow-up.
