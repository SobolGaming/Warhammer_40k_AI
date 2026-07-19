import { resolve } from "node:path";
import { isDeepStrictEqual } from "node:util";

import { canonicalJsonSha256 } from "./canonical-json.js";
import { ContractHttpClient, type HttpResult } from "./client.js";
import {
  ContractRegistry,
  type DeploymentPlacementPayload,
  type ErrorEnvelope,
  type EventDelta,
  type JsonValue,
  type ReplayMetadata,
  type RulesCatalog,
  type SessionCommandEnvelope,
  type SessionCommandOutcome,
  type SessionCreate,
  type SessionMetadata,
  type SessionPathParameters,
  type SessionProjection,
  jsonArray,
  jsonObject,
  parseJsonFile,
  requiredString,
} from "./contract.js";

export interface PrincipalTokens {
  readonly administrator: string;
  readonly playerA: string;
  readonly playerB: string;
  readonly replayViewer: string;
}

export interface CertifiedScenarioResult {
  readonly assertion_count: number;
  readonly replay: ReplayMetadata;
  readonly replay_sha256: string;
  readonly scenario_id: "phase18m-a-certified-setup";
}

interface ScenarioClients {
  readonly administrator: ContractHttpClient;
  readonly anonymous: ContractHttpClient;
  readonly playerA: ContractHttpClient;
  readonly playerB: ContractHttpClient;
  readonly replayViewer: ContractHttpClient;
}

interface MutableAssertionCounter {
  count: number;
}

