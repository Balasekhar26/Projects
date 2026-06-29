import type { BuilderProfile, CapabilityLadder, CodexParityReport, EvolutionCycle, Skill } from "../types";

type AgentsPanelProps = {
  agentStatus: string;
  builderProfile: BuilderProfile | null;
  codexParity: CodexParityReport | null;
  evolutionRunning: boolean;
  evolutionCycle: EvolutionCycle | null;
  capabilityLadder: CapabilityLadder | null;
  skills: Skill[];
  onRunSelfEvolution: () => void;
  onSetSkillTrust: (skillId: string, trust: "draft" | "approved" | "trusted" | "disabled") => void;
};

function statusTone(status: string) {
  const value = status.toLowerCase();
  if (["ready", "done", "completed", "success", "trusted", "installed", "supported"].includes(value)) return "ready";
  if (["approved", "running", "active", "paused", "partial", "degraded", "fallback", "in_progress", "requested", "pending", "draft"].includes(value)) return "working";
  if (["missing", "needs_dependency", "failed", "blocked", "error", "rejected", "disabled", "manual_required"].includes(value)) return "missing";
  return "working";
}

function statusLabel(status: string) {
  const value = status.toLowerCase();
  if (value === "missing" || value === "needs_dependency") return "Missing";
  if (value === "pending" || value === "draft") return "Ready for review";
  if (value === "fallback") return "Fallback";
  if (value === "partial" || value === "degraded" || value === "in_progress") return "Partially ready";
  if (value === "failed" || value === "blocked" || value === "error" || value === "rejected") return "Needs attention";
  if (value === "disabled") return "Disabled";
  return status.replace(/_/g, " ");
}

