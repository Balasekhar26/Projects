import type { Health } from "../types";

type MemoryPanelProps = {
  health: Health | null;
  onRefreshHealth: () => void;
};

export function MemoryPanel({ health, onRefreshHealth }: MemoryPanelProps) {
  return (
    <section className="panelView">
      <h2>Memory</h2>
      <p>{health ? `${health.memory_count} memories stored in Chroma + SQLite.` : "Memory status is loading."}</p>
      <p>Saved chats are now searched locally and added to the agent context when they match the current request.</p>
      <button onClick={onRefreshHealth}>Refresh Memory Count</button>
    </section>
  );
}
