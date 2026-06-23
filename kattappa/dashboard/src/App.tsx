import { useState, useEffect } from 'react';

// --- Types & Interfaces -----------------------------------

interface MetricInfo {
  key: string;
  name: string;
  value: number | null;
  display_value: string;
  unit: string;
  status: 'ok' | 'warn' | 'critical' | 'unknown';
  ci_band?: string | null;
  trust_level?: 'MEASURED' | 'DERIVED' | 'PREDICTED';
}

interface ExecutivePanel {
  id: string;
  name: string;
  priority: number;
  status: 'ok' | 'warn' | 'critical' | 'unknown';
  metrics: MetricInfo[];
}

interface ExecutiveData {
  panels: ExecutivePanel[];
  metric_trust: Record<string, 'MEASURED' | 'DERIVED' | 'PREDICTED'>;
}

interface ProposalInfo {
  id: string;
  title?: string;
  status: string;
  created_at: number;
  predicted_gain?: number;
  production_gain?: number;
}

interface ProposalsPanelData {
  total: number;
  by_status: Record<string, number>;
  awaiting_review: number;
  elevated_review: number;
  proposals: ProposalInfo[];
}

interface ExperimentInfo {
  id: string;
  status: string;
  created_at: number;
  results?: {
    passed?: boolean;
    score?: number;
  } | null;
}

interface ExperimentsPanelData {
  total: number;
  orphan: number;
  completed: number;
  sandbox_pass_rate: number | null;
  experiments: ExperimentInfo[];
}

interface BenchmarkCategory {
  category: string;
  current_score: number | null;
  floor: number;
  status: 'ok' | 'critical' | 'unknown';
  runs: number;
  history: Array<{ score: number; timestamp: number }>;
}

interface BenchmarksPanelData {
  categories: BenchmarkCategory[];
  floors: Record<string, number>;
  total_runs: number;
}

interface ResearchItem {
  id: string;
  paper_title: string;
  trust_level: 'High' | 'Medium' | 'Low' | 'Very Low';
  usefulness_score: number;
  comparison?: {
    touches_protected_core?: boolean;
    suggested_changes?: string[];
  };
}

interface ResearchPanelData {
  total: number;
  by_trust: Record<string, number>;
  avg_usefulness: number | null;
  protected_core_touches: number;
  items: ResearchItem[];
}

interface EroidData {
  eroi: number | null;
  insufficient: boolean;
  formula: string;
  ci: {
    n: number;
    mean: number | null;
    std_dev: number | null;
    margin: number | null;
    low: number | null;
    high: number | null;
  };
}

interface MetricTrustData {
  classification: Record<string, 'MEASURED' | 'DERIVED' | 'PREDICTED'>;
  by_trust: Record<'MEASURED' | 'DERIVED' | 'PREDICTED', string[]>;
  note: string;
}

interface BurnInSnapshot {
  week_index: number;
  timestamp: number;
  production_eroi: number | null;
  rollback_rate: number;
  approval_error_rate: number;
  transfer_rate: number;
  research_debt: number;
  reviewer_backlog: number;
  false_improvement_rate: number;
  prediction_reliability_error: number | null;
  protected_core_violations: number;
}

interface BurnInStatusData {
  state: 'NORMAL' | 'AUDIT';
  active_freezes: string[];
  research_debt: number;
  debt_accumulating: boolean;
  average_prediction_error: number | null;
  snapshots: BurnInSnapshot[];
}

interface SourceReputationEntry {
  source_name: string;
  trust_level: string;
  correct_predictions: number;
  incorrect_predictions: number;
  useful_ideas: number;
  rejected_ideas: number;
  reputation_score: number;
}

interface ResearchLoopStatusData {
  documents_read_today: number;
  summaries_generated_today: number;
  ideas_extracted_today: number;
  proposals_created_today: number;
  pending_approvals: number;
  last_run_time: number | null;
  duplicate_documents_filtered?: number;
  duplicate_proposals_filtered?: number;
  reputations?: SourceReputationEntry[];
}

interface AgentReputationEntry {
  agent: string;
  role: string;
  reputation: number;
  successes: number;
  failures: number;
  health: string;
}

interface DebateStep {
  agent: string;
  evidence?: string;
  proposal?: string;
  complexity?: number;
  risk?: string;
  safety?: string;
  score?: number;
  vote?: string;
}

interface DebateEntry {
  id: string;
  title: string;
  timestamp: number;
  proposal_details: string;
  steps: DebateStep[];
  votes: Record<string, string>;
  consensus: string;
  vetoed: boolean;
}

interface AgentSocietyData {
  reputations: AgentReputationEntry[];
  debates: DebateEntry[];
  top_performing_agent: string;
  most_accurate_reviewer: string;
  most_common_failure_source: string;
  veto_count: number;
  total_debates: number;
}

interface MissionInfo {
  id: string;
  title: string;
  description: string;
  stages: string[];
  current_stage: string;
  status: 'running' | 'waiting_approval' | 'completed' | 'failed';
  created_at: number;
  completed_at: number | null;
  lessons_learned: string[];
  user_project: string;
}

interface AgentPerformanceStats {
  plan: number;
  execution: number;
  accuracy: number;
  cost: number;
  time: number;
}

interface StrategicRecommendation {
  project_title: string;
  details: string;
  confidence: number;
  priority: 'High' | 'Medium' | 'Low';
  reason: string;
  created_at: number;
}

interface LongHorizonPlan {
  goal: string;
  today: string;
  this_week: string;
  this_month: string;
  this_quarter: Record<string, string>;
}

interface ExecutiveBrainData {
  missions: MissionInfo[];
  counts: Record<'running' | 'waiting_approval' | 'completed' | 'failed', number>;
  performance: Record<string, AgentPerformanceStats>;
  weekly_trend: Array<{ week: string; success_rate: number }>;
  recommendations: StrategicRecommendation[];
  long_horizon: LongHorizonPlan;
}

interface PersistentMissionForecast {
  completion_percentage: number;
  risk_score: number;
  success_probability: number;
  time_remaining_minutes: number;
}

interface PersistentMissionInfo {
  id: string;
  title: string;
  description: string;
  user_project: string;
  status: string;
  stage: string;
  progress: number;
  blocked: boolean;
  blockers: string[];
  resources: string[];
  confidence_score: number;
  next_action: string;
  completed_stages: string[];
  pending_stages: string[];
  forecast: PersistentMissionForecast;
}

interface UnresolvedFailure {
  failure_id: string;
  mission_id: string;
  stage: string;
  agent: string;
  reason: string;
  recovery_path: string;
  timestamp: number;
  resolved: boolean;
  retry_count: number;
}

interface CrossLearningFinding {
  knowledge_id: string;
  source_mission_id: string;
  topic: string;
  details: string;
  timestamp: number;
}

interface CommandCenterData {
  active_missions: PersistentMissionInfo[];
  recovery_queue: UnresolvedFailure[];
  cross_learning: CrossLearningFinding[];
}

// --- Icons (Emoji representation for high compatibility and speed) -----
const ICONS: Record<string, string> = {
  safety_governance: '🛡️',
  learning_reality: '📊',
  system_health: '🩺',
  proposals: '📜',
  experiments: '🧪',
  benchmarks: '🎯',
  research: '🔬',
  eroi: '📈',
  trust: '🏷️',
};

const API_BASE = ''; // Proxy or same-origin in production

