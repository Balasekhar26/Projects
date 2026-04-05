"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { LANGUAGE_CATALOG } from "@/packages/ult-core/src/catalog/languages";
import { analyzePcmChunk, CHUNK_SAMPLE_TARGET, encodeWav, floatToPcmChunk, mergePcmChunks, SAMPLE_RATE } from "./audio";
import type { BootstrapReport, FeedEntry, RoutingOptions, SessionEvent, VoiceProfile } from "./types";
import { MiniStat, SectionTitle, SelectField, StatCard } from "./ui";

const EMPTY_ROUTING_OPTIONS: RoutingOptions = {
  inputDevices: [],
  outputDevices: [],
  voices: [],
  routeProfiles: [],
  defaultInputDeviceName: "",
  defaultOutputDeviceName: "",
  defaultVoiceName: "alloy",
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
  const [sessionKind, setSessionKind] = useState("browser-debug");
  const [onlinePolicy, setOnlinePolicy] = useState("auto");
  const [routeProfileId, setRouteProfileId] = useState("browser-debug");
  const [inputDeviceId, setInputDeviceId] = useState("");
  const [outputDeviceId, setOutputDeviceId] = useState("");
  const [voiceProfileId, setVoiceProfileId] = useState("builtin:alloy");
  const [preserveEmotion, setPreserveEmotion] = useState(true);
  const [isStreaming, setIsStreaming] = useState(false);
  const [statusMessage, setStatusMessage] = useState("Idle");
  const [errorMessage, setErrorMessage] = useState("");
  const [feed, setFeed] = useState<FeedEntry[]>([]);
  const [routingOptions, setRoutingOptions] = useState<RoutingOptions>(EMPTY_ROUTING_OPTIONS);
  const [bootstrapReport, setBootstrapReport] = useState<BootstrapReport | null>(null);
  const [modelPacks, setModelPacks] = useState<Array<Record<string, string>>>([]);
  const [voiceProfiles, setVoiceProfiles] = useState<VoiceProfile[]>([]);

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
        : profiles[0]?.id || "builtin:alloy"
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
        sessionKind,
        inputDeviceId,
        outputDeviceId,
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
    eventSourceRef.current = new EventSource(
      `/api/realtime/sessions/${sessionPayload.sessionId}/events`
    );

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
                  { value: "browser-debug", label: "Browser Debug Harness" },
                  { value: "microphone", label: "Native Microphone Translate" },
                  { value: "system", label: "System Speaker Intercept" },
                ]}
              />
              <SelectField
                label="Online Policy"
                value={onlinePolicy}
                disabled={isStreaming}
                onChange={setOnlinePolicy}
                options={[
                  { value: "auto", label: "Auto" },
                  { value: "online-only", label: "Online Only" },
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
      </div>
    </div>
  );
}
