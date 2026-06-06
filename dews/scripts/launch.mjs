import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));

function run(command, args, cwd) {
  const result = spawnSync(command, args, { cwd, stdio: "inherit", shell: process.platform === "win32" });
  if (result.status !== 0) process.exit(result.status ?? 1);
}

if (!existsSync(join(root, "node_modules"))) {
  console.error("Dependencies are missing. Run: npm run setup");
  process.exit(1);
}

run("npm", ["run", "build"], root);
run("npm", ["start"], root);
