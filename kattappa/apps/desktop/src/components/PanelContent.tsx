import type {
  BuilderProfile,
  CapabilityLadder,
  CodexParityReport,
  FreeCapability,
  FreeStack,
  Health,
  Improvement,
  InstallResult,
  LongTask,
  ProjectEcosystem,
  ProjectIndex,
  Reflection,
  ResearchResult,
  ResumeResult,
  SimulationResult,
  Skill,
  SourcePolicy,
  ToolAdoptionJob,
  ToolScoutStatus,
  WritingResult,
} from "../types";
import { FinancePlayground } from "./FinancePlayground";
import { SystemDiagnostics } from "./SystemDiagnostics";

type PanelContentProps = {
  activePanel: string;
  health: Health | null;
  freeStack: FreeStack | null;
  sourcePolicy: SourcePolicy | null;
  toolScout: ToolScoutStatus | null;
  toolAdoptions: ToolAdoptionJob[];
  capabilityLadder: CapabilityLadder | null;
  improvements: Improvement[];
  skills: Skill[];
  reflections: Reflection[];
  evolutionCycle: { reflections_scanned: number; draft_skills_created: { skill_id: string; approval_id: string; trigger: string }[]; next_step: string } | null;
  evolutionRunning: boolean;
  builderProfile: BuilderProfile | null;
  codexParity: CodexParityReport | null;
  projectEcosystem: ProjectEcosystem | null;
  projectIndex: ProjectIndex | null;
  resumeResult: ResumeResult | null;
  installResult: InstallResult | null;
  longTasks: LongTask[];
  taskDraft: { title: string; goal: string; priority: string };
  writingDraft: { text: string; tone: string };
  writingResult: WritingResult | null;
  researchDraft: { url: string; goal: string };
  researchResult: ResearchResult | null;
  simulationDraft: { seed: string; horizon: string };
  simulationResult: SimulationResult | null;
  agentStatus: string;
  onTaskDraftChange: (draft: { title: string; goal: string; priority: string }) => void;
  onWritingDraftChange: (draft: { text: string; tone: string }) => void;
  onResearchDraftChange: (draft: { url: string; goal: string }) => void;
  onSimulationDraftChange: (draft: { seed: string; horizon: string }) => void;
  onRefreshHealth: () => void;
  onRefreshLongTasks: () => void;
  onCreateLongTask: () => void;
  onUpdateLongTask: (taskId: string, update: Partial<Pick<LongTask, "status" | "progress" | "next_step">>) => void;
  onContinueLongTask: (task: LongTask) => void;
  onPlanLongTaskResume: (task: LongTask) => void;
  onCheckWriting: () => void;
  onRewriteWriting: () => void;
  onExtractResearch: () => void;
  onRunSimulation: () => void;
  onRequestMissingInstalls: () => void;
  onRunManualToolScout: () => void;
  onStartToolAdoption: (reportId: string) => void;
  onRunSelfEvolution: () => void;
  onSetSkillTrust: (skillId: string, trust: "draft" | "approved" | "trusted" | "disabled") => void;
};

export function PanelContent(props: PanelContentProps) {
  if (props.activePanel === "Memory") {
    return <MemoryPanel health={props.health} onRefreshHealth={props.onRefreshHealth} />;
  }
  if (props.activePanel === "Tasks") {
    return <TasksPanel {...props} />;
  }
  if (props.activePanel === "Finance") {
    return <FinancePlayground />;
  }
  if (props.activePanel === "Writing") {
    return <WritingPanel {...props} />;
  }
  if (props.activePanel === "Research") {
    return <ResearchPanel {...props} />;
  }
  if (props.activePanel === "Simulation") {
    return <SimulationPanel {...props} />;
  }
  if (props.activePanel === "Tools") {
    return <ToolsPanel {...props} />;
  }
  if (props.activePanel === "Diagnostics") {
    return <SystemDiagnostics />;
  }
  if (props.activePanel === "Agents") {
    return <AgentsPanel {...props} />;
  }
  if (props.activePanel === "Settings") {
    return <SettingsPanel {...props} />;
  }
  return <ProjectsPanel {...props} />;
}

