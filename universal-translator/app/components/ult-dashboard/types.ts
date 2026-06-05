export type Device = {
  id: string;
  name: string;
};

export type RouteProfile = {
  id: string;
  label: string;
  sessionKind: string;
  status: string;
  requirements: string[];
};

export type VoiceProfile = {
  id: string;
  label: string;
  provider: string;
  kind: string;
};

export type RoutingOptions = {
  inputDevices: Device[];
  outputDevices: Device[];
  voices: Array<{ id: string; name: string }>;
  routeProfiles: RouteProfile[];
  defaultInputDeviceName: string;
  defaultOutputDeviceName: string;
  defaultVoiceName: string;
  defaultRouteProfileId: string;
};

export type ModelPack = {
  id: string;
  label: string;
  description: string;
  installState: string;
  transport: string;
};

export type BootstrapReport = {
  inspectedAt: string;
  hardware: {
    profileId: string;
    cpuCount: number;
    totalMemGb: number;
    gpu: {
      name: string;
      adapterRamGb: number;
    };
  };
  selfTest: {
    ok: boolean;
    checks: Array<{
      label: string;
      ok: boolean;
      path: string;
    }>;
  };
};

export type SessionEvent = {
  type: string;
  sessionId?: string;
  chunkNumber?: number;
  transcript?: string;
  translatedText?: string;
  backend?: string;
  detectedLanguage?: string;
  message?: string;
  latencyMs?: number;
  voiceProfileId?: string;
  events?: SessionEvent[];
};

export type FeedEntry = {
  id: string;
  transcript: string;
  translatedText: string;
  backend: string;
  detectedLanguage: string;
  latencyMs?: number;
};

export type DebugContribution = {
  id: string;
  contribution: number;
};

export type DebugEventRecord = {
  id: string;
  type: string;
  schemaVersion: "1.0";
  normalizationVersion: "v1";
  rawTime: number;
  sessionTime: number;
  normalizedTime: number;
  causalityKey: {
    sourceEventIds: string[];
    transformation: string;
    dependencyHash: string;
  };
  timing: {
    raw: {
      system?: number;
      stream?: number;
      utterance?: number;
      observer?: number;
      quota?: number | { readyAt?: number; delayMs?: number };
    };
    rebased: {
      system?: number;
      stream?: number;
      utterance?: number;
      observer?: number;
      quota?: number;
    };
    normalizationTrace: {
      mode?: string;
      denominator?: number;
      contributingDomains?: Array<{
        domain: string;
        rawTime: number;
        rebasedTime: number;
        baseWeight: number;
        confidence: number;
        effectiveWeight: number;
      }>;
      ignoredDomains?: Array<{
        domain: string;
        reason: string;
        baseWeight: number;
        confidence: number;
      }>;
    };
    skew: Record<string, number | undefined>;
    coherenceScore: number;
    flags: {
      normalizedTimeBackward: boolean;
      chunkNumber: number | null;
    };
  };
  weights: Record<string, number>;
  confidences: Record<string, number>;
  ignoredDomains: string[];
  ignoredDomainsDecision: Array<{
    domain: string;
    reason: string;
  }>;
  dominantDomain: string;
  contributions: Record<string, number>;
  flags: string[];
  integrityHash: string;
  decisionHash: string;
  timingHash: string;
  logicHash: string;
  createdAt: number;
};

export type IdentityBlock = {
  decisionHash: string;
  logicHash: string;
  startTime: number;
  endTime: number;
  dominantDomain: "system" | "observer";
  state: "balanced" | "dominant" | "degenerate" | "void";
  samples: number;
};

export type DominantDomain = "system" | "observer";

export type IdentityState = "balanced" | "dominant" | "degenerate" | "void";

export type BreakReason = "initial" | "decision-change" | "void-interruption" | "state-transition";

export type IdentityFracture = {
  time: number;
  state: IdentityState;
  reason: "state-transition";
};

export type StrictIdentityBlock =
  | { state: "void"; dominantDomain: null; decisionHash: string; logicHash: string; startTime: number; endTime: number; samples: number; startReason: BreakReason; fractures?: IdentityFracture[]; }
  | { state: "balanced"; dominantDomain: null; decisionHash: string; logicHash: string; startTime: number; endTime: number; samples: number; startReason: BreakReason; fractures?: IdentityFracture[]; }
  | { state: "dominant" | "degenerate"; dominantDomain: DominantDomain; decisionHash: string; logicHash: string; startTime: number; endTime: number; samples: number; startReason: BreakReason; fractures?: IdentityFracture[]; };