export async function runCertifiedScenario(
  baseUrl: string,
  contractRoot: string,
  tokens: PrincipalTokens,
): Promise<CertifiedScenarioResult> {
  const registry = new ContractRegistry(contractRoot);
  const assertions: MutableAssertionCounter = { count: 0 };
  const administrator = new ContractHttpClient(baseUrl, tokens.administrator, registry);
  const clients: ScenarioClients = {
    administrator,
    anonymous: administrator.withToken(null),
    playerA: administrator.withToken(tokens.playerA),
    playerB: administrator.withToken(tokens.playerB),
    replayViewer: administrator.withToken(tokens.replayViewer),
  };

  await assertAuthentication(clients, registry, assertions);
  const createBody = registry.validate<SessionCreate>(
    "session-create.schema.json",
    parseJsonFile(resolve(contractRoot, "examples/sessions/session-create.json")),
  );
  const armyIdsByPlayer = playerArmyIds(createBody);
  const createdResponse = await clients.administrator.createSession(createBody);
  equal(createdResponse.status, 201, "administrator creates authoritative session", assertions);
  const created = validateMetadata(createdResponse, registry);
  const sessionId = created.session_id;
  equal(created.session_revision, 0, "new session begins at revision zero", assertions);
  equal(created.session_state, "created", "new session is created but not started", assertions);
  notEqual(sessionId, created.game_id, "transport and engine identities are distinct", assertions);

  const initialPlayerA = await projection(clients.playerA, sessionId, registry);
  const initialPlayerB = await projection(clients.playerB, sessionId, registry);
  const initialPlayerACursor = initialPlayerA.event_cursor;
  const initialPlayerBCursor = initialPlayerB.event_cursor;

  await assertMalformedCommand(clients, sessionId, registry, assertions);
  await assertLiveUnsupportedBoundary(clients, createBody, registry, assertions);
  const started = lifecycleEnvelope(sessionId, "phase18m-start-000001", 0, "start_session");
  const startResponse = await clients.administrator.executeCommand(
    sessionParameters(sessionId),
    started,
  );
  equal(startResponse.status, 200, "administrator starts session", assertions);
  const startOutcome = validateOutcome(startResponse, registry);
  assertCommittedAccepted(startOutcome, "start command", assertions);
  equal(startOutcome.session.session_revision, 1, "start commits one revision", assertions);
  const startRetry = await clients.administrator.executeCommand(
    sessionParameters(sessionId),
    started,
  );
  equal(startRetry.status, startResponse.status, "idempotent retry preserves status", assertions);
  equal(startRetry.rawBody, startResponse.rawBody, "idempotent retry is byte-equivalent", assertions);

  await assertStaleRevision(clients, sessionId, registry, assertions);
  await assertUnsupportedClassification(clients, sessionId, assertions);
  await assertActiveReplayAuthorization(clients, sessionId, registry, assertions);

  const ownerProjection = await projection(clients.playerA, sessionId, registry);
  const opponentProjection = await projection(clients.playerB, sessionId, registry);
  assertDecisionRedaction(ownerProjection, opponentProjection, assertions);
  await assertCatalogEquivalence(clients, sessionId, registry, assertions);

  const firstRequest = pendingDecision(ownerProjection);
  await assertAdministratorCannotSubmit(
    clients,
    sessionId,
    firstRequest,
    registry,
    assertions,
  );
  const firstFinite = finiteEnvelope(
    sessionId,
    "phase18m-finite-a-000001",
    1,
    firstRequest,
  );
  const firstFiniteResponse = await clients.playerA.executeCommand(
    sessionParameters(sessionId),
    firstFinite,
  );
  equal(firstFiniteResponse.status, 200, "player submits visible finite option", assertions);
  const firstFiniteOutcome = validateOutcome(firstFiniteResponse, registry);
  assertCommittedAccepted(firstFiniteOutcome, "first finite decision", assertions);
  const firstFiniteRetry = await clients.playerA.executeCommand(
    sessionParameters(sessionId),
    firstFinite,
  );
  equal(
    firstFiniteRetry.rawBody,
    firstFiniteResponse.rawBody,
    "finite command retry is byte-equivalent",
    assertions,
  );
  await assertStaleRequest(
    clients,
    sessionId,
    firstRequest,
    firstFiniteOutcome.session.session_revision,
    registry,
    assertions,
  );

  const secondProjection = await projection(clients.playerB, sessionId, registry);
  const secondRequest = pendingDecision(secondProjection);
  const secondFinite = finiteEnvelope(
    sessionId,
    "phase18m-finite-b-000001",
    firstFiniteOutcome.session.session_revision,
    secondRequest,
  );
  const secondFiniteOutcome = validateOutcome(
    await clients.playerB.executeCommand(sessionParameters(sessionId), secondFinite),
    registry,
  );
  assertCommittedAccepted(secondFiniteOutcome, "second player finite decision", assertions);

  let setupRevision = secondFiniteOutcome.session.session_revision;
  let setupFiniteCount = 0;
  let placementProjection = await visiblePendingProjection(clients, sessionId, registry);
  while (!pendingDecision(placementProjection).is_parameterized) {
    const setupRequest = pendingDecision(placementProjection);
    const setupClient = clientForActor(clients, setupRequest.actor_id);
    setupFiniteCount += 1;
    const setupOutcome = validateOutcome(
      await setupClient.executeCommand(
        sessionParameters(sessionId),
        finiteEnvelope(
          sessionId,
          `phase18m-setup-finite-${String(setupFiniteCount).padStart(6, "0")}`,
          setupRevision,
          setupRequest,
        ),
      ),
      registry,
    );
    assertCommittedAccepted(setupOutcome, "setup finite decision", assertions);
    setupRevision = setupOutcome.session.session_revision;
    if (setupFiniteCount > 20) {
      throw new Error("Certified setup exceeded finite-decision safety bound.");
    }
    placementProjection = await visiblePendingProjection(clients, sessionId, registry);
  }
  truthy(setupFiniteCount > 0, "setup traverses a finite decision before proposal", assertions);

  const placementRequest = pendingDecision(placementProjection);
  equal(placementRequest.is_parameterized, true, "placement request is parameterized", assertions);
  const proposalPayload = deploymentPayload(
    placementProjection.projection.pending_proposal,
    armyIdsByPlayer,
  );
  registry.validate<DeploymentPlacementPayload>("proposal-payload.schema.json", proposalPayload);
  const placementClient = clientForActor(clients, placementRequest.actor_id);
  const placementEnvelope = parameterizedEnvelope(
    sessionId,
    "phase18m-deployment-placement-000001",
    setupRevision,
    placementRequest,
    proposalPayload,
  );
  const placementResponse = await placementClient.executeCommand(
    sessionParameters(sessionId),
    placementEnvelope,
  );
  equal(placementResponse.status, 200, "player submits deployment proposal", assertions);
  const placementOutcome = validateOutcome(placementResponse, registry);
  assertCommittedAccepted(placementOutcome, "deployment proposal", assertions);
  const placementRetry = await placementClient.executeCommand(
    sessionParameters(sessionId),
    placementEnvelope,
  );
  equal(
    placementRetry.rawBody,
    placementResponse.rawBody,
    "parameterized command retry is byte-equivalent",
    assertions,
  );

  await assertEventPagination(
    clients.playerA,
    sessionId,
    initialPlayerACursor,
    registry,
    assertions,
  );
  await assertEventPagination(
    clients.playerB,
    sessionId,
    initialPlayerBCursor,
    registry,
    assertions,
  );
  await assertForcedResynchronization(clients.playerA, sessionId, registry, assertions);

  const activeReplay = await replay(clients.administrator, sessionId, registry);
  assertReplayContainsDecisions(activeReplay.body, 4, assertions);
  const closeEnvelope = lifecycleEnvelope(
    sessionId,
    "phase18m-close-000001",
    placementOutcome.session.session_revision,
    "close_session",
  );
  const closeResponse = await clients.administrator.executeCommand(
    sessionParameters(sessionId),
    closeEnvelope,
  );
  equal(closeResponse.status, 200, "administrator closes session", assertions);
  const closeOutcome = validateOutcome(closeResponse, registry);
  assertCommittedAccepted(closeOutcome, "close command", assertions);
  equal(closeOutcome.session.session_state, "closed", "session reaches closed state", assertions);
  equal(
    closeOutcome.session.terminal_reason?.code,
    "session_closed",
    "closed session publishes terminal reason",
    assertions,
  );
  await assertTerminalHandling(
    clients,
    sessionId,
    closeOutcome.session.session_revision,
    registry,
    assertions,
  );

  const closedReplay = await replay(clients.administrator, sessionId, registry);
  equal(
    closedReplay.rawBody,
    activeReplay.rawBody,
    "transport close leaves authoritative replay unchanged",
    assertions,
  );
  const replayViewerExport = await replay(clients.replayViewer, sessionId, registry);
  equal(
    replayViewerExport.rawBody,
    closedReplay.rawBody,
    "terminal replay viewer receives equivalent immutable artifact",
    assertions,
  );

  return {
    assertion_count: assertions.count,
    replay: closedReplay.body,
    replay_sha256: canonicalJsonSha256(closedReplay.body),
    scenario_id: "phase18m-a-certified-setup",
  };
}

