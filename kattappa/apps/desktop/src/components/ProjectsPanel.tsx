import type { Health, ProjectEcosystem, ProjectIndex } from "../types";

type ProjectsPanelProps = {
  projectEcosystem: ProjectEcosystem | null;
  projectIndex: ProjectIndex | null;
  health: Health | null;
  onRefreshHealth: () => void;
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

export function ProjectsPanel({ projectEcosystem, projectIndex, health, onRefreshHealth }: ProjectsPanelProps) {
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
