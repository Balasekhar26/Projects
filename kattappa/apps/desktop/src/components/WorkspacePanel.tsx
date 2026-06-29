import { useState, useEffect } from "react";

type Workspace = {
  workspace_id: string;
  name: string;
  description: string | null;
  project_ids: string[];
  goal_ids: string[];
  chat_session_id: string | null;
  created_at: number;
  updated_at: number;
};

export function WorkspacePanel() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [activeWorkspace, setActiveWorkspace] = useState<Workspace | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  const fetchWorkspaces = async () => {
    try {
      const response = await fetch("http://localhost:8000/workspaces");
      if (response.ok) {
        const data = await response.json();
        setWorkspaces(data.items);
      }
    } catch (err) {
      console.error("Failed to fetch workspaces:", err);
    }
  };

  useEffect(() => {
    fetchWorkspaces();
    // Connect to WebSocket events
    const ws = new WebSocket("ws://localhost:8000/ws/events");
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (
          msg.type === "WORKSPACE_CREATED" ||
          msg.type === "WORKSPACE_UPDATED" ||
          msg.type === "WORKSPACE_DELETED"
        ) {
          fetchWorkspaces();
        }
      } catch (err) {
        console.error("Error parsing event:", err);
      }
    };
    return () => {
      ws.close();
    };
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    setLoading(true);
    setMessage("");
    try {
      const response = await fetch("http://localhost:8000/workspaces", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          description: description.trim() || null,
          project_ids: [],
          goal_ids: [],
          chat_session_id: "kattappa-main-chat",
        }),
      });
      if (response.ok) {
        const data = await response.json();
        setName("");
        setDescription("");
        setActiveWorkspace(data.workspace);
        setMessage(`Workspace "${data.workspace.name}" created successfully!`);
      } else {
        setMessage("Failed to create workspace.");
      }
    } catch (err) {
      console.error(err);
      setMessage("Error creating workspace.");
    } finally {
      setLoading(false);
    }
  };

  const handleSelect = (ws: Workspace) => {
    setActiveWorkspace(ws);
    setMessage(`Switched to workspace: ${ws.name}`);
  };

  const handleDelete = async (id: string) => {
    try {
      const response = await fetch(`http://localhost:8000/workspaces/${id}`, {
        method: "DELETE",
      });
      if (response.ok) {
        if (activeWorkspace?.workspace_id === id) {
          setActiveWorkspace(null);
        }
        setMessage("Workspace deleted successfully.");
      }
    } catch (err) {
      console.error(err);
      setMessage("Error deleting workspace.");
    }
  };

  return (
    <section className="panelView">
      <h2>Workspaces</h2>
      <p className="subtitle">Group goals, projects, and execution context under persistent profiles.</p>

      {message && <div className="infoBanner">{message}</div>}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px", marginTop: "20px" }}>
        {/* Left Side: Create Workspace */}
        <div style={{ background: "#222", padding: "20px", borderRadius: "8px" }}>
          <h3>Create Workspace</h3>
          <form onSubmit={handleCreate} style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
              <span>Name</span>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Spectrum Analyzer, Memory Engine"
                style={{ padding: "8px", background: "#333", border: "1px solid #444", color: "#fff", borderRadius: "4px" }}
                required
              />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
              <span>Description</span>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Brief description of the workspace objective..."
                style={{ padding: "8px", background: "#333", border: "1px solid #444", color: "#fff", borderRadius: "4px", minHeight: "80px" }}
              />
            </label>
            <button
              type="submit"
              disabled={loading}
              style={{
                marginTop: "10px",
                padding: "10px",
                background: "#007acc",
                color: "#fff",
                border: "none",
                borderRadius: "4px",
                cursor: "pointer",
              }}
            >
              {loading ? "Creating..." : "Create"}
            </button>
          </form>
        </div>

        {/* Right Side: Workspace List */}
        <div style={{ background: "#222", padding: "20px", borderRadius: "8px" }}>
          <h3>All Workspaces</h3>
          {workspaces.length === 0 ? (
            <p style={{ color: "#888" }}>No workspaces created yet.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              {workspaces.map((ws) => (
                <div
                  key={ws.workspace_id}
                  style={{
                    padding: "12px",
                    background: activeWorkspace?.workspace_id === ws.workspace_id ? "#333" : "#282828",
                    borderLeft: activeWorkspace?.workspace_id === ws.workspace_id ? "4px solid #007acc" : "4px solid transparent",
                    borderRadius: "4px",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <div style={{ cursor: "pointer", flex: 1 }} onClick={() => handleSelect(ws)}>
                    <strong style={{ display: "block" }}>{ws.name}</strong>
                    <span style={{ fontSize: "0.85em", color: "#aaa" }}>{ws.description || "No description"}</span>
                  </div>
                  <button
                    onClick={() => handleDelete(ws.workspace_id)}
                    style={{
                      background: "transparent",
                      color: "#ff5555",
                      border: "none",
                      cursor: "pointer",
                      fontSize: "0.9em",
                    }}
                  >
                    Delete
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {activeWorkspace && (
        <div style={{ marginTop: "30px", padding: "20px", background: "#1a1a1a", borderRadius: "8px", border: "1px solid #333" }}>
          <h3>Active Workspace Details</h3>
          <dl>
            <dt>Workspace ID</dt>
            <dd style={{ fontFamily: "monospace", color: "#007acc" }}>{activeWorkspace.workspace_id}</dd>
            <dt>Objective / Context</dt>
            <dd>{activeWorkspace.description || "None"}</dd>
            <dt>Chat Session</dt>
            <dd>{activeWorkspace.chat_session_id || "None"}</dd>
            <dt>Linked Projects</dt>
            <dd>{activeWorkspace.project_ids.length ? activeWorkspace.project_ids.join(", ") : "None"}</dd>
            <dt>Linked Goals</dt>
            <dd>{activeWorkspace.goal_ids.length ? activeWorkspace.goal_ids.join(", ") : "None"}</dd>
          </dl>
        </div>
      )}
    </section>
  );
}
