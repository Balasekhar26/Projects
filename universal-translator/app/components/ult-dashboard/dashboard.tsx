"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { LANGUAGE_CATALOG } from "@/packages/ult-core/src/catalog/languages";
import { analyzePcmChunk, CHUNK_SAMPLE_TARGET, encodeWav, floatToPcmChunk, mergePcmChunks, SAMPLE_RATE } from "./audio";
import type {
  BootstrapReport,
  DebugEventRecord,
  FeedEntry,
  IdentityBlock,
  StrictIdentityBlock,
  BreakReason,
  RoutingOptions,
  SessionEvent,
  VoiceProfile,
} from "./types";
import { MiniStat, SectionTitle, SelectField, StatCard } from "./ui";

const EMPTY_ROUTING_OPTIONS: RoutingOptions = {
  inputDevices: [],
  outputDevices: [],
  voices: [],
  routeProfiles: [],
  defaultInputDeviceName: "",
  defaultOutputDeviceName: "",
  defaultVoiceName: "generic:offline-default",
  defaultRouteProfileId: "browser-debug",
};

async function fetchModelPackPayload(sourceLanguage: string, targetLanguage: string) {
  const response = await fetch(
    `/api/models?sourceLanguage=${encodeURIComponent(sourceLanguage)}&targetLanguage=${encodeURIComponent(targetLanguage)}`
  );
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload?.error || "Unable to load model packs.");
  }

  return Array.isArray(payload.packs) ? payload.packs : [];
}

