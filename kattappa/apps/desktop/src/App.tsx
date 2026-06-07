import { useEffect, useMemo, useRef, useState } from "react";
import { ChatPanel } from "./components/ChatPanel";
import { DesktopGuidanceOverlay } from "./components/DesktopGuidanceOverlay";
import { PanelContent } from "./components/PanelContent";
import { RightPanel } from "./components/RightPanel";
import { Sidebar } from "./components/Sidebar";
import {
  API_BASE_URL as API,
  checkWriting,
  continueToolAdoptionForApproval,
  createChatSession,
  createLongTask as createLongTaskRequest,
  decideApproval as decideApprovalRequest,
  extractResearch,
  fetchApprovals,
  fetchChatSessionMessages,
  fetchChatSessions,
  fetchDashboardData,
  fetchLongTasks,
  requestMissingInstalls as requestMissingInstallsRequest,
  resumeLongTask,
  rewriteWriting,
  runApprovedInstallJob,
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
  BuilderProfile,
  CapabilityLadder,
  ChatSession,
  EvolutionCycle,
  FreeStack,
  Health,
  Improvement,
  InstallResult,
  LongTask,
  Message,
  OperatorMode,
  ProjectEcosystem,
  ProjectIndex,
  Reflection,
  ResearchResult,
  ResumeResult,
  SimulationResult,
  Skill,
  SourcePolicy,
  ToolAdoptionJob,
  ToolScoutStatus,
  VisualGuidance,
  WritingResult,
} from "./types";

type QueuedTurn = {
  text: string;
  operatorMode: OperatorMode;
};

const VISUAL_GUIDANCE_AUTO_HIDE_MS = 6500;

