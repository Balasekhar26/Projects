import type { Message } from "../types";

export const PANELS = [
  "Projects",
  "Jarvis HUD",
  "Memory",
  "Tasks",
  "Finance",
  "Writing",
  "Research",
  "Simulation",
  "Tools",
  "Cluster",
  "Diagnostics",
  "Agents",
  "Settings",
];

export function initialMessages(): Message[] {
  return [{ role: "system", content: "Kattappa AI OS ready." }];
}
