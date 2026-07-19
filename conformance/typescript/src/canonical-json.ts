import { createHash } from "node:crypto";

export function canonicalJson(value: unknown): string {
  if (value === null) {
    return "null";
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new Error("Canonical JSON numbers must be finite.");
    }
    return JSON.stringify(value);
  }
  if (typeof value === "string") {
    return asciiJsonString(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJson(item)).join(",")}]`;
  }
  if (typeof value === "object") {
    const entries = Object.entries(value).sort(([left], [right]) =>
      compareUnicodeCodePoints(left, right),
    );
    return `{${entries
      .map(([key, item]) => `${asciiJsonString(key)}:${canonicalJson(item)}`)
      .join(",")}}`;
  }
  throw new Error(`Canonical JSON cannot encode ${typeof value}.`);
}

export function canonicalJsonSha256(value: unknown): string {
  return createHash("sha256").update(canonicalJson(value), "utf8").digest("hex");
}

function asciiJsonString(value: string): string {
  return JSON.stringify(value).replace(/[\u007f-\uffff]/g, (character) => {
    const codeUnit = character.charCodeAt(0).toString(16).padStart(4, "0");
    return `\\u${codeUnit}`;
  });
}

function compareUnicodeCodePoints(left: string, right: string): number {
  const leftCodePoints = Array.from(left, (character) => character.codePointAt(0)!);
  const rightCodePoints = Array.from(right, (character) => character.codePointAt(0)!);
  const sharedLength = Math.min(leftCodePoints.length, rightCodePoints.length);
  for (let index = 0; index < sharedLength; index += 1) {
    const difference = leftCodePoints[index]! - rightCodePoints[index]!;
    if (difference !== 0) {
      return difference;
    }
  }
  return leftCodePoints.length - rightCodePoints.length;
}
