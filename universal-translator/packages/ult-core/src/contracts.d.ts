export declare const SESSION_KINDS: Readonly<{
  DESKTOP_RUNTIME: "desktop_runtime";
  ANDROID_RUNTIME: "android_runtime";
  BROWSER_DEBUG: "browser_debug";
  MICROPHONE: "microphone";
  SYSTEM: "system";
}>;

export declare const ONLINE_POLICIES: Readonly<{
  AUTO: "auto";
  ONLINE_ONLY: "online-only";
  OFFLINE_ONLY: "offline-only";
}>;

export declare const SESSION_EVENT_TYPES: Readonly<{
  STATUS: "status";
  ROUTING_STATE: "routing_state";
  PARTIAL_TRANSCRIPT: "partial_transcript";
  PARTIAL_TRANSLATION: "partial_translation";
  FINAL_TRANSLATION: "final_translation";
  TTS_STARTED: "tts_started";
  TTS_FINISHED: "tts_finished";
  LATENCY_SAMPLE: "latency_sample";
  ERROR: "error";
  SNAPSHOT: "snapshot";
  HEALTH: "health";
}>;

export type SessionKind = (typeof SESSION_KINDS)[keyof typeof SESSION_KINDS];
export type OnlinePolicy = (typeof ONLINE_POLICIES)[keyof typeof ONLINE_POLICIES];
export type SessionEventType = (typeof SESSION_EVENT_TYPES)[keyof typeof SESSION_EVENT_TYPES];

export type StartSessionRequest = {
  platform: string;
  sourceLanguage: string;
  autoDetectSource: boolean;
  targetLanguage: string;
  sessionKind: SessionKind;
  inputDeviceId: string;
  outputDeviceId: string;
  micInputDeviceId: string;
  speakerOutputDeviceId: string;
  micTargetLanguage: string;
  speakerTargetLanguage: string;
  routeProfileId: string;
  onlinePolicy: OnlinePolicy;
  voiceProfileId: string;
  preserveEmotion: boolean;
};

export type SessionEvent = {
  type: SessionEventType | string;
  timestamp: string;
  [key: string]: unknown;
};

export declare function createStartSessionRequest(
  overrides?: Partial<StartSessionRequest>
): StartSessionRequest;

export declare function normalizeStartSessionRequest(
  input?: Partial<StartSessionRequest>
): StartSessionRequest;

export declare function createSessionEvent(
  type: SessionEventType | string,
  payload?: Record<string, unknown>
): SessionEvent;