function lifecycleEnvelope(
  sessionId: string,
  commandId: string,
  expectedRevision: number,
  submissionKind: "start_session" | "advance_session" | "close_session",
): SessionCommandEnvelope {
  return {
    schema_version: "session-command-envelope-v1",
    command_id: commandId,
    session_id: sessionId,
    expected_session_revision: expectedRevision,
    request_id: null,
    result_id: null,
    submission: { submission_kind: submissionKind },
  } satisfies SessionCommandEnvelope;
}

function finiteEnvelope(
  sessionId: string,
  commandId: string,
  expectedRevision: number,
  request: ReturnType<typeof pendingDecision>,
): SessionCommandEnvelope {
  const firstOption = request.options[0];
  if (firstOption === undefined) {
    throw new Error("Finite request did not publish an option.");
  }
  return {
    schema_version: "session-command-envelope-v1",
    command_id: commandId,
    session_id: sessionId,
    expected_session_revision: expectedRevision,
    request_id: request.request_id,
    result_id: `${commandId}-result`,
    submission: { submission_kind: "finite_option", option_id: firstOption.option_id },
  } satisfies SessionCommandEnvelope;
}

function parameterizedEnvelope(
  sessionId: string,
  commandId: string,
  expectedRevision: number,
  request: ReturnType<typeof pendingDecision>,
  payload: DeploymentPlacementPayload,
): SessionCommandEnvelope {
  return {
    schema_version: "session-command-envelope-v1",
    command_id: commandId,
    session_id: sessionId,
    expected_session_revision: expectedRevision,
    request_id: request.request_id,
    result_id: `${commandId}-result`,
    submission: { submission_kind: "parameterized_payload", payload },
  } satisfies SessionCommandEnvelope;
}

