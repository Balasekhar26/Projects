import type { CapabilityLadder, FreeStack, Health, Improvement, Reflection, SourcePolicy } from "../types";

type SettingsPanelProps = {
  health: Health | null;
  freeStack: FreeStack | null;
  capabilityLadder: CapabilityLadder | null;
  improvements: Improvement[];
  reflections: Reflection[];
  sourcePolicy: SourcePolicy | null;
};

export function SettingsPanel({
  health,
  freeStack,
  capabilityLadder,
  improvements,
  reflections,
  sourcePolicy,
}: SettingsPanelProps) {
  return (
    <section className="panelView">
      <h2>Settings</h2>
      <dl>
        <dt>Workspace</dt>
        <dd>{health?.workspace ?? "Loading"}</dd>
        <dt>Ollama</dt>
        <dd>{health ? (health.ollama_ok ? "Reachable" : health.ollama_message) : "Checking"}</dd>
        <dt>Models</dt>
        <dd>{health?.models.length ? health.models.join(", ") : "Built-in fallback ready"}</dd>
      </dl>
      {freeStack && (
        <>
          <h3>Free Stack Next Steps</h3>
          <ul className="nextSteps">
            {freeStack.next_best_steps.map((step, index) => (
              <li key={index}>{step}</li>
            ))}
          </ul>
        </>
      )}
      {capabilityLadder && (
        <>
          <h3>Capability Next Actions</h3>
          <ul className="nextSteps">
            {capabilityLadder.next_actions.map((step, index) => (
              <li key={index}>{step}</li>
            ))}
          </ul>
        </>
      )}
      <h3>Self-Improvement Backlog</h3>
      <div className="improvementList">
        {improvements.length ? improvements.map((item) => (
          <article key={item.id} className="improvementItem">
            <header>
              <strong>{item.title}</strong>
              <span>{item.status}</span>
            </header>
            <p>{item.motive}</p>
          </article>
        )) : <p>No improvement proposals saved yet.</p>}
      </div>
      <h3>Recent Reflections</h3>
      <div className="reflectionList">
        {reflections.length ? reflections.map((item) => (
          <article key={item.id} className={`reflectionItem ${item.outcome}`}>
            <header>
              <strong>{item.outcome}</strong>
              <span>{item.created_at}</span>
            </header>
            <p>{item.task}</p>
            <small>{item.lesson}</small>
          </article>
        )) : <p>No reflections recorded yet.</p>}
      </div>
      {sourcePolicy && (
        <>
          <h3>Source-First Boundaries</h3>
          <div className="policyPanel">
            <p>{sourcePolicy.summary}</p>
            <ul className="nextSteps">
              {sourcePolicy.hard_no.map((rule, index) => (
                <li key={index}>{rule}</li>
              ))}
            </ul>
          </div>
        </>
      )}
    </section>
  );
}
