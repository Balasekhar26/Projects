export type Message = {
  id?: string;
  role: "user" | "assistant" | "system" | "progress";
  content: string;
  risk?: string;
  agent?: string;
  routingReason?: string;
  approvalId?: string;
  rating?: 1 | -1;
  metadata?: Record<string, unknown>;
  relatedMessages?: RelatedChatMessage[];
  operatorPlan?: OperatorPlan;
};

export type RelatedChatMessage = {
  id: string;
  session_id: string;
  session_title: string;
  role: string;
  content: string;
  agent: string;
  risk: string;
  created_at: string;
  matched_terms: string[];
  score: number;
};

export type ChatSession = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type StoredMessage = {
  id: string;
  session_id: string;
  role: "user" | "assistant" | "system" | "progress";
  content: string;
  agent: string;
  risk: string;
  metadata: string;
  created_at: string;
};

export type LongTask = {
  id: string;
  title: string;
  goal: string;
  status: string;
  priority: string;
  progress: string;
  next_step: string;
  source_session_id: string;
  created_at: string;
  updated_at: string;
};

export type OperatorPlan = {
  execution_path: string;
  intent: string;
  agent: string;
  goal: string;
  local_only: boolean;
  free_stack: string[];
  action_required: boolean;
  needs_approval: boolean;
  approval_policy: string;
  next_steps: string[];
  memory_used: boolean;
  screen_context_available: boolean;
  visual_guidance?: VisualGuidance;
};

export type VisualGuidance = {
  enabled: boolean;
  execution_path?: string;
  kind?: string;
  requires_approval?: boolean;
  matched_screen_text?: boolean;
  target?: {
    label: string;
    x: number;
    y: number;
    width: number;
    height: number;
    confidence: number;
    source: string;
  };
  instruction?: string;
  safety_note?: string;
  reason?: string;
};

export type Approval = {
  id: string;
  action: string;
  risk: string;
  status: string;
  created_at: string;
  continuation_type?: string;
  continuation_payload?: string;
  continued_at?: string;
  continuation_result?: string;
};

export type ApprovalContinuationResult = {
  kind?: string;
  status: string;
  approval?: Approval;
  message?: string;
  response?: string;
  state?: Record<string, unknown>;
  assistant_message?: StoredMessage;
  assistant_message_id?: string;
  previous_result?: unknown;
  results?: unknown[];
  manual_steps?: string[];
  job?: Record<string, unknown>;
  report?: Record<string, unknown>;
  improvement?: Record<string, unknown>;
  skill?: Record<string, unknown>;
  publish?: Record<string, unknown>;
};

export type Health = {
  ollama_ok: boolean;
  ollama_message: string;
  models: string[];
  memory_count: number;
  workspace: string;
};

export type ClusterNode = {
  id: string;
  name: string;
  base_url: string;
  capabilities: Record<string, unknown>;
  runnable_tasks: string[];
  trusted: boolean;
  token_configured: boolean;
  created_at?: string;
  updated_at?: string;
};

export type ClusterDiscoveryTarget = {
  id: string;
  name: string;
  base_url: string;
  trusted: boolean;
  token_required: boolean;
  created_at?: string;
  updated_at?: string;
};

export type ClusterStatus = {
  mode: string;
  enabled: boolean;
  local_node: Record<string, unknown>;
  local_runnable_tasks: string[];
  paired_nodes: ClusterNode[];
  discovery_targets: ClusterDiscoveryTarget[];
  public_worker: {
    enabled: boolean;
    mode: string;
    accepts_task_content_in_bid: boolean;
    runnable_public_tasks: string[];
    profile: Record<string, unknown>;
    cleanup_policy: Record<string, boolean>;
  };
  broker: {
    mode: string;
    broadcast_scope: string;
    transport: string;
    internet_ready: boolean;
  };
  privacy_contract: Record<string, boolean>;
};

export type ClusterRouteResult = {
  status: string;
  run_location: string;
  task_kind?: string;
  message?: string;
  local_node?: Record<string, unknown>;
  paired_nodes?: ClusterNode[];
  worker?: Record<string, unknown>;
  selected_bid?: Record<string, unknown>;
  bid_round?: {
    bid_id?: string;
    task_kind?: string;
    broadcast_scope?: string;
    bids?: Record<string, unknown>[];
    unavailable?: Record<string, unknown>[];
  };
  worker_result?: Record<string, unknown>;
  privacy_contract?: Record<string, unknown>;
};

export type VoicePipelineStatus = {
  mode: string;
  primary_path: string;
  browser_speech_primary: boolean;
  wake_names: string[];
  wake: {
    engine: string;
    installed: boolean;
    custom_models: string[];
    custom_models_configured: boolean;
    threshold: number;
    fallback_engine: string;
    primary_decision: string;
    status: string;
  };
  stt: {
    engine: string;
    installed: boolean;
    status: string;
    fallback: string;
  };
  tts: {
    preferred_engine: string;
    piper_installed: boolean;
    piper_command: string;
    piper_model: string;
    piper_model_configured: boolean;
    primary_decision: string;
    active_fallback: string;
    available: boolean;
  };
  profile: {
    id: string;
    name: string;
    style: string;
    primary_spoken_language?: string;
    secondary_spoken_language?: string;
    text_output_language?: string;
    policy: string;
  };
  language_contract: {
    primary_spoken_language: string;
    secondary_spoken_language: string;
    text_output_language: string;
    voice_prompt_policy: string;
    assistant_response_policy: string;
  };
  safe_fallback: string;
};

