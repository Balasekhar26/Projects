import type {
  Approval,
  ChatSession,
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
  WritingResult,
} from "../types";

export const API_BASE_URL = "http://127.0.0.1:8000";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 4500);
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

function postJson<T>(path: string, body: unknown): Promise<T> {
  return requestJson<T>(path, { method: "POST", body: JSON.stringify(body) });
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
    projectEcosystem,
    sourcePolicy,
    projectIndex,
    toolScout,
    toolAdoptions,
  };
}

export function sendChatMessage(message: string, sessionId?: string) {
  return postJson<{ response?: string; state?: Record<string, unknown> }>("/chat", {
    message,
    session_id: sessionId,
  });
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
  return postJson<{ item: Approval }>(`/approvals/${approvalId}`, { status }).then((data) => data.item);
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
