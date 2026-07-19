import { spawn, type ChildProcess } from "node:child_process";
import { once } from "node:events";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { isDeepStrictEqual } from "node:util";

import { ContractHttpClient } from "./client.js";
import { ContractRegistry, type ReplayMetadata } from "./contract.js";
import {
  type CertifiedScenarioResult,
  type PrincipalTokens,
  runCertifiedScenario,
} from "./scenario.js";

const REFERENCE_TOKENS: PrincipalTokens = {
  administrator: "core-v2-dev-administrator",
  playerA: "core-v2-dev-player-a",
  playerB: "core-v2-dev-player-b",
  replayViewer: "core-v2-dev-replay-viewer",
};

interface CommandLineOptions {
  readonly baseUrl: string | null;
  readonly comparisonBaseUrl: string | null;
}

interface ManagedServer {
  readonly baseUrl: string;
  readonly child: ChildProcess;
  readonly logs: string[];
  readonly shutdownDirectory: string;
  readonly shutdownFile: string;
}

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(packageRoot, "../..");
const contractRoot = resolve(repositoryRoot, "contracts");

await main();

async function main(): Promise<void> {
  const options = parseArguments(process.argv.slice(2));
  const tokens = principalTokens();
  const registry = new ContractRegistry(contractRoot);
  const managedServers: ManagedServer[] = [];
  try {
    const primaryUrl =
      options.baseUrl ??
      (await startReferenceServer(repositoryRoot, managedServers, tokens.administrator, registry))
        .baseUrl;
    const comparisonUrl =
      options.comparisonBaseUrl ??
      (options.baseUrl === null
        ? (
            await startReferenceServer(
              repositoryRoot,
              managedServers,
              tokens.administrator,
              registry,
            )
          ).baseUrl
        : null);
    if (comparisonUrl === null) {
      throw new Error(
        "External conformance requires both --base-url and --comparison-base-url for replay equivalence.",
      );
    }
    const primary = await runCertifiedScenario(primaryUrl, contractRoot, tokens);
    const comparison = await runCertifiedScenario(comparisonUrl, contractRoot, tokens);
    const equivalenceAssertions = assertReplayEquivalence(primary, comparison);
    process.stdout.write(
      `${JSON.stringify(
        {
          assertion_count:
            primary.assertion_count + comparison.assertion_count + equivalenceAssertions,
          client_language: "typescript",
          contract_version: "2.0.0",
          replay_sha256: primary.replay_sha256,
          scenario_id: primary.scenario_id,
          status: "passed",
        },
        null,
        2,
      )}\n`,
    );
  } finally {
    await Promise.all(managedServers.map(stopReferenceServer));
  }
}

function parseArguments(arguments_: string[]): CommandLineOptions {
  let baseUrl: string | null = null;
  let comparisonBaseUrl: string | null = null;
  for (let index = 0; index < arguments_.length; index += 1) {
    const argument = arguments_[index];
    const value = arguments_[index + 1];
    if (argument === "--base-url" && value !== undefined) {
      baseUrl = normalizedBaseUrl(value);
      index += 1;
      continue;
    }
    if (argument === "--comparison-base-url" && value !== undefined) {
      comparisonBaseUrl = normalizedBaseUrl(value);
      index += 1;
      continue;
    }
    throw new Error(`Unknown or incomplete argument ${argument ?? "<missing>"}.`);
  }
  return { baseUrl, comparisonBaseUrl };
}

function normalizedBaseUrl(value: string): string {
  const url = new URL(value);
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("Conformance base URL must use HTTP or HTTPS.");
  }
  return url.toString().replace(/\/$/, "");
}

async function startReferenceServer(
  projectRoot: string,
  managedServers: ManagedServer[],
  administratorToken: string,
  registry: ContractRegistry,
): Promise<ManagedServer> {
  const port = await availablePort();
  const logs: string[] = [];
  const shutdownDirectory = mkdtempSync(resolve(tmpdir(), "core-v2-reference-server-"));
  const shutdownFile = resolve(shutdownDirectory, "shutdown");
  const child = spawn(
    "uv",
    [
      "run",
      "python",
      "scripts/run_phase18m_reference_server.py",
      "--host",
      "127.0.0.1",
      "--port",
      String(port),
      "--shutdown-file",
      shutdownFile,
    ],
    { cwd: projectRoot, stdio: ["ignore", "pipe", "pipe"], windowsHide: true },
  );
  child.stdout?.on("data", (chunk: Buffer) => logs.push(chunk.toString("utf8")));
  child.stderr?.on("data", (chunk: Buffer) => logs.push(chunk.toString("utf8")));
  const server: ManagedServer = {
    baseUrl: `http://127.0.0.1:${port}`,
    child,
    logs,
    shutdownDirectory,
    shutdownFile,
  };
  managedServers.push(server);
  await waitUntilReady(server, administratorToken, registry);
  return server;
}

