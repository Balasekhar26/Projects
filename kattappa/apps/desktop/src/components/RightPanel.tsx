import type { Approval, CapabilityLadder, FreeStack, Health } from "../types";

type RightPanelProps = {
  agentStatus: string;
  health: Health | null;
  freeStack: FreeStack | null;
  capabilityLadder: CapabilityLadder | null;
  activeApproval?: Approval;
  approvalNotice?: {
    tone: "danger" | "working" | "ready";
    title: string;
    message: string;
  } | null;
  onDecideApproval: (approvalId: string, status: "approved" | "rejected") => void;
};

export function RightPanel({
  agentStatus,
  health,
  freeStack,
  capabilityLadder,
  activeApproval,
  approvalNotice,
  onDecideApproval,
}: RightPanelProps) {
  return (
    <aside className="rightPanel">
      <h2>Agent Status</h2>
      <dl>
        <dt>Input</dt>
        <dd>Message or voice order</dd>
        <dt>Backend</dt>
        <dd>{agentStatus}</dd>
        <dt>Ollama</dt>
        <dd>{health ? (health.ollama_ok ? "Reachable" : "Ready via built-in fallback") : "Checking"}</dd>
        <dt>Safety</dt>
        <dd>Human approval enabled</dd>
        <dt>Memory</dt>
        <dd>{health ? `${health.memory_count} memories` : "Chroma + SQLite"}</dd>
        <dt>Automation</dt>
        <dd>Browser ready, desktop gated</dd>
        <dt>Models</dt>
        <dd>{health?.models.length ? health.models.slice(0, 3).join(", ") : "Built-in fallback ready"}</dd>
        <dt>Free Stack</dt>
        <dd>{freeStack ? `${freeStack.ready_count}/${freeStack.total_count} ready` : "Checking"}</dd>
        <dt>Maturity</dt>
        <dd>{capabilityLadder ? `${capabilityLadder.maturity_percent}%` : "Checking"}</dd>
      </dl>
      <div className={`approvalBox ${activeApproval ? "danger" : approvalNotice?.tone ?? "ready"}`}>
        <h3>Approval Panel</h3>
        {activeApproval ? (
          <>
            <p>{activeApproval.action}</p>
            <dl className="approvalMeta">
              <dt>Risk</dt>
              <dd>{activeApproval.risk}</dd>
              <dt>Status</dt>
              <dd>Needs approval</dd>
            </dl>
            <div className="approvalActions">
              <button onClick={() => onDecideApproval(activeApproval.id, "approved")}>Approve</button>
              <button onClick={() => onDecideApproval(activeApproval.id, "rejected")}>Reject</button>
            </div>
          </>
        ) : approvalNotice ? (
          <>
            <strong className="approvalStateTitle">{approvalNotice.title}</strong>
            <p>{approvalNotice.message}</p>
          </>
        ) : (
          <>
            <strong className="approvalStateTitle">All Clear</strong>
            <p>No actions are waiting for approval. Risky actions will pause here before they run.</p>
          </>
        )}
      </div>
    </aside>
  );
}