async function assertAuthentication(
  clients: ScenarioClients,
  registry: ContractRegistry,
  assertions: MutableAssertionCounter,
): Promise<void> {
  const response = await clients.anonymous.getGlobalCatalog();
  equal(response.status, 401, "missing bearer credential is rejected", assertions);
  const error = registry.validate<ErrorEnvelope>("error-envelope.schema.json", response.body);
  equal(error.error.code, "authentication_required", "authentication error is typed", assertions);
}

async function assertMalformedCommand(
  clients: ScenarioClients,
  sessionId: string,
  registry: ContractRegistry,
  assertions: MutableAssertionCounter,
): Promise<void> {
  const response = await clients.administrator.probeMalformedSessionCommand(
    sessionParameters(sessionId),
    { schema_version: "session-command-envelope-v1", unexpected: true },
  );
  equal(response.status, 400, "malformed command is rejected before mutation", assertions);
  const error = registry.validate<ErrorEnvelope>("error-envelope.schema.json", response.body);
  equal(
    error.error.code,
    "canonical_schema_invalid",
    "malformed command has typed classification",
    assertions,
  );
  const metadata = await metadataFor(clients.administrator, sessionId, registry);
  equal(metadata.session_revision, 0, "malformed command preserves revision", assertions);
}

async function assertStaleRevision(
  clients: ScenarioClients,
  sessionId: string,
  registry: ContractRegistry,
  assertions: MutableAssertionCounter,
): Promise<void> {
  const response = await clients.administrator.executeCommand(
    sessionParameters(sessionId),
    lifecycleEnvelope(sessionId, "phase18m-stale-revision", 0, "advance_session"),
  );
  equal(response.status, 409, "stale expected revision is rejected", assertions);
  const error = registry.validate<ErrorEnvelope>("error-envelope.schema.json", response.body);
  equal(error.error.code, "session_revision_conflict", "stale revision is classified", assertions);
  const metadata = await metadataFor(clients.administrator, sessionId, registry);
  equal(metadata.session_revision, 1, "stale revision preserves authoritative revision", assertions);
}

async function assertUnsupportedClassification(
  clients: ScenarioClients,
  sessionId: string,
  assertions: MutableAssertionCounter,
): Promise<void> {
  const response = await clients.administrator.probeUnpublishedSupportProfile(
    sessionParameters(sessionId),
  );
  equal(response.status, 404, "unpublished formal route is rejected", assertions);
  equal(
    response.body.error.code,
    "route_not_found",
    "unpublished transport path is classified",
    assertions,
  );
}

async function assertLiveUnsupportedBoundary(
  clients: ScenarioClients,
  createBody: SessionCreate,
  registry: ContractRegistry,
  assertions: MutableAssertionCounter,
): Promise<void> {
  const boundaryBody = jsonObject(
    structuredClone(createBody),
    "transition-budget session create body",
  );
  const boundaryConfig = jsonObject(boundaryBody.config, "transition-budget config");
  boundaryConfig.game_id = `${requiredString(boundaryConfig, "game_id")}-transition-budget`;
  boundaryConfig.max_lifecycle_transitions = 1;
  const validatedBody = registry.validate<SessionCreate>(
    "session-create.schema.json",
    boundaryBody,
  );
  const created = await clients.administrator.createSession(validatedBody);
  equal(created.status, 201, "administrator creates unsupported-boundary session", assertions);
  const metadata = validateMetadata(created, registry);
  const started = await clients.administrator.executeCommand(
    sessionParameters(metadata.session_id),
    lifecycleEnvelope(metadata.session_id, "phase18m-budget-start", 0, "start_session"),
  );
  equal(started.status, 200, "transition-budget command returns public outcome", assertions);
  const outcome = validateOutcome(started, registry);
  assertCommittedAccepted(outcome, "transition-budget boundary", assertions);
  const lifecycleStatus = jsonObject(
    outcome.session.lifecycle_status,
    "transition-budget lifecycle status",
  );
  equal(lifecycleStatus.status_kind, "unsupported", "unsupported lifecycle is classified", assertions);
  const payload = jsonObject(lifecycleStatus.payload, "unsupported lifecycle payload");
  equal(
    payload.unsupported_reason,
    "transition_budget_exhausted",
    "live unsupported boundary preserves its typed reason",
    assertions,
  );
  const closed = await clients.administrator.executeCommand(
    sessionParameters(metadata.session_id),
    lifecycleEnvelope(metadata.session_id, "phase18m-budget-close", 1, "close_session"),
  );
  equal(closed.status, 200, "unsupported-boundary session closes cleanly", assertions);
}

