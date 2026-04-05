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
