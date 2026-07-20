import {
  ContractRegistry,
  type CreateSessionOperation,
  type ErrorEnvelope,
  type EventDelta,
  type ExecuteSessionCommandOperation,
  type ExportSessionReplayOperation,
  type GetRulesCatalogOperation,
  type GetSessionCatalogOperation,
  type GetSessionEventsOperation,
  type GetSessionMetadataOperation,
  type GetSessionProjectionOperation,
  type ReplayMetadata,
  type RulesCatalog,
  type SessionCommandOutcome,
  type SessionMetadata,
  type SessionPathParameters,
  type SessionProjection,
  jsonObject,
} from "./contract.js";

export interface HttpResult<T, Status extends number = number> {
  readonly status: Status;
  readonly rawBody: string;
  readonly body: T;
}

type OperationResponses<Operation> = Operation extends { responses: infer Responses }
  ? Responses
  : never;
type JsonResponseBody<Response> = Response extends {
  content: { "application/json": infer Body };
}
  ? Body
  : never;
type NumericResponseStatus<Operation> = Extract<keyof OperationResponses<Operation>, number>;
type KnownOperationHttpResult<Operation> = {
  [Status in NumericResponseStatus<Operation>]: HttpResult<
    JsonResponseBody<OperationResponses<Operation>[Status]>,
    Status
  >;
}[NumericResponseStatus<Operation>];
type DefaultOperationHttpResult<Operation> = "default" extends keyof OperationResponses<Operation>
  ? HttpResult<JsonResponseBody<OperationResponses<Operation>["default"]>>
  : never;
export type OperationHttpResult<Operation> =
  | KnownOperationHttpResult<Operation>
  | DefaultOperationHttpResult<Operation>;

export type CreateSessionHttpResult = OperationHttpResult<CreateSessionOperation>;
export type SessionMetadataHttpResult = OperationHttpResult<GetSessionMetadataOperation>;
export type SessionCommandHttpResult = OperationHttpResult<ExecuteSessionCommandOperation>;
export type SessionProjectionHttpResult = OperationHttpResult<GetSessionProjectionOperation>;
export type RulesCatalogHttpResult = OperationHttpResult<GetSessionCatalogOperation>;
export type EventDeltaHttpResult = OperationHttpResult<GetSessionEventsOperation>;
export type ReplayHttpResult = OperationHttpResult<ExportSessionReplayOperation>;

interface RawHttpResult {
  readonly status: number;
  readonly rawBody: string;
  readonly body: unknown;
}

export class ContractHttpClient {
  readonly #baseUrl: string;
  readonly #bearerToken: string | null;
  readonly #registry: ContractRegistry;

  constructor(baseUrl: string, bearerToken: string | null, registry: ContractRegistry) {
    this.#baseUrl = baseUrl.replace(/\/$/, "");
    this.#bearerToken = bearerToken;
    this.#registry = registry;
  }

  withToken(bearerToken: string | null): ContractHttpClient {
    return new ContractHttpClient(this.#baseUrl, bearerToken, this.#registry);
  }

  async createSession(
    body: CreateSessionOperation["requestBody"]["content"]["application/json"],
  ): Promise<CreateSessionHttpResult> {
    const raw = await this.#request("POST", "/sessions", body);
    if (raw.status === 201) {
      return result(
        raw,
        201,
        this.#registry.validate<SessionMetadata>("session-metadata.schema.json", raw.body),
      );
    }
    return this.#errorResult(raw);
  }

  async getMetadata(
    parameters: GetSessionMetadataOperation["parameters"]["path"],
  ): Promise<SessionMetadataHttpResult> {
    return this.#readResult<SessionMetadata>(
      await this.#request("GET", sessionPath(parameters)),
      "session-metadata.schema.json",
    );
  }

  async executeCommand(
    parameters: ExecuteSessionCommandOperation["parameters"]["path"],
    body: ExecuteSessionCommandOperation["requestBody"]["content"]["application/json"],
  ): Promise<SessionCommandHttpResult> {
    const raw = await this.#request("POST", `${sessionPath(parameters)}/commands`, body);
    switch (raw.status) {
      case 200:
        return result(
          raw,
          200,
          this.#registry.validate<SessionCommandOutcome>(
            "session-command-outcome.schema.json",
            raw.body,
          ),
        );
      case 400:
      case 401:
      case 403:
      case 409:
        return result(
          raw,
          raw.status,
          this.#registry.validate<ErrorEnvelope>("error-envelope.schema.json", raw.body),
        );
      case 422:
        return result(raw, 422, this.#validateRejectedCommand(raw.body));
      default:
        return this.#errorResult(raw);
    }
  }

