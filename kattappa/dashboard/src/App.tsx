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

interface AgentReliabilityInfo {
  agent: string;
  total_actions: number;
  success_rate: number;
  rollback_rate: number;
}

interface CalibrationData {
  prediction_accuracy: number;
  success_brier: number;
  rollback_brier: number;
  duration_mae_ms: number;
  total_predictions: number;
  workflow_success_rate: number;
  workflow_total: number;
  workflow_successes: number;
  rollback_frequency: number;
  total_workflow_rollbacks: number;
  agent_reliability: AgentReliabilityInfo[];
  active_policies_count: number;
  policy_actions_blocked: number;
  policy_actions_deferred: number;
  timestamp: number;
}

// --- Goal System Interfaces (Step 8.1) -----------------------
interface GoalMilestone {
  milestone_id: string;
  goal_id: string;
  title: string;
  description: string;
  status: 'PROPOSED' | 'APPROVED' | 'ACTIVE' | 'BLOCKED' | 'COMPLETED' | 'FAILED' | 'ARCHIVED' | 'CANCELLED' | 'PENDING';
  weight: number;
  progress: number;
  created_at: number;
  completed_at: number | null;
  expected_duration_sec: number | null;
  success_probability: number | null;
  rollback_risk: number | null;
}

interface GoalV1 {
  goal_id: string;
  title: string;
  description: string;
  priority: string;
  status: string;
  created_at: number;
  target_date: string | null;
  progress: number;
  success_criteria: string[];
  owner: string | null;
  metadata: Record<string, any>;
  importance: number;
  urgency: number;
  strategic_alignment: number;
  resource_cost: number;
  priority_score: number;
  milestones: GoalMilestone[];
  dependencies: string[];
}

interface GoalReflectionMetrics {
  goal_completion_rate: number;
  goal_block_rate: number;
  goal_average_duration: number;
  goal_prediction_accuracy: number;
  goal_rollback_frequency: number;
  total_goals: number;
  completed_goals: number;
}

interface Project {
  project_id: string;
  name: string;
  description: string;
  status: string;
  completion_percent: number;
  success_rate: number;
  risk_score: number;
  resource_cost: number;
  predicted_finish: number | null;
  actual_finish: number | null;
  created_at: number;
  metadata: Record<string, any>;
  goals: {
    goal_id: string;
    title: string;
    status: string;
    progress: number;
    priority_score: number;
  }[];
  dependencies: string[];
  events: {
    event_type: string;
    payload: Record<string, any>;
    timestamp: number;
  }[];
  decisions: {
    decision_id: string;
    title: string;
    description: string;
    rationale: string;
    status: string;
    timestamp: number;
  }[];
  failures: {
    failure_id: string;
    component: string;
    error_message: string;
    resolved: boolean;
    timestamp: number;
  }[];
  rollbacks: {
    rollback_id: string;
    milestone_id: string | null;
    action_id: string | null;
    reason: string;
    timestamp: number;
  }[];
  goals_tree?: GoalV1[];
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
  calibration: '🎛️',
  goals: '🎯',
};

const API_BASE = ''; // Proxy or same-origin in production

