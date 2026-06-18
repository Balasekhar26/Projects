type SidebarProps = {
  panels: string[];
  activePanel: string;
  connected: boolean;
  onOpenChat: () => void;
  onSelectPanel: (panel: string) => void;
};

export function Sidebar({
  panels,
  activePanel,
  connected,
  onOpenChat,
  onSelectPanel,
}: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="brandMark">
        <img src="/kattappa-logo.svg" alt="Kattappa AI OS Assistant" />
        <h1>Kattappa AI OS</h1>
      </div>
      <div className={connected ? "pill ok" : "pill"}>{connected ? "Local backend online" : "Backend offline"}</div>
      <button className={activePanel === "Chat" ? "openChatButton active" : "openChatButton"} onClick={onOpenChat}>
        Open Chat
      </button>
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
