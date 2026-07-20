import type { ReplayMetadata, SessionMetadata } from "../contract.js";

declare const sessionMetadata: SessionMetadata;
const sessionRulesetDescriptorHash: string = sessionMetadata.ruleset_descriptor_hash;
const sessionRulesOverlayIds: string[] = sessionMetadata.rules_overlay_ids;

declare const replayMetadata: ReplayMetadata;
const replayRulesOverlayIds: string[] = replayMetadata.source_identity.rules_overlay_ids;

void sessionRulesetDescriptorHash;
void sessionRulesOverlayIds;
void replayRulesOverlayIds;