  async getProjection(
    parameters: GetSessionProjectionOperation["parameters"]["path"],
  ): Promise<SessionProjectionHttpResult> {
    return this.#readResult<SessionProjection>(
      await this.#request("GET", `${sessionPath(parameters)}/projection`),
      "session-projection.schema.json",
    );
  }

  async getCatalog(
    parameters: GetSessionCatalogOperation["parameters"]["path"],
  ): Promise<RulesCatalogHttpResult> {
    return this.#readResult<RulesCatalog>(
      await this.#request("GET", `${sessionPath(parameters)}/catalog`),
      "rules-catalog.schema.json",
    );
  }

  async getGlobalCatalog(): Promise<OperationHttpResult<GetRulesCatalogOperation>> {
    return this.#readResult<RulesCatalog>(
      await this.#request("GET", "/rules-catalog"),
      "rules-catalog.schema.json",
    );
  }

  async getEvents(
    parameters: GetSessionEventsOperation["parameters"]["path"],
    queryParameters: GetSessionEventsOperation["parameters"]["query"],
  ): Promise<EventDeltaHttpResult> {
    const query = new URLSearchParams({ cursor: queryParameters.cursor });
    if (queryParameters.limit !== undefined) {
      query.set("limit", String(queryParameters.limit));
    }
    return this.#readResult<EventDelta>(
      await this.#request("GET", `${sessionPath(parameters)}/events?${query.toString()}`),
      "event-delta.schema.json",
    );
  }

  async exportReplay(
    parameters: ExportSessionReplayOperation["parameters"]["path"],
  ): Promise<ReplayHttpResult> {
    return this.#readResult<ReplayMetadata>(
      await this.#request("GET", `${sessionPath(parameters)}/replay`),
      "replay-metadata.schema.json",
    );
  }

  async probeMalformedSessionCommand(
    parameters: SessionPathParameters,
    body: unknown,
  ): Promise<HttpResult<ErrorEnvelope>> {
    return this.#errorResult(
      await this.#request("POST", `${sessionPath(parameters)}/commands`, body),
    );
  }

  async probeUnpublishedSupportProfile(
    parameters: SessionPathParameters,
  ): Promise<HttpResult<ErrorEnvelope>> {
    return this.#errorResult(
      await this.#request("GET", `${sessionPath(parameters)}/support-profile`),
    );
  }

  async #request(method: "GET" | "POST", path: string, body?: unknown): Promise<RawHttpResult> {
    const headers = new Headers({ Accept: "application/json" });
    if (this.#bearerToken !== null) {
      headers.set("Authorization", `Bearer ${this.#bearerToken}`);
    }
    if (body !== undefined) {
      headers.set("Content-Type", "application/json");
    }
    const request: RequestInit = { method, headers };
    if (body !== undefined) {
      request.body = JSON.stringify(body);
    }
    const response = await fetch(`${this.#baseUrl}${path}`, request);
    const rawBody = await response.text();
    const contentType = response.headers.get("content-type");
    if (contentType === null || !contentType.startsWith("application/json")) {
      throw new Error(`${method} ${path} returned non-JSON content.`);
    }
    const parsedBody: unknown = JSON.parse(rawBody);
    return { status: response.status, rawBody, body: parsedBody };
  }

  #readResult<T>(
    raw: RawHttpResult,
    schemaName: string,
  ): HttpResult<T, 200> | HttpResult<ErrorEnvelope> {
    if (raw.status === 200) {
      return result(raw, 200, this.#registry.validate<T>(schemaName, raw.body));
    }
    return this.#errorResult(raw);
  }

  #errorResult(raw: RawHttpResult): HttpResult<ErrorEnvelope> {
    return result(
      raw,
      raw.status,
      this.#registry.validate<ErrorEnvelope>("error-envelope.schema.json", raw.body),
    );
  }

  #validateRejectedCommand(body: unknown): SessionCommandOutcome | ErrorEnvelope {
    const payload = jsonObject(body, "HTTP 422 command response");
    if (payload.schema_version === "session-command-outcome-v3-contract") {
      return this.#registry.validate<SessionCommandOutcome>(
        "session-command-outcome.schema.json",
        body,
      );
    }
    if (payload.schema_version === "error-envelope-v1") {
      return this.#registry.validate<ErrorEnvelope>("error-envelope.schema.json", body);
    }
    throw new Error("HTTP 422 command response has an unknown schema version.");
  }
}

function sessionPath(parameters: SessionPathParameters): string {
  return `/sessions/${encodeURIComponent(parameters.session_id)}`;
}

function result<T, Status extends number>(
  raw: RawHttpResult,
  status: Status,
  body: T,
): HttpResult<T, Status> {
  return { status, rawBody: raw.rawBody, body };
}
