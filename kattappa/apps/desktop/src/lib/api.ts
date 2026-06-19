import type {
  Approval,
  ApprovalContinuationResult,
  ChatSession,
  ClusterDiscoveryTarget,
  ClusterNode,
  ClusterRouteResult,
  ClusterStatus,
  DashboardData,
  FinanceComparisonResult,
  FinanceCsvForecastRequest,
  FinanceForecastRequest,
  FinanceForecastResult,
  HardwareRequirements,
  InstallResult,
  KronosStatus,
  LongTask,
  PlatformSupport,
  ResearchResult,
  ResumeResult,
  SimulationResult,
  Skill,
  StoredMessage,
  ToolAdoptionJob,
  VoicePipelineStatus,
  VoiceProcessResult,
  WritingResult,
} from "../types";

export const API_BASE_URL = "http://127.0.0.1:8000";

async function requestJson<T>(path: string, init?: RequestInit, timeoutMs = 4500): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      signal: controller.signal,
      ...init,
    });
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new Error(detail || `${response.status} ${response.statusText}`);
    }
    return response.json() as Promise<T>;
  } finally {
    window.clearTimeout(timeout);
  }
}

function postJson<T>(path: string, body: unknown, timeoutMs?: number): Promise<T> {
  return requestJson<T>(path, { method: "POST", body: JSON.stringify(body) }, timeoutMs);
}

export async function fetchDashboardData(): Promise<DashboardData> {
  const [
    health,
    freeStack,
    capabilityLadder,
    improvements,
    skills,
    reflections,
    builderProfile,
    codexParity,
    projectEcosystem,
    sourcePolicy,
    projectIndex,
    toolScout,
    toolAdoptions,
  ] = await Promise.all([
    requestJson<DashboardData["health"]>("/health"),
    requestJson<DashboardData["freeStack"]>("/free-stack"),
    requestJson<DashboardData["capabilityLadder"]>("/capability-ladder"),
    requestJson<{ items: DashboardData["improvements"] }>("/improvements").then((data) => data.items),
    requestJson<{ items: DashboardData["skills"] }>("/skills").then((data) => data.items),
    requestJson<{ items: DashboardData["reflections"] }>("/reflections").then((data) => data.items),
    requestJson<DashboardData["builderProfile"]>("/builder/profile"),
    requestJson<DashboardData["codexParity"]>("/builder/codex-parity"),
    requestJson<DashboardData["projectEcosystem"]>("/projects/ecosystem"),
    requestJson<DashboardData["sourcePolicy"]>("/source-policy"),
    requestJson<DashboardData["projectIndex"]>("/project-index"),
    requestJson<DashboardData["toolScout"]>("/tool-scout"),
    requestJson<{ items: DashboardData["toolAdoptions"] }>("/tool-adoptions").then((data) => data.items),
  ]);

  return {
    health,
    freeStack,
    capabilityLadder,
    improvements,
    skills,
    reflections,
    builderProfile,
    codexParity,
    projectEcosystem,
    sourcePolicy,
    projectIndex,
    toolScout,
    toolAdoptions,
  };
}

export function fetchHealth() {
  return requestJson<DashboardData["health"]>("/health");
}

export function fetchClusterStatus() {
  return requestJson<ClusterStatus>("/cluster/status");
}

export function addClusterNode(node: {
  name: string;
  base_url: string;
  token: string;
  capabilities: Record<string, unknown>;
}) {
  return postJson<{ item: ClusterNode }>("/cluster/nodes", node).then((data) => data.item);
}

export function removeClusterNode(nodeId: string) {
  return requestJson<{ removed: boolean; node_id: string }>(`/cluster/nodes/${nodeId}`, { method: "DELETE" });
}

export function addClusterDiscoveryTarget(target: { name: string; base_url: string }) {
  return postJson<{ item: ClusterDiscoveryTarget }>("/cluster/discovery-targets", target).then((data) => data.item);
}

export function removeClusterDiscoveryTarget(targetId: string) {
  return requestJson<{ removed: boolean; target_id: string }>(
    `/cluster/discovery-targets/${targetId}`,
    { method: "DELETE" },
  );
}