async function assertActiveReplayAuthorization(
  clients: ScenarioClients,
  sessionId: string,
  registry: ContractRegistry,
  assertions: MutableAssertionCounter,
): Promise<void> {
  const response = await clients.replayViewer.exportReplay(sessionParameters(sessionId));
  equal(response.status, 403, "replay viewer cannot inspect active replay", assertions);
  const error = registry.validate<ErrorEnvelope>("error-envelope.schema.json", response.body);
  equal(error.error.code, "access_denied", "active replay denial is redacted", assertions);
}

function assertDecisionRedaction(
  owner: SessionProjection,
  opponent: SessionProjection,
  assertions: MutableAssertionCounter,
): void {
  const ownerDecision = pendingDecision(owner);
  const opponentDecision = pendingDecision(opponent);
  equal(ownerDecision.actor_id, "player-a", "owner sees acting player", assertions);
  equal(ownerDecision.decision_type, "select_secondary_missions", "owner sees decision type", assertions);
  truthy(ownerDecision.options.length > 0, "owner sees finite options", assertions);
  equal(opponentDecision.actor_id, null, "opponent actor is redacted", assertions);
  equal(opponentDecision.decision_type, "hidden_decision", "opponent type is redacted", assertions);
  equal(opponentDecision.options.length, 0, "opponent option count is hidden", assertions);
  truthy(
    !JSON.stringify(opponentDecision).includes("select_secondary_missions"),
    "opponent payload does not leak hidden type",
    assertions,
  );
}

async function assertCatalogEquivalence(
  clients: ScenarioClients,
  sessionId: string,
  registry: ContractRegistry,
  assertions: MutableAssertionCounter,
): Promise<void> {
  const administrator = await clients.administrator.getCatalog(sessionParameters(sessionId));
  const player = await clients.playerA.getCatalog(sessionParameters(sessionId));
  equal(administrator.status, 200, "administrator retrieves session catalog", assertions);
  equal(player.status, 200, "player retrieves session catalog", assertions);
  const administratorCatalog = registry.validate<RulesCatalog>(
    "rules-catalog.schema.json",
    administrator.body,
  );
  const playerCatalog = registry.validate<RulesCatalog>("rules-catalog.schema.json", player.body);
  equal(
    playerCatalog.source_hash,
    administratorCatalog.source_hash,
    "static catalog hash is cacheable across viewers",
    assertions,
  );
}

async function assertAdministratorCannotSubmit(
  clients: ScenarioClients,
  sessionId: string,
  request: ReturnType<typeof pendingDecision>,
  registry: ContractRegistry,
  assertions: MutableAssertionCounter,
): Promise<void> {
  const response = await clients.administrator.executeCommand(
    sessionParameters(sessionId),
    finiteEnvelope(sessionId, "phase18m-admin-impersonation", 1, request),
  );
  equal(response.status, 403, "administrator cannot impersonate decision actor", assertions);
  const error = registry.validate<ErrorEnvelope>("error-envelope.schema.json", response.body);
  equal(error.error.code, "access_denied", "actor authorization denial is typed", assertions);
}

async function assertStaleRequest(
  clients: ScenarioClients,
  sessionId: string,
  request: ReturnType<typeof pendingDecision>,
  revision: number,
  registry: ContractRegistry,
  assertions: MutableAssertionCounter,
): Promise<void> {
  const currentProjection = await visiblePendingProjection(clients, sessionId, registry);
  const currentRequest = pendingDecision(currentProjection);
  const client = clientForActor(clients, currentRequest.actor_id);
  const response = await client.executeCommand(
    sessionParameters(sessionId),
    finiteEnvelope(sessionId, "phase18m-stale-request", revision, request),
  );
  equal(response.status, 409, "consumed request is rejected", assertions);
  const error = registry.validate<ErrorEnvelope>("error-envelope.schema.json", response.body);
  equal(error.error.code, "stale_decision_request", "stale request is classified", assertions);
}