function App() {
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [activePanel, setActivePanel] = useState("Chat");
  const [input, setInput] = useState("");
  const [operatorMode, setOperatorMode] = useState<OperatorMode>("guide");
  const [connected, setConnected] = useState(false);
  const [agentStatus, setAgentStatus] = useState("Backend not connected");
  const [health, setHealth] = useState<Health | null>(null);
  const [freeStack, setFreeStack] = useState<FreeStack | null>(null);
  const [sourcePolicy, setSourcePolicy] = useState<SourcePolicy | null>(null);
  const [toolScout, setToolScout] = useState<ToolScoutStatus | null>(null);
  const [toolAdoptions, setToolAdoptions] = useState<ToolAdoptionJob[]>([]);
  const [capabilityLadder, setCapabilityLadder] = useState<CapabilityLadder | null>(null);
  const [improvements, setImprovements] = useState<Improvement[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [reflections, setReflections] = useState<Reflection[]>([]);
  const [evolutionCycle, setEvolutionCycle] = useState<EvolutionCycle | null>(null);
  const [evolutionRunning, setEvolutionRunning] = useState(false);
  const [builderProfile, setBuilderProfile] = useState<BuilderProfile | null>(null);
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

  const refreshHealth = async () => {
    try {
      const data = await fetchDashboardData();
      setHealth(data.health);
      setFreeStack(data.freeStack);
      setCapabilityLadder(data.capabilityLadder);
      setImprovements(data.improvements);
      setSkills(data.skills);
      setReflections(data.reflections);
      setBuilderProfile(data.builderProfile);
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
      setProjectEcosystem(null);
      setSourcePolicy(null);
      setProjectIndex(null);
      setToolScout(null);
      setToolAdoptions([]);
    }
  };

  const refreshChatSessions = async () => {
    try {
      setChatSessions(await fetchChatSessions());
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

  const createNewChat = async () => {
    setMessages(initialMessages());
    setActivePanel("Chat");
    try {
      const session = await createChatSession();
      setCurrentSessionId(session.id);
      currentSessionRef.current = session.id;
      await refreshChatSessions();
      return session.id;
    } catch {
      setCurrentSessionId(null);
      currentSessionRef.current = null;
      return null;
    }
  };

  const ensureChatSession = async () => currentSessionRef.current ?? createNewChat();

  const ensureMessageSession = async () => {
    if (currentSessionRef.current) return currentSessionRef.current;
    try {
      const session = await createChatSession();
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
    setMessages(
      stored.length
        ? stored.map((item) => ({
            role: item.role,
            content: item.content,
            agent: item.agent || undefined,
            risk: item.risk || undefined,
          }))
        : initialMessages(),
    );
    setActivePanel("Chat");
  };

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
        setLaunchStatus("Connecting workspace");
        setLaunchProgress((value) => Math.max(value, 70));
        await refreshHealth();
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
    };
    socket.onclose = () => {
      setConnected(false);
      setAgentStatus("Disconnected");
      if (assistantWorkingRef.current) {
        const message: Message = {
          role: "assistant",
          agent: "Kattappa AI",
          content: "The live connection dropped before the reply finished. I kept the chat usable and will continue with the next queued message.",
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
        const message: Message = {
          role: data.type === "assistant" ? "assistant" : data.type,
          content: data.content,
          risk: data.risk_level,
          agent: data.selected_agent,
          routingReason: data.routing?.reason,
          approvalId: data.approval_id,
          operatorPlan: data.operator_plan,
        };
        setMessages((prev) => [...prev, message]);
        persistChatMessage(currentSessionRef.current, message);
        if (data.selected_agent) setAgentStatus(`${data.selected_agent} / ${data.risk_level}`);
        if (data.approval_required) refreshApprovals();
        if (data.type === "assistant") finishAssistantTurn();
      } catch {
        const message: Message = { role: "assistant", content: event.data };
        setMessages((prev) => [...prev, message]);
        persistChatMessage(currentSessionRef.current, message);
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
    refreshHealth();
    refreshApprovals();
    refreshChatSessions();
    refreshLongTasks();
    const interval = window.setInterval(() => {
      refreshHealth();
      refreshApprovals();
      refreshChatSessions();
      refreshLongTasks();
    }, 5000);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    if (activePanel === "Chat") {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [messages, activePanel]);

  const latestVisualGuidanceItem = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const guidance = messages[index].operatorPlan?.visual_guidance;
      if (guidance?.enabled && guidance.target) {
        return {
          guidance,
          key: `${index}:${guidance.target.label}:${guidance.target.x}:${guidance.target.y}`,
        };
      }
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
        content: "This reply is taking too long, so I released the composer and kept any next messages queued. Send again if you want me to retry the last request.",
      };
      setMessages((prev) => [...prev, message]);
      persistChatMessage(currentSessionRef.current, message);
      finishAssistantTurn();
    }, 120000);
  };

  const finishAssistantTurn = () => {
    clearTurnTimeout();
    const next = messageQueueRef.current.shift();
    setQueuedCount(messageQueueRef.current.length);
    if (next) {
      window.setTimeout(() => {
        void sendMessageText(next.text, true, next.operatorMode);
      }, 150);
      return;
    }
    setWorking(false);
  };

  const sendMessage = async () => {
    await sendMessageText(input);
  };

  const sendMessageText = async (rawText: string, fromQueue = false, turnMode: OperatorMode = operatorMode) => {
    const text = rawText.trim();
    if (!text) return;
    if (assistantWorkingRef.current && !fromQueue) {
      messageQueueRef.current.push({ text, operatorMode: turnMode });
      setQueuedCount(messageQueueRef.current.length);
      setInput("");
      setMessages((prev) => [
        ...prev,
        {
          role: "system",
          content: `Queued message ${messageQueueRef.current.length}: ${text}`,
        },
      ]);
      return;
    }
    setWorking(true);
    startTurnTimeout();
    const userMessage: Message = { role: "user", content: text };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");

    const sessionId = await ensureMessageSession();
    if (sessionId) {
      persistChatMessage(sessionId, userMessage);
    }

    const routedText = `[operator mode: ${turnMode}]\n${text}`;
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(routedText);
      return;
    }

    setMessages((prev) => [...prev, { role: "progress", content: "WebSocket offline. Using HTTP chat fallback..." }]);
    try {
      const data = await sendChatMessage(routedText, sessionId ?? undefined);
      const assistantMessage: Message = {
        role: "assistant",
        content: data.response ?? "No response returned.",
        risk: data.state?.risk_level as string | undefined,
        agent: data.state?.selected_agent as string | undefined,
        routingReason: (data.state?.tool_request as { agent_routing?: { reason?: string } } | undefined)?.agent_routing?.reason,
        approvalId: data.state?.approval_id as string | undefined,
        operatorPlan: data.state?.operator_plan as Message["operatorPlan"],
      };
      setMessages((prev) => [...prev, assistantMessage]);
      persistChatMessage(sessionId, assistantMessage);
      if (data.state?.selected_agent) setAgentStatus(`${data.state.selected_agent} / ${data.state.risk_level}`);
      if (data.state?.approval_required) refreshApprovals();
      connectSocket();
      finishAssistantTurn();
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          agent: "Kattappa AI",
          content:
            "I am ready in the interface, but the local backend is not reachable yet. Start Kattappa AI OS with run.exe, then send the message again and I will route it through the local agent stack.",
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
    setMessages((prev) => [
      ...prev,
      {
        role: "system",
        content,
      },
    ]);
  };

  const decideApproval = async (approvalId: string, status: "approved" | "rejected") => {
    setDecidingApprovals((current) => [...current, approvalId]);
    setApprovals((current) => current.filter((approval) => approval.id !== approvalId));
    try {
      await decideApprovalRequest(approvalId, status);
      if (status === "approved") {
        setApprovalNotice({
          tone: "working",
          title: "Approved",
          message: "Approval accepted. The approved task is running or being checked now.",
        });
        const installData = await runApprovedInstallJob(approvalId);
        if (installData.status !== "not_install_job") {
          setInstallResult(installData);
          setMessages((prev) => [
            ...prev,
            { role: "system", content: `Install job ${installData.status}: ${approvalId}` },
          ]);
        }
        const adoptionData = await continueToolAdoptionForApproval(approvalId);
        if (adoptionData.status !== "not_tool_adoption_job") {
          setMessages((prev) => [
            ...prev,
            { role: "system", content: `Tool adoption ${adoptionData.status}: ${approvalId}` },
          ]);
        }
        setApprovalNotice({
          tone: "ready",
          title: "Completed",
          message: "The approved task finished or no install/adoption work was required.",
        });
      } else {
        setApprovalNotice({
          tone: "danger",
          title: "Rejected",
          message: "The task was rejected and nothing risky will run.",
        });
      }
      setMessages((prev) => [
        ...prev,
        { role: "system", content: `Approval ${status}: ${approvalId}` },
      ]);
    } catch {
      setApprovalNotice({
        tone: "danger",
        title: "Action Failed",
        message: "The approval decision was sent, but the follow-up task did not complete.",
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
        chatSessions={chatSessions}
        currentSessionId={currentSessionId}
        onCreateChat={createNewChat}
        onLoadChat={loadChatSession}
        onSelectPanel={setActivePanel}
      />

      <main className={activePanel === "Chat" ? "chat" : "chat panelMain"}>
        {activePanel === "Chat" ? (
          <ChatPanel
            messages={messages}
            input={input}
            operatorMode={operatorMode}
            messagesEndRef={messagesEndRef}
            onInputChange={setInput}
            onOperatorModeChange={setOperatorMode}
            onSendMessage={sendMessage}
            onVoiceCommand={sendMessageText}
            onVoiceWake={acknowledgeVoiceWake}
            onVoiceNotice={showVoiceNotice}
            isWorking={assistantWorking}
            queuedCount={queuedCount}
          />
        ) : (
          <PanelContent
            activePanel={activePanel}
            health={health}
            freeStack={freeStack}
            sourcePolicy={sourcePolicy}
            toolScout={toolScout}
            toolAdoptions={toolAdoptions}
            capabilityLadder={capabilityLadder}
            improvements={improvements}
            skills={skills}
            reflections={reflections}
            evolutionCycle={evolutionCycle}
            evolutionRunning={evolutionRunning}
            builderProfile={builderProfile}
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
            operatorMode={operatorMode}
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
            onRunSelfEvolution={runSelfEvolutionCycle}
            onSetSkillTrust={setSkillTrust}
            onOperatorModeChange={setOperatorMode}
          />
        )}
      </main>

      {showRightPanel && (
        <RightPanel
          operatorMode={operatorMode}
          onOperatorModeChange={setOperatorMode}
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
