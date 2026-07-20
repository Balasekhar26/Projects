import React, { useState, useEffect } from "react";
import {
  generateSuperbenchTasks,
  fetchSuperbenchTasks,
  runSuperbenchTask,
  fetchSuperbenchResults,
  fetchSuperbenchStats
} from "../lib/api";

export function SuperbenchPanel() {
  const [tasks, setTasks] = useState<any[]>([]);
  const [results, setResults] = useState<any[]>([]);
  const [stats, setStats] = useState<any>({
    total_tasks: 0,
    total_executed: 0,
    success_count: 0,
    rejected_count: 0,
    failure_count: 0,
    success_rate: 0.0,
    average_latency: 0.0,
    category_stats: {}
  });
  
  const [selectedTask, setSelectedTask] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [activeCategory, setActiveCategory] = useState<string>("All");
  const [activeRun, setActiveRun] = useState<any | null>(null);

  const loadData = async () => {
    try {
      const tasksData = await fetchSuperbenchTasks();
      if (tasksData.tasks) {
        setTasks(tasksData.tasks);
      }
      
      const statsData = await fetchSuperbenchStats();
      if (statsData.stats) {
        setStats(statsData.stats);
      }

      const resultsData = await fetchSuperbenchResults();
      if (resultsData.results) {
        setResults(resultsData.results);
      }
    } catch (e) {
      console.error("Failed to load superbench telemetry", e);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleGenerate = async () => {
    setLoading(true);
    setStatusMessage("Generating 1000 benchmark tasks across 20 categories...");
    try {
      const res = await generateSuperbenchTasks();
      setStatusMessage(res.message || "Benchmark tasks generated successfully!");
      await loadData();
    } catch (e: any) {
      setStatusMessage(`Generation failed: ${e.message || e}`);
    } finally {
      setLoading(false);
    }
  };

  const handleRunTask = async (taskId: string) => {
    setLoading(true);
    setStatusMessage(`Executing validation task ${taskId}...`);
    try {
      const res = await runSuperbenchTask(taskId);
      setActiveRun(res);
      setStatusMessage(`Task ${res.status}. Run ${res.run_id}; trace ${res.trace_id}`);
      await loadData();
      
      // Update selected task view
      const freshTasks = await fetchSuperbenchTasks();
      const updated = freshTasks.tasks.find((t: any) => t.id === taskId);
      if (updated) setSelectedTask(updated);
    } catch (e: any) {
      setStatusMessage(`Execution failed: ${e.message || e}`);
    } finally {
      setLoading(false);
    }
  };

  const handleRunAllCategory = async (category: string) => {
    setLoading(true);
    const targetTasks = tasks.filter(t => t.category === category);
    setStatusMessage(`Running category sweep: executing ${targetTasks.length} tasks for '${category}'...`);
    
    try {
      for (const t of targetTasks) {
        await runSuperbenchTask(t.id);
      }
      setStatusMessage(`Finished execution sweep for category: ${category}`);
      await loadData();
    } catch (e: any) {
      setStatusMessage(`Sweep interrupted: ${e.message || e}`);
    } finally {
      setLoading(false);
    }
  };

  // Group tasks by category
  const categoriesList = ["All", ...Array.from(new Set(tasks.map(t => t.category)))];
  
  // Filtered tasks for view
  const filteredTasks = activeCategory === "All" 
    ? tasks 
    : tasks.filter(t => t.category === activeCategory);

  // Helper to map task status colors based on results
  const getTaskStatusColor = (taskId: string) => {
    const taskResult = results.find(r => r.task_id === taskId);
    if (!taskResult) return "rgba(255, 255, 255, 0.15)"; // grey/unexecuted
    if (taskResult.status === "degraded") return "var(--warning-color, #f59e0b)";
    if (taskResult.result === "SUCCESS") return "var(--success-color, #10b981)"; // green
    if (taskResult.result === "REJECTED") return "var(--warning-color, #f59e0b)"; // yellow/constitutional gate
    return "var(--danger-color, #ef4444)"; // red/failure
  };

  return (
    <div className="panelView" style={{ padding: "1.5rem" }}>
      <h2>Superbench Validation Program v1.0</h2>
      <p style={{ opacity: 0.9, marginBottom: "1.5rem" }}>
        Pressure testing Kattappa's cognitive framework against 1000 autogenous tasks across 20 distinct intelligence domains.
      </p>
      <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap", marginBottom: "1rem", fontSize: "0.78rem" }}>
        {(["queued", "running", "verifying", "succeeded", "degraded", "failed"] as const).map((phase) => (
          <span key={phase} style={{ padding: "0.2rem 0.45rem", border: "1px solid rgba(255,255,255,0.15)", borderRadius: "4px" }}>
            {phase}
          </span>
        ))}
      </div>

      {/* Stats Row */}
      <div className="capabilityGrid" style={{ marginBottom: "2rem" }}>
        <article className="capability ready">
          <strong>Validation Progress</strong>
          <span>{stats.total_executed} / {stats.total_tasks} Executed</span>
          <div className="maturityBar" style={{ marginTop: "0.5rem", height: "6px" }}>
            <span style={{ 
              width: `${stats.total_tasks ? (stats.total_executed / stats.total_tasks) * 100 : 0}%`,
              background: "var(--accent-color)" 
            }} />
          </div>
        </article>

        <article className="capability ready">
          <strong>Success & Safe Rate</strong>
          <span>{(stats.success_rate * 100).toFixed(1)}%</span>
          <div className="maturityBar" style={{ marginTop: "0.5rem", height: "6px" }}>
            <span style={{ 
              width: `${stats.success_rate * 100}%`,
              background: "var(--success-color, #10b981)" 
            }} />
          </div>
        </article>

        <article className="capability ready">
          <strong>Average Latency</strong>
          <span>{stats.average_latency.toFixed(2)} seconds</span>
        </article>

        <article className="capability ready">
          <strong>System Health Status</strong>
          <span style={{ color: stats.failure_count > 10 ? "var(--danger-color, #ef4444)" : "var(--success-color, #10b981)", fontWeight: "bold" }}>
            {stats.failure_count > 10 ? "DEGRADED" : "NOMINAL"}
          </span>
        </article>
      </div>

      {/* Control Actions */}
      <div className="builderPanel" style={{ marginBottom: "2rem", display: "flex", gap: "1rem", alignItems: "center", flexWrap: "wrap" }}>
        <button 
          onClick={handleGenerate} 
          disabled={loading}
          className="buttonPrimary" 
          style={{ padding: "0.5rem 1rem", minWidth: "150px" }}
        >
          {tasks.length > 0 ? "Re-Generate Tasks" : "Generate 1000 Tasks"}
        </button>

        {tasks.length > 0 && activeCategory !== "All" && (
          <button
            onClick={() => handleRunAllCategory(activeCategory)}
            disabled={loading}
            className="buttonPrimary"
            style={{ padding: "0.5rem 1rem", background: "var(--success-color, #10b981)" }}
          >
            Run Sweep: {activeCategory}
          </button>
        )}

        {statusMessage && (
          <span style={{ fontSize: "0.9rem", opacity: 0.9, color: "var(--accent-color)" }}>
            {statusMessage}
          </span>
        )}
        {activeRun && (
          <div style={{ width: "100%", fontSize: "0.82rem", opacity: 0.9 }} data-testid="superbench-run-identity">
            <strong>{activeRun.status}</strong> · Run {activeRun.run_id} · Trace {activeRun.trace_id}
            {activeRun.memory_backend && <> · Memory {activeRun.memory_backend}</>}
            {activeRun.failure_category && <> · Failure {activeRun.failure_category}</>}
            {activeRun.recovery_action && <> · Recovery {activeRun.recovery_action}</>}
            {activeRun.retry_eligible && <> · Retry eligible</>}
          </div>
        )}
      </div>

      {/* Main 1000 Tasks Status Grid Dashboard */}
      {tasks.length > 0 && (
        <div className="builderPanel" style={{ marginBottom: "2rem" }}>
          <h3>Interactive Execution Grid</h3>
          <p style={{ fontSize: "0.85rem", opacity: 0.8, marginBottom: "1rem" }}>
            Hover over any cell to introspect details. Clicking a cell pins the task to the evaluation terminal below.
          </p>
          
          <div style={{ display: "flex", gap: "1.5rem", marginBottom: "1rem", fontSize: "0.85rem" }}>
            <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
              <span style={{ width: "10px", height: "10px", borderRadius: "2px", background: "rgba(255,255,255,0.15)" }} /> Unexecuted
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
              <span style={{ width: "10px", height: "10px", borderRadius: "2px", background: "var(--success-color, #10b981)" }} /> Success
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
              <span style={{ width: "10px", height: "10px", borderRadius: "2px", background: "var(--warning-color, #f59e0b)" }} /> Guard Gated / Safe
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
              <span style={{ width: "10px", height: "10px", borderRadius: "2px", background: "var(--danger-color, #ef4444)" }} /> Failed
            </span>
          </div>

          <div style={{ 
            display: "grid", 
            gridTemplateColumns: "repeat(50, 1fr)", 
            gap: "4px",
            background: "rgba(0,0,0,0.2)",
            padding: "1rem",
            borderRadius: "8px",
            border: "1px solid rgba(255,255,255,0.05)"
          }}>
            {tasks.map((task) => (
              <div
                key={task.id}
                onClick={() => setSelectedTask(task)}
                title={`[${task.id}] [${task.category}] - ${task.prompt}`}
                style={{
                  aspectRatio: "1",
                  borderRadius: "2px",
                  background: getTaskStatusColor(task.id),
                  cursor: "pointer",
                  transition: "transform 0.1s ease",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = "scale(1.3)";
                  e.currentTarget.style.zIndex = "10";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = "scale(1)";
                  e.currentTarget.style.zIndex = "1";
                }}
              />
            ))}
          </div>
        </div>
      )}

      {/* Bottom Layout: Selected Task and Logs list */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>
        
        {/* Task Terminal */}
        <div className="builderPanel">
          <h3>Evaluation Terminal</h3>
          {selectedTask ? (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                <span style={{ padding: "2px 8px", background: "rgba(255,255,255,0.1)", borderRadius: "4px", fontSize: "0.8rem" }}>
                  {selectedTask.id}
                </span>
                <span style={{ padding: "2px 8px", background: "var(--accent-color)", borderRadius: "4px", fontSize: "0.8rem", color: "#000", fontWeight: "bold" }}>
                  {selectedTask.difficulty}
                </span>
              </div>
              <strong style={{ display: "block", marginBottom: "0.5rem", color: "var(--accent-color)" }}>
                {selectedTask.category}
              </strong>
              
              <div style={{ 
                background: "rgba(0,0,0,0.3)", 
                padding: "1rem", 
                borderRadius: "6px", 
                fontSize: "0.9rem", 
                marginBottom: "1rem",
                fontFamily: "monospace",
                borderLeft: "3px solid var(--accent-color)"
              }}>
                {selectedTask.prompt}
              </div>

              <strong style={{ display: "block", marginBottom: "0.2rem", fontSize: "0.9rem" }}>Expected Verification:</strong>
              <p style={{ fontSize: "0.85rem", opacity: 0.9, marginBottom: "1.5rem" }}>
                {selectedTask.expected_output}
              </p>

              <div style={{ display: "flex", gap: "1rem" }}>
                <button
                  onClick={() => handleRunTask(selectedTask.id)}
                  disabled={loading}
                  className="buttonPrimary"
                  style={{ padding: "0.5rem 1rem", flex: 1 }}
                >
                  {loading ? "Running..." : "Run Task"}
                </button>
              </div>

              {/* Execution telemetry logs */}
              {results.find(r => r.task_id === selectedTask.id) && (
                <div style={{ marginTop: "1.5rem", borderTop: "1px solid rgba(255,255,255,0.1)", paddingTop: "1rem" }}>
                  <h4 style={{ color: "var(--accent-color)", marginBottom: "0.5rem" }}>Telemetry Execution Log</h4>
                  
                  {(() => {
                    const runLog = results.find(r => r.task_id === selectedTask.id);
                    return (
                      <div style={{ fontSize: "0.85rem", display: "grid", gap: "0.5rem" }}>
                        <div><strong>Result Status:</strong> <span style={{ color: runLog.status === "succeeded" ? "var(--success-color)" : runLog.status === "degraded" ? "var(--warning-color)" : "var(--danger-color)" }}>{runLog.status}</span></div>
                        <div><strong>Run ID:</strong> {runLog.run_id}</div>
                        <div><strong>Trace ID:</strong> {runLog.trace_id}</div>
                        <div><strong>Memory:</strong> {runLog.memory_mode} / {runLog.memory_backend}</div>
                        <div><strong>Latency:</strong> {runLog.latency}s</div>
                        <div><strong>Confidence Indicator:</strong> {Math.round(runLog.confidence * 100)}%</div>
                        <div><strong>Planning Strategy:</strong> {runLog.planning_strategy}</div>
                        <div><strong>Lessons Learned:</strong> {runLog.lessons_learned}</div>
                        {runLog.failure_mode && (
                          <div style={{ background: "rgba(239, 68, 68, 0.1)", padding: "0.5rem", borderRadius: "4px", border: "1px solid rgba(239,68,68,0.2)" }}>
                            <div style={{ color: "var(--danger-color)" }}><strong>Failure Mode:</strong> {runLog.failure_mode}</div>
                            <div><strong>Root Cause:</strong> {runLog.root_cause}</div>
                            <div><strong>Proposed Fix:</strong> {runLog.proposed_fix}</div>
                          </div>
                        )}
                      </div>
                    );
                  })()}
                </div>
              )}

            </div>
          ) : (
            <div style={{ padding: "3rem 1rem", textAlign: "center", opacity: 0.7 }}>
              Select a task cell from the grid above to load it in the terminal.
            </div>
          )}
        </div>

        {/* Categories breakdown & Execution Logs List */}
        <div className="builderPanel" style={{ display: "flex", flexDirection: "column", maxHeight: "500px" }}>
          <h3>Category Statistics</h3>
          <div style={{ overflowY: "auto", flex: 1, paddingRight: "0.5rem" }}>
            <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem", flexWrap: "wrap" }}>
              {categoriesList.map(cat => (
                <button
                  key={cat}
                  onClick={() => setActiveCategory(cat)}
                  style={{
                    padding: "3px 10px",
                    borderRadius: "4px",
                    background: activeCategory === cat ? "var(--accent-color)" : "rgba(255,255,255,0.08)",
                    color: activeCategory === cat ? "#000" : "#fff",
                    border: "none",
                    cursor: "pointer",
                    fontSize: "0.8rem",
                    fontWeight: activeCategory === cat ? "bold" : "normal"
                  }}
                >
                  {cat}
                </button>
              ))}
            </div>

            <div className="ladderList">
              {Object.entries(stats.category_stats).map(([catName, data]: [string, any]) => (
                <article key={catName} className="ladderItem ready" style={{ marginBottom: "0.5rem", padding: "0.5rem" }}>
                  <header>
                    <strong>{catName}</strong>
                    <span>{data.success}/{data.executed} OK</span>
                  </header>
                  <div className="maturityBar" style={{ marginTop: "0.3rem", height: "4px" }}>
                    <span style={{ 
                      width: `${data.executed ? (data.success / data.executed) * 100 : 0}%`,
                      background: "var(--success-color, #10b981)" 
                    }} />
                  </div>
                </article>
              ))}
            </div>
          </div>
        </div>

      </div>

    </div>
  );
}