async function assertEventPagination(
  client: ContractHttpClient,
  sessionId: string,
  initialCursor: string,
  registry: ContractRegistry,
  assertions: MutableAssertionCounter,
): Promise<void> {
  let cursor = initialCursor;
  const sequenceNumbers: number[] = [];
  let pageCount = 0;
  while (true) {
    const response = await client.getEvents(sessionParameters(sessionId), { cursor, limit: 5 });
    equal(response.status, 200, "viewer event page succeeds", assertions);
    const page = registry.validate<EventDelta>("event-delta.schema.json", response.body);
    equal(page.resync_required, false, "retained cursor does not require resync", assertions);
    truthy(page.events.length <= 5, "event page respects requested limit", assertions);
    sequenceNumbers.push(...page.events.map((event) => event.sequence_number));
    cursor = page.next_cursor;
    pageCount += 1;
    if (!page.has_more) {
      break;
    }
    if (pageCount > 1000) {
      throw new Error("Event pagination exceeded deterministic safety bound.");
    }
  }
  truthy(pageCount > 1, "event stream is paginated", assertions);
  for (let index = 1; index < sequenceNumbers.length; index += 1) {
    equal(
      sequenceNumbers[index],
      sequenceNumbers[index - 1]! + 1,
      "viewer event sequence remains contiguous",
      assertions,
    );
  }
}

async function assertForcedResynchronization(
  client: ContractHttpClient,
  sessionId: string,
  registry: ContractRegistry,
  assertions: MutableAssertionCounter,
): Promise<void> {
  const response = await client.getEvents(sessionParameters(sessionId), {
    cursor: "not-a-cursor",
  });
  equal(response.status, 200, "invalid cursor returns typed resync payload", assertions);
  const delta = registry.validate<EventDelta>("event-delta.schema.json", response.body);
  equal(delta.resync_required, true, "invalid cursor forces resynchronization", assertions);
  equal(delta.resync_reason, "malformed", "resync reason is classified", assertions);
  equal(delta.events.length, 0, "resync response does not leak events", assertions);
  const replacement = await projection(client, sessionId, registry);
  equal(delta.next_cursor, replacement.event_cursor, "resync resumes from full projection", assertions);
  equal(
    delta.projection_state_hash,
    replacement.projection_state_hash,
    "resync checkpoint matches replacement projection",
    assertions,
  );
}

async function assertTerminalHandling(
  clients: ScenarioClients,
  sessionId: string,
  revision: number,
  registry: ContractRegistry,
  assertions: MutableAssertionCounter,
): Promise<void> {
  const response = await clients.administrator.executeCommand(
    sessionParameters(sessionId),
    lifecycleEnvelope(sessionId, "phase18m-after-close", revision, "advance_session"),
  );
  equal(response.status, 409, "closed session rejects further commands", assertions);
  const error = registry.validate<ErrorEnvelope>("error-envelope.schema.json", response.body);
  equal(error.error.code, "session_closed", "closed session response is terminally typed", assertions);
  const playerMetadata = await metadataFor(clients.playerA, sessionId, registry);
  equal(playerMetadata.session_state, "closed", "player observes closed terminal state", assertions);
}

function assertReplayContainsDecisions(
  replayMetadata: ReplayMetadata,
  minimumDecisionCount: number,
  assertions: MutableAssertionCounter,
): void {
  truthy(
    replayMetadata.decision_records.length >= minimumDecisionCount,
    "replay includes submitted finite and parameterized decisions",
    assertions,
  );
  truthy(replayMetadata.event_records.length > 0, "replay includes authoritative events", assertions);
  truthy(
    replayMetadata.source_identity.game_config_hash.length >= 64 &&
      replayMetadata.source_identity.ruleset_descriptor_hash.length >= 64,
    "replay pins deterministic config and ruleset identities",
    assertions,
  );
}

