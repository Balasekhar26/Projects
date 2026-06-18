import type { Message } from "../types";

export const PANELS = [
  "Diagnostics",
];

export function initialMessages(): Message[] {
  return [{ role: "system", content: "Kattappa AI OS ready. All capabilities — projects, memory, tasks, research, writing, finance, simulation, tools, agents, cluster — activate automatically. Just talk to me." }];
}
