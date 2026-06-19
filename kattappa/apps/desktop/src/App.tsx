import { useEffect, useMemo, useRef, useState } from "react";
import { ChatPanel } from "./components/ChatPanel";
import { DesktopGuidanceOverlay } from "./components/DesktopGuidanceOverlay";
import { PanelContent } from "./components/PanelContent";
import { RightPanel } from "./components/RightPanel";
import { Sidebar } from "./components/Sidebar";
import {
  API_BASE_URL as API,
  addClusterDiscoveryTarget,
  addClusterNode,
  checkWriting,
  continueApprovedWork,
  createChatSession,
  createLongTask as createLongTaskRequest,
  decideApproval as decideApprovalRequest,
  extractResearch,
  fetchApprovals,
  fetchChatSessionMessages,
  fetchChatSessions,
  fetchClusterStatus,
  fetchDashboardData,
  fetchHealth,
  fetchLongTasks,
  rateChatMessage,
  removeClusterDiscoveryTarget,
  removeClusterNode,
  requestMissingInstalls as requestMissingInstallsRequest,
  resumeLongTask,
  routeClusterTask,
  rewriteWriting,
  runSelfEvolution,
  runSimulation,
  runToolScout,
  saveChatSessionMessage,
  sendChatMessage,
  setSkillTrust as setSkillTrustRequest,
  startToolAdoption as startToolAdoptionRequest,
  updateLongTask as updateLongTaskRequest,
} from "./lib/api";
import { PANELS, initialMessages } from "./state/appState";
import type {
  Approval,
  ApprovalContinuationResult,
  BuilderProfile,
  CapabilityLadder,
  ChatSession,
  ClusterRouteResult,
  ClusterStatus,
  CodexParityReport,
  EvolutionCycle,
  FreeStack,
  Health,
  Improvement,
  InstallResult,
  LongTask,
  Message,
  ProjectEcosystem,
  ProjectIndex,
  Reflection,
  RelatedChatMessage,
  ResearchResult,
  ResumeResult,
  SimulationResult,
  Skill,
  SourcePolicy,
  StoredMessage,
  ToolAdoptionJob,
  ToolScoutStatus,
  VisualGuidance,
  WritingResult,
} from "./types";

type QueuedTurn = {
  text: string;
};

const VISUAL_GUIDANCE_AUTO_HIDE_MS = 6500;

function parseMessageMetadata(metadata: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(metadata || "{}");
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : {};
  } catch {
    return {};
  }
}

function metadataRating(metadata: Record<string, unknown>): 1 | -1 | undefined {
  const rating = metadata.sage_feedback_rating ?? metadata.response_rating;
  return rating === 1 || rating === -1 ? rating : undefined;
}

function storedMessageToChat(item: StoredMessage): Message {
  const metadata = parseMessageMetadata(item.metadata);
  return {
    id: item.id,
    role: item.role,
    content: item.content,
    agent: item.agent || undefined,
    risk: item.risk || undefined,
    rating: metadataRating(metadata),
    metadata,
  };
}

function storedMessagesToChat(stored: StoredMessage[]): Message[] {
  return stored.length
    ? stored.map(storedMessageToChat)
    : initialMessages();
}

function approvalContinuationMessage(data: ApprovalContinuationResult) {
  const kind = data.kind ? data.kind.replace(/_/g, " ") : "approval";
  const message = data.message ?? `${kind}: ${data.status}.`;
  const finalApprovalId = data.job?.["final_approval_id"];
  const nextApproval =
    typeof finalApprovalId === "string" && finalApprovalId
      ? " Next approval needed."
      : "";
  return `${message}${nextApproval}`;
}

function compactLiveStatus(raw: string) {
  const text = raw.trim();
  const lower = text.toLowerCase();
  if (!text) return "Working";
  if (lower.includes("planning") || lower.includes("planner:")) return "Routing";
  if (lower.includes("memory:")) return "Memory";
  if (lower.includes("safety:")) return lower.includes("approved") ? "Approved" : "Safety";
  if (lower.includes("approval") && lower.includes("waiting")) return "Approval needed";
  if (lower.includes("approval")) return "Approval";
  if (lower.includes("desktop:")) return "Desktop";
  if (lower.includes("coder:")) return "Coding";
  if (lower.includes("builder:")) return "Builder";
  if (lower.includes("file:")) return "Files";
  if (lower.includes("voice:")) return "Voice";
  if (lower.includes("finalized") || lower.includes("completed")) return "Done";
  return text.length > 28 ? `${text.slice(0, 25).trim()}...` : text;
}