export type VoiceProcessResult = {
  ok: boolean;
  reason: string;
  pipeline: VoicePipelineStatus;
  transcript: string;
  wake_engine: string;
  wake_result: {
    engine: string;
    used: boolean;
    detected: boolean;
    wake_name: string;
    score: number;
    scores: Record<string, number>;
    threshold: number;
    reason: string;
  };
  wake_detected: boolean;
  wake_name: string;
  command: string;
};

export type FreeCapability = {
  key: string;
  name: string;
  role: string;
  installed: boolean;
  status: string;
  install_hint: string;
  actual_installed?: boolean;
  fallback_available?: boolean;
  required?: boolean;
  usable?: boolean;
  fallback?: string;
};

export type FreeStack = {
  mode: string;
  approval_required_for_actions: boolean;
  desktop_control_enabled: boolean;
  shell_enabled: boolean;
  capabilities: FreeCapability[];
  free_tool_decisions?: FreeToolDecisionReport;
  models: {
    installed: string[];
    recommended: Record<string, string>;
    missing_recommended: string[];
  };
  ready_count: number;
  installed_count?: number;
  fallback_count?: number;
  missing_count?: number;
  usable_count?: number;
  total_count: number;
  next_best_steps: string[];
  source_first?: SourcePolicy;
};

export type FreeToolDecisionReport = {
  mode: string;
  allowed_now: string[];
  optional_labs: string[];
  blocked: string[];
  rule: string;
};

export type SourcePolicy = {
  mode: string;
  summary: string;
  rules: string[];
  hard_no: string[];
};

export type ToolScoutReport = {
  id: string;
  task: string;
  capability: string;
  recommendation: string;
  source: string;
  license_note: string;
  build_own_plan: string;
  status: string;
  improvement_id: string;
  created_at: string;
};

export type ToolScoutStatus = {
  mode: string;
  copying_rule: string;
  reports: ToolScoutReport[];
  catalog: { capability: string; tool: string; source: string; license_note: string }[];
};

export type ToolAdoptionJob = {
  id: string;
  report_id: string;
  install_approval_id: string;
  final_approval_id: string;
  status: string;
  install_observation: string;
  build_own_result: string;
  test_result: string;
  created_at: string;
  updated_at: string;
};

export type CapabilityLevel = {
  key: string;
  name: string;
  description: string;
  status: string;
  score: number;
  evidence: string;
  next_step: string;
};

export type CapabilityLadder = {
  label: string;
  truth_boundary: string;
  maturity_percent: number;
  fully_free_only: boolean;
  levels: CapabilityLevel[];
  next_actions: string[];
};