export function Ultdashboard() {
  const [sourceLanguage, setSourceLanguage] = useState("en");
  const [targetLanguage, setTargetLanguage] = useState("te");
  const [sessionKind, setSessionKind] = useState("browser_debug");
  const [onlinePolicy, setOnlinePolicy] = useState("offline-only");
  const [routeProfileId, setRouteProfileId] = useState("browser-debug");
  const [inputDeviceId, setInputDeviceId] = useState("");
  const [outputDeviceId, setOutputDeviceId] = useState("");
  const [voiceProfileId, setVoiceProfileId] = useState("generic:offline-default");
  const [preserveEmotion, setPreserveEmotion] = useState(true);
  const [isStreaming, setIsStreaming] = useState(false);
  const [statusMessage, setStatusMessage] = useState("Idle");
  const [errorMessage, setErrorMessage] = useState("");
  const [feed, setFeed] = useState<FeedEntry[]>([]);
  const [routingOptions, setRoutingOptions] = useState<RoutingOptions>(EMPTY_ROUTING_OPTIONS);
  const [bootstrapReport, setBootstrapReport] = useState<BootstrapReport | null>(null);
  const [modelPacks, setModelPacks] = useState<Array<Record<string, string>>>([]);
  const [voiceProfiles, setVoiceProfiles] = useState<VoiceProfile[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [debugEvents, setDebugEvents] = useState<DebugEventRecord[]>([]);
  const [selectedDebugEventId, setSelectedDebugEventId] = useState<string | null>(null);
  const [selectedDebugEvent, setSelectedDebugEvent] = useState<DebugEventRecord | null>(null);
  const [debugLoading, setDebugLoading] = useState(false);

  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const processorNodeRef = useRef<ScriptProcessorNode | null>(null);
  const pcmQueueRef = useRef<Int16Array[]>([]);
  const sessionIdRef = useRef<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const uploadQueueRef = useRef(Promise.resolve());

  const selectedRouteProfile = useMemo(
    () => routingOptions.routeProfiles.find((profile) => profile.id === routeProfileId) || null,
    [routeProfileId, routingOptions.routeProfiles]
  );

  const [blockDetailsOpen, setBlockDetailsOpen] = useState(false);
  const [hoveredBlock, setHoveredBlock] = useState<StrictIdentityBlock | null>(null);
  const [testMode, setTestMode] = useState<string | null>(null);
  const [truthMode, setTruthMode] = useState<"truth" | "trace">("truth");

  const getBlockState = (event: DebugEventRecord): StrictIdentityBlock["state"] => {
    const system = Math.abs(event.contributions?.system || 0);
    const observer = Math.abs(event.contributions?.observer || 0);
    const primaryTotal = system + observer;
    if (primaryTotal < 1e-8) {
      return "void";
    }

    const ratio = Math.min(system, observer) / Math.max(system, observer);
    if (ratio < 1e-6) {
      return "degenerate";
    }
    if (ratio < 0.75) {
      return "dominant";
    }
    return "balanced";
  };

  const buildIdentityBlocks = (events: DebugEventRecord[]): StrictIdentityBlock[] => {
    const sortedEvents = [...events].sort((left, right) => {
      if (left.normalizedTime !== right.normalizedTime) {
        return left.normalizedTime - right.normalizedTime;
      }
      return left.sessionTime - right.sessionTime;
    });

    const blocks: StrictIdentityBlock[] = [];
    for (const event of sortedEvents) {
      const state = getBlockState(event);
      const dominantDomain: StrictIdentityBlock["dominantDomain"] =
        state === "void" || state === "balanced" ? null : (event.dominantDomain === "observer" ? "observer" : "system");

      let startReason: BreakReason = "initial";
      if (blocks.length > 0) {
        const prevBlock = blocks[blocks.length - 1];
        if (prevBlock.decisionHash !== event.decisionHash) {
          startReason = "decision-change";
        } else if (prevBlock.state === "void") {
          startReason = "void-interruption";
        } else if (prevBlock.state !== state) {
          prevBlock.fractures = prevBlock.fractures ?? [];
          const transitionTime = event.normalizedTime;
          prevBlock.fractures.push({
            time: transitionTime,
            state,
            reason: "state-transition",
          });
          prevBlock.endTime = transitionTime;
          prevBlock.samples += 1;
          continue;
        } else {
          // Same decisionHash and state, extend block
          prevBlock.endTime = event.normalizedTime;
          prevBlock.samples += 1;
          continue;
        }
      }

      const blockEvent: StrictIdentityBlock = {
        decisionHash: event.decisionHash,
        logicHash: event.logicHash,
        startTime: event.normalizedTime,
        endTime: event.normalizedTime,
        dominantDomain,
        state,
        samples: 1,
        startReason,
      } as StrictIdentityBlock;

      blocks.push(blockEvent);
    }

    return blocks;
  };

  const identityBlocks = useMemo(() => buildIdentityBlocks(debugEvents), [debugEvents]);

  const identityTimeRange = useMemo(() => {
    if (!identityBlocks.length) {
      return { min: 0, max: 1 };
    }

    const min = identityBlocks[0].startTime;
    const max = identityBlocks[identityBlocks.length - 1].endTime;
    return { min, max: max <= min ? min + 1 : max };
  }, [identityBlocks]);

  const identityScale = useMemo(() => {
    const range = identityTimeRange.max - identityTimeRange.min;
    return range < 1e-3 ? 1 : range;
  }, [identityTimeRange]);

  const colorByState = (state: StrictIdentityBlock["state"]) => {
    switch (state) {
      case "void":
        return "bg-slate-200/20 border border-slate-300/50"; // hollow/faded
      case "balanced":
        return "bg-slate-400/60 border border-slate-500/70"; // calm, low contrast
      case "dominant":
        return "bg-blue-500/90 border border-blue-400"; // clear, readable emphasis
      case "degenerate":
        return "bg-red-600/95 border-2 border-red-500"; // sharp, aggressive, finality
      default:
        return "bg-slate-500/80 border border-slate-600";
    }
  };

  const formatTime = (value: number) => `${value.toFixed(2)}s`;

  const createMockEvent = (
    id: string,
    time: number,
    decisionHash: string,
    system: number,
    observer: number,
    dominant: "system" | "observer"
  ): DebugEventRecord => ({
    id,
    type: "debug-event",
    schemaVersion: "1.0",
    normalizationVersion: "v1",
    rawTime: time,
    sessionTime: time,
    normalizedTime: time,
    causalityKey: {
      sourceEventIds: [],
      transformation: "test",
      dependencyHash: "test",
    },
    timing: {
      raw: { system, observer, stream: 0.1, utterance: 0.1, quota: 0.1 },
      rebased: { system, observer, stream: 0.1, utterance: 0.1, quota: 0.1 },
      normalizationTrace: {
        mode: "test",
        denominator: 1,
        contributingDomains: [],
        ignoredDomains: [],
      },
      skew: {},
      coherenceScore: 1.0,
      flags: {
        normalizedTimeBackward: false,
        chunkNumber: null,
      },
    },
    weights: {},
    confidences: {},
    ignoredDomains: [],
    ignoredDomainsDecision: [],
    dominantDomain: dominant,
    contributions: { system, observer },
    flags: [],
    integrityHash: "test",
    decisionHash,
    timingHash: "test",
    logicHash: decisionHash,
    createdAt: Date.now(),
  });

  const findRepresentativeEventId = (decisionHash: string) => {
    return debugEvents.find((event) => event.decisionHash === decisionHash)?.id || null;
  };

  const loadTest1 = () => {
    // A A A (A') A B B A A (A'') A C C C A
    // A' and A'' same hash but tiny drift
    const events: DebugEventRecord[] = [
      createMockEvent("1", 0.1, "A", 1.0, 0.5, "system"),
      createMockEvent("2", 0.2, "A", 1.0, 0.5, "system"),
      createMockEvent("3", 0.3, "A", 1.0, 0.5, "system"),
      createMockEvent("4", 0.4, "A", 1.0001, 0.5, "system"), // A' tiny drift
      createMockEvent("5", 0.5, "A", 1.0, 0.5, "system"),
      createMockEvent("6", 0.6, "B", 0.8, 0.3, "system"),
      createMockEvent("7", 0.7, "B", 0.8, 0.3, "system"),
      createMockEvent("8", 0.8, "A", 1.0, 0.5, "system"),
      createMockEvent("9", 0.9, "A", 1.0, 0.5, "system"),
      createMockEvent("10", 1.0, "A", 1.0002, 0.5, "system"), // A'' tiny drift
      createMockEvent("11", 1.1, "A", 1.0, 0.5, "system"),
      createMockEvent("12", 1.2, "C", 0.6, 0.7, "observer"),
      createMockEvent("13", 1.3, "C", 0.6, 0.7, "observer"),
      createMockEvent("14", 1.4, "C", 0.6, 0.7, "observer"),
      createMockEvent("15", 1.5, "A", 1.0, 0.5, "system"),
    ];
    setDebugEvents(events);
    setTestMode("Test 1: Micro-Fracture Injection");
  };

  const loadTest2 = () => {
    // A D A D A D A - D near boundary
    const events: DebugEventRecord[] = [
      createMockEvent("1", 0.1, "A", 1.0, 0.5, "system"),
      createMockEvent("2", 0.2, "D", 0.74, 0.26, "system"), // near dominant threshold
      createMockEvent("3", 0.3, "A", 1.0, 0.5, "system"),
      createMockEvent("4", 0.4, "D", 0.76, 0.24, "system"), // flip to dominant
      createMockEvent("5", 0.5, "A", 1.0, 0.5, "system"),
      createMockEvent("6", 0.6, "D", 0.73, 0.27, "system"),
      createMockEvent("7", 0.7, "A", 1.0, 0.5, "system"),
    ];
    setDebugEvents(events);
    setTestMode("Test 2: Threshold Oscillation");
  };

  const loadTest3 = () => {
    // A A A [VOID] [VOID] A A
    const events: DebugEventRecord[] = [
      createMockEvent("1", 0.1, "A", 1.0, 0.5, "system"),
      createMockEvent("2", 0.2, "A", 1.0, 0.5, "system"),
      createMockEvent("3", 0.3, "A", 1.0, 0.5, "system"),
      createMockEvent("4", 0.4, "", 0.0, 0.0, "system"), // void
      createMockEvent("5", 0.5, "", 0.0, 0.0, "system"), // void
      createMockEvent("6", 0.6, "A", 1.0, 0.5, "system"),
      createMockEvent("7", 0.7, "A", 1.0, 0.5, "system"),
    ];
    setDebugEvents(events);
    setTestMode("Test 3: Temporal Void Intrusion");
  };

  const loadTest4 = () => {
    // A (degenerate) → A (dominant) → A (balanced) - same decisionHash
    const events: DebugEventRecord[] = [
      createMockEvent("1", 0.1, "A", 1e-7, 1e-8, "system"), // degenerate
      createMockEvent("2", 0.2, "A", 0.8, 0.2, "system"), // dominant
      createMockEvent("3", 0.3, "A", 0.5, 0.5, "system"), // balanced
    ];
    setDebugEvents(events);
    setTestMode("Test 4: Dominance Collapse");
  };

  const handleSelectBlock = (decisionHash: string) => {
    const representativeId = findRepresentativeEventId(decisionHash);
    if (representativeId && activeSessionId) {
      setSelectedDebugEventId(representativeId);
      void loadDebugEvent(activeSessionId, representativeId).catch((error: unknown) => {
        setErrorMessage(
          error instanceof Error ? error.message : "Unable to load normalization event detail."
        );
      });
    }
  };

  const loadRoutingOptions = async () => {
    const response = await fetch("/api/audio/options");
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload?.error || "Unable to load routing options.");
    }

    setRoutingOptions(payload);
    setRouteProfileId(payload.defaultRouteProfileId || "browser-debug");
    setInputDeviceId(payload.defaultInputDeviceName || payload.inputDevices[0]?.name || "");
    setOutputDeviceId(payload.defaultOutputDeviceName || payload.outputDevices[0]?.name || "");
  };

  const loadBootstrap = async () => {
    const response = await fetch("/api/bootstrap");
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload?.error || "Unable to inspect bootstrap state.");
    }

    setBootstrapReport(payload);
  };

  const loadVoiceProfiles = async () => {
    const response = await fetch("/api/voice-profiles");
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload?.error || "Unable to load voice profiles.");
    }

    const profiles = Array.isArray(payload.profiles) ? payload.profiles : [];
    setVoiceProfiles(profiles);
    setVoiceProfileId((current) =>
      profiles.some((profile: VoiceProfile) => profile.id === current)
        ? current
        : profiles[0]?.id || "generic:offline-default"
    );
  };

  const loadModelPacks = async (nextSource = sourceLanguage, nextTarget = targetLanguage) => {
    setModelPacks(await fetchModelPackPayload(nextSource, nextTarget));
  };

  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      try {
        const [modelPackPayload] = await Promise.all([
          fetchModelPackPayload("en", "te"),
          loadRoutingOptions(),
          loadBootstrap(),
          loadVoiceProfiles(),
        ]);
        if (!cancelled) {
          setModelPacks(modelPackPayload);
        }
      } catch (error) {
        if (!cancelled) {
          setErrorMessage(
            error instanceof Error ? error.message : "Unable to initialize the debug harness."
          );
        }
      }
    };

    void run();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      try {
        const packs = await fetchModelPackPayload(sourceLanguage, targetLanguage);
        if (!cancelled) {
          setModelPacks(packs);
        }
      } catch (error) {
        if (!cancelled) {
          setErrorMessage(
            error instanceof Error ? error.message : "Unable to refresh model packs."
          );
        }
      }
    };

    void run();

    return () => {
      cancelled = true;
    };
  }, [sourceLanguage, targetLanguage]);

  function appendFeedEvent(event: SessionEvent) {
    if (event.type !== "final_translation" || !event.translatedText) {
      return;
    }

    setFeed((currentFeed) =>
      [
        {
          id: `${event.chunkNumber}-${event.translatedText}`,
          transcript: event.transcript || "",
          translatedText: event.translatedText || "",
          backend: event.backend || "unknown",
          detectedLanguage: event.detectedLanguage || sourceLanguage,
          latencyMs: event.latencyMs,
        },
        ...currentFeed,
      ].slice(0, 16)
    );
  }

  const loadDebugEvent = async (sessionId: string, eventId: string) => {
    const response = await fetch(`/api/debug/normalization/sessions/${sessionId}/events/${eventId}`);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload?.error || "Unable to load normalization event detail.");
    }

    setSelectedDebugEvent(payload);
  };

  const loadDebugEvents = async (sessionId: string, preferredEventId?: string | null) => {
    setDebugLoading(true);

    try {
      const response = await fetch(`/api/debug/normalization/sessions/${sessionId}/events?limit=40`);
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.error || "Unable to load normalization events.");
      }

      const nextEvents = Array.isArray(payload.events) ? payload.events : [];
      setDebugEvents(nextEvents);

      const nextSelectedId =
        preferredEventId && nextEvents.some((event: DebugEventRecord) => event.id === preferredEventId)
          ? preferredEventId
          : nextEvents[0]?.id || null;
      setSelectedDebugEventId(nextSelectedId);

      if (nextSelectedId) {
        await loadDebugEvent(sessionId, nextSelectedId);
      } else {
        setSelectedDebugEvent(null);
      }
    } finally {
      setDebugLoading(false);
    }
  };

  const uploadChunk = async (pcmChunks: Int16Array[]) => {
    const sessionId = sessionIdRef.current;
    if (!sessionId || pcmChunks.length === 0) {
      return;
    }

    const merged = mergePcmChunks(pcmChunks);
    const wavBlob = encodeWav(merged, SAMPLE_RATE);
    const analysis = analyzePcmChunk(merged);
    const formData = new FormData();
    formData.append("file", wavBlob, `debug-mic-${Date.now()}.wav`);
    formData.append("analysis", JSON.stringify(analysis));

    const response = await fetch(`/api/realtime/sessions/${sessionId}/chunks`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      throw new Error(payload?.error || "Unable to upload microphone chunk.");
    }
  };

  const flushQueuedAudio = async (force = false) => {
    const bufferedSampleCount = pcmQueueRef.current.reduce((sum, chunk) => sum + chunk.length, 0);
    if (!force && bufferedSampleCount < CHUNK_SAMPLE_TARGET) {
      return;
    }

    const chunksToUpload = pcmQueueRef.current;
    pcmQueueRef.current = [];

    uploadQueueRef.current = uploadQueueRef.current.then(() => uploadChunk(chunksToUpload));
    await uploadQueueRef.current;
  };

  const teardownAudioGraph = async () => {
    processorNodeRef.current?.disconnect();
    sourceNodeRef.current?.disconnect();
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    processorNodeRef.current = null;
    sourceNodeRef.current = null;
    mediaStreamRef.current = null;

    if (audioContextRef.current) {
      await audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
  };

  const stopStreaming = async () => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;

    await teardownAudioGraph();
    await flushQueuedAudio(true).catch((error: unknown) => {
      setErrorMessage(error instanceof Error ? error.message : "Unable to flush queued audio.");
    });

    const sessionId = sessionIdRef.current;
    sessionIdRef.current = null;
    setActiveSessionId(null);
    setDebugEvents([]);
    setSelectedDebugEventId(null);
    setSelectedDebugEvent(null);
    if (sessionId) {
      await fetch(`/api/realtime/sessions/${sessionId}`, { method: "DELETE" }).catch(() => null);
    }

    setIsStreaming(false);
    setStatusMessage("Idle");
  };

  const startStreaming = async () => {
    setErrorMessage("");
    setFeed([]);
    setStatusMessage("Creating session...");

    const sessionResponse = await fetch("/api/realtime/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sourceLanguage,
        targetLanguage,
        platform: "browser",
        autoDetectSource: sourceLanguage === "auto",
        sessionKind,
        inputDeviceId,
        outputDeviceId,
        micInputDeviceId: inputDeviceId,
        speakerOutputDeviceId: outputDeviceId,
        micTargetLanguage: targetLanguage,
        speakerTargetLanguage: targetLanguage,
        routeProfileId,
        onlinePolicy,
        voiceProfileId,
        preserveEmotion,
      }),
    });

    const sessionPayload = await sessionResponse.json();
    if (!sessionResponse.ok) {
      throw new Error(sessionPayload?.error || "Unable to create a translation session.");
    }

    sessionIdRef.current = sessionPayload.sessionId;
    setActiveSessionId(sessionPayload.sessionId);
    eventSourceRef.current = new EventSource(
      `/api/realtime/sessions/${sessionPayload.sessionId}/events`
    );
    await loadDebugEvents(sessionPayload.sessionId);

    eventSourceRef.current.onmessage = (message) => {
      const event = JSON.parse(message.data) as SessionEvent;

      if (event.type === "snapshot" && Array.isArray(event.events)) {
        event.events.forEach(appendFeedEvent);
        return;
      }

      if (event.type === "status" && event.message) {
        setStatusMessage(event.message);
      }
      if (event.type === "error" && event.message) {
        setErrorMessage(event.message);
      }
      if (event.type === "latency_sample" && typeof event.latencyMs === "number") {
        setStatusMessage(`Chunk latency ${event.latencyMs} ms`);
      }

      appendFeedEvent(event);
    };

    eventSourceRef.current.onerror = () => {
      setStatusMessage("Live event stream disconnected");
    };

    const mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: SAMPLE_RATE,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    const audioContext = new AudioContext({ sampleRate: SAMPLE_RATE });
    const sourceNode = audioContext.createMediaStreamSource(mediaStream);
    const processorNode = audioContext.createScriptProcessor(4096, 1, 1);
    const silentGainNode = audioContext.createGain();
    silentGainNode.gain.value = 0;

    processorNode.onaudioprocess = (event) => {
      const pcmChunk = floatToPcmChunk(event.inputBuffer.getChannelData(0));
      pcmQueueRef.current.push(pcmChunk);

      void flushQueuedAudio().catch((error: unknown) => {
        setErrorMessage(error instanceof Error ? error.message : "Unable to stream microphone audio.");
      });
    };

    sourceNode.connect(processorNode);
    processorNode.connect(silentGainNode);
    silentGainNode.connect(audioContext.destination);

    mediaStreamRef.current = mediaStream;
    audioContextRef.current = audioContext;
    sourceNodeRef.current = sourceNode;
    processorNodeRef.current = processorNode;
    setIsStreaming(true);
    setStatusMessage("Listening to browser microphone...");
  };

  useEffect(() => {
    return () => {
      eventSourceRef.current?.close();
      mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
      processorNodeRef.current?.disconnect();
      sourceNodeRef.current?.disconnect();
      if (audioContextRef.current) {
        void audioContextRef.current.close().catch(() => {});
      }
      const sessionId = sessionIdRef.current;
      if (sessionId) {
        void fetch(`/api/realtime/sessions/${sessionId}`, {
          method: "DELETE",
        }).catch(() => null);
      }
    };
  }, []);

  const handleToggleStreaming = async () => {
    try {
      if (isStreaming) {
        await stopStreaming();
      } else {
        await startStreaming();
      }
    } catch (error) {
      await stopStreaming();
      setErrorMessage(error instanceof Error ? error.message : "Unable to start the session.");
      setStatusMessage("Error");
    }
  };

  const formatTimeValue = (
    value: DebugEventRecord["timing"]["raw"]["quota"] | number | undefined
  ) => {
    if (typeof value === "number") {
      return `${value}`;
    }
    if (value && typeof value === "object") {
      if (typeof value.delayMs === "number") {
        return `delayed +${value.delayMs} ms`;
      }
      if (typeof value.readyAt === "number") {
        return `${value.readyAt}`;
      }
    }
    return "n/a";
  };

  const formatContribution = (value: number) => value.toFixed(2);
  const contributionEntries = selectedDebugEvent
    ? Object.entries(selectedDebugEvent.contributions).sort((left, right) => Math.abs(right[1]) - Math.abs(left[1]))
    : [];

  return (
    <div className="min-h-screen bg-[#07111d] px-5 py-6 text-slate-100 sm:px-8 lg:px-10">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <header className="overflow-hidden rounded-[2rem] border border-cyan-200/10 bg-[radial-gradient(circle_at_top_left,_rgba(91,214,194,0.16),transparent_28%),linear-gradient(150deg,_rgba(6,14,25,0.96),rgba(13,22,37,0.94)_56%,rgba(4,10,18,0.98))] p-8 shadow-[0_30px_80px_rgba(0,0,0,0.35)]">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl">
              <p className="text-xs uppercase tracking-[0.42em] text-cyan-300/80">
                Universal Language Translator
              </p>
              <h1 className="mt-3 font-serif text-4xl tracking-tight text-white sm:text-5xl">
                System Translation Control Tower
              </h1>
              <p className="mt-4 max-w-2xl text-base leading-7 text-slate-300">
                This web surface is the debug harness for the shared runtime. Native speaker
                interception and microphone rerouting are handled by the Windows Electron shell and
                Android app, while this page lets us inspect models, routes, and the live chunk
                pipeline from the browser microphone.
              </p>
            </div>

            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => void handleToggleStreaming()}
                className={`rounded-full px-6 py-3 text-sm font-semibold transition ${
                  isStreaming
                    ? "bg-rose-500 text-white shadow-lg shadow-rose-500/25"
                    : "bg-cyan-300 text-slate-950 shadow-lg shadow-cyan-300/25"
                }`}
              >
                {isStreaming ? "Stop Debug Session" : "Start Debug Session"}
              </button>
              <button
                type="button"
                onClick={() => {
                  void Promise.all([
                    loadRoutingOptions(),
                    loadBootstrap(),
                    loadVoiceProfiles(),
                    loadModelPacks(),
                  ]).catch((error: unknown) => {
                    setErrorMessage(
                      error instanceof Error ? error.message : "Unable to refresh runtime state."
                    );
                  });
                }}
                className="rounded-full border border-slate-600 bg-slate-950/70 px-5 py-3 text-sm font-semibold text-slate-100"
              >
                Refresh Runtime
              </button>
            </div>
          </div>

          <div className="mt-8 grid gap-4 md:grid-cols-4">
            <StatCard label="Status" value={statusMessage} />
            <StatCard label="Hardware Profile" value={bootstrapReport?.hardware.profileId || "loading"} />
            <StatCard label="Session Mode" value={sessionKind} />
            <StatCard
              label="Self Test"
              value={bootstrapReport?.selfTest.ok ? "passing" : "attention needed"}
            />
          </div>
        </header>

        <main className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
          <section className="flex flex-col gap-6 rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-[0_24px_50px_rgba(0,0,0,0.24)]">
            <SectionTitle
              title="Session Contract"
              body="Every control here maps directly to the shared StartSessionRequest contract that desktop and Android also use."
            />

            <div className="grid gap-4 md:grid-cols-2">
              <SelectField
                label="Source Language"
                value={sourceLanguage}
                disabled={isStreaming}
                onChange={setSourceLanguage}
                options={LANGUAGE_CATALOG.map((language: { code: string; label: string }) => ({
                  value: language.code,
                  label: `${language.label} (${language.code})`,
                }))}
              />
              <SelectField
                label="Target Language"
                value={targetLanguage}
                disabled={isStreaming}
                onChange={setTargetLanguage}
                options={LANGUAGE_CATALOG.map((language: { code: string; label: string }) => ({
                  value: language.code,
                  label: `${language.label} (${language.code})`,
                }))}
              />
              <SelectField
                label="Session Kind"
                value={sessionKind}
                disabled={isStreaming}
                onChange={setSessionKind}
                options={[
                  { value: "browser_debug", label: "Browser Debug Harness" },
                  { value: "desktop_runtime", label: "Desktop Runtime" },
                  { value: "android_runtime", label: "Android Runtime" },
                ]}
              />
              <SelectField
                label="Online Policy"
                value={onlinePolicy}
                disabled={isStreaming}
                onChange={setOnlinePolicy}
                options={[
                  { value: "offline-only", label: "Offline Only" },
                ]}
              />
              <SelectField
                label="Route Profile"
                value={routeProfileId}
                disabled={isStreaming}
                onChange={(value) => {
                  setRouteProfileId(value);
                  const profile = routingOptions.routeProfiles.find((entry) => entry.id === value);
                  if (profile) {
                    setSessionKind(profile.sessionKind);
                  }
                }}
                options={routingOptions.routeProfiles.map((profile) => ({
                  value: profile.id,
                  label: `${profile.label} (${profile.status})`,
                }))}
              />
              <SelectField
                label="Voice Profile"
                value={voiceProfileId}
                disabled={isStreaming}
                onChange={setVoiceProfileId}
                options={voiceProfiles.map((profile) => ({
                  value: profile.id,
                  label: profile.label,
                }))}
              />
              <SelectField
                label="Input Device"
                value={inputDeviceId}
                disabled={isStreaming}
                onChange={setInputDeviceId}
                options={routingOptions.inputDevices.map((device) => ({
                  value: device.name,
                  label: device.name,
                }))}
              />
              <SelectField
                label="Output Device"
                value={outputDeviceId}
                disabled={isStreaming}
                onChange={setOutputDeviceId}
                options={routingOptions.outputDevices.map((device) => ({
                  value: device.name,
                  label: device.name,
                }))}
              />
            </div>

            <label className="inline-flex items-center gap-3 rounded-3xl border border-cyan-400/15 bg-cyan-400/5 px-4 py-3 text-sm text-slate-200">
              <input
                type="checkbox"
                checked={preserveEmotion}
                disabled={isStreaming}
                onChange={(event) => setPreserveEmotion(event.target.checked)}
                className="h-4 w-4 rounded border-slate-600 bg-slate-950"
              />
              Preserve emotion and vocal intensity whenever the active voice stack allows it.
            </label>

            <div className="rounded-[1.5rem] border border-slate-800 bg-slate-950/70 p-5 text-sm leading-7 text-slate-300">
              <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Route Profile</p>
              <p className="mt-3 text-lg font-semibold text-white">
                {selectedRouteProfile?.label || "No route profile selected"}
              </p>
              <p className="mt-2 text-slate-400">
                Status: {selectedRouteProfile?.status || "unknown"}
              </p>
              <p className="mt-3">
                {selectedRouteProfile?.requirements.join(" / ") ||
                  "The browser harness uses uploaded microphone chunks and does not perform native interception directly."}
              </p>
            </div>

            {errorMessage ? (
              <div className="rounded-[1.5rem] border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-100">
                {errorMessage}
              </div>
            ) : null}
          </section>

          <section className="flex flex-col gap-6">
            <div className="rounded-[2rem] border border-white/10 bg-slate-950/80 p-6 shadow-[0_20px_50px_rgba(0,0,0,0.32)]">
              <SectionTitle
                title="Bootstrap"
                body="First-launch detection, self-test, and model selection are all exposed here so we can verify runtime readiness before packaging."
              />
              <div className="mt-4 grid gap-4 sm:grid-cols-3">
                <MiniStat label="CPU Threads" value={String(bootstrapReport?.hardware.cpuCount || 0)} />
                <MiniStat label="Memory" value={`${bootstrapReport?.hardware.totalMemGb || 0} GB`} />
                <MiniStat label="GPU" value={bootstrapReport?.hardware.gpu.name || "unknown"} />
              </div>

              <div className="mt-5 space-y-3">
                {bootstrapReport?.selfTest.checks.map((check) => (
                  <div
                    key={check.label}
                    className="flex items-center justify-between rounded-2xl border border-slate-800 bg-slate-900/75 px-4 py-3 text-sm"
                  >
                    <span className="text-slate-300">{check.label}</span>
                    <span className={check.ok ? "text-cyan-300" : "text-rose-300"}>
                      {check.ok ? "ready" : "missing"}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-[0_20px_50px_rgba(0,0,0,0.22)]">
              <SectionTitle
                title="Model Packs"
                body="Universal online coverage stays broad, while offline packs are tracked per language pair and delivered on demand."
              />
              <div className="mt-4 space-y-3">
                {modelPacks.map((pack) => (
                  <article
                    key={pack.id}
                    className="rounded-[1.5rem] border border-slate-800 bg-slate-950/70 p-4"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-sm font-semibold text-white">{pack.label}</p>
                        <p className="mt-1 text-sm leading-6 text-slate-400">{pack.description}</p>
                      </div>
                      <div className="rounded-full border border-slate-700 px-3 py-1 text-xs uppercase tracking-[0.22em] text-cyan-200">
                        {pack.installState}
                      </div>
                    </div>
                    <p className="mt-3 text-xs uppercase tracking-[0.2em] text-slate-500">
                      {pack.transport}
                    </p>
                  </article>
                ))}
              </div>
            </div>
          </section>
        </main>

        <section className="rounded-[2rem] border border-white/10 bg-slate-900/85 p-6 shadow-[0_24px_60px_rgba(0,0,0,0.28)]">
          <div className="flex items-center justify-between gap-4">
            <SectionTitle
              title="Live Feed"
              body="Chunk events come from the shared session runtime. Final translations appear here after STT, translation, and TTS stages finish."
            />
            <span className="rounded-full bg-slate-800 px-3 py-1 text-xs uppercase tracking-[0.2em] text-slate-400">
              {isStreaming ? "streaming" : "standby"}
            </span>
          </div>

          <div className="mt-6 grid gap-4 xl:grid-cols-2">
            {feed.length ? (
              feed.map((entry) => (
                <article
                  key={entry.id}
                  className="rounded-[1.5rem] border border-slate-800 bg-slate-950/90 p-5 shadow-inner shadow-slate-950/30"
                >
                  <div className="flex flex-wrap items-center gap-3 text-xs uppercase tracking-[0.2em] text-slate-500">
                    <span>{entry.detectedLanguage}</span>
                    <span>{entry.backend}</span>
                    {entry.latencyMs ? <span>{entry.latencyMs} ms</span> : null}
                  </div>
                  <div className="mt-4 grid gap-4">
                    <div>
                      <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
                        Transcript
                      </p>
                      <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-slate-200">
                        {entry.transcript || "No transcript returned for this chunk."}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
                        Translated Output
                      </p>
                      <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-cyan-100">
                        {entry.translatedText}
                      </p>
                    </div>
                  </div>
                </article>
              ))
            ) : (
              <div className="col-span-full flex min-h-[18rem] items-center justify-center rounded-[1.75rem] border border-dashed border-slate-700 bg-slate-950/80 p-8 text-center text-sm leading-7 text-slate-400">
                Start a debug session and speak into the browser microphone. Native system capture
                and translated-only routing are exposed through the Electron and Android clients,
                but this page still exercises the same session contracts and engine stack.
              </div>
            )}
          </div>
        </section>

        <section className="rounded-[2rem] border border-white/10 bg-[#06101a] p-6 shadow-[0_24px_60px_rgba(0,0,0,0.28)]">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <SectionTitle
              title="Normalization Microscope"
              body="Read-only inspection of stored GETS decisions. This view only reads stored normalized events and traces."
            />
            <div className="flex items-center gap-3">
              <span className="rounded-full bg-slate-900 px-3 py-1 text-xs uppercase tracking-[0.2em] text-slate-400">
                {activeSessionId ? "attached" : "no session"}
              </span>
              <button
                type="button"
                disabled={!activeSessionId || debugLoading}
                onClick={() => {
                  if (!activeSessionId) return;
                  void loadDebugEvents(activeSessionId, selectedDebugEventId).catch((error: unknown) => {
                    setErrorMessage(
                      error instanceof Error
                        ? error.message
                        : "Unable to refresh normalization debugger."
                    );
                  });
                }}
                className="rounded-full border border-slate-700 bg-slate-950/80 px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-200 disabled:opacity-40"
              >
                {debugLoading ? "Loading" : "Refresh Debugger"}
              </button>
            </div>
          </div>

          <div className="mt-6 grid gap-5 xl:grid-cols-[0.92fr_1.08fr]">
            <div className="rounded-[1.5rem] border border-slate-800 bg-slate-950/80 p-4">
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Event List</p>
                <span className="text-xs text-slate-500">{debugEvents.length} events</span>
              </div>

              <div className="mt-4 rounded-[1.5rem] border border-slate-800 bg-slate-900/70 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Truth Surface</p>
                    <p className="mt-2 text-sm text-slate-300">
                      Blocks represent identical decisions stretched across time. Gaps change length, never identity.
                    </p>
                    {testMode && (
                      <p className="mt-1 text-xs text-cyan-300">{testMode}</p>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={loadTest1}
                      className="rounded-full border border-slate-700 bg-slate-950/80 px-2 py-1 text-xs uppercase tracking-[0.2em] text-slate-200"
                    >
                      Test 1
                    </button>
                    <button
                      type="button"
                      onClick={loadTest2}
                      className="rounded-full border border-slate-700 bg-slate-950/80 px-2 py-1 text-xs uppercase tracking-[0.2em] text-slate-200"
                    >
                      Test 2
                    </button>
                    <button
                      type="button"
                      onClick={loadTest3}
                      className="rounded-full border border-slate-700 bg-slate-950/80 px-2 py-1 text-xs uppercase tracking-[0.2em] text-slate-200"
                    >
                      Test 3
                    </button>
                    <button
                      type="button"
                      onClick={loadTest4}
                      className="rounded-full border border-slate-700 bg-slate-950/80 px-2 py-1 text-xs uppercase tracking-[0.2em] text-slate-200"
                    >
                      Test 4
                    </button>
                    <button
                      type="button"
                      onClick={() => setTruthMode((current) => (current === "truth" ? "trace" : "truth"))}
                      className="rounded-full border border-slate-700 bg-slate-950/80 px-3 py-1 text-xs uppercase tracking-[0.2em] text-slate-200"
                    >
                      {truthMode === "truth" ? "Trace Mode" : "Truth Mode"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setBlockDetailsOpen((current) => !current)}
                      className="rounded-full border border-slate-700 bg-slate-950/80 px-3 py-1 text-xs uppercase tracking-[0.2em] text-slate-200"
                    >
                      {blockDetailsOpen ? "Hide details" : "Show samples"}
                    </button>
                  </div>
                </div>

                <div className="mt-4 overflow-hidden rounded-2xl bg-slate-950/80 p-2">
                  {identityBlocks.length ? (
                    <div className="relative h-16 rounded-2xl bg-slate-900">
                      {truthMode === "trace" ? (
                        debugEvents.map((event, eventIndex) => {
                          const tickLeft = parseFloat((((event.normalizedTime - identityTimeRange.min) / identityScale) * 100).toFixed(2));
                          return (
                            <span
                              key={`trace-${event.id}-${eventIndex}`}
                              className="absolute top-0 h-full w-px bg-slate-500/40"
                              style={{ left: `${tickLeft}%` }}
                            />
                          );
                        })
                      ) : null}
                      {identityBlocks.map((block, index) => {
                        const left = parseFloat((((block.startTime - identityTimeRange.min) / identityScale) * 100).toFixed(2));
                        const width = parseFloat(Math.max(
                          0.75,
                          ((block.endTime - block.startTime) / identityScale) * 100
                        ).toFixed(2));
                        const boundaryClass = block.startReason === "decision-change"
                          ? "border-l-2 border-white/80"
                          : "";

                        return (
                          <button
                            key={`${block.decisionHash}-${index}-${block.state}-${block.startReason}`}
                            type="button"
                            onMouseEnter={() => setHoveredBlock(block)}
                            onMouseLeave={() => setHoveredBlock(null)}
                            onClick={() => handleSelectBlock(block.decisionHash)}
                            title={`${block.state.toUpperCase()} · ${block.samples} sample(s)`}
                            className={`absolute top-0 h-full overflow-hidden rounded-sm ${boundaryClass} ${colorByState(block.state)} text-[10px] text-slate-950 transition-none ${truthMode === "trace" ? "opacity-80" : ""}`}
                            style={{
                              left: `${left}%`,
                              width: `${width}%`,
                            }}
                          >
                            {block.state === "void" ? (
                              <div className="absolute inset-0 border border-dashed border-slate-400/60 bg-slate-950/10" />
                            ) : null}
                            {block.fractures?.map((fracture, fractureIndex) => {
                              const fractureLeft = ((fracture.time - block.startTime) / (block.endTime - block.startTime)) * 100;
                              return (
                                <span
                                  key={fractureIndex}
                                  className="absolute top-2 bottom-2 w-px bg-slate-100/70"
                                  style={{ left: `${fractureLeft}%` }}
                                />
                              );
                            })}
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="rounded-2xl border border-dashed border-slate-800 bg-slate-900/60 p-6 text-sm text-slate-500">
                      The truth surface appears once debug events are loaded. It groups same decisions into stable identity blocks.
                    </div>
                  )}
                </div>

                {hoveredBlock ? (
                  <div className="mt-3 rounded-2xl border border-slate-700 bg-slate-900/90 p-4 text-sm">
                    <div className="font-mono text-xs text-slate-400">decisionHash</div>
                    <div className="font-mono text-slate-200">{hoveredBlock.decisionHash.slice(0, 16)}...</div>
                    <div className="mt-2 grid grid-cols-2 gap-4">
                      <div>
                        <div className="font-mono text-xs text-slate-400">state</div>
                        <div className="text-slate-200">{hoveredBlock.state}</div>
                      </div>
                      <div>
                        <div className="font-mono text-xs text-slate-400">dominantDomain</div>
                        <div className="text-slate-200">{hoveredBlock.dominantDomain || "none"}</div>
                      </div>
                      <div>
                        <div className="font-mono text-xs text-slate-400">duration</div>
                        <div className="text-slate-200">{((hoveredBlock.endTime - hoveredBlock.startTime) * 1000).toFixed(0)}ms</div>
                      </div>
                      <div>
                        <div className="font-mono text-xs text-slate-400">samples</div>
                        <div className="text-slate-200">{hoveredBlock.samples}</div>
                      </div>
                      <div className="col-span-2">
                        <div className="font-mono text-xs text-slate-400">startReason</div>
                        <div className="text-slate-200">{hoveredBlock.startReason}</div>
                      </div>
                    </div>
                  </div>
                ) : null}

                {identityBlocks.length ? (
                  <div className="mt-3 grid gap-2 text-[11px] text-slate-400 sm:grid-cols-2">
                    <div>range {formatTime(identityTimeRange.min)} → {formatTime(identityTimeRange.max)}</div>
                    <div>samples {identityBlocks.reduce((sum, block) => sum + block.samples, 0)}</div>
                  </div>
                ) : null}

                {blockDetailsOpen && identityBlocks.length ? (
                  <div className="mt-3 space-y-2 text-slate-300">
                    {identityBlocks.map((block, index) => (
                      <div
                        key={`${block.decisionHash}-detail-${index}`}
                        className="rounded-2xl border border-slate-800 bg-slate-950/80 p-3"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2 text-xs uppercase tracking-[0.18em] text-slate-500">
                          <span>{block.state}</span>
                          <span>{block.samples} sample{block.samples === 1 ? "" : "s"}</span>
                        </div>
                        <div className="mt-2 grid gap-2 sm:grid-cols-2">
                          <p className="truncate text-sm text-slate-200">decision {block.decisionHash.slice(0, 12)}...</p>
                          <p className="truncate text-sm text-slate-200">logic {block.logicHash.slice(0, 12)}...</p>
                          <p className="text-slate-400">domain {block.dominantDomain}</p>
                          <p className="text-slate-400">
                            {formatTime(block.startTime)} → {formatTime(block.endTime)}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>

              <div className="mt-4 space-y-3">
                {debugEvents.length ? (
                  debugEvents.map((event) => (
                    <button
                      key={event.id}
                      type="button"
                      onClick={() => {
                        if (!activeSessionId) return;
                        setSelectedDebugEventId(event.id);
                        void loadDebugEvent(activeSessionId, event.id).catch((error: unknown) => {
                          setErrorMessage(
                            error instanceof Error
                              ? error.message
                              : "Unable to load normalization event detail."
                          );
                        });
                      }}
                      className={`w-full rounded-[1.25rem] border px-4 py-3 text-left transition ${
                        selectedDebugEventId === event.id
                          ? "border-cyan-300/40 bg-cyan-300/10"
                          : "border-slate-800 bg-slate-900/70 hover:border-slate-700"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-4">
                        <p className="text-sm font-semibold text-white">{event.type}</p>
                        <span className="text-xs uppercase tracking-[0.18em] text-cyan-200">
                          {event.normalizedTime.toFixed(2)}
                        </span>
                      </div>
                      <p className="mt-2 truncate text-xs text-slate-400">{event.id}</p>
                      <p className="mt-1 truncate text-[11px] text-slate-500">
                        {event.causalityKey.transformation} :: {event.causalityKey.sourceEventIds.join(", ") || "root"}
                      </p>
                    </button>
                  ))
                ) : (
                  <div className="rounded-[1.25rem] border border-dashed border-slate-800 bg-slate-900/60 p-5 text-sm leading-6 text-slate-500">
                    Start a debug session, then refresh this panel to inspect stored normalized events.
                  </div>
                )}
              </div>
            </div>

            <div className="rounded-[1.5rem] border border-slate-800 bg-slate-950/80 p-5">
              {selectedDebugEvent ? (
                <div className="space-y-5">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="rounded-full border border-cyan-300/30 bg-cyan-300/10 px-3 py-1 text-xs uppercase tracking-[0.2em] text-cyan-200">
                      {selectedDebugEvent.type}
                    </span>
                    <span className="rounded-full border border-slate-700 px-3 py-1 text-xs uppercase tracking-[0.2em] text-slate-400">
                      {selectedDebugEvent.causalityKey.transformation}
                    </span>
                  </div>

                  <div className="rounded-[1.25rem] border border-cyan-400/20 bg-cyan-400/5 p-4">
                    <p className="text-xs uppercase tracking-[0.2em] text-cyan-200">Why Did This Win?</p>
                    <p className="mt-3 text-lg font-semibold text-white">
                      TIME DOMINATED BY: {selectedDebugEvent.dominantDomain}
                    </p>
                    <p className="mt-2 text-sm text-slate-300">
                      integrity {selectedDebugEvent.integrityHash.slice(0, 16)}...
                    </p>
                    <p className="mt-1 text-sm text-slate-300">
                      decision {selectedDebugEvent.decisionHash.slice(0, 16)}...
                    </p>
                    <p className="mt-1 text-sm text-slate-300">
                      timing {selectedDebugEvent.timingHash.slice(0, 16)}...
                    </p>
                    <p className="mt-1 text-sm text-slate-300">
                      logic {selectedDebugEvent.logicHash.slice(0, 16)}...
                    </p>
                  </div>

                  <div className="grid gap-4 lg:grid-cols-2">
                    <div className="rounded-[1.25rem] border border-slate-800 bg-slate-900/70 p-4">
                      <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Raw Times</p>
                      <div className="mt-4 space-y-2 text-sm text-slate-200">
                        <p>rawTime: {selectedDebugEvent.rawTime}</p>
                        <p>system: {formatTimeValue(selectedDebugEvent.timing.raw.system)}</p>
                        <p>stream: {formatTimeValue(selectedDebugEvent.timing.raw.stream)}</p>
                        <p>utterance: {formatTimeValue(selectedDebugEvent.timing.raw.utterance)}</p>
                        <p>observer: {formatTimeValue(selectedDebugEvent.timing.raw.observer)}</p>
                        <p>quota: {formatTimeValue(selectedDebugEvent.timing.raw.quota)}</p>
                      </div>
                    </div>

                    <div className="rounded-[1.25rem] border border-slate-800 bg-slate-900/70 p-4">
                      <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Final Decision</p>
                      <div className="mt-4 space-y-2 text-sm text-slate-200">
                        <p>sessionTime = {selectedDebugEvent.sessionTime.toFixed(3)}</p>
                        <p>normalizedTime = {selectedDebugEvent.normalizedTime.toFixed(3)}</p>
                        <p>
                          mode = {selectedDebugEvent.timing.normalizationTrace.mode || selectedDebugEvent.normalizationVersion}
                        </p>
                        <p>
                          ignored ={" "}
                          {selectedDebugEvent.ignoredDomains.length
                            ? selectedDebugEvent.ignoredDomains.join(", ")
                            : "none"}
                        </p>
                        <p>coherence = {selectedDebugEvent.timing.coherenceScore.toFixed(3)}</p>
                        <p>
                          backward = {selectedDebugEvent.timing.flags.normalizedTimeBackward ? "flagged" : "no"}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="rounded-[1.25rem] border border-slate-800 bg-slate-900/70 p-4">
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Weights + Confidence</p>
                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      {(["stream", "utterance", "system", "observer", "quota"] as const).map((domain) => (
                        <div
                          key={domain}
                          className="rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-sm text-slate-200"
                        >
                          {domain}: weight {(selectedDebugEvent.weights[domain] || 0).toFixed(3)} x conf{" "}
                          {(selectedDebugEvent.confidences[domain] || 0).toFixed(3)}
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-[1.25rem] border border-slate-800 bg-slate-900/70 p-4">
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Contribution Breakdown</p>
                    <div className="mt-4 space-y-3">
                      {contributionEntries.map(([domain, contribution]) => (
                        <div
                          key={`${selectedDebugEvent.id}-${domain}`}
                          className="flex items-center justify-between rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-sm"
                        >
                          <div>
                            <p className="font-semibold text-white">{domain}</p>
                            <p className="text-xs text-slate-500">
                              weight {(selectedDebugEvent.weights[domain] || 0).toFixed(3)} x conf{" "}
                              {(selectedDebugEvent.confidences[domain] || 0).toFixed(3)}
                            </p>
                          </div>
                          <span className="text-cyan-200">{formatContribution(contribution)}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-[1.25rem] border border-slate-800 bg-slate-900/70 p-4 text-xs text-slate-500">
                    <p>causality.transformation: {selectedDebugEvent.causalityKey.transformation}</p>
                    <p className="mt-2">
                      causality.sources: {selectedDebugEvent.causalityKey.sourceEventIds.join(", ") || "root"}
                    </p>
                    <p className="mt-2">
                      dependencyHash: {selectedDebugEvent.causalityKey.dependencyHash.slice(0, 24)}...
                    </p>
                  </div>
                </div>
              ) : (
                <div className="flex min-h-[24rem] items-center justify-center rounded-[1.5rem] border border-dashed border-slate-800 bg-slate-900/60 p-8 text-center text-sm leading-7 text-slate-500">
                  Select a normalized event to inspect why time became what it is.
                </div>
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
