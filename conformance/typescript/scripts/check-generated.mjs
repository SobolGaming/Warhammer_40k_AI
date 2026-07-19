import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const temporaryDirectory = mkdtempSync(resolve(tmpdir(), "core-v2-openapi-"));
const temporaryOutput = resolve(temporaryDirectory, "openapi.ts");
const committedOutput = resolve(packageRoot, "src/generated/openapi.ts");
const generator = resolve(packageRoot, "scripts/generate-models.mjs");

try {
  const generated = spawnSync(process.execPath, [generator, temporaryOutput], {
    cwd: packageRoot,
    encoding: "utf8",
  });
  if (generated.status !== 0) {
    process.stderr.write(generated.stdout);
    process.stderr.write(generated.stderr);
    process.exit(generated.status ?? 1);
  }
  if (readFileSync(temporaryOutput, "utf8") !== readFileSync(committedOutput, "utf8")) {
    process.stderr.write(
      "Generated OpenAPI models drifted; run `npm run generate` in conformance/typescript.\n",
    );
    process.exit(1);
  }
} finally {
  rmSync(temporaryDirectory, { recursive: true, force: true });
}
