import type { FreeCapability, FreeStack, InstallResult, SourcePolicy, ToolAdoptionJob, ToolScoutStatus } from "../types";

type ToolsPanelProps = {
  freeStack: FreeStack | null;
  sourcePolicy: SourcePolicy | null;
  toolScout: ToolScoutStatus | null;
  toolAdoptions: ToolAdoptionJob[];
  installResult: InstallResult | null;
  onRequestMissingInstalls: () => void;
  onRunManualToolScout: () => void;
  onStartToolAdoption: (reportId: string) => void;
};

function statusTone(status: string) {
  const value = status.toLowerCase();
  if (["ready", "done", "completed", "success", "trusted", "installed", "supported"].includes(value)) return "ready";
  if (["approved", "running", "active", "paused", "partial", "degraded", "fallback", "in_progress", "requested", "pending", "draft"].includes(value)) return "working";
  if (["missing", "needs_dependency", "failed", "blocked", "error", "rejected", "disabled", "manual_required"].includes(value)) return "missing";
  return "working";
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

export function ToolsPanel({
  freeStack,
  sourcePolicy,
  toolScout,
  toolAdoptions,
  installResult,
  onRequestMissingInstalls,
  onRunManualToolScout,
  onStartToolAdoption,
}: ToolsPanelProps) {
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