function playerArmyIds(createBody: SessionCreate): ReadonlyMap<string, string> {
  const result = new Map<string, string>();
  const musterRequests = jsonArray(
    createBody.config.army_muster_requests,
    "session-create army muster requests",
  );
  for (const requestValue of musterRequests) {
    const request = jsonObject(requestValue, "session-create army muster request");
    const playerId = requiredString(request, "player_id");
    const armyId = requiredString(request, "army_id");
    if (result.has(playerId)) {
      throw new Error(`Session-create fixture repeats army identity for ${playerId}.`);
    }
    result.set(playerId, armyId);
  }
  for (const playerId of createBody.config.player_ids) {
    if (!result.has(playerId)) {
      throw new Error(`Session-create fixture has no published army identity for ${playerId}.`);
    }
  }
  return result;
}

function deploymentPayload(
  value: JsonValue,
  armyIdsByPlayer: ReadonlyMap<string, string>,
): DeploymentPlacementPayload {
  const proposal = jsonObject(value, "pending deployment proposal");
  const playerId = requiredString(proposal, "player_id");
  const unitInstanceId = requiredString(proposal, "unit_instance_id");
  const armyId = armyIdsByPlayer.get(playerId);
  if (armyId === undefined) {
    throw new Error(`Deployment actor ${playerId} has no published session-create army identity.`);
  }
  const proposalKind = requiredString(proposal, "proposal_kind");
  if (proposalKind !== "deployment_placement") {
    throw new Error(`Certified deployment received proposal kind ${proposalKind}.`);
  }
  const placementKind = requiredString(proposal, "placement_kind");
  if (placementKind !== "deployment") {
    throw new Error(`Certified deployment received placement kind ${placementKind}.`);
  }
  const zones = jsonArray(proposal.legal_deployment_zones, "legal deployment zones");
  const firstZone = jsonObject(zones[0], "first legal deployment zone");
  const shape = jsonObject(firstZone.shape, "deployment zone shape");
  const polygons = jsonArray(shape.polygons, "deployment zone polygons");
  const firstPolygon = jsonObject(polygons[0], "first deployment polygon");
  const vertices = jsonArray(firstPolygon.vertices, "deployment polygon vertices").map((vertex) =>
    jsonObject(vertex, "deployment vertex"),
  );
  const xs = vertices.map((vertex) => requiredNumber(vertex, "x"));
  const ys = vertices.map((vertex) => requiredNumber(vertex, "y"));
  const minimumX = Math.min(...xs);
  const minimumY = Math.min(...ys);
  const modelIds = jsonArray(proposal.model_instance_ids, "deployment model IDs");
  const modelPlacements = modelIds.map((modelId, index) => {
    if (typeof modelId !== "string" || modelId.length === 0) {
      throw new Error("Deployment model ID must be a non-empty string.");
    }
    return {
      army_id: armyId,
      player_id: playerId,
      unit_instance_id: unitInstanceId,
      model_instance_id: modelId,
      pose: {
        position: {
          x: minimumX + 3 + Math.floor(index / 3) * 1.8,
          y: minimumY + 3 + (index % 3) * 1.8,
          z: 0,
        },
        facing: { degrees: 0 },
      },
    };
  });
  return {
    proposal_request_id: requiredString(proposal, "request_id"),
    proposal_kind: "deployment_placement",
    game_id: requiredString(proposal, "game_id"),
    ruleset_descriptor_hash: requiredString(proposal, "ruleset_descriptor_hash"),
    setup_step: requiredString(proposal, "setup_step"),
    player_id: playerId,
    unit_instance_id: unitInstanceId,
    placement_kind: "deployment",
    model_placements: modelPlacements,
    context: proposal.context ?? null,
  } satisfies DeploymentPlacementPayload;
}

function requiredNumber(value: unknown, key: string): number {
  const field = jsonObject(value, "payload")[key];
  if (typeof field !== "number" || !Number.isFinite(field)) {
    throw new Error(`Payload requires finite number ${key}.`);
  }
  return field;
}

function sessionParameters(sessionId: string): SessionPathParameters {
  return { session_id: sessionId } satisfies SessionPathParameters;
}

