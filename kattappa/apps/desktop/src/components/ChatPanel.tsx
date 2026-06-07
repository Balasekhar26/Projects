import { useEffect, useRef, useState, type RefObject } from "react";
import { fetchVoiceStatus, processVoiceAudio, speakWithLocalVoice } from "../lib/api";
import type { Message, OperatorMode } from "../types";
import { OperatorModeSelector } from "./OperatorModeSelector";

type VoiceState = "idle" | "listening" | "processing" | "unsupported";

type ChatPanelProps = {
  messages: Message[];
  input: string;
  operatorMode: OperatorMode;
  messagesEndRef: RefObject<HTMLDivElement | null>;
  onInputChange: (input: string) => void;
  onOperatorModeChange: (mode: OperatorMode) => void;
  onSendMessage: () => void;
  onVoiceCommand: (command: string) => void;
  onVoiceWake: () => void;
  onVoiceNotice: (message: string) => void;
  isWorking: boolean;
  queuedCount: number;
};

export function ChatPanel({
  messages,
  input,
  operatorMode,
  messagesEndRef,
  onInputChange,
  onOperatorModeChange,
  onSendMessage,
  onVoiceCommand,
  onVoiceWake,
  onVoiceNotice,
  isWorking,
  queuedCount,
}: ChatPanelProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const voiceStopTimerRef = useRef<number | null>(null);
  const lastSpokenIndexRef = useRef(-1);
  const speakNextAssistantRef = useRef(false);
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const visibleMessages = messages.filter(
    (message, index) => !(index === 0 && message.role === "system" && message.content === "Kattappa AI OS ready."),
  );
  const canSend = input.trim().length > 0;

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "0px";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`;
  }, [input]);

  useEffect(() => {
    if (!speakNextAssistantRef.current) return;
    const latestIndex = messages.length - 1;
    const latest = messages[latestIndex];
    if (!latest || latestIndex === lastSpokenIndexRef.current) return;
    if (latest.role !== "assistant" || !latest.content.trim()) return;
    lastSpokenIndexRef.current = latestIndex;
    speakNextAssistantRef.current = false;
    void speakLocal(latest.content, "assistant_response");
  }, [messages]);

  useEffect(() => {
    return () => {
      stopVoiceTimer();
      stopMediaStream();
    };
  }, []);

  const getMessageName = (message: Message) => {
    if (message.role === "user") return "You";
    if (message.role === "assistant") return message.agent || "Kattappa AI";
    if (message.role === "progress") return "Working";
    return "System";
  };

  const getAvatar = (message: Message) => {
    if (message.role === "user") return "You";
    if (message.role === "assistant") return "K";
    if (message.role === "progress") return "...";
    return "i";
  };

  const stopVoiceTimer = () => {
    if (voiceStopTimerRef.current !== null) {
      window.clearTimeout(voiceStopTimerRef.current);
      voiceStopTimerRef.current = null;
    }
  };

  const stopMediaStream = () => {
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
    mediaRecorderRef.current = null;
  };

  const toggleVoice = async () => {
    if (voiceState === "listening") {
      stopVoiceCapture();
      return;
    }
    if (voiceState === "processing") return;

    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setVoiceState("unsupported");
      onVoiceNotice("Local microphone capture is unavailable in this desktop runtime. Type your command instead.");
      return;
    }

    try {
      const status = await fetchVoiceStatus();
      if (!status.stt.installed) {
        setVoiceState("unsupported");
        onVoiceNotice("Local STT is not installed. Install faster-whisper from the tools panel, or type the command.");
        return;
      }
      if (status.wake.primary_decision !== "openwakeword_custom_models") {
        onVoiceNotice("Custom openWakeWord wake models are not active, so Kattappa will use local STT wake-name parsing for this command.");
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = preferredAudioMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      audioChunksRef.current = [];
      mediaStreamRef.current = stream;
      mediaRecorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        const blob = new Blob(audioChunksRef.current, { type: recorder.mimeType || "audio/webm" });
        audioChunksRef.current = [];
        stopMediaStream();
        void processRecordedVoice(blob);
      };
      recorder.start();
      setVoiceState("listening");
      void speakLocal("వింటున్నాను. Say Kattappa, Mama, or Kittu, then your command.", "wake_prompt");
      voiceStopTimerRef.current = window.setTimeout(() => stopVoiceCapture(), 7000);
    } catch {
      setVoiceState("unsupported");
      stopMediaStream();
      onVoiceNotice("Local backend voice pipeline is unavailable. Start Kattappa with run.exe, or type the command.");
    }
  };

  const stopVoiceCapture = () => {
    stopVoiceTimer();
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      setVoiceState("processing");
      recorder.stop();
      return;
    }
    setVoiceState("idle");
    stopMediaStream();
  };

  const processRecordedVoice = async (blob: Blob) => {
    if (blob.size === 0) {
      setVoiceState("idle");
      onVoiceNotice("No voice audio was captured. Try again or type your command.");
      return;
    }
    setVoiceState("processing");
    try {
      const audio_base64 = await blobToBase64(blob);
      const result = await processVoiceAudio({ audio_base64, mime_type: blob.type || "audio/webm" });
      if (!result.ok) {
        onVoiceNotice(result.transcript || "Local voice transcription is unavailable. Type your command instead.");
        setVoiceState("idle");
        return;
      }
      if (!result.wake_detected) {
        onVoiceNotice("No wake name detected. Say Kattappa, Mama, or Kittu before the command.");
        setVoiceState("idle");
        return;
      }
      if (!result.command.trim()) {
        onVoiceWake();
        void speakLocal("చెప్పండి. I am listening.", "wake_ack");
        setVoiceState("idle");
        return;
      }
      void speakLocal("సరే. Okay.", "command_ack");
      speakNextAssistantRef.current = true;
      onVoiceCommand(result.command);
    } catch {
      onVoiceNotice("Local voice processing failed. Type your command while the backend voice stack is checked.");
    } finally {
      setVoiceState("idle");
    }
  };

  return (
    <>
      <div className="chatTopbar">
        <div className="chatHeaderInner">
          <button className="modelButton" type="button" aria-label="Current assistant mode">
            <span>Kattappa AI</span>
            <strong>{operatorMode}</strong>
          </button>
          <div className="chatHeaderActions">
            <button
              className={`voiceButton ${voiceState}`}
              type="button"
              onClick={toggleVoice}
              aria-pressed={voiceState === "listening"}
              aria-label={voiceState === "listening" ? "Stop voice listening" : "Start voice listening"}
            >
              {voiceState === "listening"
                ? "Listening"
                : voiceState === "processing"
                  ? "Processing"
                  : voiceState === "unsupported"
                    ? "Voice unavailable"
                    : "Voice"}
            </button>
            <span className="privacyBadge">Local-first</span>
          </div>
        </div>
      </div>
      <div className="messages">
        <div className="messageStack">
          {visibleMessages.length === 0 && (
            <section className="chatWelcome" aria-label="Chat ready">
              <div className="welcomeMark">K</div>
              <h2>What can I do for you?</h2>
              <p className="wakeHint">Use Voice, then say "Kattappa", "Mama", or "Kittu" with your command.</p>
              <div className="promptGrid" aria-label="Starter prompts">
                {[
                  "Make this project production ready",
                  "Check what is ready",
                  "Improve the Kattappa AI interface",
                  "Plan the next safe step",
                ].map((prompt) => (
                  <button key={prompt} type="button" onClick={() => onInputChange(prompt)}>
                    {prompt}
                  </button>
                ))}
              </div>
            </section>
          )}
          {visibleMessages.map((message, index) => (
            <article key={index} className={`message ${message.role}`}>
              <div className="messageAvatar" aria-hidden="true">{getAvatar(message)}</div>
              <div className="messageBody">
                <header>
                  <strong>{getMessageName(message)}</strong>
                  {message.risk && <span>{message.risk}</span>}
                  {message.approvalId && <span>{message.approvalId}</span>}
                </header>
                {message.routingReason && <small className="routingReason">{message.routingReason}</small>}
                <MessageContent content={message.content} />
                {message.operatorPlan && (
                  <div className="operatorPlan">
                    <div className="planHeader">
                      <strong>{message.operatorPlan.mode}</strong>
                      <span>{message.operatorPlan.local_only ? "free/local only" : "external allowed"}</span>
                      <span>{message.operatorPlan.needs_approval ? "approval needed" : "no action approval"}</span>
                    </div>
                    {message.operatorPlan.visual_guidance?.enabled && message.operatorPlan.visual_guidance.target && (
                      <div className="visualGuidanceCard">
                        <div className="guideScreen" aria-label="Visual desktop guidance preview">
                          <span
                            className="guideTarget"
                            style={{
                              left: `${message.operatorPlan.visual_guidance.target.x * 100}%`,
                              top: `${message.operatorPlan.visual_guidance.target.y * 100}%`,
                              width: `${message.operatorPlan.visual_guidance.target.width * 100}%`,
                              height: `${message.operatorPlan.visual_guidance.target.height * 100}%`,
                            }}
                          />
                          <span
                            className="guideCursor"
                            style={{
                              left: `${message.operatorPlan.visual_guidance.target.x * 100}%`,
                              top: `${message.operatorPlan.visual_guidance.target.y * 100}%`,
                            }}
                          />
                        </div>
                        <p>{message.operatorPlan.visual_guidance.instruction}</p>
                        <small>
                          {message.operatorPlan.visual_guidance.requires_approval
                            ? "Preview only until approved"
                            : "Safe visual guide"}
                          {" / "}
                          {message.operatorPlan.visual_guidance.target.source}
                        </small>
                      </div>
                    )}
                    <ol>
                      {message.operatorPlan.next_steps.map((step, stepIndex) => (
                        <li key={stepIndex}>{step}</li>
                      ))}
                    </ol>
                  </div>
                )}
              </div>
            </article>
          ))}
          <div ref={messagesEndRef} />
        </div>
      </div>
      <div className="inputBar">
        <div className="composer">
          <button className="composerToolButton" type="button" aria-label="Attach or add context">+</button>
          <textarea
            ref={textareaRef}
            value={input}
            rows={1}
            onChange={(event) => onInputChange(event.target.value)}
            placeholder={isWorking ? "Message Kattappa AI - your next message will queue" : "Message Kattappa AI"}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                onSendMessage();
              }
            }}
          />
          <button className="sendButton" onClick={onSendMessage} disabled={!canSend} aria-label="Send message" />
        </div>
        <div className="composerFooter">
          <OperatorModeSelector operatorMode={operatorMode} onChange={onOperatorModeChange} />
          <span className={`turnStatus ${isWorking ? "working" : "ready"}`}>
            {isWorking ? `Working${queuedCount ? ` / ${queuedCount} queued` : ""}` : "Ready"}
          </span>
        </div>
      </div>
    </>
  );
}

function MessageContent({ content }: { content: string }) {
  const blocks = splitCodeBlocks(content);
  return (
    <div className="messageText">
      {blocks.map((block, index) =>
        block.kind === "code" ? (
          <pre key={index} className="codeBlock">
            <code>{block.text}</code>
          </pre>
        ) : (
          block.text
            .split(/\n{2,}/)
            .filter((paragraph) => paragraph.trim())
            .map((paragraph, paragraphIndex) => (
              <p key={`${index}-${paragraphIndex}`}>{paragraph.trim()}</p>
            ))
        ),
      )}
    </div>
  );
}

function splitCodeBlocks(content: string): { kind: "text" | "code"; text: string }[] {
  const parts: { kind: "text" | "code"; text: string }[] = [];
  const pattern = /```[a-zA-Z0-9_-]*\n?([\s\S]*?)```/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(content))) {
    if (match.index > lastIndex) {
      parts.push({ kind: "text", text: content.slice(lastIndex, match.index) });
    }
    parts.push({ kind: "code", text: match[1].trimEnd() });
    lastIndex = pattern.lastIndex;
  }
  if (lastIndex < content.length) {
    parts.push({ kind: "text", text: content.slice(lastIndex) });
  }
  return parts.length ? parts : [{ kind: "text", text: content }];
}

function preferredAudioMimeType(): string {
  const types = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
  return types.find((type) => MediaRecorder.isTypeSupported(type)) ?? "";
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error);
    reader.onloadend = () => {
      const value = String(reader.result ?? "");
      resolve(value.includes(",") ? value.split(",").pop() ?? "" : value);
    };
    reader.readAsDataURL(blob);
  });
}

async function speakLocal(text: string, purpose: string) {
  const clean = text.replace(/\s+/g, " ").slice(0, 420);
  if (!clean) return;
  try {
    await speakWithLocalVoice(clean, purpose);
  } catch {
    // Typed output stays available when local speech output is not installed.
  }
}
