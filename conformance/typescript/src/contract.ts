import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";

import {
  Ajv2020,
  type AnySchema,
  type ErrorObject,
  type ValidateFunction,
} from "ajv/dist/2020.js";
import * as addFormatsModule from "ajv-formats";
import type { FormatsPlugin } from "ajv-formats";

import type { components } from "./generated/openapi.js";

export type ErrorEnvelope = components["schemas"]["error-envelope.schema"];
export type EventDelta = components["schemas"]["event-delta.schema"];
export type ReplayMetadata = components["schemas"]["replay-metadata.schema"];
export type RulesCatalog = components["schemas"]["rules-catalog.schema"];
export type SessionCommandEnvelope = components["schemas"]["session-command-envelope.schema"];
export type SessionCommandOutcome = components["schemas"]["session-command-outcome.schema"];
export type SessionCreate = components["schemas"]["session-create.schema"];
export type SessionMetadata = components["schemas"]["session-metadata.schema"];
export type SessionProjection = components["schemas"]["session-projection.schema"];

export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

const REQUIRED_OPERATION_IDS = new Set([
  "createAuthoritativeSession",
  "getSessionMetadata",
  "executeSessionCommand",
  "getSessionProjection",
  "getSessionCatalog",
  "getSessionEvents",
  "exportSessionReplay",
]);
const addFormats = addFormatsModule.default as unknown as FormatsPlugin;

export class ContractRegistry {
  readonly #validatorsByName = new Map<string, ValidateFunction>();

  constructor(contractRoot: string) {
    assertPublishedOpenApi(contractRoot);
    const ajv = new Ajv2020({ allErrors: true, strict: false, validateSchema: true });
    addFormats(ajv);
    const schemaRoot = resolve(contractRoot, "schemas");
    const schemas = readdirSync(schemaRoot)
      .filter((name) => name.endsWith(".schema.json"))
      .sort()
      .map((name) => [name, parseJsonFile(resolve(schemaRoot, name))] as const);
    for (const [, schema] of schemas) {
      ajv.addSchema(schema as AnySchema);
    }
    for (const [name, schema] of schemas) {
      const schemaId = requiredString(schema, "$id");
      const validator = ajv.getSchema(schemaId);
      if (validator === undefined) {
        throw new Error(`JSON Schema validator was not registered for ${name}.`);
      }
      this.#validatorsByName.set(name, validator);
    }
  }

  validate<T>(schemaName: string, value: unknown): T {
    const validator = this.#validatorsByName.get(schemaName);
    if (validator === undefined) {
      throw new Error(`Unknown public schema ${schemaName}.`);
    }
    if (!validator(value)) {
      throw new Error(`${schemaName} rejected payload: ${formatAjvErrors(validator.errors)}`);
    }
    return value as T;
  }
}

export function parseJsonFile(path: string): JsonValue {
  return JSON.parse(readFileSync(path, "utf8")) as JsonValue;
}

export function jsonObject(value: unknown, label: string): { [key: string]: JsonValue } {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be a JSON object.`);
  }
  return value as { [key: string]: JsonValue };
}

export function jsonArray(value: unknown, label: string): JsonValue[] {
  if (!Array.isArray(value)) {
    throw new Error(`${label} must be a JSON array.`);
  }
  return value as JsonValue[];
}

export function requiredString(value: unknown, key: string): string {
  const field = jsonObject(value, "payload")[key];
  if (typeof field !== "string" || field.length === 0) {
    throw new Error(`Payload requires non-empty string ${key}.`);
  }
  return field;
}

function assertPublishedOpenApi(contractRoot: string): void {
  const document = jsonObject(parseJsonFile(resolve(contractRoot, "openapi.yaml")), "OpenAPI");
  if (document.openapi !== "3.1.0") {
    throw new Error("Conformance requires the published OpenAPI 3.1.0 document.");
  }
  const info = jsonObject(document.info, "OpenAPI info");
  if (info.version !== "2.0.0") {
    throw new Error("Conformance requires external contract version 2.0.0.");
  }
  const operationIds = new Set<string>();
  for (const pathValue of Object.values(jsonObject(document.paths, "OpenAPI paths"))) {
    const pathItem = jsonObject(pathValue, "OpenAPI path item");
    for (const methodValue of Object.values(pathItem)) {
      if (methodValue === null || typeof methodValue !== "object" || Array.isArray(methodValue)) {
        continue;
      }
      const operationId = (methodValue as { [key: string]: JsonValue }).operationId;
      if (typeof operationId === "string") {
        operationIds.add(operationId);
      }
    }
  }
  for (const operationId of REQUIRED_OPERATION_IDS) {
    if (!operationIds.has(operationId)) {
      throw new Error(`Published OpenAPI operation ${operationId} is missing.`);
    }
  }
}

function formatAjvErrors(errors: ErrorObject[] | null | undefined): string {
  if (errors === null || errors === undefined || errors.length === 0) {
    return "unknown validation error";
  }
  return errors
    .map((error) => `${error.instancePath || "/"} ${error.message ?? "is invalid"}`)
    .join("; ");
}
