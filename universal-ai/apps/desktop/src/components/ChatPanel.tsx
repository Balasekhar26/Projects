import { useEffect, useRef, type RefObject } from "react";
import type { Message, OperatorMode } from "../types";
import { OperatorModeSelector } from "./OperatorModeSelector";

type ChatPanelProps = {
  messages: Message[];
  input: string;
  operatorMode: OperatorMode;
  messagesEndRef: RefObject<HTMLDivElement | null>;
  onInputChange: (input: string) => void;
  onOperatorModeChange: (mode: OperatorMode) => void;
  onSendMessage: () => void;
};

export function ChatPanel({
  messages,
  input,
  operatorMode,
  messagesEndRef,
  onInputChange,
  onOperatorModeChange,
  onSendMessage,
}: ChatPanelProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const visibleMessages = messages.filter(
    (message, index) => !(index === 0 && message.role === "system" && message.content === "Sekhar AI OS ready."),
  );
  const canSend = input.trim().length > 0;

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "0px";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`;
  }, [input]);

  const getMessageName = (message: Message) => {
    if (message.role === "user") return "You";
    if (message.role === "assistant") return message.agent || "Sekhar AI";
    if (message.role === "progress") return "Working";
    return "System";
  };

  const getAvatar = (message: Message) => {
    if (message.role === "user") return "You";
    if (message.role === "assistant") return "AI";
    if (message.role === "progress") return "...";
    return "i";
  };

  return (
    <>
      <div className="chatTopbar">
        <div className="chatHeaderInner">
          <button className="modelButton" type="button" aria-label="Current assistant mode">
            <span>Sekhar AI</span>
            <strong>{operatorMode}</strong>
          </button>
          <div className="chatHeaderActions">
            <span className="privacyBadge">Local-first</span>
          </div>
        </div>
      </div>
      <div className="messages">
        <div className="messageStack">
          {visibleMessages.length === 0 && (
            <section className="chatWelcome" aria-label="Chat ready">
              <div className="welcomeMark">S</div>
              <h2>What can I help with?</h2>
              <div className="promptGrid" aria-label="Starter prompts">
                {[
                  "Make this project production ready",
                  "Check what is ready",
                  "Improve the Universal AI interface",
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
            placeholder="Message Sekhar AI"
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