function compactVoiceStatus(raw: string) {
  const lower = raw.toLowerCase();
  if (lower.includes("wake")) return "Wake name needed";
  if (lower.includes("stt") || lower.includes("transcription")) return "Voice setup needed";
  if (lower.includes("audio")) return "No voice audio";
  if (lower.includes("microphone") || lower.includes("voice")) return "Voice unavailable";
  return compactLiveStatus(raw);
}

function App() {
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [activePanel, setActivePanel] = useState("Chat");
  const [input, setInput] = useState("");
  const [connected, setConnected] = useState(false);
  const [agentStatus, setAgentStatus] = useState("Backend not connected");
  const [liveStatus, setLiveStatus] = useState("Ready");
  const [health, setHealth] = useState<Health | null>(null);
  const [freeStack, setFreeStack] = useState<FreeStack | null>(null);
  const [sourcePolicy, setSourcePolicy] = useState<SourcePolicy | null>(null);
  const [toolScout, setToolScout] = useState<ToolScoutStatus | null>(null);
  const [toolAdoptions, setToolAdoptions] = useState<ToolAdoptionJob[]>([]);
  const [clusterStatus, setClusterStatus] = useState<ClusterStatus | null>(null);
  const [clusterDraft, setClusterDraft] = useState({
    name: "",
    base_url: "",
    token: "",
    capabilities: "{\"cpu_count_logical\": 16, \"ram_total_gb\": 64}",
  });
  const [clusterDiscoveryDraft, setClusterDiscoveryDraft] = useState({
    name: "",
    base_url: "",
  });
  const [clusterRouteDraft, setClusterRouteDraft] = useState({
    message: "use a large model to summarize this project",
    task_kind: "large_local_model",
    sensitivity: "normal",
    force_remote: false,
  });
  const [clusterRouteResult, setClusterRouteResult] = useState<ClusterRouteResult | null>(null);
  const [clusterError, setClusterError] = useState("");
  const [capabilityLadder, setCapabilityLadder] = useState<CapabilityLadder | null>(null);
  const [improvements, setImprovements] = useState<Improvement[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [reflections, setReflections] = useState<Reflection[]>([]);
  const [evolutionCycle, setEvolutionCycle] = useState<EvolutionCycle | null>(null);
  const [evolutionRunning, setEvolutionRunning] = useState(false);
  const [builderProfile, setBuilderProfile] = useState<BuilderProfile | null>(null);
  const [codexParity, setCodexParity] = useState<CodexParityReport | null>(null);
  const [projectEcosystem, setProjectEcosystem] = useState<ProjectEcosystem | null>(null);
  const [projectIndex, setProjectIndex] = useState<ProjectIndex | null>(null);
  const [resumeResult, setResumeResult] = useState<ResumeResult | null>(null);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [installResult, setInstallResult] = useState<InstallResult | null>(null);
  const [chatSessions, setChatSessions] = useState<ChatSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [longTasks, setLongTasks] = useState<LongTask[]>([]);
  const [taskDraft, setTaskDraft] = useState({ title: "", goal: "", priority: "normal" });
  const [writingDraft, setWritingDraft] = useState({ text: "", tone: "clear" });
  const [writingResult, setWritingResult] = useState<WritingResult | null>(null);
  const [researchDraft, setResearchDraft] = useState({ url: "", goal: "Extract the main useful facts as structured data." });
  const [researchResult, setResearchResult] = useState<ResearchResult | null>(null);
  const [simulationDraft, setSimulationDraft] = useState({ seed: "", horizon: "short" });
  const [simulationResult, setSimulationResult] = useState<SimulationResult | null>(null);
  const [assistantWorking, setAssistantWorking] = useState(false);
  const [queuedCount, setQueuedCount] = useState(0);
  const [currentTask, setCurrentTask] = useState("");
  const [queuedTurns, setQueuedTurns] = useState<QueuedTurn[]>([]);
  const [hiddenGuidanceKey, setHiddenGuidanceKey] = useState<string | null>(null);
  const [launchProgress, setLaunchProgress] = useState(8);
  const [launchStatus, setLaunchStatus] = useState("Opening Kattappa AI OS");
  const [launchComplete, setLaunchComplete] = useState(false);
  const [decidingApprovals, setDecidingApprovals] = useState<string[]>([]);
  const [approvalNotice, setApprovalNotice] = useState<{
    tone: "danger" | "working" | "ready";
    title: string;
    message: string;
  } | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const ws = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<number | null>(null);
  const currentSessionRef = useRef<string | null>(null);
  const assistantWorkingRef = useRef(false);
  const messageQueueRef = useRef<QueuedTurn[]>([]);
  const turnTimeoutRef = useRef<number | null>(null);
  const messagesLoadedRef = useRef(false);

  useEffect(() => {
    currentSessionRef.current = currentSessionId;
  }, [currentSessionId]);

  const refreshApprovals = async () => {
    try {
      const items = await fetchApprovals();
      setApprovals(items);
      if (items.length > 0) {
        setApprovalNotice(null);
      }
    } catch {
      setApprovals([]);
    }
  };

  const refreshHealth = async (mode: "quiet" | "full" = "full") => {
    try {
      if (mode === "quiet") {
        setHealth(await fetchHealth());
        return;
      }
      const data = await fetchDashboardData();
      setHealth(data.health);
      setFreeStack(data.freeStack);
      setCapabilityLadder(data.capabilityLadder);
      setImprovements(data.improvements);
      setSkills(data.skills);
      setReflections(data.reflections);
      setBuilderProfile(data.builderProfile);
      setCodexParity(data.codexParity);
      setProjectEcosystem(data.projectEcosystem);
      setSourcePolicy(data.sourcePolicy);
      setProjectIndex(data.projectIndex);
      setToolScout(data.toolScout);
      setToolAdoptions(data.toolAdoptions);
    } catch {
      setHealth(null);
      setFreeStack(null);
      setCapabilityLadder(null);
      setImprovements([]);
      setSkills([]);
      setReflections([]);
      setBuilderProfile(null);
      setCodexParity(null);
      setProjectEcosystem(null);
      setSourcePolicy(null);
      setProjectIndex(null);
      setToolScout(null);
      setToolAdoptions([]);
    }
  };

  const refreshChatSessions = async () => {
    try {
      const sessions = await fetchChatSessions();
      setChatSessions(sessions);
      const primarySession = sessions[0];
      if (primarySession && (!currentSessionRef.current || !messagesLoadedRef.current)) {
        setCurrentSessionId(primarySession.id);
        currentSessionRef.current = primarySession.id;
        const stored = await fetchChatSessionMessages(primarySession.id);
        if (stored.length > 0 || launchComplete) {
          setMessages(storedMessagesToChat(stored));
          messagesLoadedRef.current = true;
        }
      }
    } catch {
      setChatSessions([]);
    }
  };

  const refreshLongTasks = async () => {
    try {
      setLongTasks(await fetchLongTasks());
    } catch {
      setLongTasks([]);
    }
  };

  const refreshCluster = async () => {
    try {
      setClusterStatus(await fetchClusterStatus());
      setClusterError("");
    } catch (error) {
      setClusterStatus(null);
      setClusterError(error instanceof Error ? error.message : "Cluster status unavailable.");
    }
  };

  const registerClusterWorker = async () => {
    setClusterError("");
    try {
      const capabilities = clusterDraft.capabilities.trim()
        ? JSON.parse(clusterDraft.capabilities)
        : {};
      await addClusterNode({
        name: clusterDraft.name.trim(),
        base_url: clusterDraft.base_url.trim(),
        token: clusterDraft.token.trim(),
        capabilities,
      });
      setClusterDraft((current) => ({ ...current, name: "", base_url: "", token: "" }));
      await refreshCluster();
    } catch (error) {
      setClusterError(error instanceof Error ? error.message : "Could not add worker.");
    }
  };

  const deleteClusterWorker = async (nodeId: string) => {
    setClusterError("");
    try {
      await removeClusterNode(nodeId);
      await refreshCluster();
    } catch (error) {
      setClusterError(error instanceof Error ? error.message : "Could not remove worker.");
    }
  };

  const registerClusterDiscoveryTarget = async () => {
    setClusterError("");
    try {
      await addClusterDiscoveryTarget({
        name: clusterDiscoveryDraft.name.trim(),
        base_url: clusterDiscoveryDraft.base_url.trim(),
      });
      setClusterDiscoveryDraft({ name: "", base_url: "" });
      await refreshCluster();
    } catch (error) {
      setClusterError(error instanceof Error ? error.message : "Could not add discovery target.");
    }
  };

  const deleteClusterDiscoveryTarget = async (targetId: string) => {
    setClusterError("");
    try {
      await removeClusterDiscoveryTarget(targetId);
      await refreshCluster();
    } catch (error) {
      setClusterError(error instanceof Error ? error.message : "Could not remove discovery target.");
    }
  };

  const runClusterRoute = async () => {
    setClusterError("");
    setClusterRouteResult(null);
    try {
      setClusterRouteResult(await routeClusterTask(clusterRouteDraft));
      await refreshCluster();
    } catch (error) {
      setClusterError(error instanceof Error ? error.message : "Cluster route failed.");
    }
  };

  const ensureMessageSession = async () => {
    if (currentSessionRef.current) return currentSessionRef.current;
    try {
      const session = await createChatSession("Kattappa Chat");
      setCurrentSessionId(session.id);
      currentSessionRef.current = session.id;
      refreshChatSessions();
      return session.id;
    } catch {
      return null;
    }
  };

  const loadChatSession = async (sessionId: string) => {
    const stored = await fetchChatSessionMessages(sessionId);
    setCurrentSessionId(sessionId);
    currentSessionRef.current = sessionId;
    setMessages(storedMessagesToChat(stored));
    setActivePanel("Chat");
  };

  const openChat = async () => {
    setActivePanel("Chat");
    if (currentSessionRef.current) return currentSessionRef.current;
    try {
      const sessions = chatSessions.length ? chatSessions : await fetchChatSessions();
      if (sessions[0]) {
        await loadChatSession(sessions[0].id);
        return sessions[0].id;
      }
    } catch {
      // Opening chat should stay local and quiet; message sending will surface real failures.
    }
    return ensureMessageSession();
  };

  const ensureChatSession = async () => currentSessionRef.current ?? openChat();

  const persistChatMessage = async (sessionId: string | null, message: Message) => {
    if (!sessionId || message.role === "progress") return;
    await saveChatSessionMessage(sessionId, message);
    refreshChatSessions();
  };

  const createLongTask = async () => {
    const goal = taskDraft.goal.trim();
    if (!goal) return;
    await createLongTaskRequest({
      title: taskDraft.title.trim() || goal.slice(0, 80),
      goal,
      priority: taskDraft.priority,
      source_session_id: currentSessionRef.current ?? "",
    });
    setTaskDraft({ title: "", goal: "", priority: "normal" });
    refreshLongTasks();
  };

  const updateLongTask = async (taskId: string, update: Partial<Pick<LongTask, "status" | "progress" | "next_step">>) => {
    await updateLongTaskRequest(taskId, update);
    refreshLongTasks();
  };

  const runWritingCheck = async () => {
    if (!writingDraft.text.trim()) return;
    setWritingResult(await checkWriting(writingDraft.text));
  };

  const runWritingRewrite = async () => {
    if (!writingDraft.text.trim()) return;
    setWritingResult(await rewriteWriting(writingDraft));
  };

  const runResearchExtract = async () => {
    if (!researchDraft.url.trim()) return;
    setResearchResult(await extractResearch(researchDraft));
  };

  const runScenarioSimulation = async () => {
    if (!simulationDraft.seed.trim()) return;
    setSimulationResult(await runSimulation(simulationDraft));
  };

  const continueLongTask = async (task: LongTask) => {
    await ensureChatSession();
    setInput(
      `Continue long task: ${task.title}\nGoal: ${task.goal}\nCurrent progress: ${task.progress || "not recorded yet"}\nNext step: ${task.next_step || "decide the next safe step"}`,
    );
    setActivePanel("Chat");
  };

  const planLongTaskResume = async (task: LongTask) => {
    const data = await resumeLongTask(task.id);
    setResumeResult(data);
    setInput(data.resume_prompt);
    setActivePanel("Chat");
    refreshLongTasks();
  };

  useEffect(() => {
    if (launchComplete) return;
    const timer = window.setInterval(() => {
      setLaunchProgress((value) => Math.min(value + 3, connected ? 96 : 88));
    }, 300);
    return () => window.clearInterval(timer);
  }, [connected, launchComplete]);

  useEffect(() => {
    if (launchComplete) return;
    let cancelled = false;
    const checkReady = async () => {
      try {
        setLaunchStatus("Starting local services");
        setLaunchProgress((value) => Math.max(value, 28));
        const response = await fetch(`${API}/ready`);
        if (!response.ok) throw new Error("not ready");
        if (cancelled) return;
        setLaunchStatus("Connecting local chat");
        setLaunchProgress((value) => Math.max(value, 70));
        await refreshHealth("quiet");
      } catch {
        if (!cancelled) setLaunchStatus("Waiting for backend");
      }
    };
    checkReady();
    const interval = window.setInterval(checkReady, 700);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [launchComplete]);

  useEffect(() => {
    if (!connected || launchComplete) return;
    setLaunchStatus("Ready");
    setLaunchProgress(100);
    const timer = window.setTimeout(() => setLaunchComplete(true), 450);
    return () => window.clearTimeout(timer);
  }, [connected, launchComplete]);

  useEffect(() => {
    if (launchComplete) return;
    const timer = window.setTimeout(() => {
      setLaunchStatus("Chat opened");
      setLaunchComplete(true);
    }, 5200);
    return () => window.clearTimeout(timer);
  }, [launchComplete]);

  const runSelfEvolutionCycle = async () => {
    if (evolutionRunning) return;
    setEvolutionRunning(true);
    try {
      setEvolutionCycle(await runSelfEvolution());
      refreshHealth();
      refreshApprovals();
    } finally {
      setEvolutionRunning(false);
    }
  };

  const setSkillTrust = async (skillId: string, trust: "draft" | "approved" | "trusted" | "disabled") => {
    setSkills((current) => current.map((skill) => (skill.id === skillId ? { ...skill, trust } : skill)));
    await setSkillTrustRequest(skillId, trust);
    refreshHealth();
  };

  const requestMissingInstalls = async () => {
    const data = await requestMissingInstallsRequest();
    setInstallResult(data);
    setMessages((prev) => [
      ...prev,
      {
        role: "system",
        content:
          data.status === "approval_required"
            ? `Install approval created: ${data.approval_id}`
            : data.message ?? "Install check completed.",
      },
    ]);
    refreshApprovals();
    refreshHealth();
  };

  const runManualToolScout = async () => {
    const task = input.trim() || messages.filter((message) => message.role === "user").at(-1)?.content || "Improve Kattappa AI OS with free local tools";
    await runToolScout(task);
    refreshHealth();
  };

  const startToolAdoption = async (reportId: string) => {
    await startToolAdoptionRequest(reportId);
    refreshApprovals();
    refreshHealth();
  };

  const connectSocket = () => {
    if (ws.current?.readyState === WebSocket.OPEN || ws.current?.readyState === WebSocket.CONNECTING) return;

    const socket = new WebSocket("ws://127.0.0.1:8000/ws/chat");
    ws.current = socket;
    socket.onopen = () => {
      setConnected(true);
      setAgentStatus("Connected");
      setLiveStatus("Ready");
    };
    socket.onclose = () => {
      setConnected(false);
      setAgentStatus("Disconnected");
      setLiveStatus("Reconnecting");
      if (assistantWorkingRef.current) {
        const message: Message = {
          role: "assistant",
          agent: "Kattappa AI",
          content: "Connection dropped. I released the composer.",
        };
        setMessages((prev) => [...prev, message]);
        persistChatMessage(currentSessionRef.current, message);
        finishAssistantTurn();
      }
      reconnectTimer.current = window.setTimeout(connectSocket, 1500);
    };
    socket.onerror = () => socket.close();
    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "progress" || data.type === "system") {
          const status = compactLiveStatus(String(data.content || ""));
          setLiveStatus(status);
          setAgentStatus(status);
          return;
        }
        const message: Message = {
          id: data.assistant_message_id || data.assistant_message?.id,
          role: data.type === "assistant" ? "assistant" : data.type,
          content: data.content,
          risk: data.risk_level,
          agent: data.selected_agent,
          routingReason: data.routing?.reason,
          approvalId: data.approval_id,
          relatedMessages: data.related_messages,
          operatorPlan: data.operator_plan,
        };
        setMessages((prev) => [...prev, message]);
        if (data.session_id && !currentSessionRef.current) {
          setCurrentSessionId(data.session_id);
          currentSessionRef.current = data.session_id;
        }
        if (data.selected_agent) setAgentStatus(`${data.selected_agent} / ${data.risk_level}`);
        if (data.approval_required) refreshApprovals();
        if (data.type === "assistant") {
          setLiveStatus(data.approval_required ? "Approval needed" : "Done");
          refreshChatSessions();
          finishAssistantTurn();
        }
      } catch {
        const message: Message = { role: "assistant", content: event.data };
        setMessages((prev) => [...prev, message]);
        finishAssistantTurn();
      }
    };
  };

  useEffect(() => {
    connectSocket();
    return () => {
      if (reconnectTimer.current) window.clearTimeout(reconnectTimer.current);
      ws.current?.close();
    };
  }, []);

  useEffect(() => {
    refreshHealth("quiet");
    refreshApprovals();
    refreshChatSessions();
    refreshLongTasks();
    const interval = window.setInterval(() => {
      refreshHealth("quiet");
      refreshApprovals();
      refreshChatSessions();
      refreshLongTasks();
    }, 5000);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    if (activePanel !== "Chat") refreshHealth();
  }, [activePanel]);

  useEffect(() => {
    if (activePanel === "Cluster") refreshCluster();
  }, [activePanel]);

  useEffect(() => {
    if (activePanel === "Chat") {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [messages, activePanel]);

  const latestVisualGuidanceItem = useMemo(() => {
    const index = messages.length - 1;
    const guidance = messages[index]?.operatorPlan?.visual_guidance;
    if (guidance?.enabled && guidance.target) {
      return {
        guidance,
        key: `${index}:${guidance.target.label}:${guidance.target.x}:${guidance.target.y}`,
      };
    }
    return null;
  }, [messages]);

  useEffect(() => {
    if (!latestVisualGuidanceItem || activePanel !== "Chat") return;
    setHiddenGuidanceKey(null);
    const timer = window.setTimeout(() => {
      setHiddenGuidanceKey(latestVisualGuidanceItem.key);
    }, VISUAL_GUIDANCE_AUTO_HIDE_MS);
    return () => window.clearTimeout(timer);
  }, [latestVisualGuidanceItem?.key, activePanel]);

  const latestVisualGuidance =
    activePanel === "Chat" && latestVisualGuidanceItem && latestVisualGuidanceItem.key !== hiddenGuidanceKey
      ? latestVisualGuidanceItem.guidance
      : null;

  const setWorking = (value: boolean) => {
    assistantWorkingRef.current = value;
    setAssistantWorking(value);
  };

  const syncQueueState = () => {
    setQueuedCount(messageQueueRef.current.length);
    setQueuedTurns([...messageQueueRef.current]);
  };

  const clearTurnTimeout = () => {
    if (turnTimeoutRef.current) {
      window.clearTimeout(turnTimeoutRef.current);
      turnTimeoutRef.current = null;
    }
  };

  const startTurnTimeout = () => {
    clearTurnTimeout();
    turnTimeoutRef.current = window.setTimeout(() => {
      if (!assistantWorkingRef.current) return;
      const message: Message = {
        role: "assistant",
        agent: "Kattappa AI",
        content: "This took too long. I released the composer; send again to retry.",
      };
      setMessages((prev) => [...prev, message]);
      persistChatMessage(currentSessionRef.current, message);
      finishAssistantTurn();
    }, 120000);
  };

  const finishAssistantTurn = () => {
    clearTurnTimeout();
    const next = messageQueueRef.current.shift();
    syncQueueState();
    if (next) {
      setCurrentTask(next.text);
      setLiveStatus("Starting next");
      window.setTimeout(() => {
        void sendMessageText(next.text, true);
      }, 150);
      return;
    }
    setCurrentTask("");
    setWorking(false);
    setLiveStatus("Ready");
  };

  const sendMessage = async () => {
    await sendMessageText(input);
  };

  const sendMessageText = async (rawText: string, fromQueue = false) => {
    const text = rawText.trim();
    if (!text) return;
    if (assistantWorkingRef.current && !fromQueue) {
      messageQueueRef.current.push({ text });
      syncQueueState();
      setInput("");
      setLiveStatus(`Queued ${messageQueueRef.current.length}`);
      return;
    }
    setWorking(true);
    setCurrentTask(text);
    setLiveStatus("Working");
    startTurnTimeout();
    const userMessage: Message = { role: "user", content: text };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");

    const sessionId = await ensureMessageSession();

    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(text);
      return;
    }

    setLiveStatus("HTTP fallback");
    try {
      const data = await sendChatMessage(text, sessionId ?? undefined);
      const assistantMessage: Message = {
        id: data.assistant_message_id || data.assistant_message?.id,
        role: "assistant",
        content: data.response ?? "No response returned.",
        risk: data.state?.risk_level as string | undefined,
        agent: data.state?.selected_agent as string | undefined,
        routingReason: (data.state?.tool_request as { agent_routing?: { reason?: string } } | undefined)?.agent_routing?.reason,
        approvalId: data.state?.approval_id as string | undefined,
        relatedMessages: data.state?.related_messages as RelatedChatMessage[] | undefined,
        operatorPlan: data.state?.operator_plan as Message["operatorPlan"],
      };
      setMessages((prev) => [...prev, assistantMessage]);
      if (data.session?.id) {
        setCurrentSessionId(data.session.id);
        currentSessionRef.current = data.session.id;
      }
      if (data.state?.selected_agent) setAgentStatus(`${data.state.selected_agent} / ${data.state.risk_level}`);
      if (data.state?.approval_required) refreshApprovals();
      setLiveStatus(data.state?.approval_required ? "Approval needed" : "Done");
      refreshChatSessions();
      connectSocket();
      finishAssistantTurn();
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          agent: "Kattappa AI",
          content: "Backend is offline. Start Kattappa, then send again.",
        },
      ]);
      finishAssistantTurn();
    }
  };

  const acknowledgeVoiceWake = () => {
    setMessages((prev) => [
      ...prev,
      {
        role: "assistant",
        agent: "Kattappa AI",
        content: "Yes, I am listening. Say the work after Kattappa, Mama, or Kittu.",
      },
    ]);
  };

  const showVoiceNotice = (content: string) => {
    const status = compactVoiceStatus(content);
    setLiveStatus(status);
    setAgentStatus(status);
  };

  const handleApprovalContinuation = async (
    approvalId: string,
    continuation?: ApprovalContinuationResult,
  ) => {
    const data = continuation ?? await continueApprovedWork(approvalId);
    const kind = data.kind ?? "approval";
    setLiveStatus(data.status === "completed" ? "Done" : compactLiveStatus(`${kind}: ${data.status}`));
    if (kind === "install_job") {
      setInstallResult(data as unknown as InstallResult);
    }
    if (kind === "chat" && data.status === "completed") {
      const state = data.state ?? {};
      const assistantMessage: Message = {
        id: data.assistant_message_id || data.assistant_message?.id,
        role: "assistant",
        content: data.response || "The approved task completed.",
        risk: state.risk_level as string | undefined,
        agent: state.selected_agent as string | undefined,
        routingReason: (state.tool_request as { agent_routing?: { reason?: string } } | undefined)?.agent_routing?.reason,
        approvalId: state.approval_id as string | undefined,
        relatedMessages: state.related_messages as RelatedChatMessage[] | undefined,
        operatorPlan: state.operator_plan as Message["operatorPlan"],
      };
      setMessages((prev) => [...prev, assistantMessage]);
      if (state.selected_agent) setAgentStatus(`${state.selected_agent} / ${state.risk_level}`);
      if (state.approval_required) refreshApprovals();
    } else {
      setMessages((prev) => [
        ...prev,
        {
          role: "system",
          content: approvalContinuationMessage(data),
        },
      ]);
    }
    refreshChatSessions();
    refreshApprovals();
    return !["approval_missing", "rejected", "waiting_for_approval"].includes(data.status);
  };

  const rateResponse = async (message: Message, rating: 1 | -1) => {
    setMessages((prev) =>
      prev.map((item) =>
        (message.id ? item.id === message.id : item === message)
          ? { ...item, rating }
          : item,
      ),
    );
    if (!message.id) return;
    try {
      const stored = await rateChatMessage(message.id, rating);
      const updated = storedMessageToChat(stored);
      setMessages((prev) =>
        prev.map((item) => (item.id === stored.id ? { ...item, ...updated } : item)),
      );
      refreshChatSessions();
    } catch {
      setLiveStatus("Rating not saved");
    }
  };

  const decideApproval = async (approvalId: string, status: "approved" | "rejected") => {
    setDecidingApprovals((current) => [...current, approvalId]);
    setApprovals((current) => current.filter((approval) => approval.id !== approvalId));
    try {
      const decisionData = await decideApprovalRequest(approvalId, status);
      if (status === "approved") {
        setLiveStatus("Continuing");
        setApprovalNotice({
          tone: "working",
          title: "Approved",
          message: "Continuing.",
        });
        const followUpRan = await handleApprovalContinuation(approvalId, decisionData.continuation);
        setApprovalNotice({
          tone: "ready",
          title: followUpRan ? "Continued" : "Approved",
          message: followUpRan ? "Done." : "No follow-up attached.",
        });
      } else {
        setLiveStatus("Rejected");
        setApprovalNotice({
          tone: "danger",
          title: "Rejected",
          message: "Stopped.",
        });
      }
    } catch {
      setLiveStatus("Approval failed");
      setApprovalNotice({
        tone: "danger",
        title: "Failed",
        message: "Follow-up did not complete.",
      });
    } finally {
      setDecidingApprovals((current) => current.filter((id) => id !== approvalId));
      refreshApprovals();
      refreshHealth();
    }
  };

  const visibleApprovals = approvals.filter((approval) => !decidingApprovals.includes(approval.id));
  const activeApproval = visibleApprovals[0];
  const showRightPanel = activePanel !== "Chat" || Boolean(activeApproval || approvalNotice);

  return (
    <div className={showRightPanel ? "app" : "app chatOnly"}>
      <Sidebar
        panels={PANELS}
        activePanel={activePanel}
        connected={connected}
        onOpenChat={openChat}
        onSelectPanel={setActivePanel}
      />

      <main className={activePanel === "Chat" ? "chat" : "chat panelMain"}>
        {activePanel === "Chat" ? (
          <ChatPanel
            messages={messages}
            input={input}
            messagesEndRef={messagesEndRef}
            onInputChange={setInput}
            onSendMessage={sendMessage}
            onRateResponse={rateResponse}
            onVoiceCommand={sendMessageText}
            onVoiceWake={acknowledgeVoiceWake}
            onVoiceNotice={showVoiceNotice}
            isWorking={assistantWorking}
            queuedCount={queuedCount}
            liveStatus={liveStatus}
            currentTask={currentTask}
            queuedTurns={queuedTurns}
          />
        ) : (
          <PanelContent
            activePanel={activePanel}
            health={health}
            freeStack={freeStack}
            sourcePolicy={sourcePolicy}
            toolScout={toolScout}
            toolAdoptions={toolAdoptions}
            clusterStatus={clusterStatus}
            clusterDraft={clusterDraft}
            clusterDiscoveryDraft={clusterDiscoveryDraft}
            clusterRouteDraft={clusterRouteDraft}
            clusterRouteResult={clusterRouteResult}
            clusterError={clusterError}
            capabilityLadder={capabilityLadder}
            improvements={improvements}
            skills={skills}
            reflections={reflections}
            evolutionCycle={evolutionCycle}
            evolutionRunning={evolutionRunning}
            builderProfile={builderProfile}
            codexParity={codexParity}
            projectEcosystem={projectEcosystem}
            projectIndex={projectIndex}
            resumeResult={resumeResult}
            installResult={installResult}
            longTasks={longTasks}
            taskDraft={taskDraft}
            writingDraft={writingDraft}
            writingResult={writingResult}
            researchDraft={researchDraft}
            researchResult={researchResult}
            simulationDraft={simulationDraft}
            simulationResult={simulationResult}
            agentStatus={agentStatus}
            onTaskDraftChange={setTaskDraft}
            onWritingDraftChange={setWritingDraft}
            onResearchDraftChange={setResearchDraft}
            onSimulationDraftChange={setSimulationDraft}
            onRefreshHealth={refreshHealth}
            onRefreshLongTasks={refreshLongTasks}
            onCreateLongTask={createLongTask}
            onUpdateLongTask={updateLongTask}
            onContinueLongTask={continueLongTask}
            onPlanLongTaskResume={planLongTaskResume}
            onCheckWriting={runWritingCheck}
            onRewriteWriting={runWritingRewrite}
            onExtractResearch={runResearchExtract}
            onRunSimulation={runScenarioSimulation}
            onRequestMissingInstalls={requestMissingInstalls}
            onRunManualToolScout={runManualToolScout}
            onStartToolAdoption={startToolAdoption}
            onClusterDraftChange={setClusterDraft}
            onClusterDiscoveryDraftChange={setClusterDiscoveryDraft}
            onClusterRouteDraftChange={setClusterRouteDraft}
            onRefreshCluster={refreshCluster}
            onRegisterClusterWorker={registerClusterWorker}
            onDeleteClusterWorker={deleteClusterWorker}
            onRegisterClusterDiscoveryTarget={registerClusterDiscoveryTarget}
            onDeleteClusterDiscoveryTarget={deleteClusterDiscoveryTarget}
            onRunClusterRoute={runClusterRoute}
            onRunSelfEvolution={runSelfEvolutionCycle}
            onSetSkillTrust={setSkillTrust}
          />
        )}
      </main>

      {showRightPanel && (
        <RightPanel
          agentStatus={agentStatus}
          health={health}
          freeStack={freeStack}
          capabilityLadder={capabilityLadder}
          activeApproval={activeApproval}
          approvalNotice={approvalNotice}
          onDecideApproval={decideApproval}
        />
      )}
      {latestVisualGuidance && (
        <DesktopGuidanceOverlay
          guidance={latestVisualGuidance}
          autoHideMs={VISUAL_GUIDANCE_AUTO_HIDE_MS}
        />
      )}
      {!launchComplete && (
        <div className="launchOverlay" role="status" aria-live="polite">
          <div className="launchPanel">
            <img src="/kattappa-logo.svg" alt="Kattappa AI OS" />
            <h2>Kattappa AI OS</h2>
            <p>{launchStatus}<span className="loadingDots"><span>.</span><span>.</span><span>.</span></span></p>
            <div className="launchBar">
              <span style={{ width: `${launchProgress}%` }} />
            </div>
            <strong>{launchProgress}%</strong>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