export default function App() {
  const [executive, setExecutive] = useState<ExecutiveData | null>(null);
  const [proposals, setProposals] = useState<ProposalsPanelData | null>(null);
  const [experiments, setExperiments] = useState<ExperimentsPanelData | null>(null);
  const [benchmarks, setBenchmarks] = useState<BenchmarksPanelData | null>(null);
  const [research, setResearch] = useState<ResearchPanelData | null>(null);
  const [eroi, setEroi] = useState<EroidData | null>(null);
  const [trustMap, setTrustMap] = useState<MetricTrustData | null>(null);
  const [burnIn, setBurnIn] = useState<BurnInStatusData | null>(null);
  const [researchLoop, setResearchLoop] = useState<ResearchLoopStatusData | null>(null);
  const [society, setSociety] = useState<AgentSocietyData | null>(null);
  const [executiveBrain, setExecutiveBrain] = useState<ExecutiveBrainData | null>(null);
  const [missionTitle, setMissionTitle] = useState('');
  const [missionDesc, setMissionDesc] = useState('');
  const [creatingMission, setCreatingMission] = useState(false);
  const [creationError, setCreationError] = useState<string | null>(null);
  const [commandCenter, setCommandCenter] = useState<CommandCenterData | null>(null);
  const [recovering, setRecovering] = useState(false);

  const [triggeringLoop, setTriggeringLoop] = useState(false);
  const [triggerMessage, setTriggerMessage] = useState<string | null>(null);
  const [triggerError, setTriggerError] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const refreshInterval = 5000; // 5 seconds (constant to resolve unused state setter compile warning)
  const [lastRefreshed, setLastRefreshed] = useState<Date>(new Date());
  const [isPaused, setIsPaused] = useState(false);
  const [timeToNext, setTimeToNext] = useState(5);

  const [resetReviewer, setResetReviewer] = useState('');
  const [resetMessage, setResetMessage] = useState<string | null>(null);
  const [resetError, setResetError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      const [execRes, propRes, expRes, benchRes, resRes, eroiRes, trustRes, burnRes, loopRes, societyRes, brainRes, centerRes] = await Promise.all([
        fetch(`${API_BASE}/dashboard/executive`),
        fetch(`${API_BASE}/dashboard/proposals`),
        fetch(`${API_BASE}/dashboard/experiments`),
        fetch(`${API_BASE}/dashboard/benchmarks`),
        fetch(`${API_BASE}/dashboard/research`),
        fetch(`${API_BASE}/dashboard/eroi`),
        fetch(`${API_BASE}/dashboard/metric-trust`),
        fetch(`${API_BASE}/dashboard/burn-in/status`),
        fetch(`${API_BASE}/dashboard/research-loop/status`),
        fetch(`${API_BASE}/dashboard/agent-society/debates`),
        fetch(`${API_BASE}/dashboard/executive-brain/missions`),
        fetch(`${API_BASE}/dashboard/executive-brain/persistent-missions`),
      ]);

      const [execData, propData, expData, benchData, resData, eroiData, trustData, burnData, loopData, societyData, brainData, centerData] = await Promise.all([
        execRes.json(),
        propRes.json(),
        expRes.json(),
        benchRes.json(),
        resRes.json(),
        eroiRes.json(),
        trustRes.json(),
        burnRes.json(),
        loopRes.json(),
        societyRes.json(),
        brainRes.json(),
        centerRes.json(),
      ]);

      if (
        execData.status === 'ok' &&
        propData.status === 'ok' &&
        expData.status === 'ok' &&
        benchData.status === 'ok' &&
        resData.status === 'ok' &&
        eroiData.status === 'ok' &&
        trustData.status === 'ok' &&
        burnData.status === 'ok' &&
        loopData.status === 'ok' &&
        societyData.status === 'ok' &&
        brainData.status === 'ok' &&
        centerData.status === 'ok'
      ) {
        setExecutive(execData.data);
        setProposals(propData.data);
        setExperiments(expData.data);
        setBenchmarks(benchData.data);
        setResearch(resData.data);
        setEroi(eroiData.data);
        setTrustMap(trustData.data);
        setBurnIn(burnData.data);
        setResearchLoop(loopData.data);
        setSociety(societyData.data);
        setExecutiveBrain(brainData.data);
        setCommandCenter(centerData.data);
        setError(null);
      } else {
        setError('One or more backend API calls returned an error status.');
      }
    } catch (err: any) {
      setError(err.message || 'Failed to connect to the backend dashboard API.');
    } finally {
      setLoading(false);
      setLastRefreshed(new Date());
      setTimeToNext(refreshInterval / 1000);
    }
  };

  // Initial fetch
  useEffect(() => {
    fetchData();
  }, []);

  // Timer & Auto-Polling
  useEffect(() => {
    if (isPaused) return;

    const timer = setInterval(() => {
      setTimeToNext((prev) => {
        if (prev <= 1) {
          fetchData();
          return refreshInterval / 1000;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [isPaused, refreshInterval]);

  const handleManualRefresh = () => {
    setLoading(true);
    fetchData();
  };

  const handleReset = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resetReviewer) return;
    try {
      const res = await fetch(`${API_BASE}/dashboard/burn-in/reset?reviewer=${encodeURIComponent(resetReviewer)}`, {
        method: 'POST',
      });
      const data = await res.json();
      if (data.status === 'ok') {
        setResetMessage(data.message);
        setResetError(null);
        setResetReviewer('');
        fetchData();
      } else {
        setResetError(data.message);
        setResetMessage(null);
      }
    } catch (err: any) {
      setResetError(err.message || 'Failed to submit override.');
    }
  };

  const handleSnapshot = async () => {
    try {
      const res = await fetch(`${API_BASE}/dashboard/burn-in/snapshot`, {
        method: 'POST',
      });
      const data = await res.json();
      if (data.status === 'ok') {
        fetchData();
      } else {
        alert('Snapshot error: ' + data.message);
      }
    } catch (err: any) {
      alert('Snapshot failed: ' + err.message);
    }
  };

  const handleTriggerResearchLoop = async () => {
    setTriggeringLoop(true);
    setTriggerError(null);
    setTriggerMessage(null);
    try {
      const res = await fetch(`${API_BASE}/dashboard/research-loop/trigger`, {
        method: 'POST',
      });
      const data = await res.json();
      if (data.status === 'ok') {
        const stats = data.data;
        setTriggerMessage(
          `Research loop execution completed. Read ${stats.documents_read} docs, generated ${stats.summaries_generated} summaries, extracted ${stats.ideas_extracted} ideas, created ${stats.proposals_created} proposals, and rejected ${stats.proposals_rejected} proposals.`
        );
        fetchData();
      } else {
        setTriggerError(data.message || 'Trigger execution failed.');
      }
    } catch (err: any) {
      setTriggerError(err.message || 'Failed to trigger research loop.');
    } finally {
      setTriggeringLoop(false);
    }
  };

  const handleCreateMission = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!missionTitle.trim()) return;
    setCreatingMission(true);
    setCreationError(null);
    try {
      const res = await fetch(`${API_BASE}/dashboard/executive-brain/missions/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: missionTitle, description: missionDesc })
      });
      const data = await res.json();
      if (data.status === 'ok') {
        setMissionTitle('');
        setMissionDesc('');
        fetchData();
      } else {
        setCreationError(data.message || 'Failed to create mission.');
      }
    } catch (err: any) {
      setCreationError(err.message || 'Error occurred during mission creation.');
    } finally {
      setCreatingMission(false);
    }
  };

  const handleRecoverMission = async (failureId: string) => {
    setRecovering(true);
    try {
      const res = await fetch(`${API_BASE}/dashboard/executive-brain/missions/recover`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ failure_id: failureId })
      });
      const data = await res.json();
      if (data.status === 'ok') {
        fetchData();
      } else {
        alert('Recovery error: ' + data.message);
      }
    } catch (err: any) {
      alert('Recovery connection failed: ' + err.message);
    } finally {
      setRecovering(false);
    }
  };

  if (loading && !executive) {
    return (
      <div className="loading-state">
        <div className="spinner"></div>
        <p>Loading governance telemetry...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="error-state">
        <p style={{ color: 'var(--critical)', fontWeight: 'bold' }}>⚠️ API Connection Failure</p>
        <p style={{ fontSize: '12px', opacity: 0.8 }}>{error}</p>
        <button
          onClick={handleManualRefresh}
          style={{
            marginTop: '12px',
            padding: '6px 16px',
            background: 'var(--accent-blue)',
            border: 'none',
            borderRadius: 'var(--radius-xs)',
            color: '#fff',
            cursor: 'pointer',
          }}
        >
          Retry Connection
        </button>
      </div>
    );
  }

  return (
    <div className="dashboard">
      {/* HEADER */}
      <header className="header">
        <div className="header-title">
          <div className="header-icon">🛡️</div>
          <div>
            <h1>Kattappa Observability Layer</h1>
            <div className="header-subtitle">Step 7.3 — Governance-Grade Decision & Safety Oversight Dashboard</div>
          </div>
        </div>
        <div className="header-meta">
          <div className="refresh-indicator">
            <div className="refresh-dot"></div>
            <span>
              {isPaused
                ? `Polling Paused (Sync: ${lastRefreshed.toLocaleTimeString()})`
                : `Refreshing in ${timeToNext}s (Sync: ${lastRefreshed.toLocaleTimeString()})`}
            </span>
          </div>
          <button
            onClick={() => setIsPaused(!isPaused)}
            style={{
              padding: '4px 10px',
              background: 'var(--bg-glass)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-xs)',
              color: 'var(--text-secondary)',
              cursor: 'pointer',
              fontSize: '11px',
            }}
          >
            {isPaused ? 'Resume Auto-Poll' : 'Pause'}
          </button>
          <button
            onClick={handleManualRefresh}
            style={{
              padding: '4px 10px',
              background: 'var(--bg-glass)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-xs)',
              color: 'var(--text-secondary)',
              cursor: 'pointer',
              fontSize: '11px',
            }}
          >
            🔄 Refresh Now
          </button>
          <span className="readonly-badge">READ ONLY MODE</span>
        </div>
      </header>

      {/* BURN-IN SAFETY STATUS BANNER */}
      {burnIn && (
        <div className="panel" style={{
          borderLeft: `5px solid ${burnIn.state === 'AUDIT' ? 'var(--critical)' : 'var(--ok)'}`,
          background: burnIn.state === 'AUDIT' ? 'rgba(239, 68, 68, 0.08)' : 'rgba(34, 197, 94, 0.04)',
          display: 'flex',
          flexDirection: 'column',
          gap: '14px',
          padding: '20px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <span style={{ fontSize: '24px' }}>
                {burnIn.state === 'AUDIT' ? '🚨' : '🛡️'}
              </span>
              <div>
                <h3 style={{ fontSize: '15px', fontWeight: 600, color: '#fff' }}>
                  System Burn-In Status: {burnIn.state === 'AUDIT' ? 'AUDIT MODE (SYSTEM FROZEN)' : 'NORMAL OPERATION'}
                </h3>
                <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                  {burnIn.state === 'AUDIT' 
                    ? 'Economic, Safety, Governance, or Research trend failures detected. Proposal generation, sandbox testing, and deployments are BLOCKED.'
                    : 'All telemetry filters active. Monitoring week-over-week metric trends.'}
                </p>
              </div>
            </div>

            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                onClick={handleSnapshot}
                style={{
                  padding: '6px 12px',
                  background: 'var(--bg-glass)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-xs)',
                  color: 'var(--text-primary)',
                  cursor: 'pointer',
                  fontSize: '12px',
                  fontWeight: 500
                }}
              >
                📸 Trigger Weekly Snapshot
              </button>
            </div>
          </div>

          {burnIn.state === 'AUDIT' && (
            <div style={{ borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '14px' }}>
              <h4 style={{ fontSize: '12px', color: 'var(--critical)', fontWeight: 600, marginBottom: '6px' }}>Active Freeze Triggers:</h4>
              <ul style={{ paddingLeft: '20px', fontSize: '12px', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                {burnIn.active_freezes.map((f, i) => <li key={i}>{f}</li>)}
              </ul>

              <form onSubmit={handleReset} style={{ marginTop: '16px', display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                <label style={{ fontSize: '12px', color: '#fff' }}>Reset State (Human Reviewer Name):</label>
                <input
                  type="text"
                  placeholder="e.g. Alice Smith"
                  value={resetReviewer}
                  onChange={(e) => setResetReviewer(e.target.value)}
                  style={{
                    padding: '6px 10px',
                    background: '#0e131f',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-xs)',
                    color: '#fff',
                    fontSize: '12px',
                    width: '180px'
                  }}
                />
                <button
                  type="submit"
                  style={{
                    padding: '6px 14px',
                    background: 'var(--critical)',
                    border: 'none',
                    borderRadius: 'var(--radius-xs)',
                    color: '#fff',
                    fontWeight: 600,
                    cursor: 'pointer',
                    fontSize: '12px'
                  }}
                >
                  Confirm Manual Override
                </button>
                {resetMessage && <span style={{ color: 'var(--ok)', fontSize: '12px', marginLeft: '10px' }}>{resetMessage}</span>}
                {resetError && <span style={{ color: 'var(--critical)', fontSize: '12px', marginLeft: '10px' }}>{resetError}</span>}
              </form>
            </div>
          )}
        </div>
      )}


      {/* THREE-PANEL EXECUTIVE SUMMARY */}
      <div className="section-label">Executive Metrics (Governance Priority Order)</div>
      <div className="executive-row">
        {executive?.panels.map((panel) => (
          <div key={panel.id} className={`panel exec-panel priority-${panel.priority}`}>
            <div className="panel-header">
              <div className="panel-title">
                <span className="panel-title-icon">{ICONS[panel.id] || '📊'}</span>
                <h2>{panel.name}</h2>
              </div>
              <span className="panel-priority">Priority {panel.priority}</span>
            </div>

            <div className="metrics-grid">
              {panel.metrics.map((metric) => {
                const trust = executive.metric_trust[metric.key];
                return (
                  <div key={metric.key} className={`metric-card ${metric.status}`} title={`${metric.name}: Trust level is ${trust}`}>
                    <div className="metric-label">{metric.name}</div>
                    <div className="metric-value">
                      {metric.value === null ? (
                        <span className="metric-na">N/A</span>
                      ) : (
                        metric.display_value
                      )}
                    </div>
                    {metric.ci_band && (
                      <div className="metric-ci" title="95% Confidence Interval">
                        ± {metric.ci_band}
                      </div>
                    )}
                    <div className="metric-footer">
                      <div className={`alert-dot ${metric.status}`}></div>
                      {trust && (
                        <span className={`trust-badge ${trust}`}>{trust}</span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* LOWER DATA DRILL-DOWN */}
      <div className="lower-row-3">
        {/* EROI DEEP DIVE PANEL */}
        <div className="panel">
          <div className="panel-header">
            <div className="panel-title">
              <span className="panel-title-icon">{ICONS.eroi}</span>
              <h2>Production EROI</h2>
            </div>
            <span className="protected-tag">PROTECTED CORE</span>
          </div>

          <div className="eroi-display">
            {eroi?.insufficient ? (
              <>
                <div className="eroi-na">Insufficient Data to Compute EROI</div>
                <div className="eroi-n">Valid Deployments (N): {eroi.ci.n} / Minimum: 2</div>
              </>
            ) : (
              <>
                <div className="eroi-main" title="Mean Return on Investment">
                  {eroi?.eroi !== null ? eroi?.eroi.toFixed(2) : 'N/A'}
                </div>
                {eroi?.ci.margin && (
                  <div className="eroi-ci">
                    Interval (95% CI): {eroi.ci.low?.toFixed(2)} to {eroi.ci.high?.toFixed(2)} (margin ± {eroi.ci.margin.toFixed(2)})
                  </div>
                )}
                <div className="eroi-n">Total Evaluated Deployments (N): {eroi?.ci.n}</div>
              </>
            )}
            <div className="eroi-formula">
              Formula:<br />
              <code>{eroi?.formula}</code>
            </div>
          </div>
        </div>

        {/* RESEARCH DEBT & PREDICTION RELIABILITY */}
        <div className="panel">
          <div className="panel-header">
            <div className="panel-title">
              <span className="panel-title-icon">⚖️</span>
              <h2>Research Debt & Reliability</h2>
            </div>
            <span className="protected-tag">BURN-IN AUDIT</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '18px', padding: '10px 0' }}>
            <div>
              <div style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Research Debt</div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '4px' }}>
                <span style={{ fontSize: '32px', fontWeight: 'bold', fontFamily: 'JetBrains Mono, monospace', color: burnIn?.debt_accumulating ? 'var(--warn)' : 'var(--text-primary)' }}>
                  {burnIn ? `${burnIn.research_debt.toFixed(1)} units` : 'N/A'}
                </span>
                {burnIn?.debt_accumulating && (
                  <span className="status-pill" style={{ background: 'var(--warn-dim)', color: 'var(--warn)', border: '1px solid rgba(245,158,11,0.2)', fontSize: '9px', fontWeight: 600 }}>
                    DEBT ACCUMULATING
                  </span>
                )}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                Debt = Total Improvement Costs - Production Benefits
              </div>
            </div>

            <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '14px' }}>
              <div style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Prediction Error Rate</div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', fontFamily: 'JetBrains Mono, monospace', color: 'var(--text-primary)', marginTop: '4px' }}>
                {burnIn?.average_prediction_error !== null && burnIn?.average_prediction_error !== undefined
                  ? `± ${(burnIn.average_prediction_error * 100).toFixed(2)}%`
                  : 'No evaluations yet'}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                Average divergence between predicted and actual gain
              </div>
            </div>
          </div>
        </div>

        {/* METRIC TRUST MAP EXPLANATION */}
        <div className="panel">
          <div className="panel-header">
            <div className="panel-title">
              <span className="panel-title-icon">{ICONS.trust}</span>
              <h2>Metric Trust Mapping</h2>
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '13px' }}>
            <p style={{ opacity: 0.8, lineHeight: 1.4 }}>
              To prevent metric cascades, Kattappa categorizes all telemetry into three distinct levels of evidentiary trust:
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <div style={{ padding: '6px 10px', background: 'rgba(59,130,246,0.06)', borderRadius: 'var(--radius-sm)', border: '1px solid rgba(59,130,246,0.15)', fontSize: '12px' }}>
                <strong style={{ color: 'var(--measured)' }}>MEASURED:</strong> Direct counts (e.g. rollbacks).
              </div>
              <div style={{ padding: '6px 10px', background: 'rgba(168,85,247,0.06)', borderRadius: 'var(--radius-sm)', border: '1px solid rgba(168,85,247,0.15)', fontSize: '12px' }}>
                <strong style={{ color: 'var(--derived)' }}>DERIVED:</strong> Statistical processing (e.g. EROI CI).
              </div>
              <div style={{ padding: '6px 10px', background: 'rgba(249,115,22,0.06)', borderRadius: 'var(--radius-sm)', border: '1px solid rgba(249,115,22,0.15)', fontSize: '12px' }}>
                <strong style={{ color: 'var(--predicted)' }}>PREDICTED:</strong> Forecast models (e.g. sandbox gain).
              </div>
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontStyle: 'italic' }}>
              {trustMap?.note}
            </div>
          </div>
        </div>
      </div>

      <div className="lower-row-3">
        {/* PROPOSALS FUNNEL PANEL */}
        <div className="panel">
          <div className="panel-header">
            <div className="panel-title">
              <span className="panel-title-icon">{ICONS.proposals}</span>
              <h2>Proposals Funnel & Backlog</h2>
            </div>
          </div>

          <div className="funnel-bar-wrap">
            <div className="funnel-row">
              <span className="funnel-label">Total Proposals</span>
              <div className="funnel-bar-bg">
                <div className="funnel-bar-fill" style={{ width: '100%', background: 'var(--accent-blue)' }}></div>
              </div>
              <span className="funnel-count">{proposals?.total || 0}</span>
            </div>
            <div className="funnel-row">
              <span className="funnel-label">Awaiting Review</span>
              <div className="funnel-bar-bg">
                <div className="funnel-bar-fill" style={{
                  width: proposals?.total ? `${(proposals.awaiting_review / proposals.total) * 100}%` : '0%',
                  background: 'var(--accent-purple)'
                }}></div>
              </div>
              <span className="funnel-count">{proposals?.awaiting_review || 0}</span>
            </div>
            <div className="funnel-row">
              <span className="funnel-label">Elevated Review</span>
              <div className="funnel-bar-bg">
                <div className="funnel-bar-fill" style={{
                  width: proposals?.total ? `${(proposals.elevated_review / proposals.total) * 100}%` : '0%',
                  background: 'var(--warn)'
                }}></div>
              </div>
              <span className="funnel-count">{proposals?.elevated_review || 0}</span>
            </div>
            <div className="funnel-row">
              <span className="funnel-label">Deployed</span>
              <div className="funnel-bar-bg">
                <div className="funnel-bar-fill" style={{
                  width: proposals?.total ? `${((proposals.by_status.deployed || 0) / proposals.total) * 100}%` : '0%',
                  background: 'var(--ok)'
                }}></div>
              </div>
              <span className="funnel-count">{proposals?.by_status.deployed || 0}</span>
            </div>
          </div>

          <div style={{ marginTop: '20px' }}>
            <h3 style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '8px', letterSpacing: '0.5px' }}>
              Recent Lifecycle Events (Max 5)
            </h3>
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Status</th>
                  <th>Predicted Gain</th>
                </tr>
              </thead>
              <tbody>
                {proposals?.proposals.slice(0, 5).map((p) => (
                  <tr key={p.id}>
                    <td style={{ fontFamily: 'monospace', color: 'var(--text-primary)' }}>{p.id}</td>
                    <td>
                      <span className={`status-pill`} style={{
                        background: p.status === 'deployed' ? 'var(--ok-dim)' : p.status === 'rejected' ? 'var(--critical-dim)' : 'var(--warn-dim)',
                        color: p.status === 'deployed' ? 'var(--ok)' : p.status === 'rejected' ? 'var(--critical)' : 'var(--warn)',
                        border: `1px solid ${p.status === 'deployed' ? 'rgba(34,197,94,0.2)' : p.status === 'rejected' ? 'rgba(239,68,68,0.2)' : 'rgba(245,158,11,0.2)'}`
                      }}>
                        <span className="status-dot" style={{
                          background: p.status === 'deployed' ? 'var(--ok)' : p.status === 'rejected' ? 'var(--critical)' : 'var(--warn)'
                        }}></span>
                        {p.status}
                      </span>
                    </td>
                    <td style={{ fontFamily: 'monospace' }}>
                      {p.predicted_gain !== undefined ? `+${(p.predicted_gain * 100).toFixed(1)}%` : 'N/A'}
                    </td>
                  </tr>
                ))}
                {(!proposals || proposals.proposals.length === 0) && (
                  <tr>
                    <td colSpan={3} style={{ textAlign: 'center', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                      No proposals recorded
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* EXPERIMENTS & SANDBOX PANEL */}
        <div className="panel">
          <div className="panel-header">
            <div className="panel-title">
              <span className="panel-title-icon">{ICONS.experiments}</span>
              <h2>Experiments & Sandbox</h2>
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-around', background: 'var(--bg-glass)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', marginBottom: '16px', textAlign: 'center' }}>
            <div>
              <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Sandbox Pass Rate</div>
              <div style={{ fontSize: '20px', fontWeight: 'bold', fontFamily: 'monospace', color: 'var(--accent-teal)', marginTop: '4px' }}>
                {experiments?.sandbox_pass_rate !== null ? `${(experiments!.sandbox_pass_rate * 100).toFixed(0)}%` : 'N/A'}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Orphan Labs</div>
              <div style={{ fontSize: '20px', fontWeight: 'bold', fontFamily: 'monospace', color: experiments?.orphan ? 'var(--critical)' : 'var(--text-primary)', marginTop: '4px' }}>
                {experiments?.orphan || 0}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Total Runs</div>
              <div style={{ fontSize: '20px', fontWeight: 'bold', fontFamily: 'monospace', color: 'var(--text-primary)', marginTop: '4px' }}>
                {experiments?.total || 0}
              </div>
            </div>
          </div>

          <div>
            <h3 style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '8px', letterSpacing: '0.5px' }}>
              Experiment Logs (Max 5)
            </h3>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Run ID</th>
                  <th>Status</th>
                  <th>Outcome</th>
                </tr>
              </thead>
              <tbody>
                {experiments?.experiments.slice(0, 5).map((exp) => (
                  <tr key={exp.id}>
                    <td style={{ fontFamily: 'monospace', color: 'var(--text-primary)' }}>{exp.id}</td>
                    <td>{exp.status}</td>
                    <td>
                      {exp.results ? (
                        <span style={{
                          color: exp.results.passed ? 'var(--ok)' : 'var(--critical)',
                          fontWeight: 'bold',
                          fontSize: '11px',
                        }}>
                          {exp.results.passed ? 'PASS' : 'FAIL'} (score: {exp.results.score !== undefined ? exp.results.score.toFixed(2) : 'N/A'})
                        </span>
                      ) : (
                        <span style={{ color: 'var(--text-muted)' }}>Running / Unknown</span>
                      )}
                    </td>
                  </tr>
                ))}
                {(!experiments || experiments.experiments.length === 0) && (
                  <tr>
                    <td colSpan={3} style={{ textAlign: 'center', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                      No active sandbox runs
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* BENCHMARKS FLOOR MONITOR */}
        <div className="panel">
          <div className="panel-header">
            <div className="panel-title">
              <span className="panel-title-icon">{ICONS.benchmarks}</span>
              <h2>Benchmark Floors</h2>
            </div>
            <span className="protected-tag">PROTECTED CORE FLOORS</span>
          </div>

          <div className="benchmark-grid">
            {benchmarks?.categories.map((c) => (
              <div key={c.category} className="bench-cell">
                <div className="bench-cat">{c.category}</div>
                <div className={`bench-score ${c.status}`}>
                  {c.current_score !== null ? c.current_score.toFixed(2) : 'N/A'}
                </div>
                <div className="bench-floor">
                  floor: &ge;{(c.floor).toFixed(2)}
                </div>
                <div style={{
                  fontSize: '9px',
                  marginTop: '6px',
                  color: c.status === 'critical' ? 'var(--critical)' : 'var(--text-muted)',
                  fontWeight: c.status === 'critical' ? 'bold' : 'normal',
                }}>
                  {c.status === 'critical' ? '⚠️ VIOLATION' : 'OK'}
                </div>
              </div>
            ))}
            {(!benchmarks || benchmarks.categories.length === 0) && (
              <div style={{ gridColumn: 'span 2', color: 'var(--text-muted)', fontStyle: 'italic', textAlign: 'center', padding: '20px 0' }}>
                No category data available
              </div>
            )}
          </div>
          <div style={{ marginTop: '16px', fontSize: '11px', color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between' }}>
            <span>Total Arena Benchmarks: {benchmarks?.total_runs || 0} runs</span>
            <span>Floors defined in Protected Core code</span>
          </div>
        </div>
      </div>

      {/* RESEARCH SUMMARIES & SUGGESTIONS */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-title">
            <span className="panel-title-icon">{ICONS.research}</span>
            <h2>Research Advisor & Insights</h2>
          </div>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            Advisory Only (No direct deployment paths allowed)
          </span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '20px', marginBottom: '20px' }}>
          <div style={{ background: 'var(--bg-glass)', padding: '14px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Analyzed Sources</div>
            <div style={{ fontSize: '24px', fontWeight: 'bold', color: 'var(--accent-blue)', marginTop: '4px' }}>
              {research?.total || 0} papers
            </div>
          </div>
          <div style={{ background: 'var(--bg-glass)', padding: '14px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Avg Usefulness Score</div>
            <div style={{ fontSize: '24px', fontWeight: 'bold', color: 'var(--accent-purple)', marginTop: '4px' }}>
              {research?.avg_usefulness !== null ? `${research?.avg_usefulness.toFixed(1)}/100` : 'N/A'}
            </div>
          </div>
          <div style={{ background: 'var(--bg-glass)', padding: '14px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Protected Core Touches</div>
            <div style={{
              fontSize: '24px',
              fontWeight: 'bold',
              color: research?.protected_core_touches ? 'var(--critical)' : 'var(--ok)',
              marginTop: '4px'
            }}>
              {research?.protected_core_touches || 0} flagged
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {research?.items.map((item) => (
            <div key={item.id} className="research-card">
              <div className="research-header">
                <span className="research-title">{item.paper_title}</span>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  {item.comparison?.touches_protected_core && (
                    <span className="protected-tag" style={{ border: '1px solid var(--critical)', color: 'var(--critical)', background: 'var(--critical-dim)' }}>
                      TOUCHES PROTECTED CORE
                    </span>
                  )}
                  <span className={`trust-level-badge ${item.trust_level}`}>
                    Trust: {item.trust_level}
                  </span>
                  <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                    Usefulness: {item.usefulness_score}/100
                  </span>
                </div>
              </div>
              <div className="research-summary">
                {item.comparison?.suggested_changes && item.comparison.suggested_changes.length > 0 ? (
                  <div>
                    <strong>Suggested modifications:</strong>
                    <ul style={{ paddingLeft: '20px', marginTop: '4px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                      {item.comparison.suggested_changes.map((change, i) => (
                        <li key={i}>{change}</li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
                    No actionable code modifications suggested.
                  </span>
                )}
              </div>
            </div>
          ))}
          {(!research || research.items.length === 0) && (
            <div style={{ color: 'var(--text-muted)', fontStyle: 'italic', textAlign: 'center', padding: '12px 0' }}>
              No research summaries registered
            </div>
          )}
        </div>
      </div>

      {/* DAILY RESEARCH STATUS PANEL */}
      <div className="panel" style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginBottom: '20px' }}>
        <div className="panel-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div className="panel-title">
            <span className="panel-title-icon">🔬</span>
            <h2>Daily Research Loop Status</h2>
          </div>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
            Autonomously reading, summarizing, and proposing solutions daily
          </span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '14px' }}>
          <div style={{ background: 'var(--bg-glass)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Docs Read Today</div>
            <div style={{ fontSize: '20px', fontWeight: 'bold', color: 'var(--accent-blue)', marginTop: '4px', fontFamily: 'JetBrains Mono, monospace' }}>
              {researchLoop?.documents_read_today ?? 0}
            </div>
          </div>
          <div style={{ background: 'var(--bg-glass)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Summaries Generated</div>
            <div style={{ fontSize: '20px', fontWeight: 'bold', color: 'var(--accent-purple)', marginTop: '4px', fontFamily: 'JetBrains Mono, monospace' }}>
              {researchLoop?.summaries_generated_today ?? 0}
            </div>
          </div>
          <div style={{ background: 'var(--bg-glass)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Ideas Extracted</div>
            <div style={{ fontSize: '20px', fontWeight: 'bold', color: 'var(--accent-orange)', marginTop: '4px', fontFamily: 'JetBrains Mono, monospace' }}>
              {researchLoop?.ideas_extracted_today ?? 0}
            </div>
          </div>
          <div style={{ background: 'var(--bg-glass)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Proposals Created</div>
            <div style={{ fontSize: '20px', fontWeight: 'bold', color: 'var(--ok)', marginTop: '4px', fontFamily: 'JetBrains Mono, monospace' }}>
              {researchLoop?.proposals_created_today ?? 0}
            </div>
          </div>
          <div style={{ background: 'var(--bg-glass)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Pending Approvals</div>
            <div style={{ fontSize: '20px', fontWeight: 'bold', color: 'var(--warn)', marginTop: '4px', fontFamily: 'JetBrains Mono, monospace' }}>
              {researchLoop?.pending_approvals ?? 0}
            </div>
          </div>
          <div style={{ background: 'var(--bg-glass)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Docs/Props Filtered</div>
            <div style={{ fontSize: '20px', fontWeight: 'bold', color: 'var(--text-muted)', marginTop: '4px', fontFamily: 'JetBrains Mono, monospace' }}>
              {(researchLoop?.duplicate_documents_filtered ?? 0) + (researchLoop?.duplicate_proposals_filtered ?? 0)}
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '14px', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '14px' }}>
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
            <strong>Last run time:</strong> {researchLoop?.last_run_time ? new Date(researchLoop.last_run_time * 1000).toLocaleString() : 'Never run'}
          </div>
          <button
            onClick={handleTriggerResearchLoop}
            disabled={triggeringLoop || burnIn?.state === 'AUDIT'}
            style={{
              padding: '6px 16px',
              background: burnIn?.state === 'AUDIT' ? 'var(--border)' : 'var(--accent-blue)',
              color: '#fff',
              border: 'none',
              borderRadius: 'var(--radius-xs)',
              cursor: triggeringLoop || burnIn?.state === 'AUDIT' ? 'not-allowed' : 'pointer',
              fontWeight: 600,
              fontSize: '12px',
            }}
          >
            {triggeringLoop ? '⏳ Executing Research Loop...' : '🔬 Trigger Research Loop'}
          </button>
        </div>

        {researchLoop?.reputations && researchLoop.reputations.length > 0 && (
          <div style={{ marginTop: '16px', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '16px' }}>
            <h3 style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '8px', letterSpacing: '0.5px' }}>
              Research Source Reputation Ledger
            </h3>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Source Name</th>
                  <th>Trust Level</th>
                  <th>Reputation Score</th>
                  <th>Correct / Incorrect</th>
                  <th>Useful / Rejected</th>
                </tr>
              </thead>
              <tbody>
                {researchLoop.reputations.map((rep) => (
                  <tr key={rep.source_name}>
                    <td style={{ fontWeight: 'bold', color: 'var(--text-primary)' }}>{rep.source_name}</td>
                    <td>
                      <span className={`status-pill`} style={{
                        background: rep.trust_level === 'VERIFIED' ? 'rgba(34,197,94,0.08)' : rep.trust_level === 'HIGH' ? 'rgba(59,130,246,0.08)' : rep.trust_level === 'REJECTED' ? 'rgba(239,68,68,0.08)' : 'rgba(245,158,11,0.08)',
                        color: rep.trust_level === 'VERIFIED' ? 'var(--ok)' : rep.trust_level === 'HIGH' ? 'var(--accent-blue)' : rep.trust_level === 'REJECTED' ? 'var(--critical)' : 'var(--warn)',
                        border: `1px solid ${rep.trust_level === 'VERIFIED' ? 'rgba(34,197,94,0.2)' : rep.trust_level === 'REJECTED' ? 'rgba(239,68,68,0.2)' : 'rgba(245,158,11,0.2)'}`,
                        fontSize: '10px',
                        fontWeight: 'bold',
                        padding: '2px 8px',
                        borderRadius: '4px'
                      }}>
                        {rep.trust_level}
                      </span>
                    </td>
                    <td style={{ fontFamily: 'monospace', fontWeight: 'bold', color: '#fff' }}>
                      {rep.reputation_score.toFixed(3)}
                    </td>
                    <td style={{ fontFamily: 'monospace', color: 'var(--text-secondary)' }}>
                      {rep.correct_predictions} / {rep.incorrect_predictions}
                    </td>
                    <td style={{ fontFamily: 'monospace', color: 'var(--text-secondary)' }}>
                      {rep.useful_ideas} / {rep.rejected_ideas}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {triggerMessage && (
          <div style={{ padding: '8px 12px', background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.2)', borderRadius: 'var(--radius-sm)', fontSize: '12px', color: 'var(--ok)' }}>
            {triggerMessage}
          </div>
        )}
        {triggerError && (
          <div style={{ padding: '8px 12px', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 'var(--radius-sm)', fontSize: '12px', color: 'var(--critical)' }}>
            ⚠️ {triggerError}
          </div>
        )}
      </div>

      {/* AUTONOMOUS EXECUTIVE BRAIN PANEL */}
      <div className="panel" style={{ display: 'flex', flexDirection: 'column', gap: '18px', marginBottom: '20px' }}>
        <div className="panel-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div className="panel-title">
            <span className="panel-title-icon">🧠</span>
            <h2>Autonomous Executive Brain</h2>
          </div>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
            Vague goal decomposition, strategic embedded planning, and agent self-evaluator
          </span>
        </div>

        {/* Goal Engine Form */}
        <div style={{ background: 'rgba(255,255,255,0.02)', padding: '16px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
          <h3 style={{ fontSize: '12px', color: '#fff', fontWeight: 600, marginBottom: '10px' }}>⚡ Decompose Vague Goal into Structured Mission</h3>
          <form onSubmit={handleCreateMission} style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <div style={{ flex: 1, minWidth: '200px' }}>
              <label style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Goal / Mission Title</label>
              <input
                type="text"
                placeholder="e.g. Build drone jammer"
                value={missionTitle}
                onChange={(e) => setMissionTitle(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  background: '#0e131f',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-xs)',
                  color: '#fff',
                  fontSize: '12px'
                }}
              />
            </div>
            <div style={{ flex: 2, minWidth: '300px' }}>
              <label style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Mission Description / Context</label>
              <input
                type="text"
                placeholder="e.g. Develop low-cost jammer using the new chipset."
                value={missionDesc}
                onChange={(e) => setMissionDesc(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  background: '#0e131f',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-xs)',
                  color: '#fff',
                  fontSize: '12px'
                }}
              />
            </div>
            <button
              type="submit"
              disabled={creatingMission}
              style={{
                padding: '8px 16px',
                background: 'var(--accent-blue)',
                border: 'none',
                borderRadius: 'var(--radius-xs)',
                color: '#fff',
                fontWeight: 600,
                fontSize: '12px',
                cursor: creatingMission ? 'not-allowed' : 'pointer'
              }}
            >
              {creatingMission ? 'Decomposing...' : '🚀 Launch Mission'}
            </button>
          </form>
          {creationError && (
            <div style={{ marginTop: '8px', fontSize: '11px', color: 'var(--critical)' }}>⚠️ {creationError}</div>
          )}
        </div>

        {/* Active Missions Progress */}
        <div>
          <h3 style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '10px', letterSpacing: '0.5px' }}>
            Mission Execution Pipeline
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {executiveBrain?.missions && executiveBrain.missions.length > 0 ? (
              executiveBrain.missions.map((mission) => {
                const activeIndex = mission.stages.indexOf(mission.current_stage);
                return (
                  <div key={mission.id} className="research-card" style={{ padding: '14px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
                      <div>
                        <span style={{ fontWeight: '600', color: '#fff', fontSize: '13px' }}>{mission.title}</span>
                        <span style={{ fontSize: '10px', color: 'var(--text-muted)', marginLeft: '8px', fontFamily: 'monospace' }}>
                          ({mission.id} | {mission.user_project})
                        </span>
                      </div>
                      <span className="status-pill" style={{
                        background: mission.status === 'completed' ? 'rgba(34,197,94,0.08)' : mission.status === 'failed' ? 'rgba(239,68,68,0.08)' : 'rgba(59,130,246,0.08)',
                        color: mission.status === 'completed' ? 'var(--ok)' : mission.status === 'failed' ? 'var(--critical)' : 'var(--accent-blue)',
                        border: `1px solid ${mission.status === 'completed' ? 'rgba(34,197,94,0.2)' : mission.status === 'failed' ? 'rgba(239,68,68,0.2)' : 'rgba(59,130,246,0.2)'}`,
                      }}>
                        {mission.status}
                      </span>
                    </div>
                    
                    <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                      {mission.description}
                    </p>

                    {/* Progress Stages Visual Chain */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap', marginTop: '12px' }}>
                      {mission.stages.map((stage, idx) => {
                        const isCompleted = idx < activeIndex || mission.status === 'completed';
                        const isActive = idx === activeIndex && mission.status === 'running';
                        return (
                          <div key={stage} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <span style={{
                              fontSize: '11px',
                              padding: '4px 10px',
                              borderRadius: '4px',
                              fontWeight: isActive || isCompleted ? '600' : 'normal',
                              background: isCompleted ? 'rgba(34,197,94,0.12)' : isActive ? 'rgba(59,130,246,0.15)' : 'rgba(255,255,255,0.03)',
                              border: `1px solid ${isCompleted ? 'var(--ok)' : isActive ? 'var(--accent-blue)' : 'var(--border)'}`,
                              color: isCompleted ? 'var(--ok)' : isActive ? '#fff' : 'var(--text-secondary)',
                              boxShadow: isActive ? '0 0 8px rgba(59,130,246,0.4)' : 'none'
                            }}>
                              {stage}
                            </span>
                            {idx < mission.stages.length - 1 && (
                              <span style={{ color: 'var(--text-muted)', fontSize: '10px' }}>➔</span>
                            )}
                          </div>
                        );
                      })}
                    </div>

                    {/* Lessons Learned */}
                    {mission.lessons_learned && mission.lessons_learned.length > 0 && (
                      <div style={{ marginTop: '10px', paddingTop: '8px', borderTop: '1px solid rgba(255,255,255,0.04)' }}>
                        <span style={{ fontSize: '10px', color: 'var(--accent-amber)', fontWeight: 'bold' }}>💡 Lesson Learned:</span>
                        <ul style={{ paddingLeft: '16px', margin: '2px 0 0 0', fontSize: '11px', color: 'var(--text-secondary)' }}>
                          {mission.lessons_learned.map((lesson, idx) => <li key={idx}>{lesson}</li>)}
                        </ul>
                      </div>
                    )}
                  </div>
                );
              })
            ) : (
              <div style={{ color: 'var(--text-muted)', fontStyle: 'italic', textAlign: 'center', padding: '12px 0' }}>
                No active goals or missions launched
              </div>
            )}
          </div>
        </div>

        {/* Agent Performance Averages */}
        <div style={{ marginTop: '14px', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '14px' }}>
          <h3 style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '10px', letterSpacing: '0.5px' }}>
            Agent Self-Evaluation Performance Ledger (Mean Scores)
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '14px' }}>
            {executiveBrain?.performance && Object.keys(executiveBrain.performance).length > 0 ? (
              Object.entries(executiveBrain.performance).map(([agent, stats]) => {
                const overall = ((stats.plan + stats.execution + stats.accuracy + stats.cost + stats.time) / 5).toFixed(1);
                return (
                  <div key={agent} style={{ background: 'var(--bg-glass)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                      <span style={{ fontWeight: 'bold', color: '#fff', fontSize: '13px' }}>{agent} Agent</span>
                      <span style={{
                        fontSize: '11px',
                        fontWeight: 'bold',
                        color: 'var(--accent-teal)',
                        background: 'rgba(20,184,166,0.08)',
                        padding: '1px 6px',
                        borderRadius: '3px'
                      }}>
                        {overall}% Avg
                      </span>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '10px', color: 'var(--text-secondary)' }}>
                      <div>Plan Score: <span style={{ float: 'right', color: '#fff', fontFamily: 'monospace' }}>{stats.plan}%</span></div>
                      <div>Execution: <span style={{ float: 'right', color: '#fff', fontFamily: 'monospace' }}>{stats.execution}%</span></div>
                      <div>Accuracy: <span style={{ float: 'right', color: '#fff', fontFamily: 'monospace' }}>{stats.accuracy}%</span></div>
                      <div>Cost Efficiency: <span style={{ float: 'right', color: '#fff', fontFamily: 'monospace' }}>{stats.cost}%</span></div>
                      <div>Time Score: <span style={{ float: 'right', color: '#fff', fontFamily: 'monospace' }}>{stats.time}%</span></div>
                    </div>
                  </div>
                );
              })
            ) : (
              <div style={{ color: 'var(--text-muted)', fontStyle: 'italic', textAlign: 'center', padding: '10px 0' }}>
                No performance evaluations logged yet
              </div>
            )}
          </div>
        </div>

        {/* Strategic Recommendations & Long Horizon Roadmap */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginTop: '14px', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '14px' }}>
          {/* Strategic recommendations */}
          <div>
            <h3 style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '8px', letterSpacing: '0.5px' }}>
              Strategic R&D Chipset Recommendations
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {executiveBrain?.recommendations && executiveBrain.recommendations.length > 0 ? (
                executiveBrain.recommendations.map((rec, i) => (
                  <div key={i} style={{ background: 'rgba(245,158,11,0.03)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid rgba(245,158,11,0.15)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap' }}>
                      <span style={{ fontWeight: 'bold', color: 'var(--warn)', fontSize: '12px' }}>🎯 Propose: {rec.project_title}</span>
                      <span style={{ fontSize: '10px', background: 'var(--bg-glass)', padding: '1px 5px', color: 'var(--text-secondary)', borderRadius: '3px' }}>
                        Conf: {(rec.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                    <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>{rec.details}</p>
                    <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '4px', fontStyle: 'italic' }}>Reason: {rec.reason}</div>
                  </div>
                ))
              ) : (
                <div style={{ color: 'var(--text-muted)', fontStyle: 'italic', fontSize: '12px' }}>No strategic recommendations scanned</div>
              )}
            </div>
          </div>

          {/* Long Horizon planning */}
          <div>
            <h3 style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '8px', letterSpacing: '0.5px' }}>
              Long-Horizon Embedded Engineering Roadmap
            </h3>
            {executiveBrain?.long_horizon ? (
              <div style={{ background: 'var(--bg-glass)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
                <span style={{ fontWeight: 'bold', color: '#fff', fontSize: '12px' }}>Goal: {executiveBrain.long_horizon.goal}</span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '11px', color: 'var(--text-secondary)', marginTop: '6px' }}>
                  <div><strong>Today:</strong> {executiveBrain.long_horizon.today}</div>
                  <div><strong>This Week:</strong> {executiveBrain.long_horizon.this_week}</div>
                  <div><strong>This Month:</strong> {executiveBrain.long_horizon.this_month}</div>
                  <div style={{ marginTop: '4px', borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: '4px' }}>
                    <strong>Quarterly roadmap:</strong>
                    <div style={{ paddingLeft: '8px', marginTop: '2px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                      {Object.entries(executiveBrain.long_horizon.this_quarter).map(([m, desc]) => (
                        <div key={m}>• <strong>{m}:</strong> {desc}</div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ color: 'var(--text-muted)', fontStyle: 'italic', fontSize: '12px' }}>No roadmap plans generated</div>
            )}
          </div>
        </div>
      </div>

      {/* EXECUTIVE COMMAND CENTER PANEL */}
      <div className="panel" style={{ display: 'flex', flexDirection: 'column', gap: '18px', marginBottom: '20px' }}>
        <div className="panel-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div className="panel-title">
            <span className="panel-title-icon">🛰️</span>
            <h2>Executive Command Center</h2>
          </div>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
            Persistent state checkpointing, risk forecasting, failure recovery, and cross-mission learning
          </span>
        </div>

        {/* Forecasts & Active Persistent Missions */}
        <div>
          <h3 style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '12px', letterSpacing: '0.5px' }}>
            Active Persistent Missions & ETAs
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {commandCenter?.active_missions && commandCenter.active_missions.length > 0 ? (
              commandCenter.active_missions.map((m) => (
                <div key={m.id} className="research-card" style={{ padding: '16px', borderLeft: m.blocked ? '3px solid var(--critical)' : '1px solid var(--border)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
                    <div>
                      <span style={{ fontWeight: 'bold', color: '#fff', fontSize: '14px' }}>{m.title}</span>
                      <span style={{ fontSize: '11px', color: 'var(--text-secondary)', marginLeft: '8px' }}>({m.user_project})</span>
                    </div>
                    <span className="status-pill" style={{
                      background: m.blocked ? 'rgba(239,68,68,0.08)' : 'rgba(34,197,94,0.08)',
                      color: m.blocked ? 'var(--critical)' : 'var(--ok)',
                      border: `1px solid ${m.blocked ? 'rgba(239,68,68,0.2)' : 'rgba(34,197,94,0.2)'}`,
                    }}>
                      {m.blocked ? 'BLOCKED' : 'RUNNING'}
                    </span>
                  </div>

                  <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>{m.description}</p>

                  {/* Forecast details metrics */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px', marginTop: '10px', background: 'rgba(255,255,255,0.02)', padding: '10px', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border)' }}>
                    <div>
                      <div style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Completion</div>
                      <div style={{ fontSize: '14px', fontWeight: 'bold', color: 'var(--accent-teal)' }}>{m.forecast.completion_percentage}%</div>
                    </div>
                    <div>
                      <div style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Risk score</div>
                      <div style={{ fontSize: '14px', fontWeight: 'bold', color: m.forecast.risk_score > 30 ? 'var(--critical)' : 'var(--ok)' }}>{m.forecast.risk_score}%</div>
                    </div>
                    <div>
                      <div style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Success prob</div>
                      <div style={{ fontSize: '14px', fontWeight: 'bold', color: m.forecast.success_probability > 70 ? 'var(--ok)' : 'var(--warn)' }}>{m.forecast.success_probability}%</div>
                    </div>
                    <div>
                      <div style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Time remaining</div>
                      <div style={{ fontSize: '14px', fontWeight: 'bold', color: '#fff' }}>{m.forecast.time_remaining_minutes} min</div>
                    </div>
                  </div>

                  {/* Blockers alert */}
                  {m.blocked && m.blockers.length > 0 && (
                    <div style={{ marginTop: '10px', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', padding: '8px 12px', borderRadius: 'var(--radius-xs)', fontSize: '11px', color: 'var(--critical)' }}>
                      <strong>Active Blockers:</strong> {m.blockers.join(', ')}
                    </div>
                  )}

                  {/* Resource List */}
                  {m.resources.length > 0 && (
                    <div style={{ marginTop: '10px', fontSize: '11px', color: 'var(--text-secondary)' }}>
                      <strong>Allocated Resources:</strong> {m.resources.join(', ')}
                    </div>
                  )}

                  {/* Next Action */}
                  {m.next_action && (
                    <div style={{ marginTop: '8px', fontSize: '12px', color: 'var(--text-secondary)' }}>
                      <strong>Next Action Plan:</strong> <span style={{ color: '#fff' }}>{m.next_action}</span>
                    </div>
                  )}
                </div>
              ))
            ) : (
              <div style={{ color: 'var(--text-muted)', fontStyle: 'italic', textAlign: 'center', padding: '12px 0' }}>
                No active persistent missions found
              </div>
            )}
          </div>
        </div>

        {/* RCA Failure Recovery Queue */}
        <div style={{ marginTop: '14px', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '14px' }}>
          <h3 style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '10px', letterSpacing: '0.5px' }}>
            RCA Failure Recovery Queue
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {commandCenter?.recovery_queue && commandCenter.recovery_queue.length > 0 ? (
              commandCenter.recovery_queue.map((fail) => (
                <div key={fail.failure_id} style={{ background: 'rgba(239,68,68,0.03)', padding: '14px', borderRadius: 'var(--radius-sm)', border: '1px solid rgba(239,68,68,0.15)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap' }}>
                    <span style={{ fontWeight: 'bold', color: 'var(--critical)', fontSize: '12px' }}>🚨 Failure in Stage: {fail.stage} (Agent: {fail.agent})</span>
                    <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Retries: {fail.retry_count}/3</span>
                  </div>
                  <p style={{ fontSize: '12px', color: '#fff', marginTop: '6px' }}><strong>Reason:</strong> {fail.reason}</p>
                  <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}><strong>Recovery Path:</strong> {fail.recovery_path}</p>
                  
                  <button
                    onClick={() => handleRecoverMission(fail.failure_id)}
                    disabled={recovering}
                    style={{
                      marginTop: '10px',
                      padding: '4px 10px',
                      background: 'var(--bg-glass)',
                      border: '1px solid var(--border)',
                      borderRadius: 'var(--radius-xs)',
                      color: 'var(--text-primary)',
                      cursor: recovering ? 'not-allowed' : 'pointer',
                      fontSize: '11px',
                      fontWeight: 600
                    }}
                  >
                    {recovering ? 'Resolving...' : '🔧 Resolve Blocker & Continue Stage'}
                  </button>
                </div>
              ))
            ) : (
              <div style={{ color: 'var(--text-muted)', fontStyle: 'italic', fontSize: '12px', textAlign: 'center', padding: '10px 0' }}>
                All pipelines running smoothly. No active failures in the recovery queue.
              </div>
            )}
          </div>
        </div>

        {/* Cross-Mission Intelligence Feed */}
        <div style={{ marginTop: '14px', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '14px' }}>
          <h3 style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '8px', letterSpacing: '0.5px' }}>
            Cross-Mission Intelligence & Bug Feed
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {commandCenter?.cross_learning && commandCenter.cross_learning.length > 0 ? (
              commandCenter.cross_learning.map((k) => (
                <div key={k.knowledge_id} style={{ background: 'var(--bg-glass)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
                  <div style={{ fontWeight: 'bold', color: 'var(--accent-amber)', fontSize: '12px' }}>🐛 Shared Alert: {k.topic}</div>
                  <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>{k.details}</p>
                  <div style={{ fontSize: '9px', color: 'var(--text-muted)', marginTop: '4px' }}>Source Mission: {k.source_mission_id} | Timestamp: {new Date(k.timestamp * 1000).toLocaleTimeString()}</div>
                </div>
              ))
            ) : (
              <div style={{ color: 'var(--text-muted)', fontStyle: 'italic', fontSize: '12px', textAlign: 'center', padding: '8px 0' }}>
                No cross-mission bugs or alerts reported yet
              </div>
            )}
          </div>
        </div>
      </div>

      {/* AGENT SOCIETY PANEL */}
      <div className="panel" style={{ display: 'flex', flexDirection: 'column', gap: '18px', marginBottom: '20px' }}>
        <div className="panel-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div className="panel-title">
            <span className="panel-title-icon">🤖</span>
            <h2>Multi-Agent Society Ledger</h2>
          </div>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
            Decentralized multi-agent consensus and reputation tracking
          </span>
        </div>

        {/* Aggregated Stats Cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '14px' }}>
          <div style={{ background: 'var(--bg-glass)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Top Performing Agent</div>
            <div style={{ fontSize: '18px', fontWeight: 'bold', color: 'var(--ok)', marginTop: '4px' }}>
              🥇 {society?.top_performing_agent ?? 'None'}
            </div>
          </div>
          <div style={{ background: 'var(--bg-glass)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Most Accurate Reviewer</div>
            <div style={{ fontSize: '18px', fontWeight: 'bold', color: 'var(--accent-blue)', marginTop: '4px' }}>
              🎯 {society?.most_accurate_reviewer ?? 'None'}
            </div>
          </div>
          <div style={{ background: 'var(--bg-glass)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Common Failure Source</div>
            <div style={{ fontSize: '18px', fontWeight: 'bold', color: 'var(--critical)', marginTop: '4px' }}>
              ⚠️ {society?.most_common_failure_source ?? 'None'}
            </div>
          </div>
          <div style={{ background: 'var(--bg-glass)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Total Vetoes Triggered</div>
            <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#fff', marginTop: '4px', fontFamily: 'JetBrains Mono, monospace' }}>
              🛑 {society?.veto_count ?? 0}
            </div>
          </div>
        </div>

        {/* Reputations Ledger Table */}
        <div style={{ marginTop: '10px' }}>
          <h3 style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '8px', letterSpacing: '0.5px' }}>
            Agent Health & Reputation Ledger
          </h3>
          <table className="data-table">
            <thead>
              <tr>
                <th>Agent Name</th>
                <th>Assigned Role</th>
                <th>Reputation Score</th>
                <th>Successes / Failures</th>
                <th>Health Status</th>
              </tr>
            </thead>
            <tbody>
              {society?.reputations && society.reputations.length > 0 ? (
                society.reputations.map((agent) => (
                  <tr key={agent.agent}>
                    <td style={{ fontWeight: 'bold', color: 'var(--text-primary)' }}>{agent.agent}</td>
                    <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{agent.role}</td>
                    <td style={{ fontFamily: 'monospace', fontWeight: 'bold', color: 'var(--accent-teal)' }}>
                      {(agent.reputation * 100).toFixed(0)}%
                    </td>
                    <td style={{ fontFamily: 'monospace', color: 'var(--text-secondary)' }}>
                      {agent.successes} / {agent.failures}
                    </td>
                    <td>
                      <span style={{
                        background: agent.health === 'healthy' ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)',
                        color: agent.health === 'healthy' ? 'var(--ok)' : 'var(--critical)',
                        border: `1px solid ${agent.health === 'healthy' ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)'}`,
                        fontSize: '10px',
                        fontWeight: 'bold',
                        padding: '2px 8px',
                        borderRadius: '4px',
                        textTransform: 'uppercase'
                      }}>
                        {agent.health}
                      </span>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>No agent reputations found</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Debates & Consensus History */}
        <div style={{ marginTop: '16px', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '16px' }}>
          <h3 style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '12px', letterSpacing: '0.5px' }}>
            Consensus & Debate History
          </h3>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {society?.debates && society.debates.length > 0 ? (
              [...society.debates].reverse().map((debate) => (
                <div key={debate.id} className="research-card" style={{ padding: '16px', borderLeft: debate.vetoed ? '3px solid var(--critical)' : '1px solid var(--border)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontWeight: '600', color: '#fff' }}>{debate.title}</span>
                      <span style={{ fontSize: '10px', color: 'var(--text-muted)', fontFamily: 'monospace' }}>({debate.id})</span>
                    </div>
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                      {new Date(debate.timestamp * 1000).toLocaleString()}
                    </span>
                  </div>
                  
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '6px', lineBreak: 'anywhere' }}>
                    <strong>Proposal:</strong> {debate.proposal_details}
                  </div>
                  
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '10px' }}>
                    {Object.entries(debate.votes).map(([agent, vote]) => (
                      <span key={agent} style={{
                        fontSize: '10px',
                        padding: '2px 8px',
                        borderRadius: '4px',
                        background: 'var(--bg-glass)',
                        border: '1px solid var(--border)',
                        color: 'var(--text-secondary)'
                      }}>
                        <strong>{agent}:</strong>{' '}
                        <span style={{
                          color: vote === 'APPROVE' ? 'var(--ok)' : vote === 'REJECT' ? 'var(--critical)' : vote === 'REVISE' ? 'var(--warn)' : 'var(--text-secondary)',
                          fontWeight: 'bold'
                        }}>{vote}</span>
                      </span>
                    ))}
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid rgba(255,255,255,0.04)', marginTop: '12px', paddingTop: '8px' }}>
                    <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                      Consensus Resolution:{' '}
                      <span style={{
                        color: debate.consensus === 'APPROVED' ? 'var(--ok)' : debate.consensus === 'REVISE' ? 'var(--warn)' : 'var(--critical)',
                        fontWeight: 'bold',
                        textTransform: 'uppercase'
                      }}>
                        {debate.consensus}
                      </span>
                    </span>
                    
                    {debate.vetoed && (
                      <span className="protected-tag" style={{ border: '1px solid var(--critical)', color: 'var(--critical)', background: 'var(--critical-dim)' }}>
                        🛑 VETOED BY SECURITY/AUDITOR
                      </span>
                    )}
                  </div>
                </div>
              ))
            ) : (
              <div style={{ color: 'var(--text-muted)', fontStyle: 'italic', textAlign: 'center', padding: '12px 0' }}>
                No debate history records available
              </div>
            )}
          </div>
        </div>
      </div>

      {/* BURN-IN WEEKLY HISTORY LOG */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-title">
            <span className="panel-title-icon">🗓️</span>
            <h2>Burn-In Weekly Snapshots history</h2>
          </div>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
            Chronological audit trail of weekly snapshots
          </span>
        </div>

        <table className="data-table" style={{ marginTop: '10px' }}>
          <thead>
            <tr>
              <th>Week</th>
              <th>Date</th>
              <th>Production EROI</th>
              <th>Rollback Rate</th>
              <th>Approval Error Rate</th>
              <th>Sandbox Transfer (GRA)</th>
              <th>Research Debt</th>
              <th>Core Violations</th>
            </tr>
          </thead>
          <tbody>
            {burnIn?.snapshots && burnIn.snapshots.length > 0 ? (
              [...burnIn.snapshots].reverse().map((snap) => (
                <tr key={snap.week_index}>
                  <td style={{ fontWeight: 'bold', color: 'var(--text-primary)' }}>W{snap.week_index}</td>
                  <td style={{ fontSize: '12px' }}>{new Date(snap.timestamp * 1000).toLocaleDateString()}</td>
                  <td style={{ fontFamily: 'monospace' }}>
                    {snap.production_eroi !== null ? snap.production_eroi.toFixed(2) : 'N/A'}
                  </td>
                  <td style={{ fontFamily: 'monospace', color: snap.rollback_rate > 0.1 ? 'var(--warn)' : 'var(--text-secondary)' }}>
                    {(snap.rollback_rate * 100).toFixed(1)}%
                  </td>
                  <td style={{ fontFamily: 'monospace', color: snap.approval_error_rate > 0.05 ? 'var(--warn)' : 'var(--text-secondary)' }}>
                    {(snap.approval_error_rate * 100).toFixed(1)}%
                  </td>
                  <td style={{ fontFamily: 'monospace' }}>
                    {(snap.transfer_rate * 100).toFixed(0)}%
                  </td>
                  <td style={{ fontFamily: 'monospace', color: snap.research_debt > 0 ? 'var(--warn)' : 'var(--ok)' }}>
                    {snap.research_debt.toFixed(1)}
                  </td>
                  <td style={{ fontFamily: 'monospace', color: snap.protected_core_violations > 0 ? 'var(--critical)' : 'var(--text-secondary)', fontWeight: snap.protected_core_violations > 0 ? 'bold' : 'normal' }}>
                    {snap.protected_core_violations}
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={8} style={{ textAlign: 'center', color: 'var(--text-muted)', fontStyle: 'italic', padding: '20px 0' }}>
                  No weekly snapshots recorded yet. Use the "Trigger Weekly Snapshot" button to log the current week's telemetry.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
