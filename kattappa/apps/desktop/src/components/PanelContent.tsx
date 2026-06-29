import type {
  BuilderProfile,
  CapabilityLadder,
  ClusterRouteResult,
  ClusterStatus,
  CodexParityReport,
  FreeStack,
  Health,
  Improvement,
  InstallResult,
  LongTask,
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
  WritingResult,
} from "../types";
import { SystemDiagnostics } from "./SystemDiagnostics";
import { MemoryPanel } from "./MemoryPanel";
import { TasksPanel } from "./TasksPanel";
import { WritingPanel } from "./WritingPanel";
import { ResearchPanel } from "./ResearchPanel";
import { SimulationPanel } from "./SimulationPanel";
import { ToolsPanel } from "./ToolsPanel";
import { ClusterPanel } from "./ClusterPanel";
import { AgentsPanel } from "./AgentsPanel";
import { SettingsPanel } from "./SettingsPanel";
import { ProjectsPanel } from "./ProjectsPanel";
import { WorkspacePanel } from "./WorkspacePanel";

export type PanelContentProps = {
  activePanel: string;
  health: Health | null;
  freeStack: FreeStack | null;
  sourcePolicy: SourcePolicy | null;
  toolScout: ToolScoutStatus | null;
  toolAdoptions: ToolAdoptionJob[];
  clusterStatus: ClusterStatus | null;
  clusterDraft: { name: string; base_url: string; token: string; capabilities: string };
  clusterDiscoveryDraft: { name: string; base_url: string };
  clusterRouteDraft: { message: string; task_kind: string; sensitivity: string; force_remote: boolean };
  clusterRouteResult: ClusterRouteResult | null;
  clusterError: string;
  capabilityLadder: CapabilityLadder | null;
  improvements: Improvement[];
  skills: Skill[];
  reflections: Reflection[];
  evolutionCycle: { reflections_scanned: number; draft_skills_created: { skill_id: string; approval_id: string; trigger: string }[]; next_step: string } | null;
  evolutionRunning: boolean;
  builderProfile: BuilderProfile | null;
  codexParity: CodexParityReport | null;
  projectEcosystem: ProjectEcosystem | null;
  projectIndex: ProjectIndex | null;
  resumeResult: ResumeResult | null;
  installResult: InstallResult | null;
  longTasks: LongTask[];
  taskDraft: { title: string; goal: string; priority: string };
  writingDraft: { text: string; tone: string };
  writingResult: WritingResult | null;
  researchDraft: { url: string; goal: string };
  researchResult: ResearchResult | null;
  simulationDraft: { seed: string; horizon: string };
  simulationResult: SimulationResult | null;
  agentStatus: string;
  onTaskDraftChange: (draft: { title: string; goal: string; priority: string }) => void;
  onWritingDraftChange: (draft: { text: string; tone: string }) => void;
  onResearchDraftChange: (draft: { url: string; goal: string }) => void;
  onSimulationDraftChange: (draft: { seed: string; horizon: string }) => void;
  onRefreshHealth: () => void;
  onRefreshLongTasks: () => void;
  onCreateLongTask: () => void;
  onUpdateLongTask: (taskId: string, update: Partial<Pick<LongTask, "status" | "progress" | "next_step">>) => void;
  onContinueLongTask: (task: LongTask) => void;
  onPlanLongTaskResume: (task: LongTask) => void;
  onCheckWriting: () => void;
  onRewriteWriting: () => void;
  onExtractResearch: () => void;
  onRunSimulation: () => void;
  onRequestMissingInstalls: () => void;
  onRunManualToolScout: () => void;
  onStartToolAdoption: (reportId: string) => void;
  onClusterDraftChange: (draft: { name: string; base_url: string; token: string; capabilities: string }) => void;
  onClusterDiscoveryDraftChange: (draft: { name: string; base_url: string }) => void;
  onClusterRouteDraftChange: (draft: { message: string; task_kind: string; sensitivity: string; force_remote: boolean }) => void;
  onRefreshCluster: () => void;
  onRegisterClusterWorker: () => void;
  onDeleteClusterWorker: (nodeId: string) => void;
  onRegisterClusterDiscoveryTarget: () => void;
  onDeleteClusterDiscoveryTarget: (targetId: string) => void;
  onRunClusterRoute: () => void;
  onRunSelfEvolution: () => void;
  onSetSkillTrust: (skillId: string, trust: "draft" | "approved" | "trusted" | "disabled") => void;
};

export function PanelContent(props: PanelContentProps) {
  switch (props.activePanel) {
    case "Diagnostics":
      return (
        <SystemDiagnostics
          health={props.health}
          freeStack={props.freeStack}
          capabilityLadder={props.capabilityLadder}
          improvements={props.improvements}
          reflections={props.reflections}
          sourcePolicy={props.sourcePolicy}
        />
      );
    case "Memory":
      return <MemoryPanel health={props.health} onRefreshHealth={props.onRefreshHealth} />;
    case "Tasks":
      return <TasksPanel {...props} />;
    case "Writing":
      return <WritingPanel {...props} />;
    case "Research":
      return <ResearchPanel {...props} />;
    case "Simulation":
      return <SimulationPanel {...props} />;
    case "Tools":
      return <ToolsPanel {...props} />;
    case "Cluster":
      return <ClusterPanel {...props} />;
    case "Agents":
      return <AgentsPanel {...props} />;
    case "Settings":
      return <SettingsPanel {...props} />;
    case "Projects":
      return <ProjectsPanel {...props} />;
    case "Workspaces":
      return <WorkspacePanel />;
    default:
      return (
        <SystemDiagnostics
          health={props.health}
          freeStack={props.freeStack}
          capabilityLadder={props.capabilityLadder}
          improvements={props.improvements}
          reflections={props.reflections}
          sourcePolicy={props.sourcePolicy}
        />
      );
  }
}
