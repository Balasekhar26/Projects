import { useState, useEffect } from "react";
import type { RequestTrace } from "../types";
import { fetchRequestTraces } from "../lib/api";

export function TracesPanel() {
  const [traces, setTraces] = useState<RequestTrace[]>([]);
  const [selectedTrace, setSelectedTrace] = useState<RequestTrace | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState<boolean>(true);
  const [modeFilter, setModeFilter] = useState<string>("ALL");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");

  const loadTraces = async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const data = await fetchRequestTraces();
      setTraces(data);
      setError(null);
      // Auto-select first trace if none is selected and we got data
      if (data.length > 0 && !selectedTrace) {
        setSelectedTrace(data[0]);
      } else if (selectedTrace) {
        // Refresh selected trace reference in case of updates
        const updated = data.find((t) => t.trace_id === selectedTrace.trace_id);
        if (updated) setSelectedTrace(updated);
      }
    } catch (err: any) {
      setError(err.message || "Failed to fetch traces");
    } finally {
      if (!silent) setLoading(false);
    }
  };

  useEffect(() => {
    loadTraces();
  }, []);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      loadTraces(true);
    }, 3000);
    return () => clearInterval(interval);
  }, [autoRefresh, selectedTrace]);

  const filteredTraces = traces.filter((t) => {
    const matchesMode = modeFilter === "ALL" || t.mode.toUpperCase() === modeFilter;
    const isSuccess = t.failure_reason === "OK";
    const matchesStatus =
      statusFilter === "ALL" ||
      (statusFilter === "SUCCESS" && isSuccess) ||
      (statusFilter === "FAILURE" && !isSuccess);
    return matchesMode && matchesStatus;
  });

  const getLatencyColor = (ms: number) => {
    if (ms < 500) return "#10a37f"; // Green
    if (ms < 2000) return "#f59e0b"; // Amber
    return "#ef4444"; // Red
  };

  return (
    <section className="panelView" style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem", flexWrap: "wrap", gap: "10px" }}>
        <div>
          <h2 style={{ margin: 0 }}>Execution Traces</h2>
          <p style={{ margin: "4px 0 0", color: "#8e8ea0", fontSize: "14px" }}>
            Observability dashboard for local AI agent routing, tool execution, and failure metrics.
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "13px", color: "#c5c5d2", cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              style={{ cursor: "pointer" }}
            />
            Auto-refresh (3s)
          </label>
          <button
            onClick={() => loadTraces(false)}
            disabled={loading}
            style={{ padding: "6px 12px", fontSize: "13px", height: "34px", display: "flex", alignItems: "center", gap: "6px" }}
          >
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>
      </header>

      {/* Filter Row */}
      <div style={{ display: "flex", gap: "12px", marginBottom: "1rem", flexWrap: "wrap" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
          <span style={{ fontSize: "11px", color: "#8e8ea0", textTransform: "uppercase", fontWeight: "bold" }}>Filter Mode</span>
          <select
            value={modeFilter}
            onChange={(e) => setModeFilter(e.target.value)}
            style={{ background: "#2d2d2d", border: "1px solid #3f3f46", color: "#ececf1", padding: "6px 10px", borderRadius: "6px", outline: "none", minWidth: "120px" }}
          >
            <option value="ALL">All Modes</option>
            <option value="CHAT">Chat</option>
            <option value="ASSISTANT">Assistant</option>
            <option value="AUTONOMOUS">Autonomous</option>
          </select>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
          <span style={{ fontSize: "11px", color: "#8e8ea0", textTransform: "uppercase", fontWeight: "bold" }}>Filter Status</span>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            style={{ background: "#2d2d2d", border: "1px solid #3f3f46", color: "#ececf1", padding: "6px 10px", borderRadius: "6px", outline: "none", minWidth: "120px" }}
          >
            <option value="ALL">All Statuses</option>
            <option value="SUCCESS">Success</option>
            <option value="FAILURE">Failure</option>
          </select>
        </div>
        <div style={{ display: "flex", alignItems: "flex-end", color: "#8e8ea0", fontSize: "13px", paddingBottom: "8px" }}>
          Showing {filteredTraces.length} of {traces.length} total traces
        </div>
      </div>

      {error && (
        <div style={{ background: "rgba(239, 68, 68, 0.15)", border: "1px solid rgba(239, 68, 68, 0.4)", borderRadius: "8px", padding: "12px", color: "#ef4444", marginBottom: "1rem" }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Main Split Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "360px 1fr", gap: "1rem", flex: 1, overflow: "hidden" }}>
        {/* Left Column: Traces List */}
        <div style={{ background: "#171717", border: "1px solid #2f2f2f", borderRadius: "8px", display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <div style={{ overflowY: "auto", flex: 1 }}>
            {filteredTraces.length === 0 ? (
              <div style={{ padding: "2rem", textAlign: "center", color: "#8e8ea0" }}>
                {loading ? "Loading traces..." : "No matching traces found."}
              </div>
            ) : (
              filteredTraces.map((trace) => {
                const isSelected = selectedTrace?.trace_id === trace.trace_id;
                const isSuccess = trace.failure_reason === "OK";
                return (
                  <div
                    key={trace.trace_id}
                    onClick={() => setSelectedTrace(trace)}
                    style={{
                      padding: "12px",
                      borderBottom: "1px solid #2f2f2f",
                      cursor: "pointer",
                      background: isSelected ? "rgba(16, 163, 127, 0.15)" : "transparent",
                      borderLeft: isSelected ? "4px solid #10a37f" : "4px solid transparent",
                      transition: "background 150ms ease, border-left 150ms ease",
                    }}
                    className="trace-item-hover"
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "6px" }}>
                      <span
                        style={{
                          fontSize: "11px",
                          fontWeight: "bold",
                          fontFamily: "monospace",
                          color: isSuccess ? "#10a37f" : "#ef4444",
                          background: isSuccess ? "rgba(16, 163, 127, 0.1)" : "rgba(239, 68, 68, 0.1)",
                          padding: "2px 6px",
                          borderRadius: "4px",
                        }}
                      >
                        {trace.trace_id}
                      </span>
                      <span style={{ fontSize: "11px", color: getLatencyColor(trace.latency_ms), fontWeight: "bold" }}>
                        {trace.latency_ms} ms
                      </span>
                    </div>
                    <div
                      style={{
                        fontSize: "14px",
                        fontWeight: "500",
                        color: "#ececf1",
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        marginBottom: "6px",
                      }}
                    >
                      "{trace.input}"
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", color: "#8e8ea0" }}>
                      <span>Agent: <strong style={{ color: "#c5c5d2" }}>{trace.router}</strong></span>
                      <span>{trace.mode}</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Column: Trace Details */}
        <div style={{ background: "#171717", border: "1px solid #2f2f2f", borderRadius: "8px", display: "flex", flexDirection: "column", overflow: "hidden", padding: "1.5rem" }}>
          {selectedTrace ? (
            <div style={{ display: "flex", flexDirection: "column", height: "100%", overflowY: "auto" }}>
              {/* Request Info Header */}
              <div style={{ borderBottom: "1px solid #2f2f2f", paddingBottom: "1rem", marginBottom: "1rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px", flexWrap: "wrap", gap: "8px" }}>
                  <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                    <span style={{ fontSize: "20px", fontWeight: "bold", fontFamily: "monospace", color: "#10a37f" }}>
                      Trace {selectedTrace.trace_id}
                    </span>
                    <span style={{ fontSize: "12px", color: "#8e8ea0" }}>
                      {new Date(selectedTrace.timestamp * 1000).toLocaleString()}
                    </span>
                  </div>
                  <div style={{ display: "flex", gap: "6px" }}>
                    <span style={{ background: "#202020", border: "1px solid #3a3a3a", borderRadius: "999px", padding: "4px 10px", fontSize: "12px", color: "#d1d5db" }}>
                      Mode: {selectedTrace.mode}
                    </span>
                    <span style={{ background: "#202020", border: "1px solid #3a3a3a", borderRadius: "999px", padding: "4px 10px", fontSize: "12px", color: "#d1d5db" }}>
                      Model: {selectedTrace.model}
                    </span>
                  </div>
                </div>

                <blockquote style={{ margin: "10px 0 0", padding: "10px 14px", background: "#202020", borderLeft: "4px solid #10a37f", borderRadius: "0 8px 8px 0", color: "#ececf1", fontSize: "15px", fontStyle: "italic" }}>
                  "{selectedTrace.input}"
                </blockquote>
              </div>

              {/* Execution Details Grid */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1rem", marginBottom: "1.5rem" }}>
                <div style={{ background: "#202020", padding: "12px", borderRadius: "8px", border: "1px solid #2f2f2f" }}>
                  <div style={{ fontSize: "11px", color: "#8e8ea0", textTransform: "uppercase", fontWeight: "bold", marginBottom: "4px" }}>Selected Agent</div>
                  <div style={{ fontSize: "16px", fontWeight: "bold", color: "#f7f7f8" }}>{selectedTrace.router}</div>
                </div>
                <div style={{ background: "#202020", padding: "12px", borderRadius: "8px", border: "1px solid #2f2f2f" }}>
                  <div style={{ fontSize: "11px", color: "#8e8ea0", textTransform: "uppercase", fontWeight: "bold", marginBottom: "4px" }}>Execution Duration</div>
                  <div style={{ fontSize: "16px", fontWeight: "bold", color: getLatencyColor(selectedTrace.latency_ms) }}>
                    {selectedTrace.latency_ms} ms
                  </div>
                </div>
                <div style={{ background: "#202020", padding: "12px", borderRadius: "8px", border: "1px solid #2f2f2f" }}>
                  <div style={{ fontSize: "11px", color: "#8e8ea0", textTransform: "uppercase", fontWeight: "bold", marginBottom: "4px" }}>Status / Reason Code</div>
                  <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                    <span style={{
                      display: "inline-block",
                      width: "8px",
                      height: "8px",
                      borderRadius: "50%",
                      background: selectedTrace.failure_reason === "OK" ? "#10a37f" : "#ef4444"
                    }} />
                    <span style={{ fontSize: "14px", fontWeight: "bold", color: selectedTrace.failure_reason === "OK" ? "#10a37f" : "#ef4444" }}>
                      {selectedTrace.failure_reason}
                    </span>
                  </div>
                  {selectedTrace.failure_detail && (
                    <small style={{ color: "#ef4444", display: "block", marginTop: "2px" }}>({selectedTrace.failure_detail})</small>
                  )}
                </div>
                <div style={{ background: "#202020", padding: "12px", borderRadius: "8px", border: "1px solid #2f2f2f" }}>
                  <div style={{ fontSize: "11px", color: "#8e8ea0", textTransform: "uppercase", fontWeight: "bold", marginBottom: "4px" }}>Policy Evaluated</div>
                  <div style={{ fontSize: "14px", fontWeight: "bold", color: "#ececf1" }}>{selectedTrace.policy}</div>
                </div>
              </div>

              {/* Capabilities & Tools */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1.5rem" }}>
                <div>
                  <h4 style={{ margin: "0 0 8px", fontSize: "13px", color: "#8e8ea0", textTransform: "uppercase" }}>Matched Capabilities</h4>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                    {selectedTrace.capabilities.length > 0 ? (
                      selectedTrace.capabilities.map((cap) => (
                        <span key={cap} style={{ background: "#2a2a2a", border: "1px solid #3f3f46", padding: "4px 8px", borderRadius: "6px", fontSize: "12px", fontFamily: "monospace", color: "#c5c5d2" }}>
                          {cap}
                        </span>
                      ))
                    ) : (
                      <span style={{ color: "#8e8ea0", fontSize: "13px" }}>None</span>
                    )}
                  </div>
                </div>
                <div>
                  <h4 style={{ margin: "0 0 8px", fontSize: "13px", color: "#8e8ea0", textTransform: "uppercase" }}>Invoked Tools</h4>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                    {selectedTrace.tools.length > 0 ? (
                      selectedTrace.tools.map((tool) => (
                        <span key={tool} style={{ background: "#2a2a2a", border: "1px solid #3f3f46", padding: "4px 8px", borderRadius: "6px", fontSize: "12px", fontFamily: "monospace", color: "#c5c5d2" }}>
                          {tool}
                        </span>
                      ))
                    ) : (
                      <span style={{ color: "#8e8ea0", fontSize: "13px" }}>None</span>
                    )}
                  </div>
                </div>
              </div>

              {/* Result Inspect Block */}
              <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: "200px" }}>
                <h4 style={{ margin: "0 0 8px", fontSize: "13px", color: "#8e8ea0", textTransform: "uppercase" }}>Result Output</h4>
                <div style={{ background: "#0d0d0d", border: "1px solid #2f2f2f", borderRadius: "8px", padding: "12px", flex: 1, overflowY: "auto", fontFamily: "monospace", fontSize: "13px", color: "#a5b4fc", whiteSpace: "pre-wrap" }}>
                  {selectedTrace.result || "<No output result returned>"}
                </div>
              </div>
            </div>
          ) : (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "#8e8ea0" }}>
              Select a trace from the left panel to inspect execution details.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
