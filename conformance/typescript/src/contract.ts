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

import type { components, paths } from "./generated/openapi.js";

type JsonResponseBody<Response> = Response extends {
  content: { "application/json": infer Body };
}
  ? Body
  : never;

export type GetRulesCatalogOperation = paths["/rules-catalog"]["get"];
export type CreateSessionOperation = paths["/sessions"]["post"];
export type GetSessionMetadataOperation = paths["/sessions/{session_id}"]["get"];
export type ExecuteSessionCommandOperation = paths["/sessions/{session_id}/commands"]["post"];
export type GetSessionProjectionOperation = paths["/sessions/{session_id}/projection"]["get"];
export type GetSessionCatalogOperation = paths["/sessions/{session_id}/catalog"]["get"];
export type GetSessionEventsOperation = paths["/sessions/{session_id}/events"]["get"];
export type ExportSessionReplayOperation = paths["/sessions/{session_id}/replay"]["get"];

export type SessionCreate =
  CreateSessionOperation["requestBody"]["content"]["application/json"];
export type SessionMetadata = JsonResponseBody<CreateSessionOperation["responses"][201]>;
export type SessionCommandEnvelope =
  ExecuteSessionCommandOperation["requestBody"]["content"]["application/json"];
export type ParameterizedPayload = Extract<
  SessionCommandEnvelope["submission"],
  { submission_kind: "parameterized_payload" }
>["payload"];
export type DeploymentPlacementPayload = Extract<
  ParameterizedPayload,
  { proposal_kind: "deployment_placement" }
>;
export type SessionCommandOutcome = JsonResponseBody<
  ExecuteSessionCommandOperation["responses"][200]
>;
export type SessionProjection = JsonResponseBody<
  GetSessionProjectionOperation["responses"][200]
>;
export type RulesCatalog = JsonResponseBody<GetSessionCatalogOperation["responses"][200]>;
export type EventDelta = JsonResponseBody<GetSessionEventsOperation["responses"][200]>;
export type ReplayMetadata = JsonResponseBody<ExportSessionReplayOperation["responses"][200]>;
export type ErrorEnvelope = JsonResponseBody<
  ExecuteSessionCommandOperation["responses"][400]
>;
export type InteractionRequest =
  | components["schemas"]["AnnotatedDecisionRequest"]
  | NonNullable<SessionProjection["projection"]["pending_decision"]>;
export type FiniteSubmission = components["schemas"]["FiniteSubmission"];
export type ParameterizedSubmission = components["schemas"]["ParameterizedSubmission"];
export type InteractionConformance = components["schemas"]["InteractionConformance"];

export type SessionPathParameters = GetSessionMetadataOperation["parameters"]["path"];
export type SessionEventQuery = GetSessionEventsOperation["parameters"]["query"];

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
  readonly #ajv: Ajv2020;
  readonly #schemaIdByName = new Map<string, string>();
  readonly #validatorsByName = new Map<string, ValidateFunction>();

  constructor(contractRoot: string) {
    assertPublishedOpenApi(contractRoot);
    const ajv = new Ajv2020({ allErrors: true, strict: false, validateSchema: true });
    this.#ajv = ajv;
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
      this.#schemaIdByName.set(name, schemaId);
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

  validateReference<T>(schemaReference: string, value: unknown): T {
    const [schemaName, fragment] = schemaReference.split("#", 2);
    if (schemaName === undefined) {
      throw new Error(`Invalid public schema reference ${schemaReference}.`);
    }
    const schemaId = this.#schemaIdByName.get(schemaName);
    if (schemaId === undefined) {
      throw new Error(`Unknown public schema reference ${schemaReference}.`);
    }
    const validator = this.#ajv.getSchema(
      fragment === undefined ? schemaId : `${schemaId}#${fragment}`,
    );
    if (validator === undefined) {
      throw new Error(`Unknown public schema reference ${schemaReference}.`);
    }
    if (!validator(value)) {
      throw new Error(
        `${schemaReference} rejected payload: ${formatAjvErrors(validator.errors)}`,
      );
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
  if (info.version !== "3.0.0") {
    throw new Error("Conformance requires external contract version 3.0.0.");
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
