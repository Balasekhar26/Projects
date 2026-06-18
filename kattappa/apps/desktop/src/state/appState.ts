import type { Message } from "../types";

export const PANELS = [
  "Tools",
  "Cluster",
  "Diagnostics",
  "Agents",
  "Settings",
];

export function initialMessages(): Message[] {
  return [{ role: "system", content: "Kattappa AI OS ready." }];
}