async function stopReferenceServer(server: ManagedServer): Promise<void> {
  if (server.child.exitCode === null) {
    const exited = once(server.child, "exit");
    writeFileSync(server.shutdownFile, "shutdown\n", "utf8");
    await Promise.race([
      exited,
      new Promise<never>((_, rejectExit) =>
        setTimeout(() => rejectExit(new Error("Reference server did not shut down.")), 10_000),
      ),
    ]);
  }
  rmSync(server.shutdownDirectory, { recursive: true, force: true });
}

async function waitUntilReady(
  server: ManagedServer,
  administratorToken: string,
  registry: ContractRegistry,
): Promise<void> {
  const client = new ContractHttpClient(server.baseUrl, administratorToken, registry);
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    if (server.child.exitCode !== null) {
      throw new Error(`Reference server exited before readiness.\n${server.logs.join("")}`);
    }
    try {
      const response = await client.getGlobalCatalog();
      if (response.status === 200) {
        return;
      }
    } catch (error: unknown) {
      if (!(error instanceof TypeError)) {
        throw error;
      }
    }
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 100));
  }
  throw new Error(`Reference server did not become ready.\n${server.logs.join("")}`);
}

function principalTokens(): PrincipalTokens {
  const configured = {
    administrator: process.env.CORE_V2_CONFORMANCE_ADMIN_TOKEN,
    playerA: process.env.CORE_V2_CONFORMANCE_PLAYER_A_TOKEN,
    playerB: process.env.CORE_V2_CONFORMANCE_PLAYER_B_TOKEN,
    replayViewer: process.env.CORE_V2_CONFORMANCE_REPLAY_TOKEN,
  };
  const providedCount = Object.values(configured).filter((value) => value !== undefined).length;
  if (providedCount === 0) {
    return REFERENCE_TOKENS;
  }
  if (providedCount !== Object.keys(configured).length) {
    throw new Error("External principal token configuration must provide all four tokens.");
  }
  return {
    administrator: configured.administrator!,
    playerA: configured.playerA!,
    playerB: configured.playerB!,
    replayViewer: configured.replayViewer!,
  };
}

function availablePort(): Promise<number> {
  return new Promise((resolvePort, rejectPort) => {
    const server = createServer();
    server.once("error", rejectPort);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (address === null || typeof address === "string") {
        server.close();
        rejectPort(new Error("Could not allocate a TCP port."));
        return;
      }
      server.close((error) => {
        if (error !== undefined) {
          rejectPort(error);
          return;
        }
        resolvePort(address.port);
      });
    });
  });
}

function assertReplayEquivalence(
  primary: CertifiedScenarioResult,
  comparison: CertifiedScenarioResult,
): number {
  const comparisons: ReadonlyArray<readonly [unknown, unknown, string]> = [
    [primary.scenario_id, comparison.scenario_id, "scenario identity"],
    [primary.replay_sha256, comparison.replay_sha256, "canonical replay SHA-256"],
    [primary.replay, comparison.replay, "complete replay semantics"],
    [primary.replay.source_identity, comparison.replay.source_identity, "source identity"],
    [primary.replay.decision_records, comparison.replay.decision_records, "decision records"],
    [primary.replay.event_records, comparison.replay.event_records, "event records"],
    [
      primary.replay.projection_checkpoints,
      comparison.replay.projection_checkpoints,
      "projection checkpoints",
    ],
    [replayHashes(primary.replay), replayHashes(comparison.replay), "published replay hashes"],
  ];
  for (const [actual, expected, label] of comparisons) {
    if (!isDeepStrictEqual(actual, expected)) {
      throw new Error(`Independent HTTP executions differ in ${label}.`);
    }
  }
  return comparisons.length;
}

function replayHashes(replay: ReplayMetadata): unknown {
  return {
    source_identity: {
      catalog_hash: replay.source_identity.catalog_hash,
      game_config_hash: replay.source_identity.game_config_hash,
      ruleset_descriptor_hash: replay.source_identity.ruleset_descriptor_hash,
    },
    projection_checkpoints: replay.projection_checkpoints.map((checkpoint) => ({
      event_log_hash: checkpoint.event_log_hash,
      projection_state_hash: checkpoint.projection_state_hash,
    })),
  };
}
