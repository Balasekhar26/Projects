import { useEffect, useMemo, useState } from "react";
import { fetchDiagnostics } from "../lib/api";
import type { HardwareRequirements, PlatformFeature, PlatformSupport } from "../types";

type DiagnosticsData = {
  platformSupport: PlatformSupport;
  hardwareRequirements: HardwareRequirements;
};

export function SystemDiagnostics() {
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
      <h2>System Diagnostics</h2>
      <p>Installer and setup checks for this machine: platform support, adapter readiness, hardware fit, and dependency gaps.</p>
      <div className="taskControls">
        <button onClick={refresh} disabled={loading}>{loading ? "Checking..." : "Refresh Diagnostics"}</button>
      </div>

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
              <span>RAM detected</span>
            </article>
            <article>
              <strong>{data.hardwareRequirements.system.cpu_count_logical ?? "?"}</strong>
              <span>logical CPUs</span>
            </article>
          </div>

          <div className="diagnosticSummary">
            <StatusCount label="Ready" count={grouped.ready.length} className="ready" />
            {grouped.missing.length > 0 && <StatusCount label="Needs setup" count={grouped.missing.length} className="missing" />}
            {grouped.degraded.length > 0 && <StatusCount label="In progress" count={grouped.degraded.length} className="degraded" />}
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
                  <dt>CPU</dt>
                  <dd>{tier.cpu}</dd>
                  <dt>RAM</dt>
                  <dd>{tier.ram}</dd>
                  <dt>GPU</dt>
                  <dd>{tier.gpu}</dd>
                  <dt>Storage</dt>
                  <dd>{tier.storage}</dd>
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
                      <dt>Laptop</dt>
                      <dd>{item.laptop}</dd>
                      <dt>Desktop</dt>
                      <dd>{item.desktop}</dd>
                      <dt>Best for</dt>
                      <dd>{item.best_for}</dd>
                      <dt>Avoid</dt>
                      <dd>{item.avoid}</dd>
                    </dl>
                  </article>
                ))}
              </div>
            </>
          ) : null}
        </>
      ) : (
        !error && <p>Diagnostics are loading.</p>
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
    missing: features.filter((feature) => statusClass(feature.status) === "missing"),
    degraded: features.filter((feature) => statusClass(feature.status) === "degraded"),
  };
}

function statusClass(status: string) {
  if (status === "ready" || status === "supported") return "ready";
  if (status === "needs_dependency" || status === "missing") return "missing";
  return "degraded";
}

function statusLabel(status: string) {
  if (status === "needs_dependency") return "Needs setup";
  if (status === "supported") return "Ready";
  if (status === "disabled") return "Disabled";
  return formatName(status);
}

function formatName(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
