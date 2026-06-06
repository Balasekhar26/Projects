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
  run("npm", ["install"], root);
}

const dashboard = join(root, "web-dashboard");
if (existsSync(join(dashboard, "package.json")) && !existsSync(join(dashboard, "node_modules"))) {
  run("npm", ["install"], dashboard);
}

console.log("AI Cyber Shield runtime is ready on " + process.platform + ".");
