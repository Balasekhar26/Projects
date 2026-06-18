import { useEffect, useMemo, useState } from "react";
import { fetchDiagnostics } from "../lib/api";
import type {
  CapabilityLadder,
  FreeStack,
  Health,
  HardwareRequirements,
  Improvement,
  PlatformFeature,
  PlatformSupport,
  Reflection,
  SourcePolicy,
} from "../types";

type DiagnosticsData = {
  platformSupport: PlatformSupport;
  hardwareRequirements: HardwareRequirements;
};

type Props = {
  health?: Health | null;
  freeStack?: FreeStack | null;
  capabilityLadder?: CapabilityLadder | null;
  improvements?: Improvement[];
  reflections?: Reflection[];
  sourcePolicy?: SourcePolicy | null;
};

export function SystemDiagnostics({
  health,
  freeStack,
  capabilityLadder,
  improvements = [],
  reflections = [],
  sourcePolicy,
}: Props) {
  const [data, setData] = useState<DiagnosticsData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    setLoading(true);
    setError("");
    try {
      setData(await fetchDiagnostics());
    } catch (exc) {
      setData(null);
      setError(exc instanceof Error ? exc.message : "Diagnostics request failed.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const grouped = useMemo(() => groupFeatures(data?.platformSupport.features ?? []), [data]);

  return (
    <section className="panelView">
      <h2>System Status</h2>
      <p>Live health check — adapters, hardware, Ollama, models, and Kattappa's self-improvement state.</p>
      <div className="taskControls">
        <button onClick={refresh} disabled={loading}>{loading ? "Checking..." : "Refresh"}</button>
      </div>

      {/* ── Kattappa runtime health ── */}
      {health && (
        <div className="diagnosticHero" style={{ marginBottom: "1.2rem" }}>
          <article>
            <strong>Backend</strong>
            <span style={{ color: "var(--accent-green, #4ade80)" }}>Online</span>
          </article>
          <article>
            <strong>Ollama</strong>
            <span style={{ color: health.ollama_ok ? "var(--accent-green, #4ade80)" : "var(--accent-red, #f87171)" }}>
              {health.ollama_ok ? "Connected" : (health.ollama_message ?? "Offline")}
            </span>
          </article>
          <article>
            <strong>{health.memory_count ?? 0}</strong>
            <span>memories stored</span>
          </article>
        </div>
      )}

      {health && (
        <dl className="settingsList" style={{ marginBottom: "1rem" }}>
          {health.workspace && (
            <>
              <dt>Workspace</dt>
              <dd style={{ wordBreak: "break-all", opacity: 0.8 }}>{health.workspace}</dd>
            </>
          )}
          {health.models?.length ? (
            <>
              <dt>Active Models</dt>
              <dd>{health.models.join(", ")}</dd>
            </>
          ) : (
            <>
              <dt>Models</dt>
              <dd>Built-in fallback ready</dd>
            </>
          )}
        </dl>
      )}

      {error && <div className="errorPanel">{error}</div>}

      {data ? (
        <>
          <div className="diagnosticHero">
            <article>
              <strong>{data.platformSupport.os.system} {data.platformSupport.os.release}</strong>
              <span>{data.platformSupport.os.machine} / Python {data.platformSupport.os.python}</span>
            </article>
            <article>
              <strong>{data.hardwareRequirements.system.ram_total_gb ?? "?"} GB</strong>
              <span>RAM</span>
            </article>
            <article>
              <strong>{data.hardwareRequirements.system.cpu_count_logical ?? "?"}</strong>
              <span>logical CPUs</span>
            </article>
          </div>

          <div className="diagnosticSummary">
            <StatusCount label="Ready" count={grouped.ready.length} className="ready" />
            {grouped.degraded.length > 0 && <StatusCount label="Fallback" count={grouped.degraded.length} className="degraded" />}
            {grouped.missing.length > 0 && <StatusCount label="Missing" count={grouped.missing.length} className="missing" />}
          </div>

          <h3>Adapters</h3>
          <div className="diagnosticList">
            {data.platformSupport.features.map((feature) => (
              <article key={feature.feature} className={`diagnosticItem ${statusClass(feature.status)}`}>
                <header>
                  <strong>{formatName(feature.feature)}</strong>
                  <span>{statusLabel(feature.status)}</span>
                </header>
                <dl>
                  <dt>Adapter</dt>
                  <dd>{feature.adapter}</dd>
                  <dt>Setup</dt>
                  <dd>{feature.setup_hint}</dd>
                  <dt>Notes</dt>
                  <dd>{feature.notes}</dd>
                </dl>
              </article>
            ))}
          </div>

          <h3>Hardware Fit</h3>
          <div className="hardwareTierList">
            {data.hardwareRequirements.tiers.map((tier) => (
              <article key={tier.tier} className="hardwareTier">
                <header>
                  <strong>{tier.name}</strong>
                  <span>{formatName(tier.tier)}</span>
                </header>
                <dl>
                  <dt>CPU</dt><dd>{tier.cpu}</dd>
                  <dt>RAM</dt><dd>{tier.ram}</dd>
                  <dt>GPU</dt><dd>{tier.gpu}</dd>
                  <dt>Storage</dt><dd>{tier.storage}</dd>
                </dl>
              </article>
            ))}
          </div>

          <div className="policyPanel">
            <h3>Setup Guidance</h3>
            <p>{data.hardwareRequirements.recommendation}</p>
            <ul className="nextSteps">
              {data.hardwareRequirements.notes.map((note, index) => (
                <li key={index}>{note}</li>
              ))}
            </ul>
          </div>

          {data.hardwareRequirements.buying_guide?.length ? (
            <>
              <h3>Buying Guide</h3>
              <div className="hardwareTierList">
                {data.hardwareRequirements.buying_guide.map((item) => (
                  <article key={item.tier} className="hardwareTier">
                    <header>
                      <strong>{formatName(item.tier)}</strong>
                      <span>setup target</span>
                    </header>
                    <dl>
                      <dt>Laptop</dt><dd>{item.laptop}</dd>
                      <dt>Desktop</dt><dd>{item.desktop}</dd>
                      <dt>Best for</dt><dd>{item.best_for}</dd>
                      <dt>Avoid</dt><dd>{item.avoid}</dd>
                    </dl>
                  </article>
                ))}
              </div>
            </>
          ) : null}
        </>
      ) : (
        !error && <p>Diagnostics loading…</p>
      )}

      {/* ── Capability next actions ── */}
      {freeStack?.next_best_steps?.length ? (
        <>
          <h3>Next Steps</h3>
          <ul className="nextSteps">
            {freeStack.next_best_steps.map((step, index) => <li key={index}>{step}</li>)}
          </ul>
        </>
      ) : null}

      {capabilityLadder?.next_actions?.length ? (
        <>
          <h3>Capability Actions</h3>
          <ul className="nextSteps">
            {capabilityLadder.next_actions.map((step, index) => <li key={index}>{step}</li>)}
          </ul>
        </>
      ) : null}

      {/* ── Source policy ── */}
      {sourcePolicy && (
        <>
          <h3>Source Boundaries</h3>
          <div className="policyPanel">
            <p>{sourcePolicy.summary}</p>
            <ul className="nextSteps">
              {sourcePolicy.hard_no.map((rule, index) => <li key={index}>{rule}</li>)}
            </ul>
          </div>
        </>
      )}

      {/* ── Self-improvement backlog ── */}
      {improvements.length > 0 && (
        <>
          <h3>Self-Improvement Backlog</h3>
          <div className="improvementList">
            {improvements.map((item) => (
              <article key={item.id} className="improvementItem">
                <header>
                  <strong>{item.title}</strong>
                  <span>{item.status}</span>
                </header>
                <p>{item.motive}</p>
              </article>
            ))}
          </div>
        </>
      )}

      {/* ── Recent reflections ── */}
      {reflections.length > 0 && (
        <>
          <h3>Recent Reflections</h3>
          <div className="reflectionList">
            {reflections.map((item) => (
              <article key={item.id} className={`reflectionItem ${item.outcome}`}>
                <header>
                  <strong>{item.outcome}</strong>
                  <span>{item.created_at}</span>
                </header>
                <p>{item.task}</p>
                <small>{item.lesson}</small>
              </article>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

function StatusCount({ label, count, className }: { label: string; count: number; className: string }) {
  return (
    <article className={className}>
      <strong>{count}</strong>
      <span>{label}</span>
    </article>
  );
}

function groupFeatures(features: PlatformFeature[]) {
  return {
    ready: features.filter((feature) => statusClass(feature.status) === "ready"),
    degraded: features.filter((feature) => statusClass(feature.status) === "degraded"),
    missing: features.filter((feature) => statusClass(feature.status) === "missing"),
  };
}

function statusClass(status: string) {
  if (status === "ready" || status === "supported" || status === "installed") return "ready";
  if (status === "fallback" || status === "partial" || status === "degraded" || status === "needs_dependency") return "degraded";
  if (status === "missing" || status === "disabled" || status === "failed" || status === "error" || status === "blocked") return "missing";
  return "degraded";
}

function statusLabel(status: string) {
  if (status === "needs_dependency" || status === "fallback") return "Fallback";
  if (status === "missing") return "Missing";
  if (status === "supported") return "Ready";
  if (status === "installed") return "Installed";
  if (status === "disabled") return "Disabled";
  return formatName(status);
}

function formatName(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