export function AgentsPanel({
  agentStatus,
  builderProfile,
  codexParity,
  evolutionRunning,
  evolutionCycle,
  capabilityLadder,
  skills,
  onRunSelfEvolution,
  onSetSkillTrust,
}: AgentsPanelProps) {
  return (
    <section className="panelView">
      <h2>Agents</h2>
      <p>Planner, memory, safety, evaluator, coder, browser, desktop, file, terminal, vision, voice, researcher, and self-improver are wired in the backend graph.</p>
      <p>Kattappa now takes one plain order by message or voice, then automatically replies, guides, or asks approval before running a risky action.</p>
      <p>Current route: {agentStatus}</p>
      {codexParity && (
        <div className="builderPanel">
          <h3>{codexParity.name}</h3>
          <p>{codexParity.truth_boundary}</p>
          <div className="maturityBar" aria-label="Codex workflow parity">
            <span style={{ width: `${codexParity.parity_percent}%` }} />
          </div>
          <p>{codexParity.parity_percent}% local/free workflow parity across {codexParity.items.length} capability points.</p>
          <div className="capabilityGrid">
            {codexParity.items.map((item) => (
              <article key={item.key} className={`capability ${statusTone(item.status)}`}>
                <strong>{item.codex_can}</strong>
                <span>{item.score}% / {statusLabel(item.status)}</span>
                <p>{item.kattappa_equivalent}</p>
                <small>{item.next_move}</small>
              </article>
            ))}
          </div>
          <h3>Order Contract</h3>
          <ul className="nextSteps">
            {codexParity.user_order_contract.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
          {codexParity.strongest_gaps.length > 0 && (
            <>
              <h3>Next Rival Moves</h3>
              <ul className="nextSteps">
                {codexParity.next_builds.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
      {builderProfile && (
        <div className="builderPanel">
          <h3>{builderProfile.name}</h3>
          <p>{builderProfile.truth_boundary}</p>
          <div className="capabilityGrid">
            {builderProfile.capabilities.slice(0, 6).map((capability) => (
              <article key={capability} className="capability ready">
                <strong>{capability}</strong>
                <span>Built in</span>
              </article>
            ))}
          </div>
          {builderProfile.local_builder_analytics && (
            <>
              <h3>Local Builder Profile</h3>
              <p>{builderProfile.local_builder_analytics.privacy_boundary}</p>
              <div className="evolutionStatus">
                <strong>{builderProfile.local_builder_analytics.archetype}</strong>
                <span>
                  {builderProfile.local_builder_analytics.repo_activity.changed_files} changed files /{" "}
                  {builderProfile.local_builder_analytics.repo_activity.recent_commits_30d} recent commits
                </span>
              </div>
              <div className="capabilityGrid">
                {builderProfile.local_builder_analytics.dimensions.map((dimension) => (
                  <article key={dimension.key} className="capability ready">
                    <strong>{dimension.label}</strong>
                    <span>{dimension.score}%</span>
                    <p>{dimension.evidence}</p>
                  </article>
                ))}
              </div>
              <h3>Growth Edges</h3>
              <ul className="nextSteps">
                {builderProfile.local_builder_analytics.growth_edges.map((edge, index) => (
                  <li key={index}>{edge}</li>
                ))}
              </ul>
              <h3>Free Replacements Added</h3>
              <div className="scoutList">
                {builderProfile.local_builder_analytics.free_replacements.map((item) => (
                  <article key={item.source} className="scoutItem ready">
                    <header>
                      <strong>{item.fully_free_replacement}</strong>
                      <span>{item.added_to}</span>
                    </header>
                    <p>{item.why_it_improves_products}</p>
                    <small>{item.source}: {item.not_added_reason}</small>
                  </article>
                ))}
              </div>
            </>
          )}
        </div>
      )}
      <button onClick={onRunSelfEvolution} disabled={evolutionRunning}>
        {evolutionRunning ? "Running Self-Evolution..." : "Run Self-Evolution Cycle"}
      </button>
      {evolutionCycle && (
        <div className="evolutionStatus">
          <strong>Last scan</strong>
          <span>{evolutionCycle.reflections_scanned} reflections, {evolutionCycle.draft_skills_created?.length ?? 0} draft skills</span>
          <p>{evolutionCycle.next_step}</p>
        </div>
      )}
      {capabilityLadder && (
        <>
          <h3>{capabilityLadder.label}</h3>
          <p>{capabilityLadder.truth_boundary}</p>
          <div className="maturityBar" aria-label="Assistant maturity">
            <span style={{ width: `${capabilityLadder.maturity_percent}%` }} />
          </div>
          <p>{capabilityLadder.maturity_percent}% assistant maturity using free/local components.</p>
          <div className="ladderList">
            {capabilityLadder.levels.map((level) => (
              <article key={level.key} className={`ladderItem ${statusTone(level.status)}`}>
                <header>
                  <strong>{level.key} {level.name}</strong>
                  <span>{statusLabel(level.status)}</span>
                </header>
                <p>{level.description}</p>
                <small>{level.evidence}</small>
              </article>
            ))}
          </div>
        </>
      )}
      <h3>Skill Library</h3>
      <div className="skillList">
        {skills.length ? skills.map((skill) => (
          <article key={skill.id} className={`skillItem ${statusTone(skill.trust)}`}>
            <header>
              <strong>{skill.name}</strong>
              <span>{statusLabel(skill.trust)}</span>
            </header>
            <p>{skill.trigger}</p>
            <small>{skill.success_count} success / {skill.failure_count} failure - {skill.risk} risk</small>
            <div className="skillActions">
              <SkillTrustActions skill={skill} onSetSkillTrust={onSetSkillTrust} />
            </div>
          </article>
        )) : <p>No reusable skills yet. Run real tasks, record reflections, then run self-evolution.</p>}
      </div>
    </section>
  );
}

function SkillTrustActions({
  skill,
  onSetSkillTrust,
}: {
  skill: Skill;
  onSetSkillTrust: (skillId: string, trust: "draft" | "approved" | "trusted" | "disabled") => void;
}) {
  if (skill.trust === "draft") {
    return (
      <>
        <button onClick={() => onSetSkillTrust(skill.id, "approved")}>Approve</button>
        <button onClick={() => onSetSkillTrust(skill.id, "disabled")}>Disable</button>
      </>
    );
  }
  if (skill.trust === "approved") {
    return <span className="actionStatus working">Approved</span>;
  }
  if (skill.trust === "trusted") {
    return <span className="actionStatus ready">Trusted</span>;
  }
  return <button onClick={() => onSetSkillTrust(skill.id, "draft")}>Restore</button>;
}
