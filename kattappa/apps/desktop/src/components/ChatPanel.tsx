import { useEffect, useRef, useState, type RefObject } from "react";
import { fetchVoiceStatus, processVoiceAudio, speakWithLocalVoice, submitSageFeedback } from "../lib/api";
import type { Message, OperatorPlan } from "../types";

type VoiceState = "idle" | "listening" | "processing" | "unsupported";

type ChatPanelProps = {
  messages: Message[];
  input: string;
  messagesEndRef: RefObject<HTMLDivElement | null>;
  onInputChange: (input: string) => void;
  onSendMessage: () => void;
  onVoiceCommand: (command: string) => void;
  onVoiceWake: () => void;
  onVoiceNotice: (message: string) => void;
  isWorking: boolean;
  queuedCount: number;
  liveStatus: string;
  currentTask: string;
  queuedTurns: { text: string }[];
};

export function ChatPanel({
  messages,
  input,
  messagesEndRef,
  onInputChange,
  onSendMessage,
  onVoiceCommand,
  onVoiceWake,
  onVoiceNotice,
  isWorking,
  queuedCount,
  liveStatus,
  currentTask,
  queuedTurns,
}: ChatPanelProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const voiceStopTimerRef = useRef<number | null>(null);
  const lastSpokenIndexRef = useRef(-1);
  const speakNextAssistantRef = useRef(false);
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const [ratedMessages, setRatedMessages] = useState<Record<number, number>>({});

  const handleSageFeedback = async (msg: Message, msgIndex: number, rating: number) => {
    const precedingUserMsg = messages
      .slice(0, msgIndex)
      .reverse()
      .find((m) => m.role === "user");
    const promptText = precedingUserMsg ? precedingUserMsg.content : "";
    try {
      await submitSageFeedback(promptText, msg.agent || "", rating);
      setRatedMessages((prev) => ({ ...prev, [msgIndex]: rating }));
    } catch (err) {
      console.error("Feedback submission failed", err);
    }
  };

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
    if (message.role === "assistant") {
      const agent = message.agent || "";
      if (agent === "sage_scientist") return "Kattappa (Scientist 🔬)";
      if (agent === "sage_engineer") return "Kattappa (Engineer ⚙️)";
      if (agent === "sage_teacher") return "Kattappa (Teacher 🎓)";
      if (agent === "sage_poet") return "Kattappa (Poet 🎨)";
      return agent || "Kattappa AI";
    }
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
      onVoiceNotice("Voice unavailable");
      return;
    }

    try {
      const status = await fetchVoiceStatus();
      if (!status.stt.installed) {
        setVoiceState("unsupported");
        onVoiceNotice("Voice setup needed");
        return;
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
      onVoiceNotice("Voice unavailable");
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
      onVoiceNotice("No voice audio");
      return;
    }
    setVoiceState("processing");
    try {
      const audio_base64 = await blobToBase64(blob);
      const result = await processVoiceAudio({ audio_base64, mime_type: blob.type || "audio/webm" });
      if (!result.ok) {
        onVoiceNotice(result.transcript ? "Voice setup needed" : "Voice unavailable");
        setVoiceState("idle");
        return;
      }
      if (!result.wake_detected) {
        onVoiceNotice("Wake name needed");
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
      onVoiceNotice("Voice unavailable");
    } finally {
      setVoiceState("idle");
    }
  };

  return (
    <>
      <div className="chatTopbar">
        <div className="chatHeaderInner">
          <div className="modelButton" aria-label="Kattappa automatic routing">
            <span>Kattappa AI</span>
            <strong>Auto route</strong>
          </div>
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
                </header>
                <MessageContent content={message.content} />
                {message.role === "assistant" && message.agent?.startsWith("sage_") && (
                  <div className="sageFeedbackRow" style={{ display: "flex", gap: "0.8rem", marginTop: "0.5rem", fontSize: "0.8rem", alignItems: "center", opacity: 0.8 }}>
                    {ratedMessages[index] !== undefined ? (
                      <span style={{ color: "var(--accent-green, #4ade80)", display: "flex", alignItems: "center", gap: "0.2rem" }}>
                        ✓ SAGE adapted ({ratedMessages[index] === 1 ? "Positive" : "Negative"})
                      </span>
                    ) : (
                      <>
                        <span style={{ opacity: 0.6 }}>Rate response:</span>
                        <button 
                          onClick={() => handleSageFeedback(message, index, 1)} 
                          style={{ background: "none", border: "none", cursor: "pointer", color: "var(--accent-green, #4ade80)", fontWeight: 500, padding: 0 }}
                          title="Rate Positive"
                        >
                          👍 Helpful
                        </button>
                        <button 
                          onClick={() => handleSageFeedback(message, index, -1)} 
                          style={{ background: "none", border: "none", cursor: "pointer", color: "var(--accent-red, #f87171)", fontWeight: 500, padding: 0 }}
                          title="Rate Negative"
                        >
                          👎 Not helpful
                        </button>
                      </>
                    )}
                  </div>
                )}
                <ActionPlanCard plan={message.operatorPlan} />
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
        <WorkQueueStrip
          isWorking={isWorking}
          liveStatus={liveStatus}
          currentTask={currentTask}
          queuedTurns={queuedTurns}
        />
        <div className="composerFooter">
          <span className={`turnStatus ${isWorking ? "working" : "ready"}`}>
            {isWorking ? liveStatus : liveStatus || "Ready"}
            {queuedCount ? ` / ${queuedCount} queued` : ""}
          </span>
        </div>
      </div>
    </>
  );
}

