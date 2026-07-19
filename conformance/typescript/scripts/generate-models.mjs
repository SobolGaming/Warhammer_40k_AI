import {
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const contractRoot = resolve(packageRoot, "../../contracts");
const outputArgument = process.argv[2];
if (outputArgument === undefined) {
  process.stderr.write("Usage: node scripts/generate-models.mjs <output-path>\n");
  process.exit(2);
}

const outputPath = resolve(packageRoot, outputArgument);
const temporaryDirectory = mkdtempSync(resolve(tmpdir(), "core-v2-openapi-source-"));
const normalizedContractRoot = resolve(temporaryDirectory, "contracts");
const normalizedSchemaRoot = resolve(normalizedContractRoot, "schemas");
const localSchemaPrefix = "https://warhammer40k-core.local/contracts/";
const normativePaths = new Set([
  "/rules-catalog",
  "/sessions",
  "/sessions/{session_id}",
  "/sessions/{session_id}/commands",
  "/sessions/{session_id}/projection",
  "/sessions/{session_id}/catalog",
  "/sessions/{session_id}/events",
  "/sessions/{session_id}/replay",
]);
const normativeParameters = new Set(["EventCursor", "EventPageLimit", "SessionId"]);
const normativeResponses = new Set([
  "Error",
  "EventDelta",
  "SessionCommandOutcome",
  "SessionCommandRejected",
  "SessionMetadata",
  "SessionProjection",
]);

try {
  mkdirSync(normalizedSchemaRoot, { recursive: true });
  const openapi = JSON.parse(readFileSync(resolve(contractRoot, "openapi.yaml"), "utf8"));
  openapi.paths = selectedEntries(openapi.paths, normativePaths);
  openapi.components.parameters = selectedEntries(
    openapi.components.parameters,
    normativeParameters,
  );
  openapi.components.responses = selectedEntries(openapi.components.responses, normativeResponses);
  delete openapi.components.schemas;
  writeFileSync(
    resolve(normalizedContractRoot, "openapi.yaml"),
    `${JSON.stringify(openapi, null, 2)}\n`,
    "utf8",
  );
  for (const schemaName of readdirSync(resolve(contractRoot, "schemas"))) {
    if (!schemaName.endsWith(".json")) {
      continue;
    }
    const source = JSON.parse(
      readFileSync(resolve(contractRoot, "schemas", schemaName), "utf8"),
    );
    const normalized = normalizeSchemaReferences(source, schemaName);
    writeFileSync(
      resolve(normalizedSchemaRoot, schemaName),
      `${JSON.stringify(normalized, null, 2)}\n`,
      "utf8",
    );
    for (const [definitionName, definition] of Object.entries(source.$defs ?? {})) {
      const definitionPath = resolve(
        normalizedSchemaRoot,
        definitionFileName(schemaName, definitionName),
      );
      writeFileSync(
        definitionPath,
        `${JSON.stringify(normalizeSchemaReferences(definition, schemaName), null, 2)}\n`,
        "utf8",
      );
    }
  }

  mkdirSync(dirname(outputPath), { recursive: true });
  const generator = resolve(packageRoot, "node_modules/openapi-typescript/bin/cli.js");
  const generated = spawnSync(
    process.execPath,
    [generator, resolve(normalizedContractRoot, "openapi.yaml"), "-o", outputPath],
    { cwd: packageRoot, encoding: "utf8" },
  );
  process.stdout.write(generated.stdout);
  process.stderr.write(generated.stderr);
  process.exitCode = generated.status ?? 1;
  if (generated.status === 0) {
    const generatedSource = readFileSync(outputPath, "utf8");
    writeFileSync(outputPath, `// @ts-nocheck -- recursive JSON values are generator-owned.\n${generatedSource}`);
  }
} finally {
  rmSync(temporaryDirectory, { recursive: true, force: true });
}

function normalizeSchemaReferences(value, currentSchemaName) {
  if (Array.isArray(value)) {
    return value.map((item) => normalizeSchemaReferences(item, currentSchemaName));
  }
  if (value === null || typeof value !== "object") {
    return value;
  }
  const normalized = {};
  for (const [key, child] of Object.entries(value)) {
    if (key === "$id" || key === "$defs") {
      continue;
    }
    if (key === "$ref" && typeof child === "string") {
      normalized[key] = normalizeReference(child, currentSchemaName);
      continue;
    }
    normalized[key] = normalizeSchemaReferences(child, currentSchemaName);
  }
  return normalized;
}

function normalizeReference(reference, currentSchemaName) {
  if (reference.startsWith("#/$defs/")) {
    return definitionReference(currentSchemaName, reference.slice(1));
  }
  if (!reference.startsWith(localSchemaPrefix)) {
    return reference;
  }
  const [schemaUrl, fragment] = reference.split("#", 2);
  const schemaName = basename(schemaUrl);
  if (fragment?.startsWith("/$defs/") === true) {
    return definitionReference(schemaName, fragment);
  }
  return `./${schemaName}${fragment === undefined ? "" : `#${fragment}`}`;
}

function definitionReference(schemaName, fragment) {
  const pointer = fragment.slice("/$defs/".length).split("/");
  const definitionName = pointer.shift();
  if (definitionName === undefined || definitionName.length === 0) {
    throw new Error(`Invalid JSON Schema definition reference #${fragment}.`);
  }
  const remainder = pointer.length === 0 ? "" : `#/${pointer.join("/")}`;
  return `./${definitionFileName(schemaName, definitionName)}${remainder}`;
}

function definitionFileName(schemaName, definitionName) {
  const stem = schemaName.replace(/\.schema\.json$/, "");
  const safeDefinitionName = definitionName.replace(/[^A-Za-z0-9_.-]/g, "-");
  return `${stem}--${safeDefinitionName}.schema.json`;
}

function selectedEntries(value, names) {
  return Object.fromEntries(Object.entries(value).filter(([name]) => names.has(name)));
}
