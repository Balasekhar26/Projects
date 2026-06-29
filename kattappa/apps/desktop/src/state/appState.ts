import type { Message } from "../types";

export const PANELS = [
  "Diagnostics",
  "Projects",
  "Workspaces",
  "Memory",
  "Tasks",
  "Writing",
  "Research",
  "Simulation",
  "Tools",
  "Cluster",
  "Agents",
  "Settings",
];

export function initialMessages(): Message[] {
  return [{ role: "system", content: "Kattappa AI OS ready. All capabilities — projects, memory, tasks, research, writing, finance, simulation, tools, agents, cluster — activate automatically. Just talk to me." }];
}