export type Improvement = {
  id: string;
  title: string;
  motive: string;
  proposal: string;
  risk: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type Skill = {
  id: string;
  name: string;
  trigger: string;
  steps: string;
  tools: string;
  risk: string;
  trust: string;
  success_count: number;
  failure_count: number;
  last_reflection: string;
  created_at: string;
  updated_at: string;
};

export type Reflection = {
  id: string;
  task: string;
  outcome: string;
  lesson: string;
  skill_id?: string | null;
  created_at: string;
};

export type EvolutionCycle = {
  reflections_scanned: number;
  draft_skills_created: { skill_id: string; approval_id: string; trigger: string }[];
  next_step: string;
};

export type BuilderProfile = {
  name: string;
  truth_boundary: string;
  capabilities: string[];
  protocol: { name: string; description: string }[];
  local_builder_analytics?: LocalBuilderAnalytics;
  codex_parity?: CodexParityReport;
  free_replacements_from_references?: FreeReferenceReplacement[];
};

export type CodexParityItem = {
  key: string;
  codex_can: string;
  kattappa_equivalent: string;
  status: string;
  status_label: string;
  score: number;
  evidence: string;
  files: string[];
  next_move: string;
  free_local_rule: string;
};

export type CodexParityReport = {
  name: string;
  truth_boundary: string;
  parity_percent: number;
  fully_free_only: boolean;
  local_first: boolean;
  memory_count: number;
  items: CodexParityItem[];
  strongest_gaps: CodexParityItem[];
  next_builds: string[];
  user_order_contract: string[];
};

export type LocalBuilderAnalytics = {
  mode: string;
  cost: string;
  privacy_boundary: string;
  inspired_by: string[];
  blocked_core_dependencies: string[];
  archetype: string;
  dimensions: {
    key: string;
    label: string;
    score: number;
    evidence: string;
  }[];
  growth_edges: string[];
  repo_activity: {
    changed_files: number;
    recent_commits_30d: number;
    has_dirty_worktree: boolean;
  };
  projects: {
    id: string;
    name: string;
    path: string;
    exists: boolean;
    files_scanned: number;
    signals: Record<string, number>;
    strengths: string[];
    next_local_moves: string[];
  }[];
  free_replacements: FreeReferenceReplacement[];
};

export type FreeReferenceReplacement = {
  source: string;
  not_added_reason: string;
  fully_free_replacement: string;
  added_to: string;
  why_it_improves_products: string;
};

export type EcosystemProject = {
  rank: number;
  id: string;
  name: string;
  motive: string;
  priority_reason: string;
  next_build: string;
  integration_role: string;
  safety_boundary: string;
  free_tools?: string[];
  path: string;
  exists: boolean;
  status: string;
};

export type ProjectEcosystem = {
  strategy: string;
  build_first: string;
  free_tool_rule?: string;
  projects: EcosystemProject[];
};

export type ProjectIndex = {
  root: string;
  files_indexed: number;
  summary: string;
  languages: { name: string; count: number }[];
  roles: { name: string; count: number }[];
  important_files: { path: string; role: string; exists: boolean }[];
  scripts: { name: string; command: string; cwd: string }[];
};

export type ResumeResult = {
  task: LongTask;
  next_steps: string[];
  project_hits: { path: string; role: string; language: string }[];
  resume_prompt: string;
};

export type InstallResult = {
  status: string;
  message?: string;
  approval_id?: string;
  manual_steps?: string[];
  results?: { label: string; status: string; message?: string; returncode?: number }[];
  plan?: {
    summary: string;
    steps: { label: string; command: string[] }[];
    manual_steps: string[];
  };
};

export type WritingResult = {
  engine: string;
  issue_count?: number;
  corrected_text?: string;
  rewritten_text?: string;
  grammar?: { corrected_text: string; issue_count: number };
  note?: string;
};

export type ResearchResult = Record<string, unknown>;

export type SimulationResult = {
  engine: string;
  scenario: { seed: string; horizon: string; assumptions: string[]; actors: string[]; unknowns: string[] };
  predictions: { outcome: string; signal: string; confidence: string }[];
  warning: string;
};

export type OhlcvCandle = {
  timestamp?: string | null;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  amount?: number | null;
};

export type FinanceForecastRequest = {
  candles: OhlcvCandle[];
  horizon: number;
  use_kronos: boolean;
};

export type FinanceCsvForecastRequest = {
  path: string;
  horizon: number;
  use_kronos: boolean;
};

export type KronosStatus = {
  installed: boolean;
  status?: string;
  fallback_available?: boolean;
  fallback_engine?: string;
  path: string;
  license: string;
  imports: Record<string, boolean>;
  ready_for_real_kronos: boolean;
  default_tokenizer: string;
  default_model: string;
  first_real_run_note: string;
};

export type FinanceForecastResult = {
  engine: string;
  input_candles: number;
  predictions: OhlcvCandle[];
  summary: {
    last_close: number;
    final_predicted_close: number;
    predicted_change_percent: number;
    trend_signal: string;
    volatility: string;
    confidence: string;
  };
  risk_warning: string;
  kronos_error?: string;
};

export type FinanceComparisonResult = {
  mode: string;
  input_candles: number;
  horizon: number;
  kronos_status: KronosStatus;
  baseline: FinanceForecastResult;
  kronos: FinanceForecastResult | null;
  fallback_after_kronos_error: FinanceForecastResult | null;
  kronos_error?: string | null;
  risk_warning: string;
};

export type PlatformFeature = {
  feature: string;
  status: string;
  adapter: string;
  setup_hint: string;
  notes: string;
  installed?: boolean;
  fallback_available?: boolean;
  required?: boolean;
  usable?: boolean;
};

export type PlatformSupport = {
  os: {
    system: string;
    release: string;
    machine: string;
    python: string;
  };
  commands: Record<string, boolean>;
  features: PlatformFeature[];
  promise: string;
};

export type HardwareTier = {
  tier: string;
  name: string;
  cpu: string;
  ram: string;
  gpu: string;
  vram: string;
  storage: string;
  models: string[];
  good_for: string[];
  limits: string[];
};

export type HardwareRequirements = {
  system: {
    platform: string;
    processor: string;
    cpu_count_logical?: number | null;
    cpu_count_physical?: number | null;
    ram_total_gb?: number | null;
    inspection_error?: string;
  };
  configured_models: Record<string, string>;
  tiers: HardwareTier[];
  buying_guide?: {
    tier: string;
    laptop: string;
    desktop: string;
    best_for: string;
    avoid: string;
  }[];
  recommendation: string;
  notes: string[];
};

export type DashboardData = {
  health: Health;
  freeStack: FreeStack;
  capabilityLadder: CapabilityLadder;
  improvements: Improvement[];
  skills: Skill[];
  reflections: Reflection[];
  builderProfile: BuilderProfile;
  codexParity: CodexParityReport;
  projectEcosystem: ProjectEcosystem;
  sourcePolicy: SourcePolicy;
  projectIndex: ProjectIndex;
  toolScout: ToolScoutStatus;
  toolAdoptions: ToolAdoptionJob[];
};
