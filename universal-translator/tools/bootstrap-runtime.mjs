import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));

for (const path of [
  join(root, ".ult-runtime"),
  join(root, ".ult-runtime", "temp"),
  join(root, "models", "voice-profiles"),
  join(root, "models", "argos"),
]) {
  mkdirSync(path, { recursive: true });
}

console.log("ULT runtime directories are ready on " + process.platform + ".");