async function visiblePendingProjection(
  clients: ScenarioClients,
  sessionId: string,
  registry: ContractRegistry,
): Promise<SessionProjection> {
  const playerA = await projection(clients.playerA, sessionId, registry);
  const playerADecision = playerA.projection.pending_decision;
  if (playerADecision !== null && playerADecision.decision_type !== "hidden_decision") {
    return playerA;
  }
  const playerB = await projection(clients.playerB, sessionId, registry);
  const playerBDecision = playerB.projection.pending_decision;
  if (playerBDecision !== null && playerBDecision.decision_type !== "hidden_decision") {
    return playerB;
  }
  throw new Error("No player-visible pending decision was published.");
}

function clientForActor(clients: ScenarioClients, actorId: string | null): ContractHttpClient {
  if (actorId === "player-a") {
    return clients.playerA;
  }
  if (actorId === "player-b") {
    return clients.playerB;
  }
  throw new Error("Certified scenario received an unknown or redacted actor.");
}

function pendingDecision(projectionPayload: SessionProjection) {
  const decision = projectionPayload.projection.pending_decision;
  if (decision === null) {
    throw new Error("Certified scenario expected a pending decision.");
  }
  return decision;
}

function validateMetadata(
  response: HttpResult<SessionMetadata | ErrorEnvelope>,
  registry: ContractRegistry,
): SessionMetadata {
  return registry.validate<SessionMetadata>("session-metadata.schema.json", response.body);
}

function validateOutcome(
  response: HttpResult<SessionCommandOutcome | ErrorEnvelope>,
  registry: ContractRegistry,
): SessionCommandOutcome {
  if (response.status !== 200 && response.status !== 422) {
    throw new Error(`Expected command outcome, received HTTP ${response.status}.`);
  }
  return registry.validate<SessionCommandOutcome>(
    "session-command-outcome.schema.json",
    response.body,
  );
}

async function metadataFor(
  client: ContractHttpClient,
  sessionId: string,
  registry: ContractRegistry,
): Promise<SessionMetadata> {
  const response = await client.getMetadata(sessionParameters(sessionId));
  if (response.status !== 200) {
    throw new Error(`Session metadata returned HTTP ${response.status}.`);
  }
  return registry.validate<SessionMetadata>("session-metadata.schema.json", response.body);
}

async function projection(
  client: ContractHttpClient,
  sessionId: string,
  registry: ContractRegistry,
): Promise<SessionProjection> {
  const response = await client.getProjection(sessionParameters(sessionId));
  if (response.status !== 200) {
    throw new Error(`Session projection returned HTTP ${response.status}.`);
  }
  return registry.validate<SessionProjection>("session-projection.schema.json", response.body);
}

async function replay(
  client: ContractHttpClient,
  sessionId: string,
  registry: ContractRegistry,
): Promise<HttpResult<ReplayMetadata>> {
  const response = await client.exportReplay(sessionParameters(sessionId));
  if (response.status !== 200) {
    throw new Error(`Replay export returned HTTP ${response.status}.`);
  }
  return {
    ...response,
    body: registry.validate<ReplayMetadata>("replay-metadata.schema.json", response.body),
  };
}

function assertCommittedAccepted(
  outcome: SessionCommandOutcome,
  label: string,
  assertions: MutableAssertionCounter,
): void {
  equal(outcome.committed, true, `${label} is committed`, assertions);
  equal(outcome.accepted, true, `${label} is accepted`, assertions);
  equal(outcome.outcome_code, "command_committed", `${label} classification`, assertions);
}

function equal(
  actual: unknown,
  expected: unknown,
  label: string,
  assertions: MutableAssertionCounter,
): void {
  assertions.count += 1;
  if (!isDeepStrictEqual(actual, expected)) {
    throw new Error(`${label}: expected ${JSON.stringify(expected)}, received ${JSON.stringify(actual)}.`);
  }
}

function notEqual(
  actual: unknown,
  expected: unknown,
  label: string,
  assertions: MutableAssertionCounter,
): void {
  assertions.count += 1;
  if (isDeepStrictEqual(actual, expected)) {
    throw new Error(`${label}: values unexpectedly matched ${JSON.stringify(actual)}.`);
  }
}

function truthy(
  condition: boolean,
  label: string,
  assertions: MutableAssertionCounter,
): void {
  assertions.count += 1;
  if (!condition) {
    throw new Error(`${label}: condition was false.`);
  }
}
