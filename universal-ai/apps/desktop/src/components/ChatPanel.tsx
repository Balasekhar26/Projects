import { useEffect, useRef, useState, type RefObject } from "react";
import type { Message, OperatorMode } from "../types";
import { OperatorModeSelector } from "./OperatorModeSelector";

const WAKE_NAMES = ["kattappa", "mama", "kittu"];

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

type SpeechRecognitionEventLike = {
  resultIndex: number;
  results: {
    length: number;
    [index: number]: {
      isFinal: boolean;
      [index: number]: { transcript: string };
    };
  };
};

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
}: ChatPanelProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const listeningRef = useRef(false);
  const lastSpokenIndexRef = useRef(-1);
  const [voiceState, setVoiceState] = useState<"idle" | "listening" | "unsupported">("idle");
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
    if (voiceState !== "listening") return;
    const latestIndex = messages.length - 1;
    const latest = messages[latestIndex];
    if (!latest || latestIndex === lastSpokenIndexRef.current) return;
    if (latest.role !== "assistant" || !latest.content.trim()) return;
    lastSpokenIndexRef.current = latestIndex;
    speak(latest.content);
  }, [messages, voiceState]);

  useEffect(() => {
    return () => {
      listeningRef.current = false;
      recognitionRef.current?.stop();
      window.speechSynthesis?.cancel();
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

  const toggleVoice = () => {
    if (voiceState === "listening") {
      listeningRef.current = false;
      recognitionRef.current?.stop();
      setVoiceState("idle");
      return;
    }

    const Recognition =
      (window as unknown as { SpeechRecognition?: SpeechRecognitionConstructor; webkitSpeechRecognition?: SpeechRecognitionConstructor })
        .SpeechRecognition ||
      (window as unknown as { webkitSpeechRecognition?: SpeechRecognitionConstructor }).webkitSpeechRecognition;

    if (!Recognition) {
      setVoiceState("unsupported");
      return;
    }

    const recognition = new Recognition();
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = "en-US";
    recognition.onresult = (event) => {
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        if (!result?.isFinal) continue;
        const transcript = result[0]?.transcript?.trim();
        if (!transcript) continue;
        handleVoiceTranscript(transcript);
      }
    };
    recognition.onerror = () => {
      if (listeningRef.current) setVoiceState("listening");
    };
    recognition.onend = () => {
      if (!listeningRef.current) return;
      window.setTimeout(() => {
        try {
          recognition.start();
        } catch {
          setVoiceState("idle");
          listeningRef.current = false;
        }
      }, 250);
    };

    recognitionRef.current = recognition;
    listeningRef.current = true;
    setVoiceState("listening");
    try {
      recognition.start();
      speak("Kattappa AI OS is listening. Say Kattappa, Mama, or Kittu, then your command.");
    } catch {
      listeningRef.current = false;
      setVoiceState("idle");
    }
  };

  const handleVoiceTranscript = (transcript: string) => {
    const normalized = transcript.toLowerCase();
    const wake = WAKE_NAMES.find((name) => new RegExp(`\\b${name}\\b`, "i").test(normalized));
    if (!wake) return;

    const command = transcript.replace(new RegExp(`^.*?\\b${wake}\\b[,\\s:;-]*`, "i"), "").trim();
    if (!command) {
      onVoiceWake();
      speak("Yes, I am listening.");
      return;
    }

    speak("Okay.");
    onVoiceCommand(command);
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
              {voiceState === "listening" ? "Listening" : voiceState === "unsupported" ? "Voice unavailable" : "Voice"}
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
              <p className="wakeHint">Say "Kattappa", "Mama", or "Kittu" after turning voice on.</p>
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
                <p>{message.content}</p>
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
            placeholder="Message Kattappa AI"
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
        </div>
      </div>
    </>
  );
}

function speak(text: string) {
  const synth = window.speechSynthesis;
  if (!synth) return;
  const clean = text.replace(/\s+/g, " ").slice(0, 420);
  if (!clean) return;
  synth.cancel();
  const utterance = new SpeechSynthesisUtterance(clean);
  utterance.rate = 1;
  utterance.pitch = 1;
  synth.speak(utterance);
}