export default function App() {
  const [executive, setExecutive] = useState<ExecutiveData | null>(null);
  const [proposals, setProposals] = useState<ProposalsPanelData | null>(null);
  const [goals, setGoals] = useState<GoalV1[]>([]);
  const [goalReflection, setGoalReflection] = useState<GoalReflectionMetrics | null>(null);
  const [selectedGoalId, setSelectedGoalId] = useState<string | null>(null);
  const [newGoalTitle, setNewGoalTitle] = useState('');
  const [newGoalDesc, setNewGoalDesc] = useState('');
  const [newGoalPriority, setNewGoalPriority] = useState('MEDIUM');
  const [newGoalTargetDate, setNewGoalTargetDate] = useState('');
  const [newGoalCriteria, setNewGoalCriteria] = useState('');
  const [newGoalOwner, setNewGoalOwner] = useState('');
  const [newGoalDeps, setNewGoalDeps] = useState<string[]>([]);
  const [newGoalImportance, setNewGoalImportance] = useState(5.0);
  const [newGoalUrgency, setNewGoalUrgency] = useState(5.0);
  const [newGoalAlignment, setNewGoalAlignment] = useState(5.0);
  const [newGoalCost, setNewGoalCost] = useState(2.0);
  const [creatingGoal, setCreatingGoal] = useState(false);
  const [goalError, setGoalError] = useState<string | null>(null);
  const [milestonesToAdd, setMilestonesToAdd] = useState<{ title: string; weight: number }[]>([
    { title: '', weight: 1.0 }
  ]);

  // --- Project System States (Step 8.2) ---
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [projectHierarchy, setProjectHierarchy] = useState<Project | null>(null);
  const [projectSimulation, setProjectSimulation] = useState<any | null>(null);
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectDesc, setNewProjectDesc] = useState('');
  const [creatingProject, setCreatingProject] = useState(false);
  const [projectError, setProjectError] = useState<string | null>(null);
  const [goalToLink, setGoalToLink] = useState('');
  const [linkingGoal, setLinkingGoal] = useState(false);
  const [depProjId, setDepProjId] = useState('');
  const [addingDep, setAddingDep] = useState(false);
  const [decisionTitle, setDecisionTitle] = useState('');
  const [decisionDesc, setDecisionDesc] = useState('');
  const [decisionRationale, setDecisionRationale] = useState('');
  const [addingDecision, setAddingDecision] = useState(false);

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
  const [calibration, setCalibration] = useState<CalibrationData | null>(null);
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
      const [execRes, propRes, expRes, benchRes, resRes, eroiRes, trustRes, burnRes, loopRes, societyRes, brainRes, centerRes, calRes] = await Promise.all([
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
        fetch(`${API_BASE}/dashboard/executive-calibration`),
      ]);

      const [execData, propData, expData, benchData, resData, eroiData, trustData, burnData, loopData, societyData, brainData, centerData, calData] = await Promise.all([
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
        calRes.json(),
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
        centerData.status === 'ok' &&
        calData.status === 'ok'
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
        setCalibration(calData.data);
        setError(null);

        // Fetch Goals V1 and Goal Reflection telemetry
        try {
          const goalsRes = await fetch(`${API_BASE}/goals/list`);
          const goalsData = await goalsRes.json();
          if (goalsData && goalsData.items) {
            setGoals(goalsData.items);
          }
        } catch (e) {
          console.error("Failed to fetch goals:", e);
        }

        try {
          const reflectionRes = await fetch(`${API_BASE}/dashboard/goals/reflection`);
          const reflectionData = await reflectionRes.json();
          if (reflectionData && reflectionData.status === 'ok') {
            setGoalReflection(reflectionData.data);
          }
        } catch (e) {
          console.error("Failed to fetch goal reflection metrics:", e);
        }

        // Fetch Projects V2
        try {
          const projRes = await fetch(`${API_BASE}/projects`);
          const projData = await projRes.json();
          if (projData && projData.items) {
            setProjects(projData.items);
          }
        } catch (e) {
          console.error("Failed to fetch projects:", e);
        }
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

  // Selected Goal History Tracking
  const [selectedGoalHistory, setSelectedGoalHistory] = useState<any[]>([]);

  useEffect(() => {
    if (selectedGoalId) {
      const fetchHistory = async () => {
        try {
          const res = await fetch(`${API_BASE}/goals/${selectedGoalId}/history`);
          const data = await res.json();
          if (data && data.items) {
            setSelectedGoalHistory(data.items);
          }
        } catch (e) {
          console.error(e);
        }
      };
      fetchHistory();
    } else {
      setSelectedGoalHistory([]);
    }
  }, [selectedGoalId, goals]);

  // --- Project System Operations (Step 8.2) ---
  useEffect(() => {
    if (selectedProjectId) {
      const fetchProjectDetails = async () => {
        try {
          const res = await fetch(`${API_BASE}/projects/${selectedProjectId}`);
          const data = await res.json();
          if (data && data.item) {
            setProjectHierarchy(data.item);
          }

          const simRes = await fetch(`${API_BASE}/projects/${selectedProjectId}/simulation`);
          const simData = await simRes.json();
          if (simData && simData.report) {
            setProjectSimulation(simData.report);
          } else {
            setProjectSimulation(null);
          }
        } catch (e) {
          console.error("Failed to fetch project details:", e);
        }
      };
      fetchProjectDetails();
    } else {
      setProjectHierarchy(null);
      setProjectSimulation(null);
    }
  }, [selectedProjectId, projects]);

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName.trim()) return;
    setCreatingProject(true);
    setProjectError(null);
    try {
      const res = await fetch(`${API_BASE}/projects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newProjectName,
          description: newProjectDesc || undefined
        })
      });
      const data = await res.json();
      if (res.ok && data.item) {
        setNewProjectName('');
        setNewProjectDesc('');
        setProjectError(null);
        fetchData();
        setSelectedProjectId(data.item.project_id);
      } else {
        setProjectError(data.detail || 'Failed to create project.');
      }
    } catch (err: any) {
      setProjectError(err.message || 'Failed to create project.');
    } finally {
      setCreatingProject(false);
    }
  };

  const handleLinkGoalToProject = async (goalId: string, projectId: string) => {
    if (!goalId || !projectId) return;
    setLinkingGoal(true);
    try {
      const res = await fetch(`${API_BASE}/projects/${projectId}/goals`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal_id: goalId })
      });
      if (res.ok) {
        setGoalToLink('');
        fetchData();
      }
    } catch (err) {
      console.error("Failed to link goal to project:", err);
    } finally {
      setLinkingGoal(false);
    }
  };

  const handleAddProjectDependency = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProjectId || !depProjId) return;
    setAddingDep(true);
    try {
      const res = await fetch(`${API_BASE}/projects/${selectedProjectId}/dependencies`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ depends_on_project_id: depProjId })
      });
      const data = await res.json();
      if (res.ok) {
        setDepProjId('');
        fetchData();
      } else {
        alert(data.detail || "Cycle/Dependency error");
      }
    } catch (err) {
      console.error(err);
    } finally {
      setAddingDep(false);
    }
  };

  const handleLogProjectDecision = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProjectId || !decisionTitle.trim()) return;
    setAddingDecision(true);
    try {
      const res = await fetch(`${API_BASE}/projects/${selectedProjectId}/decisions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: decisionTitle,
          description: decisionDesc || undefined,
          rationale: decisionRationale || undefined
        })
      });
      if (res.ok) {
        setDecisionTitle('');
        setDecisionDesc('');
        setDecisionRationale('');
        fetchData();
      }
    } catch (err) {
      console.error(err);
    } finally {
      setAddingDecision(false);
    }
  };

  // Goal Action Handlers
  const handleCreateGoal = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newGoalTitle.trim()) return;
    setCreatingGoal(true);
    setGoalError(null);
    try {
      const res = await fetch(`${API_BASE}/goals`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: newGoalTitle,
          description: newGoalDesc || undefined,
          priority: newGoalPriority,
          target_date: newGoalTargetDate || undefined,
          success_criteria: newGoalCriteria ? newGoalCriteria.split(',').map((c: string) => c.trim()) : [],
          owner: newGoalOwner || undefined,
          depends_on: newGoalDeps,
          importance: newGoalImportance,
          urgency: newGoalUrgency,
          strategic_alignment: newGoalAlignment,
          resource_cost: newGoalCost,
        })
      });
      const data = await res.json();
      if (res.ok && data.item) {
        setNewGoalTitle('');
        setNewGoalDesc('');
        setNewGoalTargetDate('');
        setNewGoalCriteria('');
        setNewGoalOwner('');
        setNewGoalDeps([]);
        setNewGoalImportance(5.0);
        setNewGoalUrgency(5.0);
        setNewGoalAlignment(5.0);
        setNewGoalCost(2.0);
        setGoalError(null);
        fetchData();
      } else {
        setGoalError(data.detail || 'Failed to create goal.');
      }
    } catch (err: any) {
      setGoalError(err.message || 'Failed to create goal.');
    } finally {
      setCreatingGoal(false);
    }
  };

  const handleApproveGoal = async (goalId: string) => {
    try {
      const res = await fetch(`${API_BASE}/goals/${goalId}/approve`, { method: 'POST' });
      if (res.ok) fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  const handleStartGoal = async (goalId: string) => {
    try {
      const res = await fetch(`${API_BASE}/goals/${goalId}/start`, { method: 'POST' });
      if (res.ok) fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  const handleAbandonGoal = async (goalId: string) => {
    try {
      const res = await fetch(`${API_BASE}/goals/${goalId}/abandon`, { method: 'POST' });
      if (res.ok) fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  const handleSetMilestones = async (goalId: string) => {
    const valid = milestonesToAdd.filter(m => m.title.trim());
    if (valid.length === 0) return;
    try {
      const res = await fetch(`${API_BASE}/goals/${goalId}/milestones`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ milestones: valid })
      });
      if (res.ok) {
        setMilestonesToAdd([{ title: '', weight: 1.0 }]);
        fetchData();
      }
    } catch (err) {
      console.error(err);
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

      {/* EXECUTIVE CALIBRATION COCKPIT */}
      <div className="section-label">Executive Self-Awareness & Cockpit Calibration</div>
      {calibration && (
        <div className="panel" style={{
          background: 'linear-gradient(135deg, rgba(16, 22, 36, 0.9) 0%, rgba(10, 15, 28, 0.95) 100%)',
          border: '1px solid rgba(79, 142, 247, 0.15)',
          boxShadow: '0 8px 32px 0 rgba(0, 0, 0, 0.37)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
            <span style={{ fontSize: '20px' }}>{ICONS.calibration}</span>
            <h2 style={{ fontSize: '15px', fontWeight: 600, color: '#fff', letterSpacing: '-0.2px' }}>
              Cognitive Self-Measurement & Prediction Calibration
            </h2>
            <span className="protected-tag" style={{ background: 'rgba(79, 142, 247, 0.1)', border: '1px solid rgba(79, 142, 247, 0.3)', color: 'var(--accent-blue)', marginLeft: 'auto' }}>
              SELF-MEASURING ACTIVE
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
            {/* Calibration & Workflow metrics */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
                {/* Prediction Accuracy Card */}
                <div style={{ background: 'var(--bg-glass)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '16px' }}>
                  <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)', letterSpacing: '0.5px' }}>Prediction Calibration (Accuracy)</div>
                  <div style={{ fontSize: '28px', fontWeight: 'bold', fontFamily: 'JetBrains Mono, monospace', color: 'var(--accent-blue)', marginTop: '6px' }}>
                    {(calibration.prediction_accuracy * 100).toFixed(1)}%
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                    Brier Score: {calibration.success_brier.toFixed(4)} (perfect = 0.0)
                  </div>
                </div>

                {/* Workflow Success Rate Card */}
                <div style={{ background: 'var(--bg-glass)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '16px' }}>
                  <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)', letterSpacing: '0.5px' }}>Workflow Success Rate</div>
                  <div style={{ fontSize: '28px', fontWeight: 'bold', fontFamily: 'JetBrains Mono, monospace', color: 'var(--ok)', marginTop: '6px' }}>
                    {(calibration.workflow_success_rate * 100).toFixed(1)}%
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                    Runs: {calibration.workflow_successes} / {calibration.workflow_total} total
                  </div>
                </div>

                {/* Rollback Frequency Card */}
                <div style={{ background: 'var(--bg-glass)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '16px' }}>
                  <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)', letterSpacing: '0.5px' }}>Rollback Frequency</div>
                  <div style={{ fontSize: '28px', fontWeight: 'bold', fontFamily: 'JetBrains Mono, monospace', color: calibration.rollback_frequency > 0.15 ? 'var(--critical)' : 'var(--text-primary)', marginTop: '6px' }}>
                    {(calibration.rollback_frequency * 100).toFixed(1)}%
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                    Total rollbacks: {calibration.total_workflow_rollbacks}
                  </div>
                </div>

                {/* Prediction Calibration Error Card */}
                <div style={{ background: 'var(--bg-glass)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '16px' }}>
                  <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)', letterSpacing: '0.5px' }}>Prediction Latency Divergence</div>
                  <div style={{ fontSize: '28px', fontWeight: 'bold', fontFamily: 'JetBrains Mono, monospace', color: 'var(--text-primary)', marginTop: '6px' }}>
                    ± {(calibration.duration_mae_ms / 1000).toFixed(2)}s
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                    Mean duration prediction error (MAE)
                  </div>
                </div>
              </div>

              {/* Policy effectiveness details */}
              <div style={{ background: 'rgba(255,255,255,0.01)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <h4 style={{ fontSize: '11px', textTransform: 'uppercase', color: '#fff', letterSpacing: '0.5px' }}>Policy Enforcement & Governance Impact</h4>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                  <span style={{ color: 'var(--text-secondary)' }}>Active Strategy Policies</span>
                  <span style={{ fontWeight: 600, fontFamily: 'monospace' }}>{calibration.active_policies_count}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                  <span style={{ color: 'var(--text-secondary)' }}>System Actions Blocked</span>
                  <span style={{ fontWeight: 600, color: 'var(--critical)', fontFamily: 'monospace' }}>{calibration.policy_actions_blocked}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                  <span style={{ color: 'var(--text-secondary)' }}>System Actions Deferred (Cooldowns)</span>
                  <span style={{ fontWeight: 600, color: 'var(--warn)', fontFamily: 'monospace' }}>{calibration.policy_actions_deferred}</span>
                </div>
              </div>
            </div>

            {/* Agent Reliability Section */}
            <div style={{ background: 'var(--bg-glass)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '20px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h4 style={{ fontSize: '11px', textTransform: 'uppercase', color: '#fff', letterSpacing: '0.5px' }}>Agent Society Reliability Breakdown</h4>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Updated dynamically</span>
              </div>

              {calibration.agent_reliability && calibration.agent_reliability.length > 0 ? (
                <table className="data-table" style={{ fontSize: '12px' }}>
                  <thead>
                    <tr>
                      <th style={{ padding: '6px 8px' }}>Agent</th>
                      <th style={{ padding: '6px 8px', textAlign: 'center' }}>Total Actions</th>
                      <th style={{ padding: '6px 8px', textAlign: 'center' }}>Success Rate</th>
                      <th style={{ padding: '6px 8px', textAlign: 'center' }}>Rollback Rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {calibration.agent_reliability.map((agentInfo) => (
                      <tr key={agentInfo.agent}>
                        <td style={{ fontWeight: 500, color: '#fff', textTransform: 'capitalize', padding: '8px' }}>
                          {agentInfo.agent}
                        </td>
                        <td style={{ textAlign: 'center', fontFamily: 'monospace', padding: '8px' }}>
                          {agentInfo.total_actions}
                        </td>
                        <td style={{ textAlign: 'center', fontWeight: 'bold', fontFamily: 'monospace', color: agentInfo.success_rate >= 0.8 ? 'var(--ok)' : agentInfo.success_rate >= 0.6 ? 'var(--warn)' : 'var(--critical)', padding: '8px' }}>
                          {(agentInfo.success_rate * 100).toFixed(1)}%
                        </td>
                        <td style={{ textAlign: 'center', fontFamily: 'monospace', padding: '8px', color: agentInfo.rollback_rate > 0.1 ? 'var(--critical)' : 'var(--text-secondary)' }}>
                          {(agentInfo.rollback_rate * 100).toFixed(1)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', fontSize: '12px', fontStyle: 'italic' }}>
                  No agent executions recorded yet
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* EXECUTIVE MISSION & PROJECT COCKPIT (STEP 8.2) */}
      <div className="section-label">📂 Executive Mission & Project Cockpit</div>
      <div className="panel" style={{
        background: 'linear-gradient(135deg, rgba(17, 24, 39, 0.9) 0%, rgba(15, 23, 42, 0.95) 100%)',
        border: '1px solid rgba(59, 130, 246, 0.15)',
        boxShadow: '0 8px 32px 0 rgba(0, 0, 0, 0.4)',
        display: 'flex',
        flexDirection: 'column',
        gap: '24px',
        marginBottom: '20px',
        padding: '24px'
      }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ fontSize: '28px' }}>📂</span>
            <div>
              <h2 style={{ fontSize: '18px', fontWeight: 700, color: '#fff', margin: 0 }}>Executive Mission & Project Cockpit</h2>
              <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                Organizing OS operations in hierarchical missions. Projects orchestrate Goals, Milestones, Tasks, and Actions.
              </p>
            </div>
          </div>
          
          {/* Project selector dropdown */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Active Mission:</span>
            <select
              value={selectedProjectId || ''}
              onChange={(e) => setSelectedProjectId(e.target.value || null)}
              style={{
                padding: '8px 12px',
                background: '#0f172a',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                color: '#fff',
                fontSize: '13px',
                cursor: 'pointer',
                minWidth: '200px'
              }}
            >
              <option value="">-- Select a Project / Mission --</option>
              {projects.map((p) => (
                <option key={p.project_id} value={p.project_id}>
                  {p.name} ({(p.completion_percent * 100).toFixed(0)}%)
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Top-level statistics row */}
        {projectHierarchy && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '16px', background: 'rgba(255,255,255,0.02)', padding: '16px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
            <div>
              <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Status</div>
              <div style={{ fontSize: '16px', fontWeight: 600, color: '#fff', marginTop: '4px', textTransform: 'capitalize' }}>{projectHierarchy.status}</div>
            </div>
            <div>
              <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Completion</div>
              <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--accent-blue)', marginTop: '4px' }}>{(projectHierarchy.completion_percent * 100).toFixed(1)}%</div>
            </div>
            <div>
              <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Est. Success Rate</div>
              <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--ok)', marginTop: '4px' }}>{(projectHierarchy.success_rate * 100).toFixed(1)}%</div>
            </div>
            <div>
              <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Rollback Risk Score</div>
              <div style={{ fontSize: '20px', fontWeight: 700, color: projectHierarchy.risk_score > 0.25 ? 'var(--critical)' : 'var(--text-primary)', marginTop: '4px' }}>{(projectHierarchy.risk_score * 100).toFixed(1)}%</div>
            </div>
            <div>
              <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Predicted Finish</div>
              <div style={{ fontSize: '14px', fontWeight: 600, color: '#fff', marginTop: '6px' }}>
                {projectHierarchy.predicted_finish ? new Date(projectHierarchy.predicted_finish * 1000).toLocaleDateString() : 'N/A'}
              </div>
            </div>
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', alignItems: 'start' }}>
          {/* LEFT COLUMN: Controls and Management */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {/* Create Project Card */}
            <div className="card" style={{ background: 'var(--bg-glass)', border: '1px solid var(--border)', padding: '16px', borderRadius: 'var(--radius-sm)' }}>
              <h3 style={{ fontSize: '13px', textTransform: 'uppercase', color: '#fff', marginBottom: '12px' }}>Initialize Mission / Project</h3>
              <form onSubmit={handleCreateProject} style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <input
                  type="text"
                  placeholder="Project Name (e.g. Kattappa OS)"
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  style={{
                    padding: '8px 12px',
                    background: '#0b0f19',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-xs)',
                    color: '#fff',
                    fontSize: '12px'
                  }}
                />
                <textarea
                  placeholder="Project Description..."
                  value={newProjectDesc}
                  onChange={(e) => setNewProjectDesc(e.target.value)}
                  style={{
                    padding: '8px 12px',
                    background: '#0b0f19',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-xs)',
                    color: '#fff',
                    fontSize: '12px',
                    minHeight: '60px',
                    resize: 'vertical'
                  }}
                />
                <button
                  type="submit"
                  disabled={creatingProject || !newProjectName.trim()}
                  style={{
                    padding: '8px',
                    background: 'var(--accent-blue)',
                    border: 'none',
                    borderRadius: 'var(--radius-xs)',
                    color: '#fff',
                    fontWeight: 600,
                    cursor: 'pointer',
                    fontSize: '12px'
                  }}
                >
                  {creatingProject ? 'Creating...' : '🚀 Create Mission'}
                </button>
                {projectError && <div style={{ color: 'var(--critical)', fontSize: '11px', marginTop: '4px' }}>{projectError}</div>}
              </form>
            </div>

            {projectHierarchy && (
              <>
                {/* Associate Goals Card */}
                <div className="card" style={{ background: 'var(--bg-glass)', border: '1px solid var(--border)', padding: '16px', borderRadius: 'var(--radius-sm)' }}>
                  <h3 style={{ fontSize: '13px', textTransform: 'uppercase', color: '#fff', marginBottom: '12px' }}>Link Goal to Project</h3>
                  <div style={{ display: 'flex', gap: '10px' }}>
                    <select
                      value={goalToLink}
                      onChange={(e) => setGoalToLink(e.target.value)}
                      style={{
                        flex: 1,
                        padding: '8px',
                        background: '#0b0f19',
                        border: '1px solid var(--border)',
                        borderRadius: 'var(--radius-xs)',
                        color: '#fff',
                        fontSize: '12px'
                      }}
                    >
                      <option value="">-- Choose Goal to Link --</option>
                      {goals
                        .filter(g => !projectHierarchy.goals.some(pg => pg.goal_id === g.goal_id))
                        .map(g => (
                          <option key={g.goal_id} value={g.goal_id}>
                            {g.title}
                          </option>
                        ))}
                    </select>
                    <button
                      onClick={() => handleLinkGoalToProject(goalToLink, projectHierarchy.project_id)}
                      disabled={linkingGoal || !goalToLink}
                      style={{
                        padding: '8px 16px',
                        background: 'var(--accent-purple)',
                        border: 'none',
                        borderRadius: 'var(--radius-xs)',
                        color: '#fff',
                        fontWeight: 600,
                        cursor: 'pointer',
                        fontSize: '12px'
                      }}
                    >
                      {linkingGoal ? 'Linking...' : '🔗 Link'}
                    </button>
                  </div>
                </div>

                {/* Project Dependencies Card */}
                <div className="card" style={{ background: 'var(--bg-glass)', border: '1px solid var(--border)', padding: '16px', borderRadius: 'var(--radius-sm)' }}>
                  <h3 style={{ fontSize: '13px', textTransform: 'uppercase', color: '#fff', marginBottom: '12px' }}>Add Project Dependency</h3>
                  <form onSubmit={handleAddProjectDependency} style={{ display: 'flex', gap: '10px' }}>
                    <select
                      value={depProjId}
                      onChange={(e) => setDepProjId(e.target.value)}
                      style={{
                        flex: 1,
                        padding: '8px',
                        background: '#0b0f19',
                        border: '1px solid var(--border)',
                        borderRadius: 'var(--radius-xs)',
                        color: '#fff',
                        fontSize: '12px'
                      }}
                    >
                      <option value="">-- Select Dependency Project --</option>
                      {projects
                        .filter(p => p.project_id !== projectHierarchy.project_id && !projectHierarchy.dependencies.includes(p.project_id))
                        .map(p => (
                          <option key={p.project_id} value={p.project_id}>
                            {p.name}
                          </option>
                        ))}
                    </select>
                    <button
                      type="submit"
                      disabled={addingDep || !depProjId}
                      style={{
                        padding: '8px 16px',
                        background: 'var(--accent-blue)',
                        border: 'none',
                        borderRadius: 'var(--radius-xs)',
                        color: '#fff',
                        fontWeight: 600,
                        cursor: 'pointer',
                        fontSize: '12px'
                      }}
                    >
                      {addingDep ? 'Adding...' : '⚡ Add Dep'}
                    </button>
                  </form>
                  {projectHierarchy.dependencies.length > 0 && (
                    <div style={{ marginTop: '12px' }}>
                      <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Depends on:</span>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '6px' }}>
                        {projectHierarchy.dependencies.map(depId => {
                          const depProj = projects.find(p => p.project_id === depId);
                          return (
                            <span key={depId} style={{ fontSize: '11px', padding: '3px 8px', background: 'rgba(59, 130, 246, 0.1)', border: '1px solid rgba(59, 130, 246, 0.3)', borderRadius: '12px', color: 'var(--accent-blue)' }}>
                              {depProj ? depProj.name : depId}
                            </span>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>

                {/* Log Decision Card */}
                <div className="card" style={{ background: 'var(--bg-glass)', border: '1px solid var(--border)', padding: '16px', borderRadius: 'var(--radius-sm)' }}>
                  <h3 style={{ fontSize: '13px', textTransform: 'uppercase', color: '#fff', marginBottom: '12px' }}>Log Executive Decision</h3>
                  <form onSubmit={handleLogProjectDecision} style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    <input
                      type="text"
                      placeholder="Decision Title"
                      value={decisionTitle}
                      onChange={(e) => setDecisionTitle(e.target.value)}
                      style={{
                        padding: '8px',
                        background: '#0b0f19',
                        border: '1px solid var(--border)',
                        borderRadius: 'var(--radius-xs)',
                        color: '#fff',
                        fontSize: '12px'
                      }}
                    />
                    <textarea
                      placeholder="Rationale / Details..."
                      value={decisionRationale}
                      onChange={(e) => setDecisionRationale(e.target.value)}
                      style={{
                        padding: '8px',
                        background: '#0b0f19',
                        border: '1px solid var(--border)',
                        borderRadius: 'var(--radius-xs)',
                        color: '#fff',
                        fontSize: '12px',
                        minHeight: '50px',
                        resize: 'vertical'
                      }}
                    />
                    <button
                      type="submit"
                      disabled={addingDecision || !decisionTitle.trim()}
                      style={{
                        padding: '8px',
                        background: 'var(--ok)',
                        border: 'none',
                        borderRadius: 'var(--radius-xs)',
                        color: '#fff',
                        fontWeight: 600,
                        cursor: 'pointer',
                        fontSize: '12px'
                      }}
                    >
                      {addingDecision ? 'Saving...' : '💾 Log Decision'}
                    </button>
                  </form>
                </div>
              </>
            )}
          </div>

          {/* RIGHT COLUMN: Project Simulation & Dependency Cascade Warning logs */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {projectHierarchy ? (
              <>
                {/* Simulation & Blocker Report */}
                <div className="card" style={{ background: 'var(--bg-glass)', border: '1px solid var(--border)', padding: '20px', borderRadius: 'var(--radius-sm)' }}>
                  <h3 style={{ fontSize: '13px', textTransform: 'uppercase', color: '#fff', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span>🔮</span> Monte-Carlo Simulation & Projections
                  </h3>
                  {projectSimulation ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
                        <div style={{ background: 'rgba(255,255,255,0.01)', border: '1px solid var(--border)', borderRadius: 'var(--radius-xs)', padding: '12px' }}>
                          <div style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Finish Probability</div>
                          <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--ok)', marginTop: '4px' }}>{(projectSimulation.completion_probability * 100).toFixed(0)}%</div>
                        </div>
                        <div style={{ background: 'rgba(255,255,255,0.01)', border: '1px solid var(--border)', borderRadius: 'var(--radius-xs)', padding: '12px' }}>
                          <div style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Predicted End Date</div>
                          <div style={{ fontSize: '18px', fontWeight: 600, color: '#fff', marginTop: '8px' }}>{projectSimulation.predicted_finish_date}</div>
                        </div>
                      </div>

                      {/* Critical Path Display */}
                      <div>
                        <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '6px' }}>Critical Path Sequence</div>
                        {projectSimulation.critical_path && projectSimulation.critical_path.length > 0 ? (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                            {projectSimulation.critical_path.map((pathName: string, idx: number) => (
                              <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px' }}>
                                <span style={{ color: 'var(--accent-blue)', fontWeight: 600 }}>#{idx + 1}</span>
                                <span style={{ color: '#fff' }}>{pathName}</span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <span style={{ fontSize: '12px', fontStyle: 'italic', color: 'var(--text-muted)' }}>No critical path calculated</span>
                        )}
                      </div>

                      {/* Resource Demand */}
                      <div>
                        <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '8px' }}>Resource Agent Workload Demand</div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                          {Object.entries(projectSimulation.resource_demand || {}).map(([agent, timeVal]: [string, any]) => (
                            <div key={agent} style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '12px' }}>
                              <span style={{ width: '80px', textTransform: 'capitalize', color: 'var(--text-secondary)' }}>{agent} agent:</span>
                              <div style={{ flex: 1, height: '8px', background: 'rgba(255,255,255,0.05)', borderRadius: '4px', overflow: 'hidden' }}>
                                <div style={{ height: '100%', background: agent === 'coder' ? 'var(--accent-blue)' : 'var(--accent-purple)', width: `${Math.min(100, (timeVal / 3600) * 10)}%` }}></div>
                              </div>
                              <span style={{ width: '60px', textAlign: 'right', fontFamily: 'monospace' }}>{(timeVal / 60).toFixed(1)} min</span>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Blockers */}
                      {projectSimulation.likely_blockers && projectSimulation.likely_blockers.length > 0 && (
                        <div style={{ borderTop: '1px solid var(--border)', paddingTop: '10px' }}>
                          <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--critical)', fontWeight: 600, marginBottom: '6px' }}>Potential Blockers Identified</div>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                            {projectSimulation.likely_blockers.map((b: any, idx: number) => (
                              <div key={idx} style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                                ⚠️ <span style={{ color: '#fff', fontWeight: 500 }}>{b.title}</span> (Success prob: {(b.success_probability * 100).toFixed(0)}%, Rollback risk: {(b.rollback_risk * 100).toFixed(0)}%)
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div style={{ fontSize: '12px', fontStyle: 'italic', color: 'var(--text-muted)' }}>Running Monte Carlo projection simulation...</div>
                  )}
                </div>

                {/* Project Event Trail Ledger */}
                <div className="card" style={{ background: 'var(--bg-glass)', border: '1px solid var(--border)', padding: '16px', borderRadius: 'var(--radius-sm)' }}>
                  <h3 style={{ fontSize: '13px', textTransform: 'uppercase', color: '#fff', marginBottom: '12px' }}>Project Mission Ledger & Decisions</h3>
                  
                  {/* Decisions Tab list */}
                  {projectHierarchy.decisions.length > 0 && (
                    <div style={{ marginBottom: '16px' }}>
                      <div style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '8px' }}>Executive Decisions ({projectHierarchy.decisions.length})</div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '150px', overflowY: 'auto' }}>
                        {projectHierarchy.decisions.map(d => (
                          <div key={d.decision_id} style={{ background: 'rgba(255,255,255,0.01)', border: '1px solid var(--border)', padding: '8px', borderRadius: 'var(--radius-xs)' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', fontWeight: 600, color: '#fff' }}>
                              <span>{d.title}</span>
                              <span style={{ fontSize: '10px', color: 'var(--ok)' }}>{d.status}</span>
                            </div>
                            {d.description && <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>{d.description}</div>}
                            {d.rationale && <div style={{ fontSize: '11px', fontStyle: 'italic', color: 'var(--text-muted)', marginTop: '2px' }}>Rationale: {d.rationale}</div>}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Failures & Rollbacks */}
                  {(projectHierarchy.failures.length > 0 || projectHierarchy.rollbacks.length > 0) && (
                    <div style={{ marginBottom: '16px' }}>
                      <div style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--critical)', fontWeight: 600, marginBottom: '8px' }}>System Exceptions & Rollbacks</div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '150px', overflowY: 'auto' }}>
                        {projectHierarchy.failures.map(f => (
                          <div key={f.failure_id} style={{ borderLeft: '3px solid var(--critical)', background: 'rgba(239, 68, 68, 0.04)', padding: '6px 10px', fontSize: '11px' }}>
                            <div style={{ fontWeight: 600, color: '#fff' }}>Failure: {f.component}</div>
                            <div style={{ color: 'var(--text-secondary)', marginTop: '2px' }}>{f.error_message}</div>
                          </div>
                        ))}
                        {projectHierarchy.rollbacks.map(r => (
                          <div key={r.rollback_id} style={{ borderLeft: '3px solid var(--warn)', background: 'rgba(245, 158, 11, 0.04)', padding: '6px 10px', fontSize: '11px' }}>
                            <div style={{ fontWeight: 600, color: '#fff' }}>Rollback Executed</div>
                            <div style={{ color: 'var(--text-secondary)', marginTop: '2px' }}>Reason: {r.reason}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* General Event Timeline */}
                  <div>
                    <div style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '8px' }}>Mission Event Timeline</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '150px', overflowY: 'auto', paddingRight: '4px' }}>
                      {projectHierarchy.events.map((e, idx) => (
                        <div key={idx} style={{ fontSize: '11px', display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.02)', paddingBottom: '4px' }}>
                          <span style={{ color: 'var(--text-primary)' }}>{e.event_type}</span>
                          <span style={{ color: 'var(--text-muted)' }}>{new Date(e.timestamp * 1000).toLocaleTimeString()}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', border: '1px dashed var(--border)', borderRadius: 'var(--radius-sm)', padding: '40px', color: 'var(--text-muted)', fontSize: '13px', fontStyle: 'italic' }}>
                Select a Project / Mission to view projections and ledger events.
              </div>
            )}
          </div>
        </div>

        {/* BOTTOM FULL-WIDTH: Cascade Hierarchy Tree View */}
        {projectHierarchy && projectHierarchy.goals_tree && projectHierarchy.goals_tree.length > 0 && (
          <div style={{ borderTop: '1px solid var(--border)', paddingTop: '20px' }}>
            <h3 style={{ fontSize: '13px', textTransform: 'uppercase', color: '#fff', marginBottom: '14px' }}>
              🌳 Cascade Hierarchy Tree: Project → Goal → Milestone → Task → Action
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {projectHierarchy.goals_tree.map(goal => (
                <div key={goal.goal_id} style={{ background: 'rgba(255,255,255,0.01)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '16px' }}>
                  {/* Goal Header */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontSize: '16px' }}>🎯</span>
                      <span style={{ fontSize: '14px', fontWeight: 700, color: '#fff' }}>{goal.title}</span>
                      <span style={{ fontSize: '10px', padding: '2px 6px', background: 'rgba(255,255,255,0.05)', borderRadius: '4px', color: 'var(--text-secondary)' }}>Goal V1</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--accent-blue)' }}>{(goal.progress * 100).toFixed(0)}% Done</span>
                      <span style={{ fontSize: '11px', padding: '3px 8px', borderRadius: '4px', background: goal.status === 'ACTIVE' ? 'rgba(34,197,94,0.1)' : 'rgba(255,255,255,0.05)', color: goal.status === 'ACTIVE' ? 'var(--ok)' : 'var(--text-secondary)' }}>
                        {goal.status}
                      </span>
                    </div>
                  </div>

                  {/* Milestones list */}
                  {goal.milestones && goal.milestones.length > 0 ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginLeft: '24px', borderLeft: '1px dashed rgba(255,255,255,0.1)', paddingLeft: '16px' }}>
                      {goal.milestones.map(m => (
                        <div key={m.milestone_id} style={{ background: 'rgba(255,255,255,0.01)', border: '1px solid rgba(255,255,255,0.04)', borderRadius: 'var(--radius-xs)', padding: '12px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                              <span>🏁</span>
                              <span style={{ fontSize: '12px', fontWeight: 600, color: '#fff' }}>{m.title}</span>
                            </div>
                            <span style={{ fontSize: '11px', fontWeight: 500, color: 'var(--text-secondary)' }}>{(m.progress * 100).toFixed(0)}%</span>
                          </div>

                          {/* Tasks list */}
                          {(m as any).tasks && (m as any).tasks.length > 0 ? (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginLeft: '16px', marginTop: '8px' }}>
                              {(m as any).tasks.map((t: any) => (
                                <div key={t.task_id} style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)', padding: '10px', borderRadius: '4px' }}>
                                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                      <span>📋</span>
                                      <span style={{ fontWeight: 600, color: '#fff' }}>{t.title}</span>
                                    </div>
                                    <span style={{ color: 'var(--accent-blue)' }}>{(t.progress * 100).toFixed(0)}%</span>
                                  </div>
                                  {t.assigned_agent && (
                                    <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '4px' }}>
                                      Assigned: <span style={{ color: 'var(--text-secondary)' }}>{t.assigned_agent}</span>
                                    </div>
                                  )}

                                  {/* Actions list */}
                                  {t.actions && t.actions.length > 0 && (
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '6px', borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: '6px' }}>
                                      {t.actions.map((act: any) => (
                                        <div key={act.action_id} style={{ fontSize: '10px', display: 'flex', justifyContent: 'space-between', color: 'var(--text-secondary)' }}>
                                          <span>⚡ {act.action_type}</span>
                                          <span style={{ color: act.status === 'COMPLETED' ? 'var(--ok)' : 'var(--text-muted)' }}>{act.status}</span>
                                        </div>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontStyle: 'italic', marginLeft: '16px' }}>No tasks assigned under milestone</div>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontStyle: 'italic', marginLeft: '24px' }}>No milestones declared for goal</div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* COGNITIVE GOALS SYSTEM PANEL (STEP 8.1) */}
      <div className="section-label">Cognitive Goal Management & Operations</div>
      <div className="panel" style={{
        background: 'linear-gradient(135deg, rgba(13, 17, 30, 0.9) 0%, rgba(9, 11, 23, 0.95) 100%)',
        border: '1px solid rgba(139, 92, 246, 0.15)',
        boxShadow: '0 8px 32px 0 rgba(0, 0, 0, 0.4)',
        display: 'flex',
        flexDirection: 'column',
        gap: '20px',
        marginBottom: '20px',
        padding: '24px'
      }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border)', paddingBottom: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ fontSize: '24px' }}>{ICONS.goals}</span>
            <div>
              <h2 style={{ fontSize: '18px', fontWeight: 600, color: '#fff', margin: 0 }}>Cognitive Goal & Milestones OS</h2>
              <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                Centering operating system loops around hierarchical goals, milestone simulation, and derived progress logic
              </p>
            </div>
          </div>
          <span className="protected-tag" style={{ background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.3)', color: '#a78bfa' }}>
            GOAL MANAGER ACTIVE
          </span>
        </div>

        {/* Telemetry Dashboard Stats */}
        {goalReflection && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '14px' }}>
            <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '14px', textAlign: 'center' }}>
              <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Completion Rate</div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#fff', marginTop: '6px', fontFamily: 'monospace' }}>
                {(goalReflection.goal_completion_rate * 100).toFixed(1)}%
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                {goalReflection.completed_goals} / {goalReflection.total_goals} goals done
              </div>
            </div>

            <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '14px', textAlign: 'center' }}>
              <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Stalled / Block Rate</div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: goalReflection.goal_block_rate > 0.25 ? 'var(--critical)' : 'var(--ok)', marginTop: '6px', fontFamily: 'monospace' }}>
                {(goalReflection.goal_block_rate * 100).toFixed(1)}%
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                Blocked milestones ratio
              </div>
            </div>

            <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '14px', textAlign: 'center' }}>
              <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Prediction Accuracy</div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#fff', marginTop: '6px', fontFamily: 'monospace' }}>
                {(goalReflection.goal_prediction_accuracy * 100).toFixed(1)}%
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                Brier score calibration
              </div>
            </div>

            <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '14px', textAlign: 'center' }}>
              <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Avg Goal Duration</div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#fff', marginTop: '6px', fontFamily: 'monospace' }}>
                {(goalReflection.goal_average_duration / 60).toFixed(1)}m
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                Average active execution time
              </div>
            </div>

            <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '14px', textAlign: 'center' }}>
              <div style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Rollback Frequency</div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: goalReflection.goal_rollback_frequency > 0.3 ? 'var(--critical)' : '#fff', marginTop: '6px', fontFamily: 'monospace' }}>
                {(goalReflection.goal_rollback_frequency * 100).toFixed(1)}%
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                Rollbacks per milestone
              </div>
            </div>
          </div>
        )}

        {/* Dynamic Warning Alert for POL-104 */}
        {goalReflection && goalReflection.goal_rollback_frequency > 0.3 && (
          <div style={{
            background: 'rgba(239,68,68,0.1)',
            border: '1px solid rgba(239,68,68,0.3)',
            borderRadius: 'var(--radius-sm)',
            padding: '12px 16px',
            fontSize: '13px',
            color: 'var(--critical)',
            display: 'flex',
            alignItems: 'center',
            gap: '10px'
          }}>
            <span>⚠️</span>
            <div>
              <strong style={{ fontWeight: 600 }}>Policy Trigger active (POL-104):</strong> Rollback rate exceeds 30%. Mandatory simulation reviews will be required prior to deploying any backend actions.
            </div>
          </div>
        )}

        {/* Split View: Left side list/creation, Right side details */}
        <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
          
          {/* Left panel: List & Create form */}
          <div style={{ flex: '1 1 450px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            
            {/* Create Goal Card */}
            <div style={{ background: 'rgba(255,255,255,0.02)', padding: '16px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
              <h3 style={{ fontSize: '13px', color: '#fff', fontWeight: 600, marginBottom: '12px' }}>🎯 Initialize Structured V1 Goal</h3>
              <form onSubmit={handleCreateGoal} style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <div style={{ display: 'flex', gap: '10px' }}>
                  <div style={{ flex: 2 }}>
                    <input
                      type="text"
                      placeholder="Goal Title (e.g. Become RF Test Engineer)"
                      value={newGoalTitle}
                      onChange={(e) => setNewGoalTitle(e.target.value)}
                      required
                      style={{ width: '100%', padding: '8px 12px', background: '#0e131f', border: '1px solid var(--border)', borderRadius: 'var(--radius-xs)', color: '#fff', fontSize: '12px' }}
                    />
                  </div>
                  <div style={{ flex: 1 }}>
                    <select
                      id="goal-priority-select"
                      title="Goal Priority"
                      aria-label="Goal Priority"
                      value={newGoalPriority}
                      onChange={(e) => setNewGoalPriority(e.target.value)}
                      style={{ width: '100%', padding: '8px 12px', background: '#0e131f', border: '1px solid var(--border)', borderRadius: 'var(--radius-xs)', color: '#fff', fontSize: '12px', height: '34px' }}
                    >
                      <option value="LOW">LOW</option>
                      <option value="MEDIUM">MEDIUM</option>
                      <option value="HIGH">HIGH</option>
                      <option value="CRITICAL">CRITICAL</option>
                    </select>
                  </div>
                </div>

                <div>
                  <textarea
                    placeholder="Description of success criteria and expectations..."
                    value={newGoalDesc}
                    onChange={(e) => setNewGoalDesc(e.target.value)}
                    style={{ width: '100%', padding: '8px 12px', background: '#0e131f', border: '1px solid var(--border)', borderRadius: 'var(--radius-xs)', color: '#fff', fontSize: '12px', minHeight: '50px', resize: 'vertical' }}
                  />
                </div>

                <div style={{ display: 'flex', gap: '10px' }}>
                  <div style={{ flex: 1 }}>
                    <input
                      type="text"
                      placeholder="Target Date (YYYY-MM-DD)"
                      value={newGoalTargetDate}
                      onChange={(e) => setNewGoalTargetDate(e.target.value)}
                      style={{ width: '100%', padding: '8px 12px', background: '#0e131f', border: '1px solid var(--border)', borderRadius: 'var(--radius-xs)', color: '#fff', fontSize: '12px' }}
                    />
                  </div>
                  <div style={{ flex: 1 }}>
                    <input
                      type="text"
                      placeholder="Owner (e.g. ExecutiveAgent)"
                      value={newGoalOwner}
                      onChange={(e) => setNewGoalOwner(e.target.value)}
                      style={{ width: '100%', padding: '8px 12px', background: '#0e131f', border: '1px solid var(--border)', borderRadius: 'var(--radius-xs)', color: '#fff', fontSize: '12px' }}
                    />
                  </div>
                </div>

                <div>
                  <input
                    type="text"
                    placeholder="Success Criteria (comma-separated, e.g. Pass RF test, Setup Spectrum Analyzer)"
                    value={newGoalCriteria}
                    onChange={(e) => setNewGoalCriteria(e.target.value)}
                    style={{ width: '100%', padding: '8px 12px', background: '#0e131f', border: '1px solid var(--border)', borderRadius: 'var(--radius-xs)', color: '#fff', fontSize: '12px' }}
                  />
                </div>

                {/* Optional Dependencies */}
                {goals.length > 0 && (
                  <div>
                    <label style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Goal Dependencies</label>
                    <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', maxHeight: '80px', overflowY: 'auto', background: '#0e131f', padding: '6px', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border)' }}>
                      {goals.map(g => (
                        <label key={g.goal_id} style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: '#fff', cursor: 'pointer' }}>
                          <input
                            type="checkbox"
                            checked={newGoalDeps.includes(g.goal_id)}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setNewGoalDeps([...newGoalDeps, g.goal_id]);
                              } else {
                                setNewGoalDeps(newGoalDeps.filter(id => id !== g.goal_id));
                              }
                            }}
                          />
                          {g.title}
                        </label>
                      ))}
                    </div>
                  </div>
                )}

                {/* Priority Score parameters */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', background: 'rgba(255,255,255,0.01)', padding: '10px', borderRadius: '4px', border: '1px solid var(--border)' }}>
                  <div>
                    <label htmlFor="goal-importance-input" style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block', marginBottom: '2px' }}>Importance (1-10): {newGoalImportance}</label>
                    <input
                      id="goal-importance-input"
                      title="Importance (1-10)"
                      type="range"
                      min="1"
                      max="10"
                      step="1"
                      value={newGoalImportance}
                      onChange={(e) => setNewGoalImportance(parseInt(e.target.value))}
                      style={{ width: '100%' }}
                    />
                  </div>
                  <div>
                    <label htmlFor="goal-urgency-input" style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block', marginBottom: '2px' }}>Urgency (1-10): {newGoalUrgency}</label>
                    <input
                      id="goal-urgency-input"
                      title="Urgency (1-10)"
                      type="range"
                      min="1"
                      max="10"
                      step="1"
                      value={newGoalUrgency}
                      onChange={(e) => setNewGoalUrgency(parseInt(e.target.value))}
                      style={{ width: '100%' }}
                    />
                  </div>
                  <div>
                    <label htmlFor="goal-alignment-input" style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block', marginBottom: '2px' }}>Strategic Alignment (1-10): {newGoalAlignment}</label>
                    <input
                      id="goal-alignment-input"
                      title="Strategic Alignment (1-10)"
                      type="range"
                      min="1"
                      max="10"
                      step="1"
                      value={newGoalAlignment}
                      onChange={(e) => setNewGoalAlignment(parseInt(e.target.value))}
                      style={{ width: '100%' }}
                    />
                  </div>
                  <div>
                    <label htmlFor="goal-cost-input" style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block', marginBottom: '2px' }}>Resource Cost (1-10): {newGoalCost}</label>
                    <input
                      id="goal-cost-input"
                      title="Resource Cost (1-10)"
                      type="range"
                      min="1"
                      max="10"
                      step="1"
                      value={newGoalCost}
                      onChange={(e) => setNewGoalCost(parseInt(e.target.value))}
                      style={{ width: '100%' }}
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={creatingGoal}
                  style={{
                    padding: '10px',
                    background: 'linear-gradient(135deg, #8b5cf6 0%, #6d28d9 100%)',
                    border: 'none',
                    borderRadius: 'var(--radius-xs)',
                    color: '#fff',
                    fontWeight: 600,
                    fontSize: '12px',
                    cursor: creatingGoal ? 'not-allowed' : 'pointer',
                    boxShadow: '0 4px 12px rgba(139, 92, 246, 0.25)',
                    transition: 'all 0.2s'
                  }}
                >
                  {creatingGoal ? 'Creating Goal...' : '🎯 Create Goal (Proposed)'}
                </button>
              </form>
              {goalError && (
                <div style={{ marginTop: '8px', fontSize: '11px', color: 'var(--critical)' }}>⚠️ {goalError}</div>
              )}
            </div>

            {/* Goals List Card */}
            <div style={{ background: 'rgba(255,255,255,0.02)', padding: '16px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', flex: 1, maxHeight: '400px', overflowY: 'auto' }}>
              <h3 style={{ fontSize: '12px', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '12px', letterSpacing: '0.5px' }}>
                System Goals Pipeline
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {goals.length === 0 ? (
                  <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px', padding: '20px', fontStyle: 'italic' }}>
                    No goals declared in the system database.
                  </div>
                ) : (
                  goals.map(g => {
                    const isSelected = selectedGoalId === g.goal_id;
                    const statusColor = g.status === 'COMPLETED' ? 'var(--ok)' : g.status === 'ACTIVE' ? 'var(--accent-blue)' : g.status === 'BLOCKED' ? 'var(--critical)' : 'var(--warn)';
                    return (
                      <div
                        key={g.goal_id}
                        onClick={() => setSelectedGoalId(g.goal_id)}
                        style={{
                          background: isSelected ? 'rgba(139, 92, 246, 0.1)' : 'rgba(255,255,255,0.01)',
                          border: `1px solid ${isSelected ? 'rgba(139, 92, 246, 0.4)' : 'var(--border)'}`,
                          borderRadius: 'var(--radius-xs)',
                          padding: '12px',
                          cursor: 'pointer',
                          transition: 'all 0.2s',
                          position: 'relative'
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                          <span style={{ fontWeight: '600', color: '#fff', fontSize: '13px' }}>{g.title}</span>
                          <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                            <span style={{
                              fontSize: '9px',
                              padding: '2px 6px',
                              borderRadius: '3px',
                              background: 'rgba(139, 92, 246, 0.15)',
                              color: '#a78bfa',
                              border: '1px solid rgba(139, 92, 246, 0.3)',
                              fontWeight: 'bold'
                            }}>
                              Score: {g.priority_score !== undefined ? g.priority_score : '1.0'}
                            </span>
                            <span style={{
                              fontSize: '9px',
                              padding: '2px 6px',
                              borderRadius: '3px',
                              background: `${statusColor}1A`,
                              color: statusColor,
                              border: `1px solid ${statusColor}33`,
                              fontWeight: 'bold'
                            }}>
                              {g.status}
                            </span>
                          </div>
                        </div>
                        <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px', margin: '4px 0 8px 0' }}>
                          {g.description || 'No description provided.'}
                        </p>
                        {/* Progress bar */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                          <div style={{ flex: 1, height: '4px', background: 'rgba(255,255,255,0.05)', borderRadius: '2px', overflow: 'hidden' }}>
                            <div style={{ width: `${g.progress * 100}%`, height: '100%', background: 'linear-gradient(90deg, #a78bfa, #8b5cf6)', borderRadius: '2px' }}></div>
                          </div>
                          <span style={{ fontSize: '11px', fontFamily: 'monospace', color: '#fff', minWidth: '32px', textAlign: 'right' }}>
                            {(g.progress * 100).toFixed(0)}%
                          </span>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </div>

          {/* Right panel: Details & Milestones */}
          <div style={{ flex: '1 1 500px', background: 'rgba(255,255,255,0.01)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px', minHeight: '500px' }}>
            {selectedGoalId && goals.find(g => g.goal_id === selectedGoalId) ? (() => {
              const goal = goals.find(g => g.goal_id === selectedGoalId)!;
              return (
                <>
                  {/* Goal Header */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '10px' }}>
                    <div>
                      <h3 style={{ fontSize: '16px', fontWeight: 'bold', color: '#fff' }}>{goal.title}</h3>
                      <span style={{ fontSize: '10px', color: 'var(--text-muted)', fontFamily: 'monospace' }}>Goal ID: {goal.goal_id}</span>
                    </div>

                    <div style={{ display: 'flex', gap: '6px' }}>
                      {goal.status === 'PROPOSED' && (
                        <button
                          onClick={() => handleApproveGoal(goal.goal_id)}
                          style={{ padding: '6px 12px', background: 'rgba(34,197,94,0.1)', border: '1px solid var(--ok)', borderRadius: '4px', color: 'var(--ok)', fontSize: '11px', fontWeight: 600, cursor: 'pointer' }}
                        >
                          ✓ Approve Goal
                        </button>
                      )}
                      {(goal.status === 'APPROVED' || goal.status === 'BLOCKED') && (
                        <button
                          onClick={() => handleStartGoal(goal.goal_id)}
                          style={{ padding: '6px 12px', background: 'rgba(59,130,246,0.1)', border: '1px solid var(--accent-blue)', borderRadius: '4px', color: 'var(--accent-blue)', fontSize: '11px', fontWeight: 600, cursor: 'pointer' }}
                        >
                          ⚡ Start Execution
                        </button>
                      )}
                      {goal.status !== 'COMPLETED' && goal.status !== 'CANCELLED' && (
                        <button
                          onClick={() => handleAbandonGoal(goal.goal_id)}
                          style={{ padding: '6px 12px', background: 'rgba(239,68,68,0.1)', border: '1px solid var(--critical)', borderRadius: '4px', color: 'var(--critical)', fontSize: '11px', fontWeight: 600, cursor: 'pointer' }}
                        >
                          ✕ Abandon
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Metadata fields */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '10px', background: 'rgba(255,255,255,0.02)', padding: '12px', borderRadius: '4px', border: '1px solid var(--border)' }}>
                    <div>
                      <span style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Priority</span>
                      <div style={{ fontSize: '12px', fontWeight: 600, color: goal.priority === 'CRITICAL' ? 'var(--critical)' : '#fff', marginTop: '2px' }}>{goal.priority}</div>
                    </div>
                    <div>
                      <span style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Target Date</span>
                      <div style={{ fontSize: '12px', fontWeight: 600, color: '#fff', marginTop: '2px' }}>{goal.target_date || 'N/A'}</div>
                    </div>
                    <div>
                      <span style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Owner</span>
                      <div style={{ fontSize: '12px', fontWeight: 600, color: '#fff', marginTop: '2px' }}>{goal.owner || 'System'}</div>
                    </div>
                    <div>
                      <span style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Dependencies</span>
                      <div style={{ fontSize: '11px', fontWeight: 600, color: '#fff', marginTop: '2px' }}>
                        {goal.dependencies && goal.dependencies.length > 0 ? goal.dependencies.join(', ') : 'None'}
                      </div>
                    </div>
                    <div>
                      <span style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Priority Score</span>
                      <div style={{ fontSize: '12px', fontWeight: 'bold', color: '#a78bfa', marginTop: '2px' }}>{goal.priority_score !== undefined ? goal.priority_score : '1.00'}</div>
                    </div>
                    <div>
                      <span style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Metrics (I/U/A/C)</span>
                      <div style={{ fontSize: '11px', color: 'var(--text-primary)', marginTop: '2px' }}>
                        {goal.importance || 5} / {goal.urgency || 5} / {goal.strategic_alignment || 5} / {goal.resource_cost || 2}
                      </div>
                    </div>
                  </div>

                  {/* Success Criteria List */}
                  {goal.success_criteria && goal.success_criteria.length > 0 && (
                    <div>
                      <h4 style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '6px' }}>Success Criteria</h4>
                      <ul style={{ paddingLeft: '16px', margin: 0, display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        {goal.success_criteria.map((c, i) => (
                          <li key={i} style={{ fontSize: '12px', color: 'var(--text-primary)' }}>{c}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Milestones Hierarchy Section */}
                  <div>
                    <h4 style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '8px' }}>Milestone Execution Tree</h4>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                      {goal.milestones && goal.milestones.length > 0 ? (
                        goal.milestones.map((m) => {
                          const mStatusColor = m.status === 'COMPLETED' ? 'var(--ok)' : m.status === 'ACTIVE' ? 'var(--accent-blue)' : m.status === 'BLOCKED' ? 'var(--critical)' : 'var(--text-muted)';
                          return (
                            <div key={m.milestone_id} style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)', borderRadius: '4px', padding: '12px' }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <span style={{ fontWeight: 600, color: '#fff', fontSize: '12px' }}>{m.title}</span>
                                <span style={{ fontSize: '9px', padding: '1px 6px', borderRadius: '3px', background: `${mStatusColor}1A`, color: mStatusColor, border: `1px solid ${mStatusColor}33`, fontWeight: 'bold' }}>
                                  {m.status}
                                </span>
                              </div>
                              <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px', margin: '4px 0' }}>{m.description}</p>
                              
                              {/* Simulation prediction data */}
                              {(m.success_probability !== null || m.rollback_risk !== null || m.expected_duration_sec !== null) && (
                                <div style={{ display: 'flex', gap: '12px', marginTop: '8px', borderTop: '1px solid rgba(255,255,255,0.03)', paddingTop: '6px', fontSize: '10px' }}>
                                  {m.success_probability !== null && (
                                    <div>
                                      <span style={{ color: 'var(--text-muted)' }}>Success Prob: </span>
                                      <span style={{ color: m.success_probability > 0.8 ? 'var(--ok)' : 'var(--warn)', fontWeight: 'bold' }}>{(m.success_probability * 100).toFixed(0)}%</span>
                                    </div>
                                  )}
                                  {m.rollback_risk !== null && (
                                    <div>
                                      <span style={{ color: 'var(--text-muted)' }}>Rollback Risk: </span>
                                      <span style={{ color: m.rollback_risk < 0.15 ? 'var(--ok)' : 'var(--critical)', fontWeight: 'bold' }}>{(m.rollback_risk * 100).toFixed(0)}%</span>
                                    </div>
                                  )}
                                  {m.expected_duration_sec !== null && (
                                    <div>
                                      <span style={{ color: 'var(--text-muted)' }}>Expected Duration: </span>
                                      <span style={{ color: '#fff', fontWeight: 'bold' }}>{(m.expected_duration_sec).toFixed(0)}s</span>
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          );
                        })
                      ) : (
                        <div style={{ background: 'rgba(255,255,255,0.01)', border: '1px dashed var(--border)', borderRadius: '4px', padding: '16px', textAlign: 'center' }}>
                          <span style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '8px' }}>No milestones created for this goal yet.</span>
                          
                          {/* Batch Milestones Form */}
                          <div style={{ textAlign: 'left', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            <span style={{ fontSize: '10px', color: '#fff', fontWeight: 600 }}>Create Milestones Batch</span>
                            {milestonesToAdd.map((m, idx) => (
                              <div key={idx} style={{ display: 'flex', gap: '6px' }}>
                                <input
                                  type="text"
                                  placeholder={`Milestone ${idx+1} Title`}
                                  value={m.title}
                                  onChange={(e) => {
                                    const copy = [...milestonesToAdd];
                                    copy[idx].title = e.target.value;
                                    setMilestonesToAdd(copy);
                                  }}
                                  style={{ flex: 3, padding: '6px 10px', background: '#0e131f', border: '1px solid var(--border)', borderRadius: '3px', color: '#fff', fontSize: '11px' }}
                                />
                                <input
                                  type="number"
                                  placeholder="Weight"
                                  step="0.1"
                                  value={m.weight}
                                  onChange={(e) => {
                                    const copy = [...milestonesToAdd];
                                    copy[idx].weight = parseFloat(e.target.value) || 1.0;
                                    setMilestonesToAdd(copy);
                                  }}
                                  style={{ flex: 1, padding: '6px 10px', background: '#0e131f', border: '1px solid var(--border)', borderRadius: '3px', color: '#fff', fontSize: '11px' }}
                                />
                              </div>
                            ))}
                            <div style={{ display: 'flex', gap: '6px', marginTop: '4px' }}>
                              <button
                                type="button"
                                onClick={() => setMilestonesToAdd([...milestonesToAdd, { title: '', weight: 1.0 }])}
                                style={{ padding: '4px 8px', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border)', borderRadius: '3px', color: '#fff', fontSize: '10px', cursor: 'pointer' }}
                              >
                                + Add Row
                              </button>
                              <button
                                type="button"
                                onClick={() => handleSetMilestones(goal.goal_id)}
                                style={{ padding: '4px 12px', background: 'var(--accent-blue)', border: 'none', borderRadius: '3px', color: '#fff', fontSize: '10px', fontWeight: 600, cursor: 'pointer', marginLeft: 'auto' }}
                              >
                                ✓ Commit Milestones
                              </button>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Append-only Event Ledger */}
                  <div>
                    <h4 style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '8px' }}>Append-only Event Log</h4>
                    <div style={{ background: '#0e131f', borderRadius: '4px', border: '1px solid var(--border)', maxHeight: '180px', overflowY: 'auto', padding: '10px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      {selectedGoalHistory.length === 0 ? (
                        <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontStyle: 'italic', textAlign: 'center' }}>No events recorded.</div>
                      ) : (
                        selectedGoalHistory.map((h, i) => (
                          <div key={i} style={{ fontSize: '11px', display: 'flex', gap: '8px', borderBottom: '1px solid rgba(255,255,255,0.02)', paddingBottom: '4px' }}>
                            <span style={{ color: 'var(--text-muted)', fontFamily: 'monospace' }}>[{new Date(h.timestamp * 1000).toLocaleTimeString()}]</span>
                            <span style={{ color: '#a78bfa', fontWeight: 'bold' }}>{h.event_type}</span>
                            <span style={{ color: 'var(--text-primary)' }}>{JSON.stringify(h.payload)}</span>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </>
              );
            })() : (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', fontSize: '13px', fontStyle: 'italic', gap: '10px' }}>
                <span>🎯</span>
                Select a goal from the pipeline to view interactive milestones, success criteria, and simulation metrics
              </div>
            )}
          </div>
        </div>
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
