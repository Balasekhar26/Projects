import type { ChatSession } from "../types";

type SidebarProps = {
  panels: string[];
  activePanel: string;
  connected: boolean;
  chatSessions: ChatSession[];
  currentSessionId: string | null;
  onCreateChat: () => void;
  onLoadChat: (sessionId: string) => void;
  onSelectPanel: (panel: string) => void;
};

export function Sidebar({
  panels,
  activePanel,
  connected,
  chatSessions,
  currentSessionId,
  onCreateChat,
  onLoadChat,
  onSelectPanel,
}: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="brandMark">
        <img src="/sekhar-logo.svg" alt="Sekhar AI OS" />
        <h1>Sekhar AI OS</h1>
      </div>
      <div className={connected ? "pill ok" : "pill"}>{connected ? "Local backend online" : "Backend offline"}</div>
      <button className="newChatButton" onClick={onCreateChat}>New Chat</button>
      <div className="chatHistory">
        <h2>History</h2>
        {chatSessions.length ? (
          chatSessions.map((session) => (
            <button
              key={session.id}
              className={currentSessionId === session.id ? "active" : ""}
              onClick={() => onLoadChat(session.id)}
              title={session.updated_at}
            >
              {session.title}
            </button>
          ))
        ) : (
          <p>No saved chats yet.</p>
        )}
      </div>
      <nav>
        {panels.map((panel) => (
          <button key={panel} className={activePanel === panel ? "active" : ""} onClick={() => onSelectPanel(panel)}>
            {panel}
          </button>
        ))}
      </nav>
    </aside>
  );
}