function MemoryPanel({ health, onRefreshHealth }: { health: Health | null; onRefreshHealth: () => void }) {
  return (
    <section className="panelView">
      <h2>Memory</h2>
      <p>{health ? `${health.memory_count} memories stored in Chroma + SQLite.` : "Memory status is loading."}</p>
      <p>Saved chats are now searched locally and added to the agent context when they match the current request.</p>
      <button onClick={onRefreshHealth}>Refresh Memory Count</button>
    </section>
  );
}

function TasksPanel({
  longTasks,
  taskDraft,
  resumeResult,
  onTaskDraftChange,
  onCreateLongTask,
  onRefreshLongTasks,
  onContinueLongTask,
  onPlanLongTaskResume,
  onUpdateLongTask,
}: PanelContentProps) {
  return (
    <section className="panelView">
      <h2>Long Tasks</h2>
      <p>Use this for work that should survive restarts: builds, research, debugging, project upgrades, and anything you want Kattappa AI OS to resume later.</p>
      <div className="taskComposer">
        <input
          value={taskDraft.title}
          onChange={(event) => onTaskDraftChange({ ...taskDraft, title: event.target.value })}
          placeholder="Task title"
        />
        <textarea
          value={taskDraft.goal}
          onChange={(event) => onTaskDraftChange({ ...taskDraft, goal: event.target.value })}
          placeholder="Goal and important details"
          rows={3}
        />
        <div className="taskControls">
          <select
            value={taskDraft.priority}
            onChange={(event) => onTaskDraftChange({ ...taskDraft, priority: event.target.value })}
          >
            <option value="normal">Normal</option>
            <option value="high">High</option>
            <option value="low">Low</option>
          </select>
          <button onClick={onCreateLongTask}>Save Long Task</button>
          <button onClick={onRefreshLongTasks}>Refresh</button>
        </div>
      </div>
      <div className="taskList">
        {longTasks.length ? longTasks.map((task) => (
          <article key={task.id} className={`taskItem ${task.status}`}>
            <header>
              <strong>{task.title}</strong>
              <span>{task.status} / {task.priority}</span>
            </header>
            <p>{task.goal}</p>
            <dl>
              <dt>Progress</dt>
              <dd>{task.progress || "Not recorded yet"}</dd>
              <dt>Next</dt>
              <dd>{task.next_step || "Ask for the next approved step"}</dd>
            </dl>
            <div className="taskActions">
              <button onClick={() => onContinueLongTask(task)}>Continue</button>
              <button onClick={() => onPlanLongTaskResume(task)}>Plan Resume</button>
              {task.status !== "done" && (
                <button onClick={() => onUpdateLongTask(task.id, { status: "done", progress: task.progress || "Completed from the Tasks tab." })}>Done</button>
              )}
              {task.status === "active" ? (
                <button onClick={() => onUpdateLongTask(task.id, { status: "paused" })}>Pause</button>
              ) : (
                <button onClick={() => onUpdateLongTask(task.id, { status: "active" })}>Resume</button>
              )}
            </div>
          </article>
        )) : <p>No long tasks saved yet.</p>}
      </div>
      {resumeResult && (
        <div className="resumePanel">
          <h3>Resume Plan</h3>
          <p>{resumeResult.task.title}</p>
          <ol>
            {resumeResult.next_steps.map((step, index) => (
              <li key={index}>{step}</li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}

function WritingPanel({ writingDraft, writingResult, onWritingDraftChange, onCheckWriting, onRewriteWriting }: PanelContentProps) {
  return (
    <section className="panelView">
      <h2>Writing</h2>
      <p>Harper is used when available; the built-in local checker stays ready as the fallback.</p>
      <div className="taskComposer">
        <textarea
          value={writingDraft.text}
          onChange={(event) => onWritingDraftChange({ ...writingDraft, text: event.target.value })}
          placeholder="Paste email, resume text, notes, or documentation"
          rows={7}
        />
        <div className="taskControls">
          <select
            value={writingDraft.tone}
            onChange={(event) => onWritingDraftChange({ ...writingDraft, tone: event.target.value })}
          >
            <option value="clear">Clear</option>
            <option value="professional">Professional</option>
            <option value="friendly">Friendly</option>
            <option value="concise">Concise</option>
          </select>
          <button onClick={onCheckWriting}>Check</button>
          <button onClick={onRewriteWriting}>Rewrite</button>
        </div>
      </div>
      {writingResult && (
        <div className="toolResult">
          <header>
            <strong>{writingResult.engine}</strong>
            <span>{writingResult.issue_count ?? writingResult.grammar?.issue_count ?? 0} issues</span>
          </header>
          {writingResult.corrected_text && <p>{writingResult.corrected_text}</p>}
          {writingResult.rewritten_text && <p>{writingResult.rewritten_text}</p>}
          {writingResult.note && <small>{writingResult.note}</small>}
        </div>
      )}
    </section>
  );
}

function ResearchPanel({ researchDraft, researchResult, onResearchDraftChange, onExtractResearch }: PanelContentProps) {
  return (
    <section className="panelView">
      <h2>Research</h2>
      <p>ScrapeGraphAI is optional; plain HTML extraction works locally with the existing backend.</p>
      <div className="taskComposer">
        <input
          value={researchDraft.url}
          onChange={(event) => onResearchDraftChange({ ...researchDraft, url: event.target.value })}
          placeholder="https://example.com"
        />
        <textarea
          value={researchDraft.goal}
          onChange={(event) => onResearchDraftChange({ ...researchDraft, goal: event.target.value })}
          rows={3}
        />
        <div className="taskControls">
          <button onClick={onExtractResearch}>Extract</button>
        </div>
      </div>
      {researchResult && (
        <div className="toolResult">
          <header>
            <strong>{String(researchResult.engine ?? "web research")}</strong>
            <span>{String(researchResult.title ?? researchResult.url ?? "result")}</span>
          </header>
          {typeof researchResult.summary_text === "string" && <p>{researchResult.summary_text}</p>}
          <pre>{JSON.stringify(researchResult, null, 2)}</pre>
        </div>
      )}
    </section>
  );
}

function SimulationPanel({ simulationDraft, simulationResult, onSimulationDraftChange, onRunSimulation }: PanelContentProps) {
  return (
    <section className="panelView">
      <h2>Simulation</h2>
      <p>MiroFish stays optional; the built-in lab can still sketch scenario outcomes without external code.</p>
      <div className="taskComposer">
        <textarea
          value={simulationDraft.seed}
          onChange={(event) => onSimulationDraftChange({ ...simulationDraft, seed: event.target.value })}
          placeholder="Describe a project decision, launch, feature, or what-if scenario"
          rows={5}
        />
        <div className="taskControls">
          <select
            value={simulationDraft.horizon}
            onChange={(event) => onSimulationDraftChange({ ...simulationDraft, horizon: event.target.value })}
          >
            <option value="short">Short</option>
            <option value="medium">Medium</option>
            <option value="long">Long</option>
          </select>
          <button onClick={onRunSimulation}>Run</button>
        </div>
      </div>
      {simulationResult && (
        <div className="toolResult">
          <header>
            <strong>{simulationResult.engine}</strong>
            <span>{simulationResult.scenario.horizon}</span>
          </header>
          <p>{simulationResult.warning}</p>
          <div className="scoutList">
            {simulationResult.predictions.map((item) => (
              <article key={item.outcome} className="scoutItem">
                <header>
                  <strong>{item.outcome}</strong>
                  <span>{item.confidence}</span>
                </header>
                <p>{item.signal}</p>
              </article>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function ToolsPanel({
  freeStack,
  sourcePolicy,
  toolScout,
  toolAdoptions,
  installResult,
  onRequestMissingInstalls,
  onRunManualToolScout,
  onStartToolAdoption,
}: PanelContentProps) {
  return (
    <section className="panelView">
      <h2>Tools</h2>
      {freeStack && (
        <p>
          {freeStack.installed_count ?? freeStack.ready_count}/{freeStack.total_count} adapters installed.
          {" "}
          {freeStack.fallback_count ?? 0} using safe fallback.
          {" "}
          {freeStack.missing_count ?? 0} unavailable.
        </p>
      )}
      {sourcePolicy && (
        <div className="policyPanel">
          <h3>Source-First Rule</h3>
          <p>{sourcePolicy.summary}</p>
          <ul className="nextSteps">
            {sourcePolicy.rules.slice(0, 4).map((rule, index) => (
              <li key={index}>{rule}</li>
            ))}
          </ul>
        </div>
      )}
      <button onClick={onRequestMissingInstalls}>Check Tools & Request Install Approval</button>
      <button onClick={onRunManualToolScout}>Run Free Tool Scout</button>
      {toolScout && (
        <div className="scoutPanel">
          <h3>Background Free Tool Scout</h3>
          <p>{toolScout.copying_rule}</p>
          <div className="scoutList">
            {toolScout.reports.length ? toolScout.reports.map((report) => (
              <article key={report.id} className={`scoutItem ${statusTone(report.status)}`}>
                <header>
                  <strong>{report.capability}</strong>
                  <span>{report.status}</span>
                </header>
                <p>{report.recommendation}</p>
                <small>{report.source}</small>
                <small>{report.license_note}</small>
                <div className="scoutActions">
                  <button onClick={() => onStartToolAdoption(report.id)}>Observe & Plan</button>
                </div>
              </article>
            )) : <p>No scout reports yet. It will run quietly after meaningful tasks.</p>}
          </div>
          {toolAdoptions.length ? (
            <>
              <h3>Adoption Pipeline</h3>
              <div className="scoutList">
                {toolAdoptions.map((job) => (
                  <article key={job.id} className={`scoutItem ${statusTone(job.status)}`}>
                    <header>
                      <strong>{job.status}</strong>
                      <span>{job.updated_at}</span>
                    </header>
                    {job.install_observation && <p>{job.install_observation}</p>}
                    {job.build_own_result && <small>{job.build_own_result}</small>}
                    {job.test_result && <small>{job.test_result}</small>}
                  </article>
                ))}
              </div>
            </>
          ) : null}
        </div>
      )}
      {installResult && (
        <div className="installPanel">
          <h3>Setup Status</h3>
          <p>{installResult.message ?? installResult.status}</p>
          {installResult.plan && <p>{installResult.plan.summary}</p>}
          {installResult.approval_id && <small>Approval state: {installResult.approval_id}</small>}
          {installResult.results?.length ? (
            <div className="installList">
              {installResult.results.map((item, index) => (
                <article key={index} className={`installItem ${statusTone(item.status)}`}>
                  <strong>{item.label}</strong>
                  <span>{item.status}</span>
                  {item.message && <small>{item.message}</small>}
                </article>
              ))}
            </div>
          ) : null}
          {installResult.manual_steps?.length ? (
            <>
              <h3>Manual Steps</h3>
              <ul className="nextSteps">
                {installResult.manual_steps.map((step, index) => (
                  <li key={index}>{step}</li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
      )}
      <dl>
        <dt>Browser</dt>
        <dd>Available through the browser agent.</dd>
        <dt>Terminal</dt>
        <dd>Allowlisted commands only unless approval is required.</dd>
        <dt>Desktop</dt>
        <dd>Replies directly when no action is needed. Desktop control pauses for approval before anything changes, installs, deletes, sends, or controls input.</dd>
        <dt>Vision</dt>
        <dd>Screenshot and OCR show installed, fallback, or missing status in the capability list below.</dd>
      </dl>
      {freeStack && (
        <div className="capabilityGrid">
          {freeStack.capabilities.map((item) => (
            <article key={item.key} className={`capability ${capabilityTone(item)}`}>
              <strong>{item.name}</strong>
              <span>{capabilityLabel(item)}</span>
              <p>{item.role}</p>
              {!item.installed && <small>{item.install_hint}</small>}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function AgentsPanel({
  agentStatus,
  builderProfile,
  codexParity,
  evolutionRunning,
  evolutionCycle,
  capabilityLadder,
  skills,
  onRunSelfEvolution,
  onSetSkillTrust,
}: PanelContentProps) {
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

function SettingsPanel({
  health,
  freeStack,
  capabilityLadder,
  improvements,
  reflections,
  sourcePolicy,
}: PanelContentProps) {
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

function ProjectsPanel({ projectEcosystem, projectIndex, health, onRefreshHealth }: PanelContentProps) {
  return (
    <section className="panelView">
      <h2>Projects</h2>
      {projectEcosystem ? (
        <>
          <p>{projectEcosystem.strategy}</p>
          <p><strong>Build first:</strong> {projectEcosystem.build_first}</p>
          {projectEcosystem.free_tool_rule && <p><strong>Free tool rule:</strong> {projectEcosystem.free_tool_rule}</p>}
          {projectIndex && (
            <div className="projectIndexPanel">
              <h3>Local Workspace Intelligence</h3>
              <p>{projectIndex.summary}</p>
              <div className="indexStats">
                <article>
                  <strong>{projectIndex.files_indexed}</strong>
                  <span>files indexed</span>
                </article>
                <article>
                  <strong>{projectIndex.languages.slice(0, 3).map((item) => item.name).join(", ") || "Mixed"}</strong>
                  <span>main languages</span>
                </article>
                <article>
                  <strong>{projectIndex.scripts.length}</strong>
                  <span>known commands</span>
                </article>
              </div>
              <h3>Important Files</h3>
              <div className="importantFiles">
                {projectIndex.important_files.map((item) => (
                  <article key={item.path} className="ready">
                    <strong>{item.path}</strong>
                    <span>{item.exists ? item.role : "Optional reference"}</span>
                  </article>
                ))}
              </div>
            </div>
          )}
          <div className="projectGrid">
            {projectEcosystem.projects.map((project) => (
              <article key={project.id} className="projectItem">
                <header>
                  <strong>{project.rank}. {project.name}</strong>
                  <span>{project.status}</span>
                </header>
                <p>{project.motive}</p>
                <dl>
                  <dt>Why</dt>
                  <dd>{project.priority_reason}</dd>
                  <dt>Next</dt>
                  <dd>{project.next_build}</dd>
                  <dt>Integrates</dt>
                  <dd>{project.integration_role}</dd>
                  <dt>Safety</dt>
                  <dd>{project.safety_boundary}</dd>
                </dl>
                {project.free_tools?.length ? (
                  <div className="tagList" aria-label={`${project.name} free tools`}>
                    {project.free_tools.map((tool) => (
                      <span key={tool}>{tool.replace(/_/g, " ")}</span>
                    ))}
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        </>
      ) : (
        <p>Project ecosystem is loading.</p>
      )}
      <p>Workspace folder: {health?.workspace ?? "Loading"}</p>
      <button onClick={onRefreshHealth}>Refresh Workspace</button>
    </section>
  );
}

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

function capabilityTone(item: FreeCapability) {
  if (item.installed || item.actual_installed) return "ready";
  if (item.fallback_available || item.usable) return "working";
  return "missing";
}

function capabilityLabel(item: FreeCapability) {
  if (item.installed || item.actual_installed) return "Installed";
  if (item.fallback_available || item.usable) return "Fallback active";
  return item.required ? "Required missing" : "Missing";
}