export function routeClusterTask(body: {
  message: string;
  task_kind: string;
  sensitivity: string;
  force_remote: boolean;
}) {
  return postJson<ClusterRouteResult>("/cluster/tasks/route", body, 180000);
}

export function sendChatMessage(message: string, sessionId?: string) {
  return postJson<{ response?: string; state?: Record<string, unknown>; session?: ChatSession }>("/chat", {
    message,
    session_id: sessionId,
  });
}

export function fetchVoiceStatus() {
  return requestJson<VoicePipelineStatus>("/voice/status");
}

export function speakWithLocalVoice(text: string, purpose = "assistant_response") {
  return postJson<{
    ok: boolean;
    purpose: string;
    spoken_text?: string;
    result: string;
    pipeline: VoicePipelineStatus;
  }>(
    "/voice/speak",
    { text, purpose },
    30000,
  );
}

export function processVoiceAudio(body: { audio_base64: string; mime_type: string; model_size?: string }) {
  return postJson<VoiceProcessResult>(
    "/voice/process",
    { model_size: "small", ...body },
    90000,
  );
}

export function createChatSession(title = "New chat") {
  return postJson<{ item: ChatSession }>("/chat-sessions", { title }).then((data) => data.item);
}

export function fetchChatSessions() {
  return requestJson<{ items: ChatSession[] }>("/chat-sessions").then((data) => data.items);
}

export function fetchChatSessionMessages(sessionId: string) {
  return requestJson<{ item: ChatSession; messages: StoredMessage[] }>(`/chat-sessions/${sessionId}`).then(
    (data) => data.messages,
  );
}

export function saveChatSessionMessage(sessionId: string, message: {
  role: string;
  content: string;
  agent?: string;
  risk?: string;
}) {
  return postJson<{ item: StoredMessage }>(`/chat-sessions/${sessionId}/messages`, {
    role: message.role,
    content: message.content,
    agent: message.agent ?? "",
    risk: message.risk ?? "",
    metadata: "{}",
  }).then((data) => data.item);
}

export function fetchApprovals() {
  return requestJson<{ items: Approval[] }>("/approvals").then((data) => data.items);
}

export function decideApproval(approvalId: string, status: "approved" | "rejected") {
  return postJson<{ item: Approval; continuation?: ApprovalContinuationResult }>(`/approvals/${approvalId}`, { status });
}

export function continueApprovedWork(approvalId: string) {
  return postJson<ApprovalContinuationResult>(`/approvals/${approvalId}/continue`, {}, 120000);
}

export function createLongTask(task: { title: string; goal: string; priority: string; source_session_id: string }) {
  return postJson<{ item: LongTask }>("/long-tasks", task).then((data) => data.item);
}

export function fetchLongTasks() {
  return requestJson<{ items: LongTask[] }>("/long-tasks").then((data) => data.items);
}

export function updateLongTask(taskId: string, update: Partial<Pick<LongTask, "status" | "progress" | "next_step">>) {
  return postJson<{ item: LongTask }>(`/long-tasks/${taskId}`, update).then((data) => data.item);
}

export function resumeLongTask(taskId: string) {
  return postJson<ResumeResult>(`/long-tasks/${taskId}/resume`, {});
}

export function checkWriting(text: string) {
  return postJson<WritingResult>("/writing/check", { text });
}

export function rewriteWriting(body: { text: string; tone: string }) {
  return postJson<WritingResult>("/writing/rewrite", body);
}

export function extractResearch(body: { url: string; goal: string }) {
  return postJson<ResearchResult>("/web-research/extract", body);
}

export function runSimulation(body: { seed: string; horizon: string }) {
  return postJson<SimulationResult>("/simulation/run", body);
}

export function requestMissingInstalls() {
  return postJson<InstallResult>("/install/missing/request", {});
}

export function runApprovedInstallJob(approvalId: string) {
  return postJson<InstallResult>(`/install/approved/${approvalId}`, {});
}