function WorkQueueStrip({
  isWorking,
  liveStatus,
  currentTask,
  queuedTurns,
}: {
  isWorking: boolean;
  liveStatus: string;
  currentTask: string;
  queuedTurns: { text: string }[];
}) {
  if (!isWorking && queuedTurns.length === 0) return null;
  const visibleQueue = queuedTurns.slice(0, 3);
  const hiddenCount = Math.max(queuedTurns.length - visibleQueue.length, 0);
  return (
    <section className="workQueueStrip" aria-label="Task processing queue">
      {isWorking && (
        <div className="processingNow">
          <span>{liveStatus || "Working"}</span>
          <strong>{clipTask(currentTask || "Current task", 92)}</strong>
        </div>
      )}
      {visibleQueue.length > 0 && (
        <div className="queuedTasks">
          <span>Next</span>
          {visibleQueue.map((item, index) => (
            <strong key={`${index}-${item.text}`}>{clipTask(item.text, 72)}</strong>
          ))}
          {hiddenCount > 0 && <em>+{hiddenCount} more</em>}
        </div>
      )}
    </section>
  );
}

function clipTask(text: string, limit: number) {
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length <= limit ? clean : `${clean.slice(0, limit - 1).trim()}...`;
}

function shouldShowOperatorPlan(plan?: OperatorPlan) {
  if (!plan) return false;
  return Boolean(plan.action_required || plan.needs_approval || plan.visual_guidance?.enabled);
}

function ActionPlanCard({ plan }: { plan?: OperatorPlan }) {
  if (!plan || !shouldShowOperatorPlan(plan)) return null;
  const guidance = plan.visual_guidance;
  const target = guidance?.target;
  return (
    <div className="operatorPlan">
      <div className="planHeader">
        <strong>{plan.intent || "Action plan"}</strong>
        <span>{plan.local_only ? "free/local only" : "external allowed"}</span>
        <span>{plan.needs_approval ? "approval needed" : "no action approval"}</span>
      </div>
      {guidance?.enabled && target && (
        <div className="visualGuidanceCard">
          <div className="guideScreen" aria-label="Visual desktop guidance preview">
            <span
              className="guideTarget"
              style={{
                left: `${target.x * 100}%`,
                top: `${target.y * 100}%`,
                width: `${target.width * 100}%`,
                height: `${target.height * 100}%`,
              }}
            />
            <span
              className="guideCursor"
              style={{
                left: `${target.x * 100}%`,
                top: `${target.y * 100}%`,
              }}
            />
          </div>
          <p>{guidance.instruction}</p>
          <small>
            {guidance.requires_approval ? "Preview only until approved" : "Safe visual guide"}
            {" / "}
            {target.source}
          </small>
        </div>
      )}
      <ol>
        {plan.next_steps.map((step, stepIndex) => (
          <li key={stepIndex}>{step}</li>
        ))}
      </ol>
    </div>
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
