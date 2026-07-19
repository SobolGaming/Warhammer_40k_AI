import type {
  ErrorEnvelope,
  EventDelta,
  JsonValue,
  ReplayMetadata,
  RulesCatalog,
  SessionCommandEnvelope,
  SessionCommandOutcome,
  SessionCreate,
  SessionMetadata,
  SessionProjection,
} from "./contract.js";

export interface HttpResult<T> {
  readonly status: number;
  readonly rawBody: string;
  readonly body: T;
}

export class ContractHttpClient {
  readonly #baseUrl: string;
  readonly #bearerToken: string | null;

  constructor(baseUrl: string, bearerToken: string | null) {
    this.#baseUrl = baseUrl.replace(/\/$/, "");
    this.#bearerToken = bearerToken;
  }

  withToken(bearerToken: string | null): ContractHttpClient {
    return new ContractHttpClient(this.#baseUrl, bearerToken);
  }

  createSession(body: SessionCreate): Promise<HttpResult<SessionMetadata | ErrorEnvelope>> {
    return this.request("POST", "/sessions", body as unknown as JsonValue);
  }

  getMetadata(sessionId: string): Promise<HttpResult<SessionMetadata | ErrorEnvelope>> {
    return this.request("GET", `/sessions/${encodeURIComponent(sessionId)}`);
  }

  executeCommand(
    sessionId: string,
    body: SessionCommandEnvelope,
  ): Promise<HttpResult<SessionCommandOutcome | ErrorEnvelope>> {
    return this.request(
      "POST",
      `/sessions/${encodeURIComponent(sessionId)}/commands`,
      body as unknown as JsonValue,
    );
  }

  getProjection(sessionId: string): Promise<HttpResult<SessionProjection | ErrorEnvelope>> {
    return this.request("GET", `/sessions/${encodeURIComponent(sessionId)}/projection`);
  }

  getCatalog(sessionId: string): Promise<HttpResult<RulesCatalog | ErrorEnvelope>> {
    return this.request("GET", `/sessions/${encodeURIComponent(sessionId)}/catalog`);
  }

  getGlobalCatalog(): Promise<HttpResult<RulesCatalog | ErrorEnvelope>> {
    return this.request("GET", "/rules-catalog");
  }

  getEvents(
    sessionId: string,
    cursor: string,
    limit?: number,
  ): Promise<HttpResult<EventDelta | ErrorEnvelope>> {
    const query = new URLSearchParams({ cursor });
    if (limit !== undefined) {
      query.set("limit", String(limit));
    }
    return this.request(
      "GET",
      `/sessions/${encodeURIComponent(sessionId)}/events?${query.toString()}`,
    );
  }

  exportReplay(sessionId: string): Promise<HttpResult<ReplayMetadata | ErrorEnvelope>> {
    return this.request("GET", `/sessions/${encodeURIComponent(sessionId)}/replay`);
  }

  async request<T>(method: "GET" | "POST", path: string, body?: JsonValue): Promise<HttpResult<T>> {
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
    return {
      status: response.status,
      rawBody,
      body: JSON.parse(rawBody) as T,
    };
  }
}