export function runSelfEvolution() {
  return postJson<{ reflections_scanned: number; draft_skills_created: { skill_id: string; approval_id: string; trigger: string }[]; next_step: string }>("/self-evolution/run", {});
}

export function setSkillTrust(skillId: string, trust: "draft" | "approved" | "trusted" | "disabled") {
  return postJson<{ item: Skill }>(`/skills/${skillId}/trust`, { trust }).then((data) => data.item);
}

export function runToolScout(task: string) {
  return postJson<Record<string, unknown>>("/tool-scout/run", { task });
}

export function startToolAdoption(reportId: string) {
  return postJson<Record<string, unknown>>(`/tool-scout/${reportId}/adopt`, {});
}

export function continueToolAdoptionForApproval(approvalId: string) {
  return postJson<{ status: string } & Partial<ToolAdoptionJob>>(`/tool-adoptions/approved/${approvalId}`, {});
}

export function fetchKronosStatus() {
  return requestJson<KronosStatus>("/finance/kronos/status");
}

export function runFinanceForecast(body: FinanceForecastRequest) {
  return postJson<FinanceForecastResult>("/finance/forecast", body);
}

export function runFinanceCsvForecast(body: FinanceCsvForecastRequest) {
  return postJson<FinanceForecastResult>("/finance/forecast-csv", body);
}

export function runFinanceComparison(body: FinanceForecastRequest) {
  return postJson<FinanceComparisonResult>("/finance/compare", body);
}

export function runFinanceCsvComparison(body: FinanceCsvForecastRequest) {
  return postJson<FinanceComparisonResult>("/finance/compare-csv", body);
}

export async function fetchDiagnostics(): Promise<{
  platformSupport: PlatformSupport;
  hardwareRequirements: HardwareRequirements;
}> {
  const [platformSupport, hardwareRequirements] = await Promise.all([
    requestJson<PlatformSupport>("/system/platform-support"),
    requestJson<HardwareRequirements>("/system/hardware-requirements"),
  ]);
  return { platformSupport, hardwareRequirements };
}

export function fetchJarvisMode(): Promise<{ enabled: boolean }> {
  return requestJson<{ enabled: boolean }>("/settings/jarvis");
}

export function saveJarvisMode(enabled: boolean): Promise<{ enabled: boolean }> {
  return postJson<{ enabled: boolean }>("/settings/jarvis", { enabled });
}

export interface JarvisDiagnostics {
  ok: boolean;
  telemetry: {
    neuroseed_brain_sync: string;
    cyber_shield_deflectors: string;
    universal_translation: string;
    pcb_doctor: string;
    kairo: string;
    prism: string;
    tempo: string;
    portal: string;
    mira: string;
  };
  stats: {
    cpu: number;
    memory: number;
    git_changes: number;
    active_tasks: number;
    projects: number;
    ollama_ok: boolean;
    voice_ok: boolean;
  };
}

export function fetchJarvisDiagnostics(): Promise<JarvisDiagnostics> {
  return requestJson<JarvisDiagnostics>("/settings/jarvis/diagnostics");
}

export interface SageStatus {
  concepts: Array<{ id: string; concept: string; confidence: number; connections: any }>;
  profile: {
    concise_preference: number;
    technical_preference: number;
    user_goals: string;
    knowledge_level?: string;
    learning_speed?: string;
    interests?: string;
  };
  weights: Record<string, number>;
  aether_metrics?: {
    memory_layers: Record<string, string>;
    self_questioning_results: {
      know: string;
      assume: string;
      evidence: string;
      wrong: string;
    };
    ethical_scores: {
      truthfulness: number;
      safety: number;
      fairness: number;
      user_benefit: number;
      long_term_impact: number;
    };
    meta_learning: {
      strategy_success_rates: Record<string, number>;
    };
    confidence_tracking: string;
  };
}

export function fetchSageStatus(): Promise<SageStatus> {
  return requestJson<SageStatus>("/sage/status");
}

export function submitSageFeedback(userInput: string, source: string, rating: number): Promise<{ success: boolean; new_weights: Record<string, number> }> {
  return postJson("/sage/feedback", { user_input: userInput, source, rating });
}


