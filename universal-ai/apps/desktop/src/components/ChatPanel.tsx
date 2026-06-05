import type { RefObject } from "react";
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
  return (
    <>
      <div className="messages">
        <div className="messageStack">
          {messages.map((message, index) => (
            <article key={index} className={`message ${message.role}`}>
              <header>
                <strong>{message.role}</strong>
                {message.agent && <span>{message.agent}</span>}
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
            </article>
          ))}
          <div ref={messagesEndRef} />
        </div>
      </div>
      <div className="inputBar">
        <OperatorModeSelector operatorMode={operatorMode} onChange={onOperatorModeChange} />
        <div className="composer">
          <textarea
            value={input}
            rows={1}
            onChange={(event) => onInputChange(event.target.value)}
            placeholder="Ask Sekhar AI OS..."
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                onSendMessage();
              }
            }}
          />
          <button onClick={onSendMessage}>Send</button>
        </div>
      </div>
    </>
  );
}
