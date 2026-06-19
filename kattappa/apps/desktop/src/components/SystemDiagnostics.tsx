import { useEffect, useMemo, useState } from "react";
import { fetchDiagnostics, fetchSageStatus } from "../lib/api";
import type { SageStatus } from "../lib/api";
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
  const [sage, setSage] = useState<SageStatus | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    setLoading(true);
    setError("");
    try {
      const [diagData, sageData] = await Promise.all([
        fetchDiagnostics(),
        fetchSageStatus()
      ]);
      setData(diagData);
      setSage(sageData);
    } catch (exc) {
      setData(null);
      setSage(null);
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
                 {sage && (
            <div className="sageDashboard" style={{ marginBottom: "2rem", borderTop: "1px solid rgba(255,255,255,0.06)", paddingTop: "1.5rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.2rem" }}>
                <div>
                  <h3 style={{ margin: 0, background: "linear-gradient(90deg, #a855f7, #6366f1, #06b6d4)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>AETHER Cognitive Brain</h3>
                  <p style={{ fontSize: "0.85rem", opacity: 0.7, margin: "0.2rem 0 0 0" }}>
                    Adaptive Ethical Hierarchical Evolutionary Reasoning — advanced multi-layered neural engine.
                  </p>
                </div>
                {sage.aether_metrics && (
                  <span style={{
                    background: "rgba(99, 102, 241, 0.15)",
                    border: "1px solid rgba(99, 102, 241, 0.3)",
                    color: "#a5b4fc",
                    fontSize: "0.75rem",
                    padding: "0.2rem 0.6rem",
                    borderRadius: "20px",
                    fontWeight: 600
                  }}>
                    Confidence: {sage.aether_metrics.confidence_tracking}
                  </span>
                )}
              </div>

              <div className="sageGrid" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "1.2rem", marginBottom: "1.5rem" }}>
                
                {/* Value Archetypes */}
                <div className="sageCard" style={{ background: "rgba(255,255,255,0.02)", backdropFilter: "blur(12px)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "8px", padding: "1.2rem" }}>
                  <h4 style={{ margin: "0 0 1rem 0", color: "#6366f1", fontSize: "0.95rem" }}>Value Archetypes</h4>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
                    {Object.entries(sage.weights).map(([name, weight]) => {
                      const pct = Math.round((weight as number) * 100);
                      let color = "#6366f1"; // Rama
                      if (name === "Krishna") color = "#a855f7";
                      if (name === "Brahma") color = "#f97316";
                      if (name === "Shiva") color = "#ef4444";
                      if (name === "Kattappa") color = "#eab308";
                      return (
                        <div key={name}>
                          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem", marginBottom: "0.2rem" }}>
                            <span><strong>{name}</strong></span>
                            <span>{pct}%</span>
                          </div>
                          <div style={{ width: "100%", height: "8px", background: "rgba(255,255,255,0.06)", borderRadius: "4px", overflow: "hidden" }}>
                            <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: "4px", transition: "width 0.5s ease" }} />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Memory Layers */}
                {sage.aether_metrics && (
                  <div className="sageCard" style={{ background: "rgba(255,255,255,0.02)", backdropFilter: "blur(12px)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "8px", padding: "1.2rem" }}>
                    <h4 style={{ margin: "0 0 1rem 0", color: "#6366f1", fontSize: "0.95rem" }}>Hierarchical Memory Stack</h4>
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", fontSize: "0.8rem" }}>
                      {Object.entries(sage.aether_metrics.memory_layers).map(([layer, status]) => (
                        <div key={layer} style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid rgba(255,255,255,0.03)", paddingBottom: "0.4rem" }}>
                          <span style={{ textTransform: "capitalize", fontWeight: 600, opacity: 0.8 }}>{layer}</span>
                          <span style={{ color: "#38bdf8", fontSize: "0.75rem" }}>{status}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Ethical Audit Matrix */}
                {sage.aether_metrics && (
                  <div className="sageCard" style={{ background: "rgba(255,255,255,0.02)", backdropFilter: "blur(12px)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "8px", padding: "1.2rem" }}>
                    <h4 style={{ margin: "0 0 1rem 0", color: "#a855f7", fontSize: "0.95rem" }}>Ethical Evaluation Layer</h4>
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
                      {Object.entries(sage.aether_metrics.ethical_scores).map(([metric, score]) => {
                        const pct = Math.round(score * 100);
                        let barColor = "#38bdf8";
                        if (metric === "safety") barColor = "#4ade80";
                        if (metric === "fairness") barColor = "#fb7185";
                        if (metric === "user_benefit") barColor = "#fcd34d";
                        if (metric === "long_term_impact") barColor = "#c084fc";
                        return (
                          <div key={metric}>
                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", marginBottom: "0.2rem" }}>
                              <span style={{ textTransform: "capitalize", fontWeight: 500, opacity: 0.8 }}>{metric.replace("_", " ")}</span>
                              <span>{pct}%</span>
                            </div>
                            <div style={{ width: "100%", height: "6px", background: "rgba(255,255,255,0.04)", borderRadius: "3px", overflow: "hidden" }}>
                              <div style={{ width: `${pct}%`, height: "100%", background: barColor, borderRadius: "3px" }} />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* User Cognitive Profile */}
                <div className="sageCard" style={{ background: "rgba(255,255,255,0.02)", backdropFilter: "blur(12px)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "8px", padding: "1.2rem" }}>
                  <h4 style={{ margin: "0 0 1rem 0", color: "#06b6d4", fontSize: "0.95rem" }}>User Cognitive Profile</h4>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.8rem", fontSize: "0.8rem" }}>
                    <div>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", marginBottom: "0.2rem" }}>
                        <span>Conciseness Bias</span>
                        <span>{Math.round(sage.profile.concise_preference * 100)}%</span>
                      </div>
                      <div style={{ width: "100%", height: "6px", background: "rgba(255,255,255,0.04)", borderRadius: "3px", overflow: "hidden" }}>
                        <div style={{ width: `${sage.profile.concise_preference * 100}%`, height: "100%", background: "#06b6d4", borderRadius: "3px" }} />
                      </div>
                    </div>
                    <div>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", marginBottom: "0.2rem" }}>
                        <span>Technical Depth Bias</span>
                        <span>{Math.round(sage.profile.technical_preference * 100)}%</span>
                      </div>
                      <div style={{ width: "100%", height: "6px", background: "rgba(255,255,255,0.04)", borderRadius: "3px", overflow: "hidden" }}>
                        <div style={{ width: `${sage.profile.technical_preference * 100}%`, height: "100%", background: "#10b981", borderRadius: "3px" }} />
                      </div>
                    </div>
                    {sage.profile.knowledge_level && (
                      <div style={{ display: "flex", justifyContent: "space-between", borderTop: "1px solid rgba(255,255,255,0.04)", paddingTop: "0.6rem", marginTop: "0.4rem" }}>
                        <span style={{ opacity: 0.7 }}>Knowledge Level:</span>
                        <strong style={{ color: "#fb7185" }}>{sage.profile.knowledge_level}</strong>
                      </div>
                    )}
                    {sage.profile.learning_speed && (
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <span style={{ opacity: 0.7 }}>Learning Speed:</span>
                        <strong style={{ color: "#fcd34d" }}>{sage.profile.learning_speed}</strong>
                      </div>
                    )}
                    {sage.profile.interests && (
                      <div style={{ borderTop: "1px solid rgba(255,255,255,0.04)", paddingTop: "0.6rem" }}>
                        <span style={{ opacity: 0.7, display: "block", marginBottom: "0.3rem" }}>Key Topic Interests:</span>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
                          {sage.profile.interests.split(",").map((int: string) => (
                            <span key={int} style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", padding: "0.1rem 0.4rem", borderRadius: "4px", fontSize: "0.7rem", color: "#cbd5e1" }}>
                              {int.trim()}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Self-Questioning Engine */}
                {sage.aether_metrics && (
                  <div className="sageCard" style={{ background: "rgba(255,255,255,0.02)", backdropFilter: "blur(12px)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "8px", padding: "1.2rem" }}>
                    <h4 style={{ margin: "0 0 1rem 0", color: "#fb7185", fontSize: "0.95rem" }}>Self-Questioning Reflection</h4>
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", fontSize: "0.75rem", maxHeight: "190px", overflowY: "auto" }}>
                      <div>
                        <strong style={{ color: "#4ade80" }}>KNOW: </strong>
                        <span style={{ opacity: 0.85 }}>{sage.aether_metrics.self_questioning_results.know}</span>
                      </div>
                      <div>
                        <strong style={{ color: "#fb7185" }}>ASSUME: </strong>
                        <span style={{ opacity: 0.85 }}>{sage.aether_metrics.self_questioning_results.assume}</span>
                      </div>
                      <div>
                        <strong style={{ color: "#38bdf8" }}>EVIDENCE: </strong>
                        <span style={{ opacity: 0.85 }}>{sage.aether_metrics.self_questioning_results.evidence}</span>
                      </div>
                      <div>
                        <strong style={{ color: "#fcd34d" }}>WRONG: </strong>
                        <span style={{ opacity: 0.85 }}>{sage.aether_metrics.self_questioning_results.wrong}</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Meta-Learning Strategy Rates */}
                {sage.aether_metrics && (
                  <div className="sageCard" style={{ background: "rgba(255,255,255,0.02)", backdropFilter: "blur(12px)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "8px", padding: "1.2rem" }}>
                    <h4 style={{ margin: "0 0 1rem 0", color: "#34d399", fontSize: "0.95rem" }}>Meta-Learning Strategy Success Rates</h4>
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                      {Object.entries(sage.aether_metrics.meta_learning.strategy_success_rates).map(([strat, rate]) => {
                        const pct = Math.round(rate * 100);
                        return (
                          <div key={strat}>
                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", marginBottom: "0.2rem" }}>
                              <span style={{ textTransform: "capitalize", fontWeight: 500, opacity: 0.8 }}>{strat} strategy</span>
                              <span>{pct}%</span>
                            </div>
                            <div style={{ width: "100%", height: "6px", background: "rgba(255,255,255,0.04)", borderRadius: "3px", overflow: "hidden" }}>
                              <div style={{ width: `${pct}%`, height: "100%", background: "#34d399", borderRadius: "3px" }} />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Dynamic Concept Graph */}
                <div className="sageCard" style={{ background: "rgba(255,255,255,0.02)", backdropFilter: "blur(12px)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "8px", padding: "1.2rem" }}>
                  <h4 style={{ margin: "0 0 1rem 0", color: "#eab308", fontSize: "0.95rem" }}>Dynamic Concept Graph</h4>
                  {sage.concepts.length === 0 ? (
                    <p style={{ fontSize: "0.85rem", opacity: 0.6, margin: 0 }}>No concepts learned yet. Start chatting to build the concept graph.</p>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", maxHeight: "190px", overflowY: "auto" }}>
                      {sage.concepts.slice(0, 8).map((concept: any) => {
                        const pct = Math.round(concept.confidence * 100);
                        return (
                          <div key={concept.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: "0.75rem" }}>
                            <span style={{ textTransform: "capitalize", fontWeight: 500, opacity: 0.95 }} title={concept.connections && concept.connections.definition ? `${concept.concept}: ${concept.connections.definition}` : concept.concept}>
                              {concept.concept}
                            </span>
                            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", width: "120px" }}>
                              <div style={{ flex: 1, height: "6px", background: "rgba(255,255,255,0.04)", borderRadius: "3px", overflow: "hidden" }}>
                                <div style={{ width: `${pct}%`, height: "100%", background: "#eab308", borderRadius: "3px" }} />
                              </div>
                              <span style={{ width: "30px", textAlign: "right", opacity: 0.7 }}>{pct}%</span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

              </div>
            </div>
          )}

          <div className="diagnosticSummary" style={{ marginBottom: "1.5rem" }}>
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
