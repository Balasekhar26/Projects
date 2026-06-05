import type { Message } from "../types";

export const PANELS = [
  "Chat",
  "Projects",
  "Memory",
  "Tasks",
  "Finance",
  "Writing",
  "Research",
  "Simulation",
  "Tools",
  "Diagnostics",
  "Agents",
  "Settings",
];

export function initialMessages(): Message[] {
  return [{ role: "system", content: "Sekhar AI OS ready." }];
}
